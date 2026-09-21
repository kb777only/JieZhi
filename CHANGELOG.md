# Changelog

All notable changes to JieZhi are documented here.

## Unreleased

- Add in-app updates: JieZhi reads its own GitHub releases, offers the patch
  notes of a newer one, and replaces the installed bundle in place after
  verifying its published checksum, then restarts. A sliding panel asks once
  whether to check on every launch; the replaced bundle is kept until the next
  launch so the process being updated can finish reading itself out of it.
- Add an OpenAI-compatible endpoint (`jiezhi-gateway`) so third-party AI workspaces
  can use the phone's NPU: model listing, streamed and whole chat completions,
  legacy completions, on-demand model loading and per-phone request queueing.
  Loopback-only, with Host checking and an optional API key.
- Add a device registry that tracks each attached phone's identity, Hexagon
  capability and connection state, with one client per phone.

## 0.6.0-alpha.1 — 2026-09-20

- Add X11 selection/right-click popups with 350 ms hover, per-action model settings,
  loading/generating toasts, cursor-adjacent results and image area-selection fallback.
- Add phone NPU image rework, expansion, variations and tiled QuickSRNet 2× upscaling.

- Project chats can create folders/files and edit/save PC files through scoped, reviewed tools, with access controls and saved paths in chat.

- Add corner Settings and quick dark-mode controls, remembered preferences,
  animated device welcome artwork and a wider Projects layout.
- Consolidate Hugging Face account, telemetry, motion and generation defaults.
- Add editable, saved node workflows with typed connections, sequential model
  switching, cancellation, output previews and per-node parameters.
- Add Android NPU image/video pipelines (Absolute Reality / Neodragon) and CPU
  alternatives (SD 1.5 / Wan), with verified starter downloads, resumable transfer
  and private outputs. No cloud inference is used. NPU media has separately
  attributed non-commercial upstream components.
- Preserve text NPU inference and existing chat, projects, attachments and PC safeguards.

## 0.5.0-alpha.1 — 2026-09-20

- Make phone-aware model discovery the primary Hugging Face experience.
- Rank repositories and GGUF files by task, phone RAM/storage, context, format,
  quantization, and calibrated SM8750 performance ranges.
- Explain every recommendation and distinguish fit heuristics from quality claims.
- Add live phone telemetry across all desktop screens.
- Add project workspaces, spreadsheets, local references, and guarded PC tools.
- Preserve authenticated/resumable USB model transfer, local chat, cancellation,
  Hugging Face revision pinning, checksums, and keyring-backed optional credentials.
- Unify host, Android, HTTP user-agent, and package release versions.
- Add public-repository documentation, CI, and a release-check script.

Earlier alpha milestones and their hardware evidence are recorded in
[`docs/validation.md`](docs/validation.md).
