"""Hugging Face metadata, account connection, and verified resumable downloads."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import threading
import time
from urllib.parse import quote

import requests

from . import __version__
from .client import CACHE, DATA, read_json, save_json


class Paused(Exception):
    pass


class Hub:
    base = "https://huggingface.co"

    def __init__(self, cache: Path | None = None):
        self.token = ""
        self.username = ""
        self.cache = cache or CACHE / "models"
        self.session = requests.Session()
        self.session.headers["User-Agent"] = f"JieZhi/{__version__}"
        self.metadata_cache = {}

    def headers(self):
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def api(self, path, **kwargs):
        try:
            response = self.session.get(self.base + path, headers=self.headers(), timeout=(10, 30), **kwargs)
            self.check(response)
            return response.json()
        except requests.RequestException:
            raise RuntimeError("Could not reach Hugging Face. Check your connection and try again.") from None

    @staticmethod
    def check(response):
        if response.status_code == 401:
            raise RuntimeError("Connect a Hugging Face account with a valid read token to access this repository.")
        if response.status_code == 403:
            raise RuntimeError("Access is restricted. Request/accept access on the model page, and check your token's read permissions.")
        if response.status_code == 404:
            raise RuntimeError("Repository or file not found, or your account does not have access.")
        if response.status_code == 429:
            raise RuntimeError("Hugging Face is rate limiting requests. Wait briefly and try again.")
        if not response.ok:
            raise RuntimeError(f"Hugging Face returned HTTP {response.status_code}. Try again later.")

    def connect(self, token: str, remember: bool):
        token = token.strip()
        if not re.fullmatch(r"hf_[A-Za-z0-9]+", token):
            raise ValueError("Paste a Hugging Face user access token beginning with hf_.")
        previous = self.token; self.token = token
        try:
            identity = self.api("/api/whoami-v2")
            self.username = identity["name"]
        except Exception:
            self.token = previous; raise
        persistent = False
        warning = ""
        if remember:
            try:
                from keyring.backends.SecretService import Keyring
                Keyring().set_password("JieZhi", "huggingface", token)
                persistent = True
            except Exception:
                warning = "The system keyring is unavailable. Connected for this session only."
        if not persistent:
            self._delete_saved_token()
        save_json(DATA / "hub-account.json", {"username": self.username, "remember": persistent})
        return {"username": self.username, "remember": persistent, "warning": warning}

    def restore(self):
        settings = read_json(DATA / "hub-account.json", {})
        if settings.get("remember"):
            try:
                from keyring.backends.SecretService import Keyring
                token = Keyring().get_password("JieZhi", "huggingface")
                if token:
                    return self.connect(token, True)
            except Exception:
                pass
        return {"username": "", "warning": ""}

    def _delete_saved_token(self):
        settings = read_json(DATA / "hub-account.json", {})
        if settings.get("remember"):
            try:
                from keyring.backends.SecretService import Keyring
                Keyring().delete_password("JieZhi", "huggingface")
            except Exception:
                raise RuntimeError("Could not remove the saved token from the system keyring. Unlock it and disconnect again.") from None

    def disconnect(self):
        self._delete_saved_token()
        self.token = ""; self.username = ""
        (DATA / "hub-account.json").unlink(missing_ok=True)

    def search(self, query):
        key=('search',query.strip(),self.username)
        cached=self.metadata_cache.get(key)
        if cached and time.monotonic()-cached[0]<300:return cached[1]
        result=self.api("/api/models", params={"search": query.strip(), "filter": "gguf", "limit": 30, "sort": "downloads", "direction": -1,"full":"true"})
        self.metadata_cache[key]=(time.monotonic(),result)
        return result

    def discover(self, category):
        from .recommendations import DISCOVERY
        results={}
        for query in DISCOVERY[category]:
            for repo in self.search(query)[:12]:
                results[repo.get('id') or repo['modelId']]=repo
        return list(results.values())

    def files(self, repo):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
            raise ValueError("Enter a repository such as unsloth/Qwen3-1.7B-GGUF.")
        key=('files',repo,self.username)
        cached=self.metadata_cache.get(key)
        if cached and time.monotonic()-cached[0]<300:return cached[1]
        info = self.api(f"/api/models/{repo}", params={"blobs": "true"})
        # Keep only ranking metadata, never a remote chat template or model code.
        metadata={k:info[k] for k in ['tags','config','pipeline_tag','gated','disabled'] if k in info}
        metadata['gguf']={k:v for k,v in (info.get('gguf') or {}).items() if k in ['total','architecture','context_length']}
        revision = info["sha"]
        files = []
        for entry in info.get("siblings", []):
            name = entry["rfilename"]
            if not name.lower().endswith(".gguf"):
                continue
            lfs = entry.get("lfs") or {}
            files.append({"repo": repo, "revision": revision, "name": name,
                          "size": entry.get("size") or lfs.get("size", 0),
                          "sha256": lfs.get("sha256") or lfs.get("oid", ""),
                          "split": bool(re.search(r"-\d{5}-of-\d{5}\.gguf$", name,re.I)),"metadata":metadata})
        result=sorted(files, key=lambda f: ("Q4_0" not in f["name"], f["name"]))
        self.metadata_cache[key]=(time.monotonic(),result)
        return result

    def destination(self, file):
        name = PurePosixPath(file["name"])
        if name.is_absolute() or ".." in name.parts or "\\" in str(name):
            raise ValueError("Unsafe model filename.")
        if not re.fullmatch(r"[a-f0-9]{40}", file["revision"]):
            raise ValueError("A pinned repository revision is required.")
        repo_hash = hashlib.sha256(file["repo"].encode()).hexdigest()[:16]
        return self.cache / repo_hash / file["revision"] / str(name)

    def download(self, file, progress=lambda *_: None, cancelled: threading.Event | None = None):
        if file.get("split"):
            raise ValueError("Split GGUF models are not supported yet. Select a single-file GGUF.")
        size, expected = int(file["size"]), file.get("sha256", "")
        if size <= 0 or not re.fullmatch(r"[a-f0-9]{64}", expected):
            raise ValueError("The Hub did not provide a size and SHA-256 for this file. Choose a GGUF with verifiable metadata.")
        target = self.destination(file); target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        partial = target.with_suffix(target.suffix + ".partial")
        def check_cancel():
            if cancelled and cancelled.is_set():
                raise Paused("Download paused. Select this file and download again to resume.")
        def verify(path):
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                while block := stream.read(4 * 1024 * 1024):
                    check_cancel(); digest.update(block)
            return digest.hexdigest() == expected
        check_cancel()
        if target.exists() and target.stat().st_size == size and verify(target):
            progress(100, "Already downloaded and verified"); return target
        offset = partial.stat().st_size if partial.exists() else 0
        if offset > size:
            partial.unlink(); offset = 0
        if shutil.disk_usage(target.parent).free < size - offset + 64 * 1024 * 1024:
            raise RuntimeError("Not enough space on the PC for this download.")
        if offset < size:
            url = f"{self.base}/{file['repo']}/resolve/{file['revision']}/{quote(file['name'], safe='/')}"
            headers = {**self.headers(), "Accept-Encoding": "identity"}
            if offset:
                headers["Range"] = f"bytes={offset}-"
            try:
                # Requests removes Authorization when redirecting to a different host.
                with self.session.get(url, headers=headers, stream=True, timeout=(10, 30)) as response:
                    self.check(response)
                    if response.status_code == 206:
                        if response.headers.get("Content-Range") != f"bytes {offset}-{size-1}/{size}":
                            raise RuntimeError("Unexpected download range. Retry the download.")
                    elif response.status_code == 200:
                        offset = 0
                    else:
                        raise RuntimeError("Unexpected download response.")
                    with partial.open("ab" if offset else "wb") as stream:
                        for block in response.iter_content(1024 * 1024):
                            check_cancel()
                            if offset + len(block) > size:
                                raise RuntimeError("Download exceeded the expected model size.")
                            stream.write(block); offset += len(block)
                            progress(offset * 100 // size, f"Downloading · {offset/1024**3:.2f} / {size/1024**3:.2f} GB")
            except requests.RequestException:
                raise RuntimeError("Download interrupted. Select this file and download again to resume.") from None
        if partial.stat().st_size != size:
            raise RuntimeError("Incomplete download. Download again to resume.")
        progress(100, "Verifying SHA-256")
        if not verify(partial):
            partial.unlink()
            raise RuntimeError("Model checksum mismatch. The incomplete download was discarded; please retry.")
        with partial.open("rb") as stream:
            if stream.read(4) != b"GGUF":
                partial.unlink(); raise RuntimeError("The downloaded file is not a GGUF model.")
        partial.replace(target)
        save_json(target.with_suffix(".source.json"), file)
        progress(100, "Downloaded and verified on this PC")
        return target
