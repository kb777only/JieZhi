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
tools_trouble=

# How this looks. The one-liner is `curl … | sh`, so stdout is a terminal while
# somebody is watching and a pipe or a file when nobody is. Colour, a spinner
# and a hidden cursor are for the first case only; everything below falls back
# to the plain lines this printed before.
fancy=
if [ -t 1 ] && [ "${TERM:-dumb}" != dumb ] && [ -z "${NO_COLOR:-}" ]; then
    fancy=yes
fi

# Blue, then purple, red and pink: the app's own order, walked across the bar.
blue=; purple=; red=; pink=; faint=; reset=
if [ -n "$fancy" ]; then
    blue=$(printf '\033[38;5;33m')
    purple=$(printf '\033[38;5;99m')
    red=$(printf '\033[38;5;204m')
    pink=$(printf '\033[38;5;211m')
    faint=$(printf '\033[38;5;242m')
    reset=$(printf '\033[0m')
fi

stages=6
stage=0
doing=
bar=
mark=

newline() { if [ -n "$fancy" ]; then printf '\n'; fi; }

# Six stages, six columns each: a bar of thirty-six.
draw_bar() {
    bar=
    index=0
    while [ "$index" -lt "$stages" ]; do
        if [ "$index" -lt "$stage" ]; then
            case $((index % 4)) in
                0) bar="$bar$blue━━━━━━" ;;
                1) bar="$bar$purple━━━━━━" ;;
                2) bar="$bar$red━━━━━━" ;;
                3) bar="$bar$pink━━━━━━" ;;
            esac
        else
            bar="$bar$faint──────"
        fi
        index=$((index + 1))
    done
    bar="$bar$reset"
    case $(((stage - 1) % 4)) in
        0) mark=$blue ;;
        1) mark=$purple ;;
        2) mark=$red ;;
        3) mark=$pink ;;
    esac
}

line() { printf '\r   %s   %s%s%s %s\033[K' "$bar" "$mark" "$1" "$reset" "$doing"; }

spinner=
spin() {
    while :; do
        for frame in ⠋ ⠙ ⠹ ⠸ ⠼ ⠴; do
            line "$frame"
            sleep 0.3
        done
    done
}

stop_spin() {
    if [ -n "$spinner" ]; then
        kill "$spinner" 2>/dev/null || :
        wait "$spinner" 2>/dev/null || :
        spinner=
    fi
}

# What is happening now. Everything that follows it runs while it is on screen.
begin() {
    stop_spin
    doing=$1
    stage=$((stage + 1))
    if [ -z "$fancy" ]; then
        printf '==> %s\n' "$doing"
        return
    fi
    draw_bar
    line '·'
    spin &
    spinner=$!
}

# Same stage, something else being done inside it.
now() {
    stop_spin
    doing=$1
    if [ -z "$fancy" ]; then
        printf '==> %s\n' "$doing"
        return
    fi
    line '·'
    spin &
    spinner=$!
}

# It worked. On a terminal the line it has been sitting on becomes the record
# of it; piped, `begin` already said what was happening and saying it again in
# the past tense would only double the output.
done_with() {
    stop_spin
    if [ -n "$fancy" ]; then
        doing=${1:-$doing}
        line '✓'
        printf '\n'
    fi
}

# Something optional did not work. The bar moves on; the mark says it did not.
gave_up() {
    stop_spin
    doing=$1
    if [ -n "$fancy" ]; then
        printf '\r   %s   %s✕%s %s\033[K\n' "$bar" "$red" "$reset" "$doing"
    else
        printf '==> %s\n' "$doing"
    fi
}

tidy() {
    stop_spin
    if [ -n "$fancy" ]; then
        printf '\033[?25h'
    fi
}
trap tidy EXIT HUP INT TERM
if [ -n "$fancy" ]; then
    printf '\033[?25l'
fi

say() { stop_spin; printf '==> %s\n' "$1"; }
die() { stop_spin; newline; printf 'JieZhi install: %s\n' "$1" >&2; exit 1; }

if [ "${1:-}" = "--uninstall" ]; then
    rm -rf "$root"
    rm -f "$desktop"
    say "Removed $root and the menu entry."
    say 'Your conversations, models and pairing state were kept in ~/.local/share/jiezhi.'
    exit 0
fi

begin 'Checking what this machine has'
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
done_with "Found git and $python"

if [ -d "$root/.git" ]; then
    begin 'Updating the checkout'
    git -C "$root" remote set-url origin "$repo"
    git -C "$root" fetch -q --prune origin "$branch"
    # Never discard someone's work to install an update. This is the same rule
    # the app's own Update button follows.
    [ -z "$(git -C "$root" status --porcelain)" ] ||
        die "$root has uncommitted changes. Commit or discard them, then run this again."
    git -C "$root" checkout -q -B "$branch" "origin/$branch"
