"""Release checks and in-place replacement of the packaged bundle.

What is running is a PyInstaller bundle in `~/.local/opt/jiezhi`, not this
checkout, so an update means replacing a directory that a live process is
reading itself out of. Two consequences shape everything here:

- The previous bundle is renamed aside instead of deleted. The running process
  still loads parts of itself lazily, and those files have to outlive it; the
  leftover is cleared on the next launch.
- Nothing is replaced until the download is complete and its published
  checksum matches, so aborting at any earlier point leaves the installation
  exactly as it was.

Releases are read from the public list endpoint rather than `/releases/latest`,
which hides pre-releases: every JieZhi release so far is an alpha.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile

import requests

from . import __version__
from .client import CACHE

REPO = "kb777only/JieZhi"
API = "https://api.github.com"
RELEASES_PAGE = f"https://github.com/{REPO}/releases"

INSTALL_DIR = Path.home() / ".local/opt/jiezhi"
DESKTOP_FILE = Path.home() / ".local/share/applications/jiezhi.desktop"

# What `scripts/package.sh` uploads: the Linux bundle, and the sums for all of it.
ARCHIVE = re.compile(r"JieZhi-.+-linux-x86_64\.tar\.gz")
CHECKSUMS = "SHA256SUMS"

BLOCK = 1024 * 1024

_STAGES = {"alpha": 0, "a": 0, "beta": 1, "b": 1, "rc": 2, "c": 2}
_VERSION = re.compile(r"v?(\d+(?:\.\d+)*)(?:[-_.]?(alpha|beta|rc|a|b|c)[-_.]?(\d+)?)?")


class Cancelled(Exception):
    """Raised when the user abandons a download that is already running."""


def parse_version(text):
    """A sort key for `0.7.0-alpha.1`, `v0.7.0-alpha.1` and the `0.7.0a1` spelling alike.

    A final release outranks every pre-release of the same numbers, which is the
    one comparison a plain string sort gets backwards. Anything unrecognised
    returns None, and an unrecognised version is never treated as newer.
    """
    match = _VERSION.fullmatch(str(text).strip().lower())
    if not match:
        return None
    numbers = (tuple(int(n) for n in match.group(1).split(".")) + (0, 0, 0, 0))[:4]
    if match.group(2) is None:
        return numbers, 1, 0, 0
    return numbers, 0, _STAGES[match.group(2)], int(match.group(3) or 0)


def is_newer(candidate, current):
    first, second = parse_version(candidate), parse_version(current)
    return bool(first and second and first > second)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(BLOCK), b""):
            digest.update(block)
    return digest.hexdigest()


def describe(release: dict) -> dict:
    """One release, reduced to what the window needs to show and fetch."""
    assets = release.get("assets") or []
    archive = next((a for a in assets if ARCHIVE.fullmatch(a.get("name") or "")), None)
    sums = next((a for a in assets if (a.get("name") or "") == CHECKSUMS), None)
    tag = str(release.get("tag_name") or "")
    return {
        "tag": tag,
        "version": tag.lstrip("v") or tag,
        "name": release.get("name") or tag,
        "notes": (release.get("body") or "").strip(),
        "url": release.get("html_url") or RELEASES_PAGE,
        "published": release.get("published_at") or "",
        "prerelease": bool(release.get("prerelease")),
        "archive": {
            "name": archive["name"],
            "url": archive["browser_download_url"],
            "size": int(archive.get("size") or 0),
        } if archive and archive.get("browser_download_url") else None,
        "checksums": (sums or {}).get("browser_download_url") or "",
    }


def write_desktop_entry(destination: Path, desktop_file: Path = DESKTOP_FILE):
    desktop_file.parent.mkdir(parents=True, exist_ok=True)
    executable = str(destination / "JieZhi").replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`").replace("$", "\\$")
    desktop_file.write_text(f'[Desktop Entry]\nType=Application\nName=JieZhi 借智\nComment=Borrow intelligence from your Android phone\nExec="{executable}"\nIcon={destination}/_internal/assets/jiezhi.svg\nTerminal=false\nCategories=Utility;\n')
    desktop_file.chmod(0o644)


def swap_bundle(stage: Path, destination: Path = INSTALL_DIR, desktop_file: Path | None = DESKTOP_FILE, keep_backup: bool = False):
    """Atomically put a prepared bundle in place of an installation.

    The old bundle is renamed aside before the new one takes its name, so a
    failure anywhere in here puts the previous installation back untouched.

    An in-place update passes keep_backup: the process being replaced is still
    running out of that directory and loads parts of itself lazily, so the old
    files have to outlive it. `clear_leftovers` removes them on the next launch.
    """
    stage = Path(stage); destination = Path(destination)
    if not (stage / "JieZhi").is_file():
        raise RuntimeError("Incomplete installer: missing JieZhi executable.")
    backup = destination.with_name(destination.name + ".previous")
    if backup.exists():
        shutil.rmtree(backup)
    if destination.exists():
        destination.rename(backup)
    try:
        stage.rename(destination)
        if desktop_file is not None:
            write_desktop_entry(destination, Path(desktop_file))
    except Exception:
        if destination.exists():
            shutil.rmtree(destination)
        if backup.exists():
            backup.rename(destination)
        raise
    if backup.exists() and not keep_backup:
        shutil.rmtree(backup)
    return str(destination)


def clear_leftovers(destination: Path = INSTALL_DIR):
    """Remove what an update left behind. Safe only once the replaced process is gone."""
    for suffix in (".previous", ".installing", ".unpack"):
        path = Path(destination).with_name(Path(destination).name + suffix)
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)


def install_bundle(source: Path, destination: Path = INSTALL_DIR, desktop_file: Path = DESKTOP_FILE):
    """Stage the full self-contained bundle, then atomically replace an installation."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = destination.with_name(destination.name + ".installing")
    if stage.exists():
        shutil.rmtree(stage)
    shutil.copytree(source, stage, symlinks=True)
    return swap_bundle(stage, destination, desktop_file)


