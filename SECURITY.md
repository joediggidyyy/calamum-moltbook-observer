# Security Policy

## Supported Versions

| Version | Supported | Notes |
| ------- | ------------------ | ------------------------------------------------ |
| 1.0.x   | :white_check_mark: | Active Research Phase (Observer Mode) |
| 0.9.x   | :x: | Legacy Pre-release |

## Reporting a Vulnerability ("The Fail-Closed Pact")

**CRITICAL**: This software contains containment measures ("Glass Box", "Sentinel") designed to prevent malware escape.

If you discover a vulnerability that allows:
1. The container to write to the host filesystem.
2. The agent to bypass the `obfuscator_lib` and leak raw PII.
3. The sentinel to be disabled silently.

Please report it immediately to the project lead (Repo Owner) via private channels.

**DO NOT** create a public GitHub issue for containment breaches.

## Threat Model (Scope)
We consider the *input data stream* to be hostile (Toxic Waste). The security boundary is the **Container Runtime**. Anything inside the container is considered "Condemned Space".

## Audit tooling safety controls

The Calamum audit tools are designed to be safe to run on developer machines and in demos:

### Output isolation (untracked)

All runtime audit outputs are written under the project-local ignored subtree:

- `projects/calamum-moltbook-observer/local_untracked/`

This includes rendered reports, JSON evidence bundles, and the append-only JSONL provenance logs.

### Dry-run support

Audit tools support `--dry-run` to compute findings and print would-be output paths without writing any files.

### Network restrictions

The GUI audit tool supports `--no-network` to guarantee no HTTP requests (and no TCP probes) are performed during the audit run. Evidence records the checks as skipped.

### Evidence minimization

Audit evidence is names-only by default and avoids storing sensitive payloads:

- GUI audit evidence does not persist raw HTTP bodies. It records status, content type (when known), body length, and a SHA-256 hash.
- Runtime artifacts audit does not embed raw service log tails. It records file stats and a SHA-256 hash over up to the last 64 KiB of each file for change detection.

### Provenance and index

Audit tools append a small JSONL provenance record per run and update a central untracked index:

- JSONL: `projects/calamum-moltbook-observer/local_untracked/audit_log/*.jsonl`
- Index: `projects/calamum-moltbook-observer/local_untracked/audit_log/audit_index.json`