else
    [ ! -e "$root" ] || die "$root already exists and is not a git checkout. Move it aside and run this again."
    begin 'Fetching JieZhi'
    mkdir -p "$(dirname "$root")"
    git clone -q --branch "$branch" "$repo" "$root"
fi
done_with

begin 'Building the environment · slow'
[ -d "$root/.venv" ] || "$python" -m venv "$root/.venv"
# Editable, so the checkout the updater moves is the code that runs, and so the
# launcher the menu entry points at is built from pyproject's console script.
"$root/.venv/bin/python" -m pip install -q --upgrade pip
"$root/.venv/bin/python" -m pip install -q -e "$root"
done_with 'Building the environment'

# PySide6 carries its own Qt, but Qt's X11 support links against system
# libraries a desktop does not necessarily have — Qt 6 needs libxcb-cursor0,
# which Qt 5 never did, so a machine full of working Qt 5 applications can
# still be missing it. Without this the app aborts with a message on a
# terminal nobody is looking at, which reads as the app simply not starting.
begin 'Checking it can open a window'
trouble=$("$root/.venv/bin/python" -c 'from jiezhi.preflight import report; print(report() or "", end="")')
if [ -n "$trouble" ]; then
    stop_spin
    printf '\n%s\n' "$trouble" >&2
    printf '\nThe checkout and its environment are already in place in %s,\n' "$root" >&2
    printf 'so running this again afterwards takes a couple of seconds.\n' >&2
    exit 1
fi
done_with

if command -v adb >/dev/null 2>&1 || [ -x "$root/.tools/platform-tools/adb" ]; then
    begin 'ADB is already available'
    done_with
else
    # TLS is what authenticates this one; Google publishes no stable checksum
    # for the rolling "latest" archive. Everything else JieZhi downloads is
    # checksum-pinned.
    # A failure here is not fatal: the app runs without adb, it just cannot
    # reach a phone until one is on PATH.
    begin 'Fetching Android platform-tools'
    mkdir -p "$root/.tools"
    tools_trouble=$("$root/.venv/bin/python" - "$platform_tools" "$root/.tools" 2>&1 <<'PY'
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
) || adb_missing=1
    [ -x "$root/.tools/platform-tools/adb" ] || adb_missing=1
    if [ -n "$adb_missing" ]; then
        gave_up 'Could not fetch platform-tools'
    else
        done_with
    fi
fi

begin 'Adding it to the application menu'
"$root/.venv/bin/python" - "$root" "$desktop" <<'PY'
import sys
from pathlib import Path
from jiezhi.updates import write_desktop_entry
write_desktop_entry(Path(sys.argv[1]), Path(sys.argv[2]))
PY

if command -v desktop-file-validate >/dev/null 2>&1; then
    desktop-file-validate "$desktop" || die "the menu entry at $desktop is not valid. That is a bug; please report it."
fi

# Everything that has gone wrong with this so far only went wrong on the
# machine it was installed on, and a menu launch has no terminal to say so on.
# Start it once here, the way the menu will, while somebody is still watching.
if [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]; then
    now 'Starting it once, as the menu will'
    if ! "$root/scripts/launch.sh" --self-test >/dev/null 2>&1 </dev/null; then
        stop_spin
        newline
        log="${XDG_DATA_HOME:-$HOME/.local/share}/jiezhi/launch.log"
        printf '\nJieZhi is installed, but it did not start:\n\n' >&2
        if [ -f "$log" ]; then
            sed 's/^/    /' "$log" >&2
        fi
        printf '\nThe checkout in %s is fine, so this is JieZhi'"'"'s problem, not yours.\n' "$root" >&2
        printf 'Please send that output along; it says exactly what stopped it.\n' >&2
        exit 1
    fi
    done_with 'Added to the menu, and it starts'
else
    done_with
fi

version=$("$root/.venv/bin/python" -c 'from jiezhi import __version__; print(__version__)')
commit=$(git -C "$root" rev-parse --short HEAD)
if [ -n "$fancy" ]; then
    printf '\n   %sJieZhi %s · %s%s\n' "$blue" "$version" "$commit" "$reset"
    printf '   %s%s%s\n\n' "$faint" "$root" "$reset"
    printf '   Start it from the application menu, or run\n\n'
    printf '       %s%s%s\n\n' "$purple" "$root/.venv/bin/jiezhi" "$reset"
    printf '   It will offer its own updates from then on.\n'
else
    say "JieZhi $version ($commit) is installed in $root"
    printf '\nStart it from the application menu, or run:\n\n    %s\n\n' "$root/.venv/bin/jiezhi"
    printf 'It will offer its own updates from then on.\n'
fi
if [ -n "$adb_missing" ]; then
    printf '\n%sADB could not be fetched, so JieZhi cannot reach a phone yet.%s\n' "$red" "$reset"
    if [ -n "$tools_trouble" ]; then
        printf '%s%s%s\n' "$faint" "$tools_trouble" "$reset"
    fi
    printf 'Install it from your package manager (on Debian: sudo apt install android-tools-adb).\n'
fi
