# Updates

JieZhi checks its own GitHub releases and can replace the installed app with a
newer one without a download page or a terminal.

## What the app does

On first launch a small panel rises into the bottom-right corner and asks
whether JieZhi should check for a new version each time it starts. It stays
there until the question is answered, and it carries a **Check for updates**
button for looking straight away. The answer is remembered in
`preferences.json` as `auto_update_check`, and can be changed later under
Settings → Updates.

A check reads `https://api.github.com/repos/kb777only/JieZhi/releases` with no
token: the repository is public. The list endpoint is used rather than
`/releases/latest`, which hides pre-releases — every JieZhi release so far is
an alpha, so hiding them would mean never finding one.

- **Nothing newer.** A manual check says so in a panel that fades out after a
  few seconds. A startup check says nothing at all.
- **Something newer.** A panel says which version is available. Clicking it
  opens the release's patch notes with **Exit** and **Update** at the bottom.
  Exit closes the box and leaves JieZhi running.

## What an update does

The running app is a PyInstaller bundle in `~/.local/opt/jiezhi`, not a
checkout, so updating means replacing a directory that a live process is
reading itself out of. The sequence is built so that every step before the last
one can be abandoned with nothing changed:

1. Download `JieZhi-<version>-linux-x86_64.tar.gz` from the release into
   `~/.cache/jiezhi/updates`. Exit during the download and the partial file is
   removed.
2. Verify it against the `SHA256SUMS` the release publishes. A release that
   publishes sums has to produce the one for this file; a checksum that cannot
   be read stops the update rather than being skipped. A bundle that does not
   match is discarded and the installation is untouched.
3. Unpack beside the installation, using tar's `data` filter, which refuses
   absolute paths, parent traversal and links that leave the directory.
4. Rename the old bundle to `jiezhi.previous`, move the new one into its place,
   and rewrite the desktop entry. A failure anywhere in here puts the previous
   installation back.
5. Start the new bundle and exit.

`jiezhi.previous` is deliberately **not** deleted during the update: the
process being replaced is still running out of that directory and loads parts
of itself lazily, so those files have to outlive it. The next launch clears it,
along with any `.installing` or `.unpack` directory an interrupted update left.

## What it does not do

- **The phone client is not updated.** Host and Android versions are kept in
  step by `scripts/release-check.sh`, but an update only replaces the PC
  bundle. After a version change, reinstall the client from Device setup.
- **A source checkout cannot update itself.** Running `host/main.py` from a
  clone, the box says so and offers the release page; use git instead.
- **A release with no Linux bundle attached cannot be installed.** The app says
  a version exists and links the release page rather than pretending.

## What a release has to carry

An update can only install what `scripts/package.sh` produces and the release
publishes. For OTA to work, a release needs at least:

```
JieZhi-<version>-linux-x86_64.tar.gz
SHA256SUMS
```

The tarball must unpack to a single `JieZhi/` directory containing the `JieZhi`
executable, which is what `package.sh` already writes.

## Version comparison

Tags are compared as versions, not as strings, so `0.7.0` outranks
`0.7.0-rc.1`, `0.7.0-beta.1` outranks `0.7.0-alpha.9`, and the `0.7.0a1`
spelling in `pyproject.toml` compares equal to `0.7.0-alpha.1`. A tag that does
not parse is never treated as newer, so an oddly named tag cannot trigger an
update.
