# Security Policy

**Document ID**: `CALAMUM_SECURITY_POLICY_20260324`  
**Status**: Public security policy  
**Owner**: ORACL-Prime  
**Project**: Calamum Moltbook Observer  
**Last updated**: 2026-03-24

This document defines the public security posture for Calamum Moltbook Observer.

The short version remains simple:

- treat the upstream environment as hostile,
- minimize persistence,
- preserve names-only evidence,
- fail closed when a required control is missing or invalid.

Calamum is built for hostile-input observation under names-only retention, guarded posture control, and independent fail-closed enforcement. The project’s security model treats containment, baseline monitoring, and evidence discipline as part of the trust contract, not as optional operational garnish.

## Purpose and scope

This policy covers:

- data-handling doctrine,
- containment and posture principles,
- secret-handling expectations,
- public/private evidence boundaries,
- vulnerability-reporting expectations.

For the architectural runtime model behind those principles, see [`docs/manuals/OBSERVER_SECURITY_MODEL_20260324.md`](docs/manuals/OBSERVER_SECURITY_MODEL_20260324.md).

## Supported Versions

| Version | Supported | Notes |
| ------- | ------------------ | ------------------------------------------------ |
| 1.0.x   | :white_check_mark: | Current supported public release line |
| 0.9.x   | :x: | Unsupported |

## Security principles

The project is built around a few non-negotiable principles:

1. **No raw content persistence by default**  
	The tracked/public workflow is designed around names-only, schema-bound telemetry rather than raw platform payloads.

2. **Fail closed, not hopefully**  
	If a required control, credential, posture, or validation surface is missing, the preferred outcome is denial or termination rather than a "best effort" continuation.

3. **Containment is part of the architecture**  
	Runtime isolation, watchdog enforcement, and local-only evidence retention are treated as first-class design constraints.

4. **Secrets stay off the public surface**  
	Credentials are expected via environment variables and operator-local secret handling. They are never part of tracked examples, public docs, or committed runtime artifacts.

5. **Operational residue stays local when it should**  
	The public repository is intentionally slimmer than the full local working environment. High-detail logs, local governance traces, and operator evidence remain outside the public tracked surface.

## Public security contract

For the public observer surface, the security contract is:

- tracked workflows remain names-only,
- runtime/evidence outputs must not expose secrets or raw payloads,
- posture changes and gate-clearing evidence must remain fail-closed,
- public docs may describe contracts and paths, but must not treat local evidence as public artifact,
- observer-scoped gate/evidence outputs are expected to carry run-linkage fields when the contract requires them:
	- `run_id`
	- `posture_trigger_id`
	- `posture_trigger`
	- `security_report_ref`

## Operational security model

The observer’s operating model combines four visible security ideas:

- **posture control** so higher-risk modes operate under stricter conditions,
- **watchdog enforcement** so stale or broken runtime state fails closed,
- **baseline monitoring** so readiness depends on current evidence rather than assumed health,
- **evidence discipline** so the system remains inspectable without normalizing unsafe retention.

Public posture model:

| Mode | Trigger posture |
|---|---|
| `watch` | `isolation` |
| `canary` | `isolation` |
| `live` | `lockdown` |
| `honeypot` | `lockdown` |

The deeper architecture for these controls is documented in [`docs/manuals/OBSERVER_SECURITY_MODEL_20260324.md`](docs/manuals/OBSERVER_SECURITY_MODEL_20260324.md), and the command-level transition contract is documented in [`docs/manuals/OBSERVERCTL_MODE_TRANSITION_MATRIX_20260221.md`](docs/manuals/OBSERVERCTL_MODE_TRANSITION_MATRIX_20260221.md).

## What we actively defend against

This project is primarily concerned with the following classes of failure:

- raw content or PII leaking into persisted artifacts
- credential exposure through docs, logs, CLI output, or tracked files
- silent weakening of containment or watchdog controls
- runtime drift that makes a healthy-looking system untrustworthy
- audit/debug tooling becoming a covert data-retention path

## Threat model (scope)

We consider the **input data stream** to be hostile by default. The project therefore emphasizes strict reduction of payloads into safer telemetry before persistence.

