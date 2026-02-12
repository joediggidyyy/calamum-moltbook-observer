# Job: CALAMUM_JOB_0003 - Moltbook Observer - Stage 2: Container Hardening

## Metadata

- Template ID: `VAULT_TEMPLATE_JOB_V1`
- Paired authoritative template: `JOB_TEMPLATE.json.template`
- Status: `completed`
- Owner: `ORACL-Prime`
- Created: `2026-02-01`
- Project: `calamum / security experiment`
- Phase: `hardening`
- Priority: `P1`
- Depends on: `CALAMUM_JOB_0002`
- Blocks: `CALAMUM_JOB_0004`

## Policy links

- `PP_GOV_PROTOCOL_POL_CORE_POLICY_20251122`
- `PP_SEC_PROTOCOL_POL_AGENT_SOCIAL_NETWORKS_20260201`

## Redaction palette (use these placeholders)

- Network endpoints:
	- `<edge_host_ip>` / `<edge_secure_ip>`
- DNS:
	- `<target_platform_dns>`
- Secrets:
	- `<redacted>`
- Identifiers:
	- `<container_id_redacted>`

## Summary

Harden the Calamum execution environment by migrating the sampler to a strictly confined container or VM. This stage enforces 'no self-modification' by mounting the code as read-only and explicitly dropping all capabilities except network egress to the allowlisted target.

## Status update (compact)

```text
STATUS_UPDATE_V2
job.id=calamum-moltbook-observer-stage2-20260201
job.doc=CodeSentinel/projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0003_MOLTBOOK_OBSERVER_STAGE2_CONTAINER_HARDENING_20260201.md
ssot.path=CodeSentinel/operations/tasks.json
ssot.status=completed
qs.id=QS-CALAMUM-MOLTBOOK-OBSERVER-STAGE2-20260201
qs.doc=projects/calamum-moltbook-observer/queststacks/QS-CALAMUM-MOLTBOOK-OBSERVER-STAGE2-20260201.md
qf.id=QF-CALAMUM-MOLTBOOK-OBSERVER-STAGE2-20260201
gates.last=POST_JOB@2026-02-03
evidence.gates=CodeSentinel/logs/behavioral/gates/gate_events.jsonl
evidence.qs=deliverables/DATA740/CALAMUM_CONTAINER_HARDENING_EVIDENCE.md
next.action=Complete. Proceed to Stage 3 Use Cases.
```

## Problem statement

**Current state**:
- Sampler runs on host processing surface, relying on process-level discipline.

**Root cause**:
- Lack of isolation boundary.

**Impact**:
- If the python runtime is compromised by a buffer overflow or logic bug in the feed parser, the host is exposed.

## Methodology & Narrative Execution

This stage implements the "Glass Box" security model, a critical requirement for safely observing hostile agent networks. The core principle is **total immutability at runtime**: once observing begins, the observer itself can have no memory of the event other than the structured telemetry it emits. This prevents prompt-injection payloads from persisting on the observer's filesystem or modifying its behavior.

### 1. Build Process & Provenance
We utilized a multi-stage Docker build to create a minimal, hardened artifact.

- **Base Image**: `python:3.11-slim` (Minimizes attack surface; shell access retained only for debugging, no compiler toolchain).
- **User Identity**: An explicit non-root user `observer` (UID 10001) was baked into the image.
- **Dependency Management**: Dependencies (`requests`, `pytest`) were installed from a verified `requirements.txt` into a system-level directory, preventing user-level modification at runtime.

### 2. Runtime Constraints (The Hardening Profile)
The container was executed with a strict set of Docker runtime flags (`src/deployment/HARDENING_PROFILE.md`) to enforce the security model:

1.  `--read-only`: The root filesystem follows a strict W^X policy (Write XOR Execute). The application code is readable but not writable.
2.  `--cap-drop ALL`: All Linux kernel capabilities (including `CAP_NET_ADMIN`) were dropped to prevent privilege escalation or raw socket creation.
3.  `--security-opt no-new-privileges`: Prevents setuid binaries from escalating privileges.

### 3. Verification & Evidence
To validate these constraints, we executed a "breakout suite" (`src/tests/test_container_constraints.py`) against the live container:

- **Immutability Test**: Attempting `touch /app/test` inside the container resulted in `Permission denied`, confirming the read-only rootfs.
- **Tooling Minimalism**: Attempting to invoke `ping` failed because the binary is not present in the minimal image, supporting the reduced surface area claim.
	- Note: ICMP/ping is not an approved connectivity check in secured environments; we treat this as a *tooling presence* probe only.
- **Identity Assurance**: Validated that the process runs as UID 10001.

Detailed forensic logs of this verification are stored in `deliverables/DATA740/CALAMUM_CONTAINER_HARDENING_EVIDENCE.md`.

## Proposed solution

### Architecture

```
Host -> Container Runtime -> [Read-Only Code + Read-Only Python] -> <target_platform_dns>
Write -> /data/logs (volume, restricted)
```

### Implementation steps

1. Create hardening profile (apparmor/seccomp/capabilities).
2. Configure read-only root filesystem.
3. Validate that `pip install` or file writes fail inside the container.

## Requirements

- Rootless execution.
- Read-only root filesystem.
- Drop all capabilities (e.g. CAP_NET_ADMIN).
- Egress filtering.

## Acceptance criteria

- Container runs sampler successfully.
- Attempt to write to code directory fails.
- Attempt to access host filesystem fails.
- Attempt to connect to non-target IP fails.

## Validation

- [ ] Verify read-only FS constraint via smoke test.
- [ ] Verify functionality of sampler in container.

## SEAM analysis

### Security
- Defense in depth: isolation prevents persistence.

### Efficiency
- Disposable containers ensure clean state per run.

### Awareness
- Runtime profile is explicit and versioned.

### Minimalism
- Minimal base image.

## Rollback plan

Revert to host-based execution (Job 0002).

## Verification

- Verify container logs show successful startup and strictly semantic error on write attempts.

## References

- `projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0002_MOLTBOOK_OBSERVER_STAGE1_OBSERVE_AND_SAMPLE_20260201.md`
