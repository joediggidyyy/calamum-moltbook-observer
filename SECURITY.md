# Security Policy

**Document ID**: `CALAMUM_SECURITY_POLICY_20260324`  
**Status**: Public security policy  
**Owner**: ORACL-Prime  
**Project**: Calamum Moltbook Observer  
**Version**: `1.0.1`  
**Last updated**: 2026-04-17

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

For the architectural runtime model behind those principles, see [`docs/manuals/reference/SECURITY_MODEL.md`](docs/manuals/reference/SECURITY_MODEL.md).

## Supported Versions

| Version | Supported          | Notes                                 |
| ------- | ------------------ | ------------------------------------- |
| 1.0.1   | :white_check_mark: | Current supported public release      |

## Security at a glance

| Control family | Public contract | Security effect |
| -------------- | --------------- | --------------- |
| Names-only persistence | Normal retained workflows store structural telemetry and linkage metadata instead of raw Moltbook content | narrows retained-data exposure while preserving reproducible evidence |
| Posture control | `watch` and `canary` stay in isolation; `live` and `honeypot` escalate into lockdown | higher-risk moves face stricter gating and stronger prerequisites |
| Baseline monitoring | readiness depends on current baseline and dependency evidence | stale or incoherent systems deny instead of drifting forward |
| Watchdog enforcement | an independent supervisory layer can deny or stop invalid runtime state | fail-closed behavior does not depend on presentation layers staying truthful |
| Evidence-linked operations | gate and transition outputs remain names-only and run-linked | state changes stay reviewable without normalizing unsafe retention |
| Public/local surface split | public docs and derived reports stay separate from local machine-readable authority | publication remains reader-facing while operational residue stays local |


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

6. **Public repo visibility and package inclusion are separate**  
	Tracked repo surfaces, public documentation, and installable package payloads are related but independently governed. Shipped-package contents must be explicitly declared rather than inferred from the full repo tree.

## Public security contract

For the public observer surface, the security contract is:

- tracked workflows remain names-only,
- runtime/evidence outputs must not expose secrets or raw payloads,
- posture changes and gate-clearing evidence must remain fail-closed,
- public repo visibility does not by itself imply shipped-package inclusion; package payloads must be explicitly declared in the packaging manifests,
- tracked report publication under `docs/reports/` must remain human-facing and derived from canonical local run data rather than becoming a second machine-readable authority surface,
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

| Mode       | Trigger posture |
| ---------- | --------------- |
| `watch`    | `isolation`     |
| `canary`   | `isolation`     |
| `live`     | `lockdown`      |
| `honeypot` | `lockdown`      |

Security authority is explicit:

- dashboards summarize state,
- the runtime CLI, watchdog, and retained packets enforce state.

Security consequences are explicit as well:

- requests targeting `live` or `honeypot` are stricter paths,
- source escalation from `sim` to `real` is a stricter path,
- readiness, baseline sufficiency, and required dependency presence are security preconditions rather than optional setup steps.

Higher-risk moves are expected to prove the following before admission:

| Precondition | Why it matters |
| ------------ | -------------- |
| heartbeat freshness and posture coherence | prevents stale runtime state from presenting as trustworthy |
| baseline sufficiency | ties escalation to current operating evidence rather than hopeful assumptions |
| required dependency presence | keeps real-source and lockdown paths bound to the surfaces they actually need |
| run-linkage and gate evidence | preserves reviewable transition history after the fact |

The deeper architecture for these controls is documented in [`docs/manuals/reference/SECURITY_MODEL.md`](docs/manuals/reference/SECURITY_MODEL.md), and the command-level transition contract is documented in [`docs/manuals/reference/RUNTIME_TRANSITIONS.md`](docs/manuals/reference/RUNTIME_TRANSITIONS.md).

## Operator expectations

When a control denies an action, treat that denial as evidence that the safety model is working.

| Expectation | Meaning in practice |
| ----------- | ------------------- |
| Honor denied gates | resolve the blocking condition or obtain explicit approval before retrying |
| Keep evidence local and linked | stricter-lane work should preserve names-only linkage without promoting local residue into the public surface |
| Follow runtime authority order | when views disagree, the CLI, watchdog, and retained packets outrank presentation surfaces |
| Treat lockdown as intentionally stricter | `live` and `honeypot` are governed escalations, not ordinary mode toggles |

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

