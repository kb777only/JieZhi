# Changelog

All notable changes to JieZhi are documented here.

## 0.8.0-alpha.1 — 2026-09-21

- Add in-app updates: JieZhi reads its own GitHub releases, offers the patch
  notes of a newer one, and replaces the installed bundle in place after
  verifying its published checksum, then restarts. A sliding panel asks once
  whether to check on every launch; the replaced bundle is kept until the next
  launch so the process being updated can finish reading itself out of it.
- Move the selection chip, action menu, style chooser, results and toasts on one
  motion budget: each rises a little as it fades in and fades out as it goes, and
  the chooser grows into place when the Custom sliders appear. Reduced motion in
  Settings stills all of it, and the area selector is left alone so the drag it
  exists to start is never delayed.
- Stop a window on its way out from taking a click. A press during a fade-out now
  lands on whatever is behind it, and the style chooser re-arms its 250 ms press
  guard when the sliders appear under the pointer.
- Keep the Translate into row and the per-action model pickers from stretching
  with the window; they use the shared row helpers the rest of the host uses.

Host-side only; nothing in this release has been validated against the phone.

## 0.7.0-alpha.1 — 2026-09-21

- Add an OpenAI-compatible endpoint (`jiezhi-gateway`) so third-party AI workspaces
  can use the phone's NPU: model listing, streamed and whole chat completions,
  legacy completions, on-demand model loading and per-phone request queueing.
  Loopback-only, with Host checking and an optional API key.
- Add a device registry that tracks each attached phone's identity, Hexagon
  capability and connection state, with one client per phone.
- Rewrite selected text in a chosen style: one button per preset, or Custom with a
  0-10 slider per style so voices can be blended. Weights reach the model as
  plain-language clauses, and a style left at zero is dropped from the prompt
  rather than named with a zero beside it.
- Lay every host screen out from one spacing, type and control scale
  (`host/jiezhi/theme.py`): title bands, grouped control rows with one primary
  action each, guidance in empty lists, and telemetry sparklines collapsed behind
  a Show graphs toggle. Dark mode is generated from its own token table instead of
  hex replacements over the light sheet.
- Fix check boxes drawing no indicator, welcome artwork cut off on the opening
  screen, the "Appearance & workspace" group title losing its ampersand, and
  clipped combo and spin box arrows.
- Fade the selection chip in over 140 ms and make it a compact 40×26 tab.
- Fix a press at the chip's edge counting as a press outside it, which hid the chip
  between press and release and swallowed the click. Hover, dismissal and the
  rewrite chooser now share the same slack.
- Keep the rewrite style chooser under the pointer where the menu was, ignore
  presses for 250 ms after it appears, and close it on a click elsewhere or on a
  second Rewrite.
- Close an abandoned action menu once the pointer has been away from it for a
  moment, instead of leaving it over other applications.
- Fix detected-image capture on scaled displays, where accessibility device pixels
  were handed to a logical-pixel grab.
- Let result popups be dragged by their body and closed with Escape, and release
  them from the session list when they close.
- Stop tracking a `.venv` symlink committed by accident, which pointed at an
  absolute path outside the repository and collided with a local virtualenv on
  checkout.

Host-side only; nothing in this release has been re-validated against the phone.

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
