# Security policy

## Supported version

Only the latest tagged alpha is maintained. JieZhi is evaluation software, not a
hardened production security boundary.

## Reporting a vulnerability

Do not open a public issue for an exploitable vulnerability, leaked credential,
pairing bypass, path escape, unsafe command execution, or malicious-model finding.
Use GitHub's **Security → Report a vulnerability** private reporting flow. Include
the affected version, impact, minimal reproduction, and suggested remediation if
known. Do not include real tokens, documents, or device identifiers.

## Trust boundaries

- The Android bridge binds to loopback and authenticated endpoints require a
  random session token obtained through a one-time code shown on the phone.
- Model and attachment contents are untrusted. Checksums prove transfer integrity,
  not that a model or file is safe or accurate.
- PC Assistant commands can affect the whole user account and are not sandboxed to
  linked folders. The exact command always requires approval.
- Scoped file edits enforce ownership, path, link, size, prior-read, hash, and
  atomic-replacement checks. Review every proposed diff and command.
- Hugging Face tokens stay on the host and are persisted only through the system
  keyring when explicitly requested.
