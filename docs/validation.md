# V1 validation — 2026-09-20

## v0.5 model discovery and alpha hardening

The Hugging Face screen now turns phone detection into a central discovery flow:
results are ranked by task, memory fit, context, quantization and the measured
SM8750/Qwen3 baseline. Unsupported split/projector files, unsuitable tasks,
insufficient storage, and incompatible metadata are kept out of recommendations.
Every score discloses that it is a fit heuristic rather than a model-quality
benchmark; speed bands outside the two measured Qwen3 Q4_0 points are explicitly
low-confidence estimates.

The host suite now contains 44 passing tests, including recommendation calibration,
category ordering, context/RAM pressure, MoE and unsupported-file treatment,
metadata sanitization, revision preservation, device-specific cache behavior,
and real Qt ranking/selection interaction. Version identifiers were unified as
`0.5.0-alpha.1`, packaging now derives filenames from the host version, and the
public source release gained reproducible test configuration and CI checks.

## Hardware and build

Host: Deepin 25 x86_64. Phone: Xiaomi 15 Ultra (`25010PN30G`), SM8750,
Android 16, user-reported 16 GB RAM. USB link reports 480 Mb/s. Runtime:
Qualcomm GenieX Android 0.7.0, llama.cpp adapter, explicit `npu` selection.
The APK was built locally and installed on the phone. The self-contained Linux
bundle and graphical installer were built and the desktop app installed/launched.

## Confirmed on the phone

- USB ADB access and Android authorization.
- One-time pairing and rejection of unauthenticated requests.
- Real PC-to-app model transfer into app-private storage, resumed after interruption.
- Full SHA-256 verification and rejection of a deliberately corrupted upload.
- Qwen3 0.6B Q4_0 load and streamed natural-language generation.
- Native `HTP0` layer assignment and model/KV/compute buffer allocation;
  log reports 29/29 layers offloaded. llama.cpp uses the word “GPU” for this
  offload abstraction; the selected device and memory buffers are HTP0/Hexagon.
- Cancellation followed by another working generation request.
- Rejection of a concurrent model load during generation.
- Removing and recreating the ADB USB forwarding tunnel without losing the model.
  This simulated tunnel disconnection; physical cable unplugging was not tested.

The initial 25-token response reported 73.16 tokens/s through the runtime SDK.
A repeated-generation run completed 76 requests over approximately 440 seconds:
median 69.19 tokens/s, range 58.79–74.46. Median host-observed first-token time was
72 ms for this short-prompt workload. Android thermal status remained 0.
Requests generated up to 256 tokens with two seconds between requests; this is
not a large-model or long-context performance claim.

The requested ten-minute run was interrupted by APK replacement. Android's
`ApplicationExitInfo` records `PACKAGE UPDATED` at 17:56:14.492 with description
`stop dev.jiezhi.client due to installPackageLI`. This is **not** recorded as a
completed ten-minute stability test, nor as a native inference crash.

## Desktop validation

Qwen3 1.7B Q4_0 was also transferred from the PC, SHA-256 verified, loaded, and
tested. A 38-token answer reported **33.88 tokens/s**, with 67 ms SDK first-token
latency. Native logs show HTP0 model buffers and 29/29 layers offloaded. Both
models remain in the phone library.

Seven automated tests cover resumed transfers, invalid model rejection, cancelled
imports, runtime error propagation, truncated streams, credential file modes,
and installation/update behavior. They pass.

Qt screens were rendered and inspected. The native desktop app launches on the
actual Deepin desktop. The self-extracting installer was launched separately and
reached its GUI without needing the project's Python environment. Its install
operation was exercised and the application-menu launcher verified.

The actual Qt Send button was exercised against the 1.7B model on the phone.
The UI streamed the answer, saved its conversation, and reopened it from history.
This passed; `artifacts/gui-hardware-check.json` records the result and
`artifacts/desktop-1.7B.png` captures the real GUI response.

## Power-management finding

HyperOS froze the first client process when it moved into the background, despite
its foreground service. The prototype now holds a bounded partial wake lock during
USB activity, renewed by desktop heartbeats, and during active inference. A
per-app Android battery exemption was also enabled on this test device using
`cmd deviceidle whitelist +dev.jiezhi.client`. The combined configuration was used
for the successful repeated-generation test. The effect of each change was not
isolated. Xiaomi's additional “No restrictions” battery setting is documented in
the setup flow; its manual setting was not independently verified.

## Limits of this evidence

