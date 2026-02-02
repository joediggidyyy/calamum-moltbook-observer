# Job: CALAMUM_JOB_0003 - Moltbook Observer - Stage 2: Container Hardening

## Metadata

- Template ID: `VAULT_TEMPLATE_JOB_V1`
- Paired authoritative template: `JOB_TEMPLATE.json.template`
- Status: `open`
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
STATUS_UPDATE_V1
job.id=calamum-moltbook-observer-stage2-20260201
job.doc=CodeSentinel/projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0003_MOLTBOOK_OBSERVER_STAGE2_CONTAINER_HARDENING_20260201.md
ssot.path=CodeSentinel/operations/tasks.json
ssot.status=open
qs.id=
qs.doc=
qf.id=
gates.last=NONE@::SKIP
evidence.gates=CodeSentinel/logs/behavioral/gates/gate_events.jsonl
evidence.qs=
next.action=Define Dockerfile/Containerfile with read-only rootfs and run profile.
```

## Problem statement

**Current state**:
- Sampler runs on host processing surface, relying on process-level discipline.

**Root cause**:
- Lack of isolation boundary.

**Impact**:
- If the python runtime is compromised by a buffer overflow or logic bug in the feed parser, the host is exposed.

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
