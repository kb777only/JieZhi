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

version=$(sed -n 's/.*versionName = "\([^"]*\)".*/\1/p' android/app/build.gradle.kts)
commit=$(git rev-parse HEAD)
sha=$(sha256sum "$apk" | cut -d' ' -f1)
size=$(wc -c < "$apk")

work=$(mktemp -d "${TMPDIR:-/tmp}/jiezhi-client.XXXXXX")
trap 'rm -rf "$work"' EXIT HUP INT TERM

# GitHub refuses a push containing a file over 100 MB, and the QNN assets put
# the APK well past that on their own, so it goes up in pieces and the app
# joins them again. 45 MB keeps each one comfortably under the limit and under
# the size GitHub warns about.
part=${JIEZHI_CLIENT_PART:-45000000}
split -b "$part" -d -a 3 "$apk" "$work/jiezhi-client.apk."

parts=""
for piece in "$work"/jiezhi-client.apk.*; do
    name=$(basename "$piece")
    piece_size=$(wc -c < "$piece")
    if [ "$piece_size" -gt 99000000 ]; then
        echo "$name is $piece_size bytes, past what a repository will hold." >&2
        echo "Lower JIEZHI_CLIENT_PART." >&2
        exit 1
    fi
    entry="    {\"name\": \"$name\", \"sha256\": \"$(sha256sum "$piece" | cut -d' ' -f1)\", \"size\": $piece_size}"
    if [ -z "$parts" ]; then parts=$entry; else parts="$parts,
$entry"; fi
done

cat > "$work/manifest.json" <<EOF
{
  "version": "$version",
  "commit": "$commit",
  "name": "jiezhi-client.apk",
  "sha256": "$sha",
  "size": $size,
  "parts": [
$parts
  ]
}
EOF

cat > "$work/README.md" <<EOF
# Prebuilt phone client

This branch holds the Android client built from \`main\`, for installations
that have no Android SDK to build it with. It is past the 100 MB a repository
will hold in one file, so it is split into \`jiezhi-client.apk.000\` and its
neighbours; JieZhi joins them in order and checks the result against the
\`sha256\` in \`manifest.json\` before sideloading it.

It is rewritten by \`.github/workflows/publish-client.yml\` whenever a push to
main touches the client, as a single orphan commit. Nothing here is edited by
hand, and the history is not kept.

Built from commit \`$commit\`, version \`$version\`.
EOF

git -C "$work" init -q -b "$branch"
git -C "$work" add .
git -C "$work" -c user.email=noreply@github.com -c user.name="JieZhi CI" \
    commit -q -m "Phone client $version from $(echo "$commit" | cut -c1-7)"
git -C "$work" push -q --force "$push_url" "$branch"
echo "Published $version ($size bytes in $(ls "$work"/jiezhi-client.apk.* | wc -l) pieces) to $branch"
