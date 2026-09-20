# JieZhi V1 proposal

Status: V1 implemented. Xiaomi 15 Ultra NPU inference has been demonstrated;
see `validation.md` for final test results and limitations. This document retains
the initial design rationale below.

Confirmed scope: Xiaomi 15 Ultra / 16 GB / SM8750 / Android 16, Deepin 25 x86_64,
USB debugging accepted, text chat and model management first. Samsung devices
remain outside the initial supported target.

## Product objective

A Linux desktop assistant borrows inference capacity from a USB-connected Android
phone. The JieZhi Host manages conversations and models; the JieZhi Android Client
owns model storage and inference. Initial hardware target: Snapdragon 8 Elite
(SM8750). Model weights are transferred once and cached on the phone; subsequent
requests carry prompts and stream generated text back to the desktop.

## Proposed V1 boundary

- Native Linux GUI with device setup, model library, streaming chat, cancellation,
  conversation history, and actionable connection/runtime errors.
- GUI installation and removal, a desktop launcher, and a first-run setup wizard
  covering USB authorization, phone compatibility, APK installation, and pairing.
- Android GUI showing the paired host, model, runtime, active request, storage,
  and an explicit stop/disconnect control.
- One phone, one loaded text model, and one active generation at a time.
- Import supported GGUF files from the PC with validation, progress, resumable
  transfer, integrity checking, and atomic commit into app-private storage.
- Offline inference after installation and model acquisition.
- NPU execution diagnostics, time to first token, generation rate, and thermal
  status where Android exposes it. A requested NPU mode is not proof of NPU use.

Voice, images, document retrieval, and PC actions are separate extensions unless
the user identifies one as essential to the first demonstration.

## Proposed architecture

Linux Qt GUI -> host connection/model service -> authenticated protocol over a
USB ADB forward -> Android foreground service -> inference runtime -> Hexagon NPU.

ADB was accepted by the user for V1. It can carry a
TCP protocol over USB without Wi-Fi. A no-debugging product needs separate USB
transport investigation; it must not be treated as an automatic replacement.

The Android service binds to loopback, accepts a paired session token, and handles
capabilities, model transfers, load/unload, generate/cancel, and diagnostics.
Model uploads go through the app protocol, rather than assuming ADB shell access
to private Android app storage. Check available space for both staging and SDK
import/cache copies. Disconnects cancel generation and leave transfers resumable.
The app must retain a visible notification while serving, with lifecycle behavior
validated on the exact phone and Android version.

Suggested desktop stack: Python/PySide6 for a fast native prototype, subject to
packaging validation on the target distro. Suggested Android stack: Kotlin and
Qualcomm GenieX, behind an adapter so the runtime can be changed independently.
Initial packaging target: Deepin 25 if confirmed by the user. Package installation
and first-run phone setup are both part of the required GUI experience.

## Inference feasibility

Qualcomm's GenieX Android demo explicitly lists Snapdragon 8 Elite NPU support.
The Android APIs expose llama.cpp/GGUF with Hexagon acceleration and Qualcomm
AI Engine Direct with chipset-specific precompiled models. Local filesystem
import and streamed generation are documented. GenieX is a developer preview;
pin and verify an actual released SDK before building against it. Public README
and sample build versions differ, so copying API snippets is not build validation.

Start with a small Q4_0 GGUF model, then a more useful 1–4B model sized for the
phone's RAM. Qualcomm recommends Q4_0 for Hexagon support. Supported architecture,
quantization, context length, runtime operators, and firmware determine actual
compatibility. “Any model” is an extensible import goal, not a promise that any
arbitrary weights or model type can run on the NPU.

Some orchestration, tokenization, sampling, or unsupported operations may execute
on the phone CPU. V1 must report the actual backend and available offload evidence
and must not silently describe CPU-only execution as successful NPU inference.

## Implementation gates

1. Confirm test phone/RAM/Android, Linux target, ADB acceptability, and the first
   assistant workflow.
2. Build a minimal Android client; import a PC-supplied model and generate through
   the NPU inside the app sandbox. Record backend logs/profiling and output.
3. Complete authenticated USB transfer and streaming requests with cancellation,
   disconnect recovery, integrity checks, and app lifecycle handling.
4. Build desktop and phone GUIs around that verified path.
5. Package the desktop installer and APK and rehearse setup on a clean target.

Acceptance: install graphically; connect and authorize the phone; transfer and
load a model from the PC; chat offline with streaming output; demonstrate NPU
work with runtime evidence; cancel, unplug, reconnect, and continue without
corrupting a model. Measure sustained behavior over a ten-minute session. Set
latency and throughput thresholds after agreeing on a model and target phone.

## Open questions

- Exact phone, RAM, Android/firmware, and whether it is available over USB now?
- Is this Deepin 25 installation the first supported Linux environment?
- Is ADB/USB debugging acceptable for V1?
- First priority: text chat, voice, or PC actions? If actions, which three tasks?
- Which model formats, example models, and languages should drive compatibility?

## Sources inspected

- https://github.com/qualcomm/geniex
- https://github.com/qualcomm/ai-hub-apps/blob/release/geniex_chat_android/README.md
- https://geniex.aihub.qualcomm.com/en/run/android/api-reference
- https://geniex.aihub.qualcomm.com/en/run/android/quickstart
- https://geniex.aihub.qualcomm.com/en/models/supported
- https://github.com/ggml-org/llama.cpp/blob/master/docs/backend/snapdragon/README.md
- https://developer.android.com/tools/adb

## Workspace inspection

The project directory was empty at discovery. The host reports Deepin 25.
JDK, Android SDK, Gradle, ADB, and a Python/Qt development environment were installed
locally for this prototype. The packaged app includes its desktop runtime, USB
tools, and Android APK; end users do not need the developer toolchain.