def restart(executable) -> None:
    """Start the freshly installed app, detached, and leave the old one to exit."""
    subprocess.Popen([str(executable)], start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class Updates:
    """The release feed, the download, and the swap — with no Qt in any of it."""

    def __init__(self, version: str = __version__, repo: str = REPO, api: str = API, cache: Path | None = None):
        self.version = version
        self.repo = repo
        self.api = api
        self.cache = Path(cache) if cache else CACHE / "updates"
        self.session = requests.Session()
        self.session.headers["User-Agent"] = f"JieZhi/{version}"
        self.session.headers["Accept"] = "application/vnd.github+json"

    def bundle(self) -> Path | None:
        """The directory an update would replace, or None when running from source."""
        if not getattr(sys, "frozen", False):
            return None
        return Path(sys.executable).resolve().parent

    def blocked(self) -> str:
        """Why an in-place update cannot run here, or '' when it can."""
        destination = self.bundle()
        if destination is None:
            return ("JieZhi is running from a source checkout, so it cannot replace itself. "
                    "Update it with git, or install the packaged build.")
        if not os.access(destination.parent, os.W_OK) or not os.access(destination, os.W_OK):
            return f"{destination} is not writable by this account, so the update cannot be installed."
        return ""

    def check(self) -> dict | None:
        """The newest published release above the running version, or None."""
        try:
            response = self.session.get(f"{self.api}/repos/{self.repo}/releases",
                                        params={"per_page": 30}, timeout=(10, 30))
        except requests.RequestException:
            raise RuntimeError("Could not reach GitHub to check for updates. Check your connection.") from None
        if response.status_code in (403, 429):
            raise RuntimeError("GitHub is rate limiting update checks. Try again in a few minutes.")
        if response.status_code == 404:
            raise RuntimeError(f"No release feed was found for {self.repo}.")
        if not response.ok:
            raise RuntimeError(f"GitHub returned HTTP {response.status_code} for the release list.")
        try:
            releases = response.json()
        except ValueError:
            raise RuntimeError("GitHub returned an unreadable release list.") from None
        best = None
        for release in releases if isinstance(releases, list) else []:
            if not isinstance(release, dict) or release.get("draft"):
                continue
            order = parse_version(release.get("tag_name") or "")
            if order is None or not is_newer(release.get("tag_name") or "", self.version):
                continue
            if best is None or order > best[0]:
                best = (order, describe(release))
        return best[1] if best else None

    def checksum(self, release: dict, name: str) -> str:
        """The SHA-256 the release publishes for one asset.

        A release that publishes sums has to produce the one for this file: a
        checksum that cannot be read is a reason to stop, not to skip the check.
        Only a release with no `SHA256SUMS` at all returns '' here.
        """
        url = release.get("checksums")
        if not url:
            return ""
        try:
            response = self.session.get(url, timeout=(10, 30))
        except requests.RequestException:
            raise RuntimeError("Could not read the release checksums, so the update was not installed.") from None
        if not response.ok:
            raise RuntimeError("Could not read the release checksums, so the update was not installed.")
        for line in response.text.splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[1].lstrip("*") == name:
                return parts[0].strip().lower()
        raise RuntimeError(f"The release publishes no checksum for {name}, so the update was not installed.")

    def download(self, release: dict, progress=lambda percent, message: None, cancel=None) -> Path:
        """Fetch the release bundle and verify it before anything is replaced."""
        archive = release.get("archive")
        if not archive:
            raise RuntimeError("This release has no Linux bundle attached, so it cannot be installed from here.")
        self.cache.mkdir(parents=True, exist_ok=True)
        expected = self.checksum(release, archive["name"])
        target = self.cache / Path(archive["name"]).name
        if expected and target.is_file() and sha256(target) == expected:
            progress(100, "Already downloaded and verified")
            return target
        partial = target.with_name(target.name + ".partial")
        digest = hashlib.sha256()
        written = 0
        try:
            with self.session.get(archive["url"], stream=True, timeout=(10, 60)) as response:
                if not response.ok:
                    raise RuntimeError(f"The download returned HTTP {response.status_code}.")
                total = int(response.headers.get("Content-Length") or archive["size"] or 0)
                with partial.open("wb") as stream:
                    for block in response.iter_content(BLOCK):
                        if cancel is not None and cancel.is_set():
                            raise Cancelled()
                        written += len(block)
                        if total and written > total:
                            raise RuntimeError("The download was larger than the published bundle.")
                        stream.write(block)
                        digest.update(block)
                        progress(written * 100 // total if total else 0,
                                 f"Downloading · {written / 1024 ** 2:.0f} of {total / 1024 ** 2:.0f} MB"
                                 if total else f"Downloading · {written / 1024 ** 2:.0f} MB")
        except requests.RequestException:
            partial.unlink(missing_ok=True)
            raise RuntimeError("The update download was interrupted. Nothing was changed; try again.") from None
        except BaseException:
            partial.unlink(missing_ok=True)
            raise
        if archive["size"] and written != archive["size"]:
            partial.unlink(missing_ok=True)
            raise RuntimeError("The download did not match the published size. Nothing was changed; try again.")
        if expected:
            if digest.hexdigest() != expected:
                partial.unlink(missing_ok=True)
                raise RuntimeError("The downloaded bundle failed its checksum and was discarded. Nothing was changed.")
            progress(100, "Downloaded and verified")
        else:
            progress(100, "Downloaded · this release publishes no checksum")
        partial.replace(target)
        return target

    def install(self, archive: Path, destination: Path, progress=lambda percent, message: None) -> Path:
        """Unpack beside the installation, then swap it in keeping the old bundle."""
        destination = Path(destination)
        unpack = destination.with_name(destination.name + ".unpack")
        stage = destination.with_name(destination.name + ".installing")
        progress(0, "Unpacking the new version…")
        for path in (unpack, stage):
            if path.exists():
                shutil.rmtree(path)
        unpack.mkdir(parents=True)
        try:
            with tarfile.open(archive, "r:gz") as tar:
                # 'data' refuses absolute paths, parent traversal and links that
                # leave the directory, so a tampered archive cannot write outside it.
                tar.extractall(unpack, filter="data")
            inner = unpack / "JieZhi"
            if not (inner / "JieZhi").is_file():
                roots = [path for path in unpack.iterdir() if path.is_dir()]
                inner = roots[0] if len(roots) == 1 else inner
            if not (inner / "JieZhi").is_file():
                raise RuntimeError("The downloaded archive does not contain a JieZhi bundle.")
            inner.rename(stage)
        finally:
            shutil.rmtree(unpack, ignore_errors=True)
        progress(70, "Putting the new version in place…")
        # Only the real installation owns the launcher entry; a bundle run from
        # somewhere else updates itself without redirecting the application menu.
        desktop = DESKTOP_FILE if destination == INSTALL_DIR else None
        swap_bundle(stage, destination, desktop_file=desktop, keep_backup=True)
        progress(100, "Installed · restarting JieZhi")
        return destination
