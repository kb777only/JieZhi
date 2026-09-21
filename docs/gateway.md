# Third-party endpoint

JieZhi serves an OpenAI-compatible API on the desktop, so any workspace that
accepts a custom base URL — Open WebUI, Jan, AnythingLLM, Continue, Cline,
LibreChat — can send work to the phone's NPU without knowing a phone exists.

```
pip install -e .        # or use the packaged desktop build
jiezhi-gateway
```

It prints the base URL and the models it found:

```
JieZhi is serving Xiaomi 15 Ultra (Snapdragon 8 Elite) at http://127.0.0.1:11435/v1
  qwen3-1.7b-q4_0
  qwen3-1.7b-q4_0@xiaomi-15-ultra
```

The server starts whether or not a phone is attached, so an app can be pointed
at it and its connection verified before the phone is plugged in. A phone that
is already paired with this host is picked up within a few seconds of being
attached; pairing itself still happens in the desktop app, because it needs the
code shown on the phone's screen. Port 11435 sits beside Ollama's 11434 rather
than on top of it.

## Why an endpoint rather than an accelerator backend

An ONNX Runtime execution provider, an OpenCL device or a Vulkan device is a
per-operator interface: every node of every layer would become a round trip
over the USB link, which `validation.md` measures at 480 Mb/s. Generation would
collapse from the measured 33.9 tok/s to unusable. One prompt down and a token
stream back is the granularity this cable supports, and it is the granularity
third-party apps already speak.

## Endpoints

| Method | Path | Behavior |
| --- | --- | --- |
| GET | `/v1/models` | Every model on every connected phone |
| GET | `/v1/models/ID` | One model, with the phone holding it |
| POST | `/v1/chat/completions` | Chat, streamed with `"stream": true` or returned whole |
| POST | `/v1/completions` | Legacy prompt completion, for older clients |
| POST | `/v1/embeddings` | 501; the phone runtime generates text only |
| GET | `/health` | Connected phones, for a quick check that it is up |

Streaming is server-sent events in OpenAI's chunk format, ending with
`data: [DONE]`. If the app hangs up mid-answer the phone is told to cancel,
rather than generating into a closed socket.

## Model names

A model is named after its file, lowercased: `Qwen3-1.7B-Q4_0.gguf` becomes
`qwen3-1.7b-q4_0`. Every model also gets a qualified `name@device` id, which
stays stable when a second phone arrives; the bare name is offered only while
one phone holds a file by that name. Pin the qualified id in an app's config if
you expect to connect more phones.

The phone caps a request at 2048 generated tokens and 100 messages. A larger
`max_tokens` is clamped rather than refused, so an app whose default is higher
still works; more than 100 messages is refused here with a clear reason instead
of failing inside the Android bridge.

The phone holds one model at a time. When an app asks for a model that is not
loaded, the gateway loads it first — a swap costs the load time, so an app
switching between two models on one phone will feel it.

## Concurrency

One phone runs one generation at a time, so requests for the same phone queue
behind each other. A request that waits longer than two minutes for its turn
gets `503` with a message naming the phone, rather than timing out silently.

When there is more than one phone, this is where the aggregated "JieZhi - Max"
model will sit: one name in the app's model list, with the router choosing
which phone answers.

## When an app cannot connect

`GET /health` answers without a phone and says what is wrong:

```
curl http://127.0.0.1:11435/health
{"service":"jiezhi","object":"health","devices":[],"ready":false,
 "trouble":"Xiaomi 15 Ultra is attached but not paired with this host."}
```

- **The app reports a network error.** Nothing is listening where it looked.
  Check the gateway is still running and on the port you expect
  (`curl http://127.0.0.1:11435/health`, or `ss -ltn | grep 11435`).
- **The app runs in a container.** Open WebUI's Docker image is the common
  case: inside the container `127.0.0.1` is the container, not your desktop, so
  the gateway is unreachable no matter what. Either run the container with
  `--network=host` and keep `http://127.0.0.1:11435/v1`, or serve wider with
  `jiezhi-gateway --host 0.0.0.0 --api-key SOMEKEY` and point the app at
  `http://host.docker.internal:11435/v1` with that key. The same applies to any
  other app in a container, and to Ollama entries that already work or do not.
- **`ready` is false and `trouble` is empty.** No phone is attached. Plug it in;
  the model list fills within a few seconds.
- **`trouble` mentions pairing.** Open the desktop app and pair the phone once.
- **`trouble` mentions ADB.** The bundled `adb` is not on the path. Install or
  reinstall the desktop package.
- **`/v1/models` returns an empty list with `ready` true.** The phone is
  connected but holds no models. Import one in the desktop app.

## Security

The server binds `127.0.0.1` and refuses a request whose `Host` header is not
loopback, which defeats DNS rebinding from a web page the user happens to be
visiting. It never sends CORS headers, and it requires a JSON content type, so
a cross-origin page cannot reach it with a simple request either.

`--api-key KEY` makes the gateway require that key as a bearer token; apps that
insist on a key being filled in can otherwise send anything.

`--host` binds elsewhere, which is what a containerised app needs, and it
requires `--api-key` — without one the gateway refuses to start rather than put
the phone on the network unauthenticated. The loopback `Host` check applies only
while bound to loopback; once you have deliberately bound wider, the name the
app uses to reach you is the point of doing so.

Usage figures report generated tokens only. The phone runtime does not count
prompt tokens, so `prompt_tokens` is reported as 0 rather than guessed.
