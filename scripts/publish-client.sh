#!/bin/sh
# Publish the built phone client where an installation without the Android SDK
# can fetch it.
#
# There is no release to attach it to any more, so it goes on a branch of its
# own: raw.githubusercontent.com serves a branch unauthenticated, and pushing a
# single orphan commit each time means exactly one copy of the APK exists in
# the repository rather than one per build.
set -eu
cd "$(dirname "$0")/.."

apk=android/app/build/outputs/apk/debug/app-debug.apk
branch=${JIEZHI_CLIENT_BRANCH:-prebuilt}
push_url=${JIEZHI_PUSH_URL:-$(git config --get remote.origin.url)}

test -f "$apk" || { echo "No built client at $apk. Run scripts/build-android.sh first." >&2; exit 1; }

# GitHub refuses a push containing a file over 100 MB, and raw.githubusercontent
# will not serve one either. The QNN assets are most of the APK and they grow,
# so fail here with the reason rather than at the push with a rejection.
size=$(wc -c < "$apk")
limit=${JIEZHI_CLIENT_LIMIT:-99000000}
if [ "$size" -gt "$limit" ]; then
    echo "The client is $size bytes, past the $limit a branch can carry." >&2
    echo "Shrink the APK or give it somewhere else to live." >&2
    exit 1
fi

version=$(sed -n 's/.*versionName = "\([^"]*\)".*/\1/p' android/app/build.gradle.kts)
commit=$(git rev-parse HEAD)
sha=$(sha256sum "$apk" | cut -d' ' -f1)

work=$(mktemp -d "${TMPDIR:-/tmp}/jiezhi-client.XXXXXX")
trap 'rm -rf "$work"' EXIT HUP INT TERM
cp "$apk" "$work/jiezhi-client.apk"

cat > "$work/manifest.json" <<EOF
{
  "version": "$version",
  "commit": "$commit",
  "name": "jiezhi-client.apk",
  "sha256": "$sha",
  "size": $size
}
EOF

cat > "$work/README.md" <<EOF
# Prebuilt phone client

This branch holds one file: the Android client built from \`main\`, for
installations that have no Android SDK to build it with. JieZhi fetches it and
checks it against the \`sha256\` in \`manifest.json\` before sideloading it.

It is rewritten by \`.github/workflows/publish-client.yml\` on every push to
main, as a single orphan commit. Nothing here is edited by hand, and the
history is not kept.

Built from commit \`$commit\`, version \`$version\`.
EOF

git -C "$work" init -q -b "$branch"
git -C "$work" add .
git -C "$work" -c user.email=noreply@github.com -c user.name="JieZhi CI" \
    commit -q -m "Phone client $version from $(echo "$commit" | cut -c1-7)"
git -C "$work" push -q --force "$push_url" "$branch"
echo "Published $version ($size bytes) to $branch"