Operationally:

- the upstream network/content surface is treated as untrusted
- the runtime boundary is treated as a containment boundary, not just a convenience wrapper
- watchdog and posture controls exist to prevent quiet degradation into an unsafe state

## Names-only doctrine

The observer’s default security stance is that persistence must remain names-only.

That means public/tracked workflows should persist structural metadata such as:

- event class,
- lengths/counts,
- hashes,
- posture/readiness state,
- evidence paths and packet linkage.

They should not persist raw message or body content as part of the normal contract.

## Reporting a Vulnerability ("The Fail-Closed Pact")

**CRITICAL**: This software contains containment measures ("Glass Box" isolation and watchdog fail-closed enforcement) designed to prevent malware escape.

If you discover a vulnerability that allows:
1. The container to write to the host filesystem.
2. The agent to bypass the `obfuscator_lib` and leak raw PII.
3. The watchdog enforcement layer to be disabled silently.
4. Credentials or high-risk runtime data to be emitted into tracked or public-facing artifacts.

Please report it immediately to the project lead (Repo Owner) via private channels.

**DO NOT** create a public GitHub issue for containment breaches.

When reporting, useful details include:

- affected version / branch / commit if known
- precise reproduction steps
- whether the issue breaks confidentiality, integrity, containment, or fail-closed behavior
- whether the issue is observable only locally or also through the public repo surface

## Security controls

These controls define how the project maintains containment, evidence discipline, and fail-closed operation:

### Data minimization and obfuscation

- names-only telemetry is the default persistence model
- raw content is intentionally excluded from the normal tracked workflow
- schemas and validators exist to keep "helpful debugging extras" from quietly becoming data leaks

### Credential discipline

- environment variables are the expected credential surface
- presence checks are acceptable; value materialization in docs/logs is not
- public examples must use placeholders, never real secrets

### Runtime containment and posture control

- isolation and lockdown postures are part of the operational model
- watchdog enforcement surfaces, including `sentinel.py`, exist to detect invalid runtime state and force a stop when necessary
- live-lane actions are expected to deny when prerequisites are incomplete

### Public/private surface separation

- the public repository intentionally shows the method, implementation, and curated docs
- local runtime evidence, detailed audit trails, and operator-governance surfaces are retained outside the public tracked surface where appropriate

## Evidence boundary rule

Public documentation may reference canonical local runtime paths and evidence families, but those references are descriptive. They do not convert local runtime evidence into public tracked artifact.

This distinction matters because the project intentionally separates:

- public contract/manual surfaces,
- local runtime outputs,
- local governance and audit residue.

## Audit tooling safety controls

The Calamum audit tools are designed to be safe to run on developer machines and in demos. We put real effort into making the tooling itself less likely to become the problem.

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

The project keeps enough detail to support integrity review and change detection without turning routine operation into a content archive.

### Provenance and index

Audit tools append a small JSONL provenance record per run and update a central untracked index:

- JSONL: `projects/calamum-moltbook-observer/local_untracked/audit_log/*.jsonl`
- Index: `projects/calamum-moltbook-observer/local_untracked/audit_log/audit_index.json`

## Security expectations for contributors

If you contribute to this project, please assume the following baseline:

- do not add raw-content persistence to tracked workflows
- do not print secrets, tokens, or credential values
- do not weaken fail-closed behavior for convenience
- do not move operator-local evidence surfaces into the public repo without a strong, reviewed reason
- do not open public issues for containment-break vulnerabilities

If a proposed change makes the system easier to demo but harder to trust, it is probably the wrong trade.

## Related surfaces

- [`README.md`](README.md)
- [`DATA_METHODOLOGY.md`](DATA_METHODOLOGY.md)
- [`docs/manuals/OBSERVER_SECURITY_MODEL_20260324.md`](docs/manuals/OBSERVER_SECURITY_MODEL_20260324.md)
- [`docs/manuals/OBSERVERCTL_MODE_TRANSITION_MATRIX_20260221.md`](docs/manuals/OBSERVERCTL_MODE_TRANSITION_MATRIX_20260221.md)
