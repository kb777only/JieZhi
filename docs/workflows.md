# Creative workflows (0.6 alpha)

The desktop canvas is an executable directed acyclic graph. Each model executes on
Android, in topological order, with one inference operation at a time. The desktop
stores the graph and verified results; it does not run inference.

## Using the canvas

1. Connect and pair the phone. Refresh phone models on Flow canvas.
2. Add Prompt, Language model, Image generation, Video generation or Output nodes.
3. Drag an output dot to an input dot. Select nodes to edit their parameters; edits
   are saved automatically. `{{input}}` inserts connected text in the node prompt.
4. Select an installed model for every model node. The starter button downloads
   and transfers pinned weights and configures the selected matching media node
   (or creates one). Downloads require both desktop and phone storage.
5. Run flow. Watch per-node status and the native progress log. Image results appear
   beside the log; Open result launches the image/video in the desktop viewer.

Ctrl+wheel zooms; middle-drag pans. Fit canvas frames all nodes. Save/Open export
and import versioned JSON. Remove selected node/wire removes its connections too.
The draft is saved in `~/.local/share/jiezhi/workflows/draft.json`; runs and outputs
are under `workflows/runs`. Stop cancels inference or a starter transfer and keeps
completed results. Repeating a starter download resumes verified partial transfers.

## Runtimes and compatibility

- **Text:** existing GenieX, requested NPU or CPU backend, selected context/output limits.
- **NPU images:** Absolute Reality, a preconverted SD 1.5 QNN package (~0.98 GiB
  download). UNet/VAE execute on Hexagon; the upstream CLIP component uses MNN.
  Fixed 512×512 in this integration, adjustable steps, guidance, seed and negative
  prompt. Supports a connected image for image-to-image. This is the LocalDream
  runtime path, separate from GenieX's text runtime.
- **NPU video:** Neodragon, ~8.1 GiB of compiled graph and supporting asset files.
  Fixed 49-frame, 1024×640 pipeline with a compiled pyramidal schedule. Prompt,
  seed and playback FPS are editable; irrelevant diffusion-step controls are hidden.
  Supports text-to-video and an image node as the starting frame. Produces H.264 MP4.
  A real V79 NPU numerical canary must pass before generation.
- **CPU images:** SD 1.5 Q4_0 (~1.46 GiB), separate stable-diffusion.cpp executable;
  PNG output. Small 256×256 / 8-step settings test transport but have poor quality.
- **CPU video:** Wan 2.1 T2V 1.3B Q4_K_M, UMT5-XXL Q3_K_S and Wan VAE (~3.81 GiB),
  real multi-frame diffusion, AVI/MJPEG output. Requires 4n+1 frames and multiples
  of 64 for dimensions. This CPU starter is text-to-video. Image-to-video on CPU
  requires compatible I2V/VACE weights; such custom weights have not been validated.

NPU media requires converted QNN packages; changing a backend dropdown does not
convert a GGUF. Wrong package/backend combinations fail before inference. Other
model families may need inputs this alpha does not expose. No arbitrary remote
model code executes. A text model cannot consume media edges; branch a prompt into
text and media nodes or use compatible image-to-video edges. One image input per node.

The app releases a loaded text runtime before media generation to recover memory.
It does not automatically restore a previous model afterwards. NPU video runs in
an isolated Android service process to keep QNN global state separate from GenieX.
CPU models remain optional fallbacks. Stop preserves completed outputs. Phone heat,
battery policy and memory affect performance; no universal real-time claim is made.

## Transport and persistence

Media endpoints use the existing authenticated loopback ADB channel. Files are
transferred in resumable 4 MiB chunks, size-checked and SHA-256 verified before
registration. QNN archives have bounded extraction, safe paths and a required-file check. Video
bundles hard-link verified components in private app storage. Output downloads are
also size/hash verified. Runtime arguments are
passed directly to ProcessBuilder, never interpreted by a shell. A native process
crash reports a failed job instead of taking down the desktop.

The media library is separate from the text library in this alpha. Import media
weights through Flow canvas. Model weights remain private to the Android app;
clearing Android app data removes all model libraries and pairing state. Model
licenses apply independently; starter downloads are not bundled with the app.

## Building

`scripts/build-media.sh` pins stable-diffusion.cpp and its submodules, cross-compiles
an ARM64 CPU executable with NDK 27.2.12479018 / CMake 3.22.1, strips it and collects
license notices. Android packages it as an extracted native library so it can be
executed under Android's native-code rules. The host and APK both carry notices. `scripts/prepare-qnn.py` verifies the upstream
Nightmare Mobile v1.5.533 APK hash and stages only the V79 QNN runtime, native image
executable, video JNI library and numerical canary. Selected Kotlin pipeline files
are attributed under `third_party/nightmare-mobile` (CC BY-NC 4.0). This component
is non-commercial licensed and is not covered by the host's MIT license.

Neodragon registration copies verified components into its runnable private bundle.
Allow roughly 16 GiB of phone storage for the approximately 8 GiB components plus
the assembled bundle; the verified source components remain available.
