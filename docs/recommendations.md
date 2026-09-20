# Model recommendations

Host 0.5 adds automatic search after a short typing pause, category discovery,
repository previews and ranked GGUF variants. The first result opens automatically.
Choose Everyday chat, Coding, Reasoning, Documents or Fast replies. A 2K/4K/8K
context selector changes the estimates; it does not load a model or change the
phone's current inference context. The existing pinned, SHA-256 verified download
and USB transfer flow is preserved.

Every result has an ordinal rank, suitability score, RAM fit, quantization,
estimated RAM and (when support can be estimated) a decoding tokens/s range.
File rows also show the actual download size. Hover for the calculation basis.
Account settings are collapsible; public search works without a token.

## Hardware and estimates

Only read-only ADB commands are used to identify the phone, SoC, total/available
RAM and free data-partition storage. No inference service is started, model
loaded, or benchmark launched. Hardware remains local; only search terms and
repository requests go to Hugging Face. A local hardware snapshot supports offline
browsing and is explicitly labelled Last detected phone. An explicitly selected
different device never inherits that snapshot. Refresh phone updates the snapshot.

SM8750 is the only calibrated chip. Unsupported/unknown chips get no speed range.
The estimate uses existing Xiaomi 15 Ultra / GenieX 0.7.0 results: Qwen3 0.6B Q4_0
around 69 tokens/s and Qwen3 1.7B Q4_0 around 34. For recognized dense models, the
base heuristic is `34 * (1.7 / parameters_in_billions)^0.70`, capped at 150.
Qwen3 Q4_0 gets a 70–130% range. Other recognized dense families/quants receive
much wider, lower-confidence ranges (15–90% before quantization adjustments).
Larger quantizations, long context and tight RAM reduce predictions. Unknown
architectures, hybrid/MoE models, unsupported files and models that exceed the
memory budget have no speed prediction. Their rows explicitly say uncalibrated.
These are decoding estimates, excluding prompt prefill, USB transfer and loading.
They are not fresh measurements or guarantees of native runtime support.

Memory uses actual file size where available, otherwise a parameter/quantization
preview. The lower bound is `1.05 * weights_GiB + 0.6 + 0.08 * B * context/2048`;
the upper bound is `1.25 * weights_GiB + 1 + 0.25 * B * context/2048`.
This is a coarse KV/workspace allowance, not architecture-specific tensor sizing.
The budget reserves max(3 GiB, 25% of total RAM) for Android and assumes the old
model is unloaded. It is a capacity estimate, not a promise about currently free
RAM. More running apps can reduce headroom. Expert models use total weights, not
only active parameters. Free storage can disqualify a file separately.

## Ranking

The score combines RAM fit (up to 40), category/name/tag signals (up to 30),
quantization/runtime familiarity (up to 18) and estimated responsiveness (up to 10).
Blocked, too-large, unknown-hardware and unfamiliar-architecture cases are capped.
The Recommended label requires a sufficient score, estimated RAM fit and a
recognized dense family. This is suitability for the selected use, not a model
quality, coding accuracy or safe tool-use benchmark. Downloads only break ties.

Blank searches discover a small set of relevant model families through live Hub
searches; typed searches use the top 30 Hub download-ranked matches. Local rankings
are limited to returned results, not the whole Hub. Search/file metadata is cached
in memory for five minutes, separately by account. Repository previews assume a
listed Q4_0 or Q4_K_M variant; selecting a repository refines estimates with actual
file metadata. GGUF metadata supplies parameter count, architecture and advertised
context when present; otherwise names/tags provide explicitly heuristic signals.
No remote model code or chat template is executed by recommendation code.

References: [Hugging Face Hub API](https://huggingface.co/docs/hub/api),
[GGUF metadata on the Hub](https://huggingface.co/docs/hub/gguf), and
[local hardware measurements](validation.md).
