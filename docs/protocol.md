# JieZhi USB protocol v1

Host creates `adb -s SERIAL forward tcp:0 tcp:39471` for a USB-attached device.
Android binds `127.0.0.1:39471`; the dynamically allocated desktop port is local.
Requests and responses use UTF-8 JSON except upload chunks and streamed chat.
No desktop model execution occurs.

Pair with `POST /v1/pair {"code":"123456"}`. Android displays a random six-digit
code; five attempts per minute are allowed. A successful pair returns a random
256-bit token, and pairing closes until the Android service is restarted.
All other requests require `Authorization: Bearer TOKEN`.

| Method | Path | Behavior |
| --- | --- | --- |
| GET | `/v1/status` | Phone capabilities, state, thermal status, model library, last profile |
| GET | `/v1/telemetry` | Authenticated live generation, battery, RAM and thermal severity; no model/storage lock |
| POST | `/v1/uploads` | `{id: SHA256, name, size}` → current byte offset / complete flag |
| PUT | `/v1/uploads/ID` | Raw chunk up to 4 MiB, Content-Length, X-Offset; durable append |
| POST | `/v1/commit` | `{id}` → length, GGUF magic, SHA-256 checks and atomic rename |
| POST | `/v1/load` | `{id, backend: npu\|cpu, context: 2048}` → native model load |
| POST | `/v1/unload` | `{}` → release loaded model |
| DELETE | `/v1/models/ID` | Remove unloaded model and any partial upload |
| POST | `/v1/chat` | `{messages: [{role, content}], max_tokens: 512}` → NDJSON stream |
| POST | `/v1/cancel` | `{}` → request native generation cancellation |

Stream events are `start`, `token` with `text`, `done` with a `profile` and
`cancelled` flag, or `error`. A closed stream without `done` is an interrupted
response, not success. Profiles contain SDK-reported first-token latency,
generation rate, and generated token count. Requested backend is distinct from
evidence of actual hardware offload.

The client serializes model load/unload, commit, delete, and inference. Android
native calls are kept off the main thread. Chat templates come from the model,
and full conversation history is submitted on each request with model state reset.
The host preserves partial responses when a stream fails. Phone models stay cached
across disconnects; partial files are never listed as loadable models.

Error responses use `{error: "explanation"}` and a non-2xx status. They close their
HTTP connection so rejected/unconsumed bodies cannot affect the next request.
Input limits include 256 KiB JSON bodies, 4 MiB upload chunks, and 16 GiB model
files. IDs must be lowercase SHA-256 hex; supplied names never determine paths.

The v0.2 status response adds `context_size`, the loaded token context, so the
host can bound document excerpts and reserve generation space. Attachments are
extracted on the PC and transmitted as text in the existing chat messages.
Hugging Face tokens and account APIs are exclusively host-side.

The v0.4 telemetry response has `schema: 1`, `uptime_ms`, `state`, `model`,
`requested_backend`, a generation sequence, `generating`, cumulative
`stream_events`, two-second `stream_rate`, `rate_basis`, `first_token_ms`,
`last_profile`, `battery_percent`, `battery_c`, `plugged`, RAM total/available
bytes, app PSS bytes/sample uptime, and Android thermal severity. Missing API
readings are JSON null. Stream events are SDK text callbacks, not verified token
IDs. Model load/unload clears the previous completion profile. CPU counters,
KGSL availability and current thermal-HAL sensors are collected separately using
constant read-only ADB commands; they are not supplied by this endpoint.

## Media extension (0.6 alpha)

All `/v1/media` routes require the same paired Bearer session token as text routes.

- `GET /media`: native-runtime availability, backends `cpu`/`npu`, media library and job.
- `POST /media/uploads`: `{id: sha256, name, size, format}` (`gguf`/`safetensors`/`qnn`/`data`),
  returns `{complete, offset}`. `PUT /media/uploads/:id` appends at `X-Offset` with
  a bounded Content-Length. `POST /media/commit` verifies full size/hash and format.
- `POST /media/bundles`: registers a Neodragon bundle from verified `data` IDs
  and allowlisted component paths. QNN image ZIPs are validated and extracted
  during commit. Model paths remain private to the client.
- `POST /media/images`: authenticated PNG/JPEG image body (at most 16 MiB and
  2048 pixels per side), re-encoded to a private PNG; returns an input result reference.
- `POST /media/generate`: kind, model_id, prompt, negative, width, height, steps,
  seed, cfg, backend. Video also takes vae_id, encoder_id, optional vision_id,
  frames and fps. Optional init_result references a generated PNG owned by the
  phone, including an image uploaded through `/media/images`. Image `operation` is
  `generate`, `expand` or `upscale`; `strength` controls img2img generation.
  Upscale uses a QuickSRNet `data` model or the graph in a Neodragon bundle.
  Filenames/CLI commands are never accepted from the host.
- `GET /media/job`: job id and `running`, `complete`, `failed` or `cancelled`; a
  bounded native log accompanies state. Complete includes result, size and sha256.
- `POST /media/cancel`: stops the native process, forcibly after a grace period.
- `GET /media/results/:name`: authenticated PNG/AVI/MP4 stream; host verifies size/hash.

Media claims the same busy guard as text inference and unloads the text model
before spawning diffusion. No simultaneous LLM/diffusion run is admitted. Process
output is bounded; a 30-minute watchdog cancels runaway generation. Uploads persist
for resume; job state is session-local, with outputs retained in private app storage.
