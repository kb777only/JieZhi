#!/bin/sh
set -eu
cd "$(dirname "$0")/.."

export QT_QPA_PLATFORM=${QT_QPA_PLATFORM:-offscreen}
.venv/bin/python -m pytest
sh scripts/build-android.sh

host_version=$(PYTHONPATH=host .venv/bin/python -c 'from jiezhi import __version__; print(__version__)')
android_version=$(sed -n 's/.*versionName = "\([^"]*\)".*/\1/p' android/app/build.gradle.kts)
test "$host_version" = "$android_version" || {
    echo "Version mismatch: host=$host_version android=$android_version" >&2
    exit 1
}
echo "Release checks passed for $host_version"
