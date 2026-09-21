# 借智 · JieZhi

**Your phone is already an AI computer. JieZhi lets Linux borrow it.**

JieZhi is a Linux assistant that borrows inference capacity from an Android phone
connected by USB. The desktop owns the interface and conversation history. The
Android app owns model storage and inference. No desktop inference or cloud chat
provider is used.

This repository contains the `v0.6.0-alpha.1` source: the native
Linux host, Android inference client, authenticated USB protocol, model discovery
and fit recommendations, local document/project context, guarded PC tools, live
phone telemetry, a saved node canvas, phone-local image/video diffusion, tests,
build scripts, and packaging flow.

![JieZhi sends a local AI model's thoughts from a phone to a desktop through USB](assets/generated/jiezhi-logo-usb-thoughts-v4.png)

**V1 target:** Deepin 25 x86_64 + Xiaomi 15 Ultra, Snapdragon 8 Elite (SM8750),
16 GB RAM, Android 16. Other phones are not yet validated.

## Install and use

1. Download the release assets from GitHub. Verify them with `SHA256SUMS`, then
   open the versioned `JieZhi-…-Installer.run`, or extract the Linux archive
   and run `Install-JieZhi.sh`. The GUI installs into `~/.local/opt/jiezhi` and adds
   JieZhi to the application menu. ADB and the Android APK are included.
2. Enable USB debugging on the phone, connect a data cable, and accept Android's
   computer authorization prompt. In **Welcome & device**, select the phone.
3. Click **Install Android client**. Approve any Xiaomi USB installation prompt.
4. Click **Connect & pair**, then enter the code shown in JieZhi on the phone.
5. On Xiaomi, set JieZhi's app battery saver to **No restrictions**. HyperOS was
   observed freezing the app in the background even with a foreground service.
6. In **Phone models**, import a local `.gguf`, select **Hexagon NPU**, and load it.
7. Open **Chat** and send a message. Use **Diagnostics** to inspect native runtime
   logs. CPU mode is an explicit diagnostic option and is labelled as such.

## Appearance, settings and creative workflows

The upper-right gear opens Settings: Hugging Face account, theme, gradient motion,
telemetry visibility/polling, reconnect behavior and context defaults. The adjacent
moon/sun switches theme immediately. Chat and Projects retain files, spreadsheets,
history, folders and guarded PC Assistant actions. Inside a project, chat can
create folders/files and edit/save files directly on the PC. The default mode
asks before each change; saved paths and action decisions appear in chat. An
unlinked project gets its own folder under `~/Documents/JieZhi Projects`.

**Flow canvas** connects Prompt, Language model, Image generation, Video generation
and Output nodes. Drag output dots to input dots; select nodes to edit parameters.
Ctrl+wheel zooms, middle-drag pans, and Save/Open share JSON workflows. Edits are
saved locally. Only **Run flow** starts inference. Text nodes can use different
phone models in sequence. Media outputs are downloaded over authenticated USB,
verified and saved locally with the flow results. Stop preserves finished outputs.

**Get starter media models…** downloads pinned, checksum-verified models and all
required components, transfers them over USB and configures the node. **Absolute
Reality uses Hexagon NPU** through QNN (512×512); **Neodragon uses the NPU** for
49-frame video at 1024×640, with text or an image as input. The CPU alternatives
are SD 1.5 images and Wan 2.1 1.3B video. Custom compatible GGUF/safetensors weights
and converted SD 1.5 QNN ZIP packages can be imported. NPU models need their
converted QNN representation; an arbitrary GGUF cannot run on that media path.
See [workflow details and limits](docs/workflows.md).

The NPU media component adapts LocalDream / Nightmare Mobile under **CC BY-NC 4.0**,
with terms separate from JieZhi's own code. Its non-commercial restriction and Qualcomm/model
terms apply to the combined prototype; see [third-party notices](THIRD_PARTY.md).

## Actions beside your cursor

Select text or right-click an image, then hover over the JieZhi icon for 350 ms.
Summarize, rewrite, continue, explain, translate or generate an image; rework,
expand, vary or upscale selected images on the phone NPU. When an app does not
expose its image, drag to select its area. Results open next to the cursor with
Copy/Save controls and loading/generating toasts. The host can remain minimized.
Set each action's model, translation language and popup toggle in Settings.
This integration currently targets X11. See [desktop actions](docs/desktop-actions.md).

## The hook: a phone-aware local model library

JieZhi does more than move inference to the phone. **Discover models** detects the
connected phone's SoC, RAM, and free storage, then ranks models and exact GGUF
files for chat, coding, reasoning, document work, or speed. Every suitability
score exposes its assumptions: estimated working RAM, context size, quantization,
compatibility cautions, and a deliberately broad decode-speed range. Recommendations
are heuristics—not quality benchmarks—and the UI keeps that distinction visible.

The result is one continuous local workflow: find a model that fits this phone,
download it with revision pinning and SHA-256 verification, resume if interrupted,
send it over USB, load it on the requested backend, and chat from the desktop.

If Linux reports no USB permissions, **Fix USB access** installs a rule for the
tested Xiaomi USB vendor/product IDs. Only this step needs system authentication.
The desktop application itself uses a per-user installation.

Model transfers resume when the same file is imported again. A SHA-256 check on
the phone must pass before a model becomes loadable. Models persist across app
restarts. Pairing tokens are session-scoped: restarting the Android service
requires pairing again. **Stop and disconnect** on the phone revokes the session.

## Documents and source files

In **Conversation**, click **Attach files** or drop spreadsheets, PDFs, text, Markdown, CSV,
or source files onto the window. Preview the extracted text, then ask a question.
Attachments are read locally; relevant excerpts are sent to the phone with your
question. They are never sent to Hugging Face. The conversation stores extracted
text so follow-up questions still work after reopening it.

Limits: five attachments per message, 20 MiB per file, up to 100 PDF pages and
200,000 extracted characters per file. PDFs need selectable text; OCR and
password-protected PDFs are not supported. Excerpts are selected by matching the
question, not semantic embeddings. Larger documents may have relevant material
outside the selected excerpts. The UI reports bounded context and omitted history;
load a larger context or narrow the question when needed. Text uses UTF-8 or UTF-16.

## Hugging Face downloads

Open **Hugging Face** for recommendations by category, or type to search GGUF
models. Entering `owner/repository` opens its files directly. Each result shows a
phone suitability score, estimated decoding speed and RAM range beneath its name.
Scores reflect hardware fit and category signals, not measured model quality.
Use the context selector to compare memory needs and hover for estimate details.
See [how recommendations work](docs/recommendations.md).

Open **Account settings** to connect a Hugging Face account. Choose a file and **Download to PC**, or **Download & send to
phone**. Select the same file again to resume a paused or interrupted download.
Downloads are pinned to a commit and SHA-256 checked before phone transfer.
Files are ranked for the phone and selected category; split GGUFs are currently unsupported. The model page
links to its license, access requirements, and instructions.

Public models need no account. To connect your account, create a **read** token
using **Get a read token**, paste it into the masked field, and click **Connect
account**. Private/gated models require the token's appropriate repository read
permissions and any access approval on Hugging Face. JieZhi does not accept model
terms on your behalf. **Remember in system keyring** uses Linux Secret Service;
otherwise the token lasts only for this app session. There is no plaintext token
fallback. **Disconnect** removes the saved token. Tokens never go to the phone.

Models and resumable partial downloads are cached under
`$XDG_CACHE_HOME/jiezhi/models` (normally `~/.cache/jiezhi/models`). The verified
path is shown after download. Cached models can also be imported through **Phone
models**. Both the desktop and Android client use the same light blue, rounded
interface, with warm orange accents inspired by Deepin and Xiaomi.

## Projects and PC Assistant

Create a general workspace under **Projects** to group chats, reference documents,
linked folders and project instructions. **PC Assistant** investigates PC problems
using phone-generated tool calls. Its default is **Ask before changes**; choose
read-only or scoped autonomy as needed. Add folders explicitly, review each
proposed diff/command, and use file rollback if necessary. Commands always ask and
are not sandboxed to selected folders. See [the full feature and access guide](docs/assistant.md).

## Live phone telemetry

A permanent bottom panel shows live output rate, battery level/temperature, CPU
load, CPU peak temperature and RAM use with two-minute line graphs. GPU/NPU load
cards report unavailable when the phone does not expose their counters. Live
tokens/s is labelled approximate; completed replies retain the SDK-reported rate.
See [sensor sources and availability](docs/telemetry.md).

## Model compatibility

V1 imports GGUF v2/v3 text models. This does not mean every GGUF architecture or
quantization is supported by the bundled runtime. Start with Q4_0 and conservative
context limits. The default context is 2048; the GUI permits 512–8192. Only one
model and generation request are active at once.

Development starter model:

- `unsloth/Qwen3-0.6B-GGUF`, file `Qwen3-0.6B-Q4_0.gguf`
- Hugging Face revision `50968a4468ef4233ed78cd7c3de230dd1d61a56b`
- File SHA-256 `33bcc57074ec7b6eada5a90651ee546ec0c2b271002c22baf9f1b2dd1e8f75cb`
- Source: https://huggingface.co/unsloth/Qwen3-0.6B-GGUF

Larger starter model prepared for the same device:

- `unsloth/Qwen3-1.7B-GGUF`, file `Qwen3-1.7B-Q4_0.gguf`
- Revision `d7f544eead698dbd1f15126ef60b45a1e1933222`
- SHA-256 `c876f159707a4e4f70e045106c69db15bfc935a4981706fd4f65c6e7ea1e81c5`
- Source: https://huggingface.co/unsloth/Qwen3-1.7B-GGUF

Model weights are not bundled in the installer. Import models you are entitled
to use. Selecting NPU requests acceleration; actual offload evidence comes from
native logs. Tokenization, sampling, and some operations may use the phone CPU.

## Develop

Desktop: Python 3.12+, PySide6, requests, pypdf, keyring. Android: JDK 17, Gradle 8.13,
Android SDK 36 / build tools 35.0.0. Native inference is supplied by the pinned
GenieX 0.7.0 Android AAR for text. Media requires Android NDK 27.2.12479018 and
CMake 3.22.1; install those SDK packages before building. The NPU runtime is staged
from a pinned, checksum-verified upstream APK by `scripts/prepare-qnn.py`.

```sh
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
# Set JAVA_HOME and ANDROID_HOME, or place the toolchains in .tools as below.
# First Android build calls build-media.sh when its native binary is absent.
sh scripts/build-android.sh
.venv/bin/python host/main.py
QT_QPA_PLATFORM=offscreen PYTHONPATH=host .venv/bin/pytest -q tests
sh scripts/package.sh
```

Run `sh scripts/release-check.sh` for the same host and Android checks used before
cutting a release. The Android build uses a standard debug key in this alpha;
release downloads are sideloadable evaluation builds, not app-store artifacts.

The initial developer setup uses `.tools/jdk`, `.tools/gradle-8.13`,
`.tools/android-sdk`, and `.tools/platform-tools`. Toolchains, binaries, model
weights, and generated artifacts are excluded from Git. Build logs live in
`.cache` during development. `scripts/build-android.sh` uses the standard Android
debug signing key: this is a sideloadable proof of concept, not a store release.

## Structure

- `host/jiezhi/client.py`: ADB connection, authenticated API, resumable model transfer.
- `host/jiezhi/gui.py`: chat, model management, setup, history, diagnostics.
- `host/jiezhi/attachments.py`: local extraction and bounded reference selection.
- `host/jiezhi/hub.py`: Hub account, model metadata, resumable verified downloads.
- `host/jiezhi/*_view.py`: attachment and Hub GUI flows.
- `host/jiezhi/installer.py`: per-user graphical installer and uninstaller.
- `android/app/src/main/java/dev/jiezhi/client/`: Android UI, foreground service,
  model store, HTTP bridge, and native inference adapter.
- `docs/protocol.md`: versioned protocol and state behavior.
- `docs/recommendations.md`: phone-fit scoring, memory, and speed assumptions.
- `tests/`: host transport/error handling and installation checks.

## Data and removal

Desktop conversations and pairing state: `$XDG_DATA_HOME/jiezhi`, defaulting to
`~/.local/share/jiezhi`. Pairing and conversation files are created with user-only permissions.
Conversation files include extracted attachments. Hugging Face account metadata
contains only the username and persistence preference; saved tokens use the system
keyring. Disconnect your Hub account before uninstalling to remove its saved token.
Phone models reside in Android app-private storage. The phone listens only on
loopback, forwarded over USB; authenticated endpoints require a random session
token. Only USB-attached devices are offered by the desktop.

Run the GUI installer again to uninstall the desktop app. Conversations are kept.
Remove the Android app through Android settings to remove its private model data.
The USB rule, if installed, is `/etc/udev/rules.d/70-jiezhi-android.rules`.

## V1 limits

Text chat, document/spreadsheet references, projects and guarded PC tools; no voice,
vision, full desktop GUI automation, or automatic model conversion.
No silent CPU fallback is added by JieZhi. Native runtime behavior is reported in
diagnostics. Telemetry refreshes automatically; model-library refresh is manual. Restarting a phone service requires
reconnection/pairing. Android OEM power management requires device-specific
validation. This prototype is not yet a signed production release or a universal
Linux distribution package.

## Project status and licensing

This is an alpha: its validated hardware target and measured evidence are documented
in [docs/validation.md](docs/validation.md). Security issues should follow
[SECURITY.md](SECURITY.md); development contributions are covered by
[CONTRIBUTING.md](CONTRIBUTING.md).

The repository is public for evaluation and collaboration, but no project-level
open-source license has been selected yet. Copyright remains with the contributors;
third-party components retain their own terms. See `THIRD_PARTY.md` before
redistributing a build.

See `THIRD_PARTY.md` for runtime and tool notices.

See `docs/validation.md` for measured hardware results and remaining validation.
