from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import threading
import time

import requests

ROOT = Path(__file__).resolve().parents[2]
DATA = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "jiezhi"
CACHE = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "jiezhi"
PACKAGE = "dev.jiezhi.client"


def asset(name: str) -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "assets" / name
    return ROOT / "assets" / name


def adb_path() -> str:
    for p in [asset("platform-tools/adb"), ROOT / ".tools/platform-tools/adb"]:
        if p.exists():
            return str(p)
    found = shutil.which("adb")
    if found:
        return found
    raise RuntimeError("ADB is missing. Reinstall the JieZhi desktop package.")


def adb(*args: str, serial: str = "", timeout: float = 30) -> str:
    cmd = [adb_path()] + (["-s", serial] if serial else []) + list(args)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout).strip())
    return result.stdout.strip()


def devices() -> list[dict]:
    result = []
    for line in adb("devices", "-l").splitlines()[1:]:
        fields = line.split()
        if len(fields) >= 2 and "usb:" in line:
            result.append({"serial": fields[0], "state": fields[1], "description": line})
    return result


def save_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_suffix(".tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
    temp.replace(path)


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


class Client:
    def __init__(self):
        self.serial = ""
        self.port = 0
        self.token = ""
        self.session = requests.Session()
        self.session.trust_env = False  # USB traffic must never traverse HTTP proxies.

    def connect(self, serial: str) -> dict:
        connected = next((d for d in devices() if d["serial"] == serial), None)
        if not connected or connected["state"] != "device":
            raise RuntimeError("Unlock the phone and accept USB debugging. If access is denied, use Setup → Fix USB access.")
        self.disconnect()
        self.serial = serial
        soc = adb("shell", "getprop", "ro.soc.model", serial=serial)
        if "8750" not in soc:
            raise RuntimeError(f"V1 targets Snapdragon 8 Elite (SM8750). This phone reports {soc}.")
        installed = adb("shell", "pm", "path", PACKAGE, serial=serial)
        if not installed:
            raise RuntimeError("Install the Android client using the button in Setup, then connect again.")
        adb("shell", "am", "start", "-n", f"{PACKAGE}/.MainActivity", serial=serial)
        self.port = int(adb("forward", "tcp:0", "tcp:39471", serial=serial))
        self.token = read_json(DATA / "pairing.json", {}).get(serial, "")
        for _ in range(30):
            try:
                response = self.session.get(self.url("/status"), headers=self.headers(), timeout=2)
                if response.status_code == 401:
                    return {"needs_pairing": True, "serial": serial}
                response.raise_for_status()
                return response.json()
            except requests.ConnectionError:
                time.sleep(0.3)
        raise RuntimeError("Phone client did not start. Open JieZhi on the phone and tap Start.")

    def disconnect(self):
        if self.port and self.serial:
            try:
                adb("forward", "--remove", f"tcp:{self.port}", serial=self.serial, timeout=5)
            except Exception:
                pass
        self.port = 0

    def install(self, serial: str):
        apk = asset("jiezhi-client.apk")
        if not apk.exists():
            apk = ROOT / "android/app/build/outputs/apk/debug/app-debug.apk"
        if not apk.exists():
            # Nothing built this client locally, so take the one CI published.
            from .updates import fetch_client
            apk = fetch_client()
        return adb("install", "-r", str(apk), serial=serial, timeout=180)

    def url(self, path: str):
        if not self.port:
            raise RuntimeError("Connect your phone in Setup first.")
        return f"http://127.0.0.1:{self.port}/v1{path}"

    def headers(self):
        return {"Authorization": f"Bearer {self.token}"}

    def request(self, method: str, path: str, **kwargs):
        timeout = kwargs.pop("timeout", (5, 180))
        response = self.session.request(method, self.url(path), headers=self.headers(), timeout=timeout, **kwargs)
        if not response.ok:
            try:
                message = response.json().get("error", response.text)
            except ValueError:
                message = response.text
            raise RuntimeError(message)
        return response

    def pair(self, code: str):
        data = self.request("POST", "/pair", json={"code": code.strip()}).json()
        self.token = data["token"]
        pairs = read_json(DATA / "pairing.json", {})
        pairs[self.serial] = self.token
        save_json(DATA / "pairing.json", pairs)
        return self.status()

    def status(self):
        return self.request("GET", "/status", timeout=(5, 10)).json()

    def import_model(self, path: Path, progress=lambda *_: None, cancelled: threading.Event | None = None):
        def check_cancel():
            if cancelled and cancelled.is_set():
                raise RuntimeError("Transfer paused. Import this file again to resume.")
        with path.open("rb") as stream:
            header = stream.read(24)
        if len(header) < 24 or header[:4] != b"GGUF" or struct.unpack_from("<I", header, 4)[0] not in (2, 3):
            raise RuntimeError("Select a valid GGUF v2/v3 model. Other formats need conversion before import.")
        size = path.stat().st_size
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            count = 0
            while block := stream.read(4 * 1024 * 1024):
                check_cancel(); digest.update(block); count += len(block)
                progress(count * 100 // size, "Checking model")
        model_id = digest.hexdigest()
        status = self.request("POST", "/uploads", json={"id": model_id, "name": path.name, "size": size}).json()
        if status["complete"]:
            return self.status()
        offset = status["offset"]
        if not 0 <= offset <= size:
            raise RuntimeError("Phone returned an invalid transfer offset.")
        with path.open("rb") as stream:
            stream.seek(offset)
            while block := stream.read(4 * 1024 * 1024):
                check_cancel()
                response = self.session.put(self.url(f"/uploads/{model_id}"),
                    headers={**self.headers(), "X-Offset": str(offset), "Content-Type": "application/octet-stream"},
                    data=block, timeout=(5, 60))
                if not response.ok:
                    raise RuntimeError(response.json().get("error", "Transfer failed; import again to resume"))
                offset = response.json()["offset"]
                progress(offset * 100 // size, "Transferring over USB")
        check_cancel()
        progress(100, "Verifying on phone")
        self.request("POST", "/commit", json={"id": model_id})
        return self.status()

    def load(self, model_id: str, backend="npu", context=2048):
        self.request("POST", "/load", json={"id": model_id, "backend": backend, "context": context})
        return self.status()

    def chat(self, messages: list[dict], emit, max_tokens=512):
        done = False
        with self.request("POST", "/chat", json={"messages": messages, "max_tokens": max_tokens}, stream=True) as response:
            for line in response.iter_lines(chunk_size=1):
                if line:
                    event = json.loads(line)
                    if event["type"] == "error":
                        raise RuntimeError(event["error"])
                    emit(event)
                    done = done or event["type"] == "done"
        if not done:
            raise RuntimeError("Connection ended before generation completed. Reconnect in Setup.")

    def cancel(self):
        # Separate request/session so cancellation never waits for the streaming connection.
        with requests.Session() as session:
            session.trust_env = False
            session.post(self.url("/cancel"), headers=self.headers(), json={}, timeout=10).raise_for_status()

    def diagnostics(self):
        pid = adb("shell", "pidof", PACKAGE, serial=self.serial)
        if not pid:
            return "Android client is not running."
        logs = adb("logcat", "-d", "--pid", pid.split()[0], "-t", "2500", serial=self.serial)
        lines = [line for line in logs.splitlines() if any(s in line.lower() for s in
            ["hexagon", "htp", "offload", "geniex", "jiezhi", "error", "fastrpc", "llama", "ggml"])]
        return "\n".join(lines[-350:]) or "No runtime logs available yet. Load a model first."
