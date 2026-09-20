#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
export JAVA_HOME="${JAVA_HOME:-$PWD/.tools/jdk}"
export ANDROID_HOME="${ANDROID_HOME:-$PWD/.tools/android-sdk}"
printf 'sdk.dir=%s\n' "$ANDROID_HOME" > android/local.properties
if test -x .tools/gradle-8.13/bin/gradle; then
    exec .tools/gradle-8.13/bin/gradle -p android assembleDebug --console plain
fi
exec android/gradlew -p android assembleDebug --console plain