Only this Xiaomi/Deepin combination has been tested. No Samsung validation,
arbitrary model-format compatibility, network-disabled inference test, fresh
machine installation test, or production release-signing validation is claimed.
The runtime executes locally using PC-transferred weights, with no cloud chat API
configured. CPU participation in tokenization/sampling and some operations is
expected; runtime offload logs are not a measurement of NPU utilization percentage.

Raw local artifacts: `artifacts/first-inference.json`, `artifacts/npu-runtime.log`,
`artifacts/hardware-check.json`, and the GUI screenshots. These generated files
are retained in the workspace but excluded from Git.

## v0.2 attachments, Hub and interface update

The host, GUI installer, and Android client now share a light Deepin/Xiaomi-inspired
interface. Android version 0.2.0 was built and installed on the same Xiaomi.
An initial activity startup exception caused by requesting the system-bar controller
before creating the decor view was caught during device testing and fixed. The
updated build starts successfully and handled the subsequent hardware test.

18 automated tests pass, including PDF extraction, scanned/encrypted PDF errors,
UTF-8/UTF-16, binary rejection, bounded excerpts, document follow-ups, paused Hub
downloads and HTTP Range resumption, SHA-256 rejection, unsafe filenames, session
and keyring account behavior, and Qt attachment/send/history interaction. Account
checks use a controlled test server and simulated keyring; no real user's Hugging
Face token was supplied, so private/gated access is not claimed as live-tested.

A real public Hugging Face API search returned 30 results. Qwen3-0.6B-Q4_0.gguf
(382,156,480 bytes) was downloaded through the new Hub implementation, deliberately
paused, resumed, and verified against the repository's SHA-256. Its pinned revision
and resulting cache path are recorded in `artifacts/v02/hub-download.json`.

The actual Qt Send button was tested with a Markdown attachment containing a
unique launch code and handoff date. The Xiaomi's Qwen3-1.7B-Q4_0 model, explicitly
loaded on NPU with a 4096-token context, correctly answered both facts. The SDK
reported 36.7 tokens/s, 0.08 seconds to first token, and 33 output tokens. The saved
conversation reopened with its extracted attachment intact. The same GUI then
queried Hugging Face and listed 26 GGUF files from the starter repository.
See `artifacts/v02/gui-hardware-check.json` and corresponding screenshots.

The self-contained 0.2.0 Linux bundle and self-extracting GUI installer were built.
The installer GUI's install action updated the per-user installation successfully.
The packaged application was launched on Deepin. These checks do not constitute
a fresh-machine or universal Linux compatibility test.

The **Download & send to phone** GUI action also completed successfully using the
verified cache entry and the already-present phone model (deduplicated import).
This verifies the chained GUI flow without claiming a second full USB transfer;
`artifacts/v02/hub-to-phone.json` records the result.

## v0.3 projects, workbooks and PC Assistant

The desktop adds general project workspaces, project-scoped history, linked folders,
reference documents and project instructions. Spreadsheet extraction supports
XLSX/XLSM, XLS and ODS in addition to CSV/TSV; formulas/macros are never executed.
A real Qt project conversation automatically selected an XLSX reference and the
Xiaomi's 1.7B model correctly answered a budget lookup (742 EUR), reporting 33.5
tokens/s. `artifacts/v03/project-hardware.json` records the result.

32 automated tests passed after integration, covering earlier transport/download
features plus workbook extraction, bounded ODS repeats, project persistence and
exclusions, project/personal history separation, approval/denial, read-only mode,
scoped writes, mandatory command approval, symlink/hardlink/traversal protection,
file-change races, rollback conflicts, command timeout, invalid model instructions,
and stopping through the real Qt approval flow. A deterministic simulated phone
model completed a fixture repair and command verification through the same tool
executor. This simulation is distinguished from physical-model testing below.

Initial physical 1.7B agent runs were unreliable: one returned invalid JSON, one
selected an incorrect configuration value and failed verification, and one tried
to edit the wrong fixture file and was denied. These are not counted as successful
repairs. The task only touched a disposable fixture under `.cache`; no real user
program was modified. The host audit and approval enforcement operated correctly.
Model-context handling was improved to retain earlier relevant evidence when an
intervening diagnostic result is large, and host-generated command status is
displayed separately from model conclusions.

The v0.3 self-contained Linux bundle/installer was built and its GUI installation
action updated the per-user desktop installation. The v0.2 Android client remains
protocol-compatible; this host feature update does not require APK replacement.