**CRITICAL**: This software contains containment measures ("Glass Box" isolation, read-only runtime containment, and watchdog fail-closed enforcement) designed to reduce containment-breach risk and stop unsafe execution when core assumptions fail.

If you discover a vulnerability that allows:
1. The container or runtime to write outside the intended mounted output boundary or otherwise bypass the read-only containment model.
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

### Security-adjacent transaction proof

- non-dry-run KEYSMITH mint is expected to remain sandbox-contained
- sandbox proof should stay version-matched and build-attested when it is used for promotion review

### Runtime containment and posture control

- isolation and lockdown postures are part of the operational model
- watchdog enforcement exists to detect invalid runtime state and force a stop when necessary
- real-source escalation and lockdown-lane actions are expected to deny when prerequisites are incomplete
- readiness, baseline sufficiency, and required dependency presence are treated as security preconditions

### Public/private surface separation

- the public repository intentionally shows the method, implementation, and curated docs
- the public repo surface and the installable package surface are separate release boundaries; packaged scope is defined explicitly rather than inferred from repo visibility
- local runtime evidence, detailed audit trails, and operator-governance surfaces are retained outside the public tracked surface where appropriate
- public report packets under `docs/reports/` are derived, reader-facing artifacts that reference local machine-readable evidence rather than replacing it

## Public report publication boundary

The current report lane is part of the public presentation surface, but it follows a strict boundary:

- collection packets are routed by collection alias under `docs/reports/collections/<collection-alias>/`
- dated stage packets live under the `build`, `train`, `evaluate`, and `score` processing leaves
- published figures must remain names-only and tied to the same packet lineage as their companion report surfaces
- canonical machine-readable authority remains under the local analysis indexes and manifests, not inside `docs/reports/`

## Security surfaces and authority

| Surface family | Public role | Security meaning |
| -------------- | ----------- | ---------------- |
| Root docs and manuals | public contract, routing, and interpretation | explain the rules without becoming runtime evidence |
| `docs/reports/` publication views | human-facing derived publication | rebuild from canonical local artifacts and stay secondary to machine-readable authority |
| local runtime outputs, manifests, indexes, and audit traces | operator-local execution evidence | carry the canonical machine-readable authority for execution, lineage, and review |

Public documentation may reference canonical local runtime paths and evidence families, but those references remain descriptive rather than promoting local execution residue into a tracked public artifact.

## Audit tooling safety controls

The Calamum audit tools are designed to be safe to run on developer machines and in demos.

Their public security contract is:

- audit outputs remain local and untracked rather than becoming public runtime residue
- audit modes support non-destructive evaluation when appropriate
- network-restricted audit execution is available when active probing is not appropriate
- audit evidence remains names-only and provenance-linked

The goal is to preserve integrity review and change detection without turning routine operation into a content archive.

## Security expectations for contributors

If you contribute to this project, please work from the following baseline:

| Contributor expectation | Why it matters |
| ---------------------- | -------------- |
| keep tracked workflows names-only | the project’s core trust boundary depends on structural telemetry instead of retained raw content |
| keep secrets in environment-injected or operator-local surfaces | public docs, logs, and tracked files are not credential surfaces |
| preserve fail-closed behavior | safety controls remain meaningful only when denial and stop paths survive pressure |
| keep operator-local evidence in operator-local lanes | public presentation should not absorb high-detail governance residue by accident |
| route containment-break reports through private disclosure | high-risk security issues need bounded handling rather than public issue traffic |

If a proposed change makes the system easier to demo but harder to trust, it is probably the wrong trade.

## Related surfaces

- [`README.md`](README.md)
- [`DATA_METHODOLOGY.md`](DATA_METHODOLOGY.md)
- [`docs/reports/INDEX.md`](docs/reports/INDEX.md)
- [`docs/reports/reference/GENERATED_REPORT_SURFACES.md`](docs/reports/reference/GENERATED_REPORT_SURFACES.md)
- [`docs/manuals/reference/SECURITY_MODEL.md`](docs/manuals/reference/SECURITY_MODEL.md)
- [`docs/manuals/reference/RUNTIME_TRANSITIONS.md`](docs/manuals/reference/RUNTIME_TRANSITIONS.md)
- [`docs/manuals/runtime/RUNTIME_WORKFLOWS.md`](docs/manuals/runtime/RUNTIME_WORKFLOWS.md)
- [`docs/manuals/runtime/RUNTIME_OPERATIONS.md`](docs/manuals/runtime/RUNTIME_OPERATIONS.md)
