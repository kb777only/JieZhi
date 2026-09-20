# Contributing to JieZhi

JieZhi is an early hardware-specific alpha. Reproducible reports are especially
valuable: include the Linux distribution, phone model, SoC, Android version,
model repository/file, quantization, requested backend, and relevant diagnostics.
Remove device serials, tokens, usernames, document contents, and other private
data before posting logs.

## Development

```sh
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
QT_QPA_PLATFORM=offscreen .venv/bin/pytest
sh scripts/build-android.sh
```

Keep host policy enforcement independent of model output. New PC actions must be
bounded, auditable, covered by tests, and denied by default outside explicit user
scope. Never weaken pairing, upload integrity, path validation, or approval gates
to make a demonstration pass.

Before opening a pull request, run `sh scripts/release-check.sh`, update user-facing
documentation for behavior changes, and state which checks were run. Do not commit
models, SDKs, APKs, installers, caches, device logs, credentials, or private test
documents. By contributing, you confirm you have the right to submit the change.

No project-level open-source license has been selected yet. Discuss substantial
external contributions in an issue before investing significant work.
