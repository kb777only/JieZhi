# Desktop selection assistant

Keep JieZhi running and your phone connected. On the tested Deepin X11 desktop,
select text in another app or right-click an image. A small JieZhi chip fades in
next to the pointer. Hover for **350 ms** to expand its action menu. The host can remain
minimized. Selecting content alone does not start inference or send it to the phone.

Text actions are Summarize, Rewrite, Continue writing, Explain, Translate and
Generate image. Image actions are Rework, Upscale 2×, Expand and Create variation.
Rewrite asks for a style first: a button for each style rewrites in that voice
straight away, and **Custom…** opens a weight slider per style, from 0 to 10,
with **Generate** to start. The weights are blended into the instruction sent to
the phone; a style left at 0 is not mentioned to the model at all, since naming
it would pull the rewrite toward it. Your last custom weights are remembered.
The chooser opens in the menu's place, under the pointer, with the heading rather
than a button beneath it, and it ignores any press for the first quarter second,
so the click that asked for a rewrite cannot also pick a style. Clicking away
closes it, and asking for a rewrite again replaces it.
Rework and Expand ask for a description. Results open beside the pointer with
Copy, Save and Stop controls. Drag a result by its body to move it, and press
Escape to close it. Loading/generating status also appears in toasts. Moving the
pointer away from the action menu closes it after a moment, so an unused menu
does not stay on screen until you click.

## Settings and models

Open the corner gear, then **Desktop selection assistant**. Enable/disable the
popup, choose a translation language and choose a separate model for each action.
**Refresh available models** reads both model libraries from the connected phone.
Text actions default to the current text model, or the last text model after a
media job unloaded it. A different selected model is loaded automatically on the
phone with NPU requested and an 8192-token context. The model must support this
configuration. Explicit choices remain saved across reconnects.

Image generation, rework, variations and expansion use converted SD 1.5 QNN
packages such as Absolute Reality, available through Flow canvas's starter models.
**Get NPU upscaler** downloads and transfers the small QuickSRNet 2× graph without
requiring the full video model. Media jobs load their native runtime for each job;
the host reports this loading phase. Only one generation runs at a time.

## Image capture and current limits

When an app exposes image bounds through accessibility, JieZhi captures that visible
image area. Otherwise the menu offers **Select area**: drag around the image and
release; Escape cancels. With fallback enabled, an unrecognized right-click can
also offer this menu. Hovering the icon dismisses the application's native context
menu so it cannot intercept JieZhi's controls.

Capture uses visible screen pixels, not an original full-resolution image hidden
inside the source app. Only the selected region is sent to the phone. Oversized
captures are reduced to a maximum side of 2048 pixels. NPU upscaling doubles each
dimension using overlapping tiles. Absolute Reality generates 512×512 outputs;
expansion fits the source into the central 384×384 area and generates its surround.
Results depend on model quality and may introduce artifacts.

Text selection is held transiently in memory (up to 32,000 characters); text actions
use a bounded excerpt of up to 5,000 UTF-8 bytes, and image prompts up to 4,000.
The selected passage is treated as content, without access to project/PC tools.
Text results are saved only when requested. Image results are retained under
`~/.local/share/jiezhi/quick-results` before an optional Save copy.

Automatic cross-app detection currently requires X11. Wayland global selection
and pointer integration is not implemented. Accessibility image detection is
optional; on the tested Deepin installation the accessibility bus is unavailable,
so image actions use the area-selection fallback. No root access is required.

NPU media incorporates separately licensed non-commercial components. See
[third-party notices](../THIRD_PARTY.md) and [workflows](workflows.md).
