#!/bin/sh
# Install JieZhi for this account, or bring an existing installation up to date.
#
#   curl -fsSL https://raw.githubusercontent.com/kb777only/JieZhi/main/scripts/install.sh | sh
#
# An installation is a git checkout with its own virtual environment. That is
# also what the app's Update button moves, so running this again is the same
# operation by hand, and it is always safe to repeat.
#
#   --uninstall   remove the installation and the menu entry, keeping your data
#
# Override with JIEZHI_HOME, JIEZHI_REPO, JIEZHI_BRANCH.
set -eu

repo=${JIEZHI_REPO:-https://github.com/kb777only/JieZhi.git}
branch=${JIEZHI_BRANCH:-main}
root=${JIEZHI_HOME:-$HOME/.local/opt/jiezhi}
desktop=${JIEZHI_DESKTOP:-$HOME/.local/share/applications/jiezhi.desktop}
platform_tools=${JIEZHI_PLATFORM_TOOLS:-https://dl.google.com/android/repository/platform-tools-latest-linux.zip}

adb_missing=

say() { printf '==> %s\n' "$1"; }
die() { printf 'JieZhi install: %s\n' "$1" >&2; exit 1; }

if [ "${1:-}" = "--uninstall" ]; then
    rm -rf "$root"
    rm -f "$desktop"
    say "Removed $root and the menu entry."
    say 'Your conversations, models and pairing state were kept in ~/.local/share/jiezhi.'
    exit 0
fi

command -v git >/dev/null 2>&1 || die 'git is required. Install it and run this again.'

# 3.12 is the floor the host is written against, and what Deepin 25 ships.
python=
for candidate in python3.13 python3.12 python3; do
    if command -v "$candidate" >/dev/null 2>&1 &&
        "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)' 2>/dev/null; then
        python=$candidate
        break
    fi
done
[ -n "$python" ] || die 'Python 3.12 or newer is required. Install it and run this again.'
"$python" -c 'import venv' 2>/dev/null || die "$python cannot create virtual environments. Install its venv package (on Debian: python3-venv)."

if [ -d "$root/.git" ]; then
    say "Updating the checkout in $root"
    git -C "$root" remote set-url origin "$repo"
    git -C "$root" fetch --prune origin "$branch"
    # Never discard someone's work to install an update. This is the same rule
    # the app's own Update button follows.
    [ -z "$(git -C "$root" status --porcelain)" ] ||
        die "$root has uncommitted changes. Commit or discard them, then run this again."
    git -C "$root" checkout -q -B "$branch" "origin/$branch"
else
    [ ! -e "$root" ] || die "$root already exists and is not a git checkout. Move it aside and run this again."
    say "Cloning JieZhi into $root"
    mkdir -p "$(dirname "$root")"
    git clone -q --branch "$branch" "$repo" "$root"
fi

say 'Preparing the virtual environment'
[ -d "$root/.venv" ] || "$python" -m venv "$root/.venv"
# Editable, so the checkout the updater moves is the code that runs, and so the
# launcher the menu entry points at is built from pyproject's console script.
"$root/.venv/bin/python" -m pip install -q --upgrade pip
"$root/.venv/bin/python" -m pip install -q -e "$root"

if command -v adb >/dev/null 2>&1 || [ -x "$root/.tools/platform-tools/adb" ]; then
    say 'ADB is already available'
else
    # TLS is what authenticates this one; Google publishes no stable checksum
    # for the rolling "latest" archive. Everything else JieZhi downloads is
    # checksum-pinned.
    # A failure here is not fatal: the app runs without adb, it just cannot
    # reach a phone until one is on PATH.
    say 'Fetching Android platform-tools from Google'
    mkdir -p "$root/.tools"
    if ! "$root/.venv/bin/python" - "$platform_tools" "$root/.tools" <<'PY'
import io, os, sys, urllib.request, zipfile

url, target = sys.argv[1], sys.argv[2]
try:
    with urllib.request.urlopen(url, timeout=300) as response:
        payload = response.read()
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        for entry in archive.infolist():
            path = archive.extract(entry, target)
            mode = entry.external_attr >> 16
            if mode:
                # extract() drops permissions, and adb has to stay executable.
                os.chmod(path, mode)
except Exception as error:
    # The caller turns this into one line of advice; a stack trace in the
    # middle of an install reads as a broken install, and this one is not.
    print(f"platform-tools could not be fetched: {error}", file=sys.stderr)
    raise SystemExit(1)
PY
    then
        adb_missing=1
    fi
    [ -x "$root/.tools/platform-tools/adb" ] || adb_missing=1
fi

say 'Adding JieZhi to the application menu'
"$root/.venv/bin/python" - "$root" "$desktop" <<'PY'
import sys
from pathlib import Path
from jiezhi.updates import write_desktop_entry
write_desktop_entry(Path(sys.argv[1]), Path(sys.argv[2]))
PY

version=$("$root/.venv/bin/python" -c 'from jiezhi import __version__; print(__version__)')
commit=$(git -C "$root" rev-parse --short HEAD)
say "JieZhi $version ($commit) is installed in $root"
printf '\nStart it from the application menu, or run:\n\n    %s\n\n' "$root/.venv/bin/jiezhi"
printf 'It will offer its own updates from then on.\n'
if [ -n "$adb_missing" ]; then
    printf '\nADB could not be fetched, so JieZhi cannot reach a phone yet.\n'
    printf 'Install it from your package manager (on Debian: sudo apt install android-tools-adb).\n'
fi
