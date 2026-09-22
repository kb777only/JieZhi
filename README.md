# Prebuilt phone client

This branch holds the Android client built from `main`, for installations
that have no Android SDK to build it with. It is past the 100 MB a repository
will hold in one file, so it is split into `jiezhi-client.apk.000` and its
neighbours; JieZhi joins them in order and checks the result against the
`sha256` in `manifest.json` before sideloading it.

It is rewritten by `.github/workflows/publish-client.yml` whenever a push to
main touches the client, as a single orphan commit. Nothing here is edited by
hand, and the history is not kept.

Built from commit `22ad3f08f9ee668c6689bd49cc67ccdaf22ff047`, version `0.9.0-alpha.1`.
