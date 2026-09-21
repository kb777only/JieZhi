# Install and update

JieZhi installs and updates itself from this repository. There are no releases,
no build artifacts and no download page.

## What an installation is

A git checkout with its own virtual environment:

```
~/.local/opt/jiezhi/          the checkout, on main
~/.local/opt/jiezhi/.venv/    its environment, with JieZhi installed editable
~/.local/opt/jiezhi/.tools/   platform-tools, if the system had no adb
```

`scripts/install.sh` puts it there:

```sh
curl -fsSL https://raw.githubusercontent.com/kb777only/JieZhi/main/scripts/install.sh | sh
```

`raw.githubusercontent.com` serves a public repository unauthenticated, so the
one-liner needs no release, no token and no hosting of our own.

The install is editable (`pip install -e .`), which is the point: the working
tree *is* the running code, so moving the tree is the whole update. It also
produces `.venv/bin/jiezhi` from the console script in `pyproject.toml`, which
is what the menu entry runs and what an update restarts.

Override `JIEZHI_HOME`, `JIEZHI_REPO` or `JIEZHI_BRANCH` to install elsewhere.
`--uninstall` removes the checkout and the menu entry, keeping your data.

## Why a checkout and not a bundle

The host is pure Python. It was being packaged with PyInstaller into a 200 MB
bundle whose only real job was to be an artifact, and an artifact needs somewhere
to live, which meant a release, which had to be built and uploaded by hand. A
checkout removes that whole chain: GitHub already serves the code.

The phone client is the exception, since it genuinely has to be compiled and
needs the Android SDK. See **The phone client** below.

## What the app does

On first launch a small panel rises into the bottom-right corner and asks
whether JieZhi should check for new commits each time it starts. It stays there
until the question is answered, and carries a **Check for updates** button for
looking straight away. The answer is `auto_update_check` in `preferences.json`,
and can be changed later under Settings → Updates.

A check reads `/repos/kb777only/JieZhi/commits/main`, compares the head against
`git rev-parse HEAD` in the checkout, and asks
`/repos/kb777only/JieZhi/compare/<installed>...<head>` for what is in between.
Both are public and unauthenticated.

- **Nothing new.** A manual check says so in a panel that fades out after a few
  seconds. A startup check says nothing at all.
- **New commits.** A panel says how many. Clicking it opens their messages —
  which read as patch notes because this repository writes them as prose — with
  **Exit** and **Update** at the bottom. Exit closes the box and leaves JieZhi
  running.

## What an update does

1. `git fetch --prune origin main`. Nothing in the working tree has changed yet,
   so leaving at this point leaves the installation exactly as it was.
2. `git reset --hard <head>`.
3. `pip install -e .`, but only when the commits being taken on actually touched
   `pyproject.toml` or `requirements.txt`. Most updates skip this and take about
   a second.
4. Rewrite the desktop entry, then start `.venv/bin/jiezhi` and exit.

Anything that fails after step 2 resets back to the commit that was installed
before, so a broken dependency install does not leave a half-updated app.

## What it refuses to do

An update moves a checkout with `git reset --hard`, which destroys uncommitted
work, so it will not run at all when:

- **the checkout has uncommitted changes.** The box names the directory and says
  to commit or discard them. Nothing is touched in the meantime.
- **the checkout is on another branch.** Updating would move you off your own
  branch, so it is left alone. This is what makes a development clone safe to
  point the app at.
- **the directory is not a git checkout**, is not writable, or has no launcher.

`scripts/install.sh` follows the same rule when re-run, for the same reason.

## The phone client

An update replaces the PC app only. The phone keeps the client it has until it
is reinstalled from Device setup, and host and Android versions are kept in step
by `scripts/release-check.sh`.

Building that client needs the Android SDK, the NDK and a pinned QNN runtime,
which an installation is not going to have. So CI builds it when a push to
`main` touches the client and `scripts/publish-client.sh` puts it on the
`prebuilt` branch as a single orphan commit, with a `manifest.json` beside it.
`raw.githubusercontent.com` serves that branch unauthenticated, and
`updates.fetch_client()` downloads and verifies it when neither a packaged APK
nor a local Android build is present.

The QNN assets put the APK at about 123 MB, and GitHub refuses a push containing
a file over 100 MB, so it goes up in 45 MB pieces named `jiezhi-client.apk.000`
and on. The manifest carries a SHA-256 for each piece and one for the whole
file; the app joins them in order, checks each piece as it lands so a bad one is
named, and checks the result before sideloading it. Nothing is kept if either
check fails.

The branch is force-pushed each time, so exactly one copy of the APK exists in
the repository rather than one per build, and the build only runs when the
client actually changed.
