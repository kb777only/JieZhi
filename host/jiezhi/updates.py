"""Checking `main` for new commits, and fast-forwarding the installation onto them.

An installation is a git checkout of this repository with its own virtual
environment, put there by `scripts/install.sh`. That is the whole design: the
host is pure Python, so there is nothing to compile and nothing to package, and
the thing that updates is a `git fetch`. GitHub already serves the code, so no
release, artifact store or build server sits between a commit and a user.

What that costs, and what it buys:

- There is no version to compare, so the installed commit is compared against
  the head of `main`, and the commits in between are the patch notes. They read
  well because this repository writes commit messages as prose.
- An update can only move a checkout that is clean and on the tracked branch.
  A checkout with uncommitted work is refused rather than reset, so nobody
  loses an afternoon to the Update button.
- `pip install -e .` means the working tree *is* the running code, so moving the
  tree is the whole update. Dependencies are only reinstalled when the commits
  being taken on actually touched them.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys

import requests

from . import __version__
from .client import CACHE, ROOT

REPO = "kb777only/JieZhi"
API = "https://api.github.com"
BRANCH = "main"
REPO_PAGE = f"https://github.com/{REPO}"

# The phone client needs the Android SDK to build, which an installation does
# not have, so CI publishes it to a branch of its own for the app to fetch.
CLIENT_BRANCH = "prebuilt"
CLIENT_BASE = f"https://raw.githubusercontent.com/{REPO}/{CLIENT_BRANCH}"

BLOCK = 1024 * 1024

DESKTOP_FILE = Path.home() / ".local/share/applications/jiezhi.desktop"

# The files whose change means the virtual environment has to be rebuilt. Every
# other update is a working-tree move and needs no install step at all.
DEPENDENCIES = ("pyproject.toml", "requirements.txt")

# How many commits of patch notes to show. More than this and the box is a log,
# not a summary.
NOTES = 40

GIT_TIMEOUT = 180
PIP_TIMEOUT = 900


class Cancelled(Exception):
    """Raised when the user abandons an update that is already running."""


def git(root: Path, *args: str, timeout: int = GIT_TIMEOUT) -> str:
    """Run git in a checkout and hand back its output, or raise with its error."""
    if not shutil.which("git"):
        raise RuntimeError("git is not installed, so JieZhi cannot update itself.")
    result = subprocess.run(["git", "-C", str(root), *args],
                            capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout).strip() or f"git {args[0]} failed.")
    return result.stdout.strip()


def short(sha: str) -> str:
    return str(sha)[:7]


def write_desktop_entry(root: Path, desktop_file: Path = DESKTOP_FILE) -> Path:
    """Point the application menu at a checkout's launcher."""
    root = Path(root); desktop_file = Path(desktop_file)
    desktop_file.parent.mkdir(parents=True, exist_ok=True)
    executable = str(launcher(root)).replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`").replace("$", "\\$")
    desktop_file.write_text(
        "[Desktop Entry]\nType=Application\nName=JieZhi 借智\n"
        "Comment=Borrow intelligence from your Android phone\n"
        f'Exec="{executable}"\nIcon={root}/assets/jiezhi.svg\n'
        "Terminal=false\nCategories=Utility;\n")
    desktop_file.chmod(0o644)
    return desktop_file


def launcher(root: Path) -> Path:
    """The console script `pip install -e .` puts in the checkout's environment."""
    return Path(root) / ".venv/bin/jiezhi"


def restart(executable) -> None:
    """Start the updated app, detached, and leave this one to exit."""
    subprocess.Popen([str(executable)], start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def notes_for(commits: list[dict]) -> str:
    """The patch notes: what each commit says, newest first."""
    lines = []
    for commit in commits[:NOTES]:
        message = ((commit.get("commit") or {}).get("message") or "").strip()
        if not message:
            continue
        subject, _, body = message.partition("\n")
        lines.append(f"### {subject}")
        if body.strip():
            lines.append(body.strip())
        lines.append("")
    if len(commits) > NOTES:
        lines.append(f"…and {len(commits) - NOTES} more.")
    return "\n\n".join(lines).strip()


class Updates:
    """The commit feed and the fast-forward — with no Qt in any of it."""

    def __init__(self, version: str = __version__, repo: str = REPO, api: str = API,
                 branch: str = BRANCH, root: Path | None = None, desktop_file: Path | None = None):
        self.version = version
        self.repo = repo
        self.api = api
        self.branch = branch
        self.root = Path(root) if root else Path(ROOT)
        self.desktop_file = Path(desktop_file) if desktop_file else DESKTOP_FILE
        self.session = requests.Session()
        self.session.headers["User-Agent"] = f"JieZhi/{version}"
        self.session.headers["Accept"] = "application/vnd.github+json"

    # Where we are ------------------------------------------------------------

    def checkout(self) -> Path | None:
        """The checkout an update would move, or None when this is not one."""
        return self.root if (self.root / ".git").exists() else None

    def installed(self) -> str:
        """The commit this app is running."""
        return git(self.root, "rev-parse", "HEAD")

    def blocked(self) -> str:
        """Why this installation cannot update itself, or '' when it can."""
        if self.checkout() is None:
            return (f"{self.root} is not a git checkout, so JieZhi cannot update itself. "
                    "Reinstall with the one-line install command.")
        if not shutil.which("git"):
            return "git is not installed, so JieZhi cannot update itself."
        if not os.access(self.root, os.W_OK):
            return f"{self.root} is not writable by this account, so the update cannot be installed."
        try:
            branch = git(self.root, "rev-parse", "--abbrev-ref", "HEAD")
            dirty = git(self.root, "status", "--porcelain")
        except (RuntimeError, subprocess.SubprocessError) as error:
            return f"{self.root} could not be read as a git checkout: {error}"
        if branch != self.branch:
            return (f"This checkout is on {branch}, not {self.branch}. "
                    f"Updating would move it off your branch, so it was left alone.")
        if dirty:
            return (f"{self.root} has uncommitted changes. Commit or discard them, "
                    "and they will not be touched in the meantime.")
        if not launcher(self.root).exists():
            return (f"{launcher(self.root)} is missing, so there would be nothing to restart. "
                    "Re-run the one-line install command.")
        return ""

    # What is out there -------------------------------------------------------

    def api_get(self, path: str, **kwargs):
        try:
            response = self.session.get(f"{self.api}{path}", timeout=(10, 30), **kwargs)
        except requests.RequestException:
            raise RuntimeError("Could not reach GitHub to check for updates. Check your connection.") from None
        if response.status_code in (403, 429):
            raise RuntimeError("GitHub is rate limiting update checks. Try again in a few minutes.")
        if response.status_code == 404:
            raise RuntimeError(f"{self.repo} has no branch named {self.branch}.")
        if not response.ok:
            raise RuntimeError(f"GitHub returned HTTP {response.status_code} for the update check.")
        try:
            return response.json()
        except ValueError:
            raise RuntimeError("GitHub returned an unreadable answer to the update check.") from None

    def head(self) -> dict:
        return self.api_get(f"/repos/{self.repo}/commits/{self.branch}")

    def version_at(self, ref: str) -> str:
        """The version string at a commit, read as the file rather than as JSON.

        Cosmetic: it only decides whether the box can name a version, so a
        failure here is not one.
        """
        try:
            response = self.session.get(
                f"{self.api}/repos/{self.repo}/contents/host/jiezhi/__init__.py",
                params={"ref": ref}, headers={"Accept": "application/vnd.github.raw"}, timeout=(10, 30))
            text = response.text if response.ok else ""
        except requests.RequestException:
            return ""
        for line in text.splitlines():
            if line.startswith("__version__"):
                return line.partition("=")[2].strip().strip('"\'')
        return ""

    def check(self) -> dict | None:
        """What `main` has that this checkout does not, or None when level."""
        if self.checkout() is None:
            return None
        try:
            installed = self.installed()
        except (RuntimeError, subprocess.SubprocessError) as error:
            raise RuntimeError(f"Could not read the installed version: {error}") from None
        head = self.head()
        target = str(head.get("sha") or "")
        if not target or target == installed:
            return None
        comparison = self.api_get(f"/repos/{self.repo}/compare/{installed}...{target}")
        # Newest first reads as patch notes; the API hands them back oldest first.
        commits = list(reversed(comparison.get("commits") or []))
        behind = int(comparison.get("ahead_by") or len(commits))
        if comparison.get("status") == "identical" or not behind:
            return None
        return {
            "head": target,
            "short": short(target),
            "installed": installed,
            "version": self.version_at(target),
            "count": behind,
            "commits": commits,
            "notes": notes_for(commits),
            "url": f"{REPO_PAGE}/compare/{short(installed)}...{short(target)}",
            "published": ((head.get("commit") or {}).get("author") or {}).get("date") or "",
        }

    # Taking it on ------------------------------------------------------------

    def touches_dependencies(self, before: str, after: str) -> bool:
        try:
            changed = git(self.root, "diff", "--name-only", f"{before}..{after}", "--", *DEPENDENCIES)
        except (RuntimeError, subprocess.SubprocessError):
            # Unreadable means unknown, and an unnecessary reinstall is cheap
            # next to an update that leaves a dependency behind.
            return True
        return bool(changed.strip())

    def install(self, update: dict, progress=lambda percent, message: None, cancel=None) -> Path:
        """Fast-forward the checkout onto a commit, rolling back if it will not run."""
        reason = self.blocked()
        if reason:
            raise RuntimeError(reason)
        target = update["head"]
        before = self.installed()
        progress(0, "Fetching the new code…")
        git(self.root, "fetch", "--prune", "origin", self.branch)
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        progress(45, f"Moving to {short(target)}…")
        git(self.root, "reset", "--hard", target)
        try:
            if self.touches_dependencies(before, target):
                progress(65, "Updating dependencies…")
                self.rebuild()
            if not launcher(self.root).exists():
                raise RuntimeError("The update left no launcher behind.")
            write_desktop_entry(self.root, self.desktop_file)
        except BaseException:
            # The fetch is harmless and the tree move is reversible, so anything
            # that goes wrong after it puts the old commit back.
            progress(90, "That did not work · putting the previous version back…")
            git(self.root, "reset", "--hard", before)
            raise
        progress(100, "Updated · restarting JieZhi")
        return self.root

    def rebuild(self) -> None:
        """Reinstall the checkout into its own environment."""
        python = self.root / ".venv/bin/python"
        if not python.exists():
            raise RuntimeError(f"{python} is missing, so dependencies could not be updated.")
        result = subprocess.run([str(python), "-m", "pip", "install", "-q", "-e", str(self.root)],
                                capture_output=True, text=True, timeout=PIP_TIMEOUT)
        if result.returncode:
            raise RuntimeError((result.stderr or result.stdout).strip()[-400:] or "Dependencies could not be updated.")


def fetch_client(progress=lambda percent, message: None, base: str = CLIENT_BASE, cache: Path | None = None) -> Path:
    """Download the prebuilt phone client, verified against the manifest beside it.

    Only used when neither a packaged APK nor a local Android build is present,
    which is every installation that did not build the client itself.
    """
    cache = Path(cache) if cache else CACHE / "client"
    session = requests.Session()
    session.headers["User-Agent"] = f"JieZhi/{__version__}"
    progress(0, "Looking up the phone client…")
    try:
        manifest = session.get(f"{base}/manifest.json", timeout=(10, 30))
        if manifest.status_code == 404:
            raise RuntimeError("No prebuilt phone client has been published yet. Build it with scripts/build-android.sh.")
        if not manifest.ok:
            raise RuntimeError(f"The phone client manifest returned HTTP {manifest.status_code}.")
        details = manifest.json()
    except requests.RequestException:
        raise RuntimeError("Could not reach GitHub for the phone client. Check your connection.") from None
    except ValueError:
        raise RuntimeError("The phone client manifest could not be read.") from None

    name = str(details.get("name") or "jiezhi-client.apk")
    expected = str(details.get("sha256") or "").lower()
    if not expected:
        raise RuntimeError("The phone client was published without a checksum, so it was not installed.")
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / Path(name).name
    if target.is_file() and sha256(target) == expected:
        progress(100, "Phone client ready")
        return target

    partial = target.with_name(target.name + ".partial")
    digest = hashlib.sha256()
    written = 0
    try:
        with session.get(f"{base}/{name}", stream=True, timeout=(10, 120)) as response:
            if not response.ok:
                raise RuntimeError(f"The phone client download returned HTTP {response.status_code}.")
            total = int(response.headers.get("Content-Length") or details.get("size") or 0)
            with partial.open("wb") as stream:
                for block in response.iter_content(BLOCK):
                    written += len(block)
                    if total and written > total:
                        raise RuntimeError("The phone client download was larger than published.")
                    stream.write(block)
                    digest.update(block)
                    progress(written * 100 // total if total else 0,
                             f"Downloading the phone client · {written / 1024 ** 2:.0f} of {total / 1024 ** 2:.0f} MB"
                             if total else "Downloading the phone client…")
    except requests.RequestException:
        partial.unlink(missing_ok=True)
        raise RuntimeError("The phone client download was interrupted. Try again.") from None
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    if digest.hexdigest() != expected:
        partial.unlink(missing_ok=True)
        raise RuntimeError("The phone client failed its checksum and was discarded.")
    partial.replace(target)
    progress(100, "Phone client downloaded and verified")
    return target


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(BLOCK), b""):
            digest.update(block)
    return digest.hexdigest()


def running_from_checkout() -> bool:
    """Whether this process is a checkout rather than something else entirely."""
    return (Path(ROOT) / ".git").exists() and not getattr(sys, "frozen", False)
