#!/bin/sh
# What the application menu runs.
#
# Started from a menu there is no terminal, so anything that stops JieZhi — a
# broken interpreter, a failed import, Qt aborting over a missing system
# library, a segfault — disappears without trace and reads as the app simply
# not starting. This keeps all of it, and puts it on screen.
#
# From a terminal it gets out of the way and behaves like any other program.
set -u

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
launcher="$root/.venv/bin/jiezhi"

if [ ! -x "$launcher" ]; then
    printf 'JieZhi: %s is missing. Run %s to put it back.\n' "$launcher" "$root/scripts/install.sh" >&2
fi

# So the app knows something is keeping its output and does not put the same
# message on screen twice.
JIEZHI_LAUNCHED_BY=launch.sh
export JIEZHI_LAUNCHED_BY

if [ -t 2 ]; then
    exec "$launcher" "$@"
fi

data=${XDG_DATA_HOME:-$HOME/.local/share}/jiezhi
log=$data/launch.log
if mkdir -p "$data" 2>/dev/null && : > "$log" 2>/dev/null; then
    {
        printf 'JieZhi launch · %s\n' "$(date '+%Y-%m-%d %H:%M:%S')"
        printf 'checkout · %s\n' "$root"
        printf 'launcher · %s\n' "$launcher"
        printf '\n'
    } >> "$log"
    "$launcher" "$@" >> "$log" 2>&1
    status=$?
else
    log=
    "$launcher" "$@"
    status=$?
fi

[ "$status" -eq 0 ] && exit 0

reason="JieZhi stopped before it could open a window (exit $status)."
if [ -n "$log" ]; then
    reason="$reason

$(tail -n 24 "$log")

All of it is in $log"
fi

for tool in zenity kdialog notify-send; do
    command -v "$tool" >/dev/null 2>&1 || continue
    case $tool in
        zenity) zenity --error --title=JieZhi --no-wrap --text="$reason" ;;
        kdialog) kdialog --title JieZhi --error "$reason" ;;
        notify-send) notify-send --urgency=critical JieZhi "JieZhi could not start. ${log:+See $log}" ;;
    esac
    break
done
exit "$status"