While an alternative 4B instruction model was downloading, the user loaded
`Qwen3.5-9B-DeepSeek-V4-Flash-Q3_K_M.gguf` and began testing it. The development
4B download process was stopped before transfer/loading, so it did not replace the
user's model. A read-only status check showed the 9B model loaded with a 2048-token
context and NPU requested. No successful 9B tool-loop repair or native offload
measurement is claimed. Further model-driven repair validation was left pending
to avoid occupying the phone during the user's test. The desktop assistant requires
4096 or more context tokens. The last focused assistant/GUI suite passed 12 tests;
the complete integration suite passed 32. The packaged installer also remained
running normally during its standalone launch smoke test.

## v0.4 live telemetry and 9B Assistant validation

Android 0.4 and the matching host were built and installed on the same Xiaomi and
Deepin PC. A fixed bottom telemetry panel remains outside the page stack, visible
across Conversation, models, setup, diagnostics, Hub, Projects and PC Assistant.
Separate worker polling continues while generation is active. All eight requested
metrics have graph cards with a two-minute history; missing counters remain gaps.

A 90-sample physical-device run during the user's 9B model workload returned
battery level/temperature, live SDK stream event rate, whole-phone RAM usage and
current CPU thermal sensors. CPU deltas were available after initial sampling.
GPU KGSL reads were denied by Android and no readable NPU utilization counter was
available. Those two cards explicitly report unavailable. GPU/NPU temperatures
are separately visible under Sensor details and never substituted for utilization.
The SoC card explicitly labels its hottest-CPU-sensor proxy. The Android thermal
HAL defines `socd`'s type 8 as BCL percentage, so that electrical reading is excluded.

Unauthenticated telemetry requests returned HTTP 401. Removing the test's own ADB
forward and closing its HTTP keep-alive connection made token readings unknown;
creating a new forward restored telemetry. The physical cable remained attached.
This did not disturb the inference test's separate forwarding tunnel.

The first 9B tool run exposed a chat-template difference: its opening thinking
marker was prefilled, so generated output included only the closing `</think>`.
The host now parses the final channel and stops decoding at the first complete
JSON action. This also bounds models that repeat valid actions instead of ending
their response. Host tool policy, edit review, command approval and stream error
checks still apply. Tests verify that incomplete or reasoning-only instructions
cannot execute. The obsolete run was cancelled with no edits or commands.

Native logs for the 9B model report 33/33 layers assigned to HTP0 and substantial
buffers on both HTP0 and CPU. This confirms accelerator participation, not exclusive
NPU execution or a utilization percentage. Observed decoding was around 3–4
stream callbacks/s with a long initial prefill. See `artifacts/v04/9b-runtime.log`.

The automated suite passed 37 tests, including current versus cached thermal
readings, electrical-sensor exclusion, CPU deltas, unavailable counters, connection
identity reset, graph gaps and reasoning-format handling. The self-contained
0.4 Linux installer reached its GUI, and the GUI install action successfully
updated the per-user installation. Real-device telemetry samples, screenshots
and tunnel-recovery results are in `artifacts/v04`.

## Phone-aware model search (host 0.5 alpha)

The host now detects SoC, RAM and data storage with read-only ADB queries. Search
and all five category discovery flows were exercised against the live Hugging Face
API. In the recorded result set, chat selected Qwen3 1.7B Q4_0, coding selected
Qwen2.5 Coder 1.5B, reasoning/documents selected Qwen3 4B, and fast replies selected
Qwen3 0.6B. These are heuristic rankings of returned candidates, not quality-test
results or new inference benchmarks. No model was loaded or run for this update;
the user's instruction to stop using the 9B model was preserved.

The real Qt search flow detected the Xiaomi's SM8750 and 14.76 GiB OS-visible RAM,
ranked 36 repository results, opened the first result automatically and ranked its
26 GGUF files. Compact rows render the rank, suitability, RAM fit/range, quantization
and speed range beneath each name. Account controls collapse to leave more room.
The current screenshot and metadata are in `artifacts/v05/model-search.png` and
`artifacts/v05/search-hardware.json`; category results are in `category-search.json`.

44 automated tests pass. New coverage checks category ordering, supported versus
unknown SoCs, calibrated versus unknown architectures, context/memory sensitivity,
MoE total parameters, unsupported split/projector files, pinned metadata caching,
read-only phone discovery and device-specific fallback, Qt selection preservation,
automatic category searches and download-to-phone handoff (simulated transfer).
Existing real model downloads/transfers are documented above; this update did not
redownload model weights. The GUI installer updated the per-user installation and
the packaged installer passed its standalone launch smoke test. The workspace's
current unified package version is `0.5.0-alpha.1`.
