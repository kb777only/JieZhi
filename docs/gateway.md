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

Pair the phone in the desktop app once first; the gateway reuses the stored
pairing token. Port 11435 sits beside Ollama's 11434 rather than on top of it.

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

## Security

The server binds `127.0.0.1` and refuses a request whose `Host` header is not
loopback, which defeats DNS rebinding from a web page the user happens to be
visiting. It never sends CORS headers, and it requires a JSON content type, so
a cross-origin page cannot reach it with a simple request either.

`--api-key KEY` makes the gateway require that key as a bearer token; apps that
insist on a key being filled in can otherwise send anything. `--host` will bind
elsewhere, but exposing the phone to a network is not the default and should be
paired with an API key.

Usage figures report generated tokens only. The phone runtime does not count
prompt tokens, so `prompt_tokens` is reported as 0 rather than guessed.
