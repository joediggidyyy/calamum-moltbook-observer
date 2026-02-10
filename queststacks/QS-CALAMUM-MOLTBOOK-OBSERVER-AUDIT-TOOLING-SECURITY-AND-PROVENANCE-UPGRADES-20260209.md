# QuestStack: QS-CALAMUM-MOLTBOOK-OBSERVER-AUDIT-TOOLING-SECURITY-AND-PROVENANCE-UPGRADES-20260209

**Title**: Moltbook Observer - Audit Tooling Security + Provenance Upgrades (Job 0010)

**Owner**: ORACL-Prime

**Primary stakeholder**: joediggidyyy

**Date**: 2026-02-09

**Status**: COMPLETED

---

## Context

Calamum audit tooling is already useful for a school-demo workflow, but it needs consistency and safety controls to match CodeSentinel repo standards.

This QuestStack standardizes the audit tools so that:

- audits are template-driven for offline reports
- outputs are isolated to `local_untracked/` (ignored)
- `--dry-run` is supported everywhere
- GUI/network checks are explicitly gated (`--no-network`)
- provenance is preserved via append-only JSONL logs (untracked)

---

## SEAM hard rules (non-negotiable)

- **Security**: names-only evidence; no secrets, tokens, hostnames, or raw Moltbook content.
- **Efficiency**: minimal diffs; shared helpers in `projects/calamum-moltbook-observer/src/ops/` when practical.
- **Awareness**: record gate + SessionMemory evidence paths; keep provenance pointers current.
- **Minimalism**: keep tracked artifacts small; all runtime outputs go to ignored paths.

ICMP is assumed unavailable; do not use ping.

---

## SessionMemory snapshot ingestion (SSOT pointers)

The following artifacts are treated as evidence inputs for deterministic execution alignment:

- Policy snapshot (machine): `.agent_session/policy_snapshot.json`
- Policy snapshot (markdown): `.agent_session/policy_snapshot.md`
- Ops-awareness (machine): `.agent_session/ops_awareness.json`
- Ops-awareness (markdown): `.agent_session/ops_awareness.md`

---

## Execution checklist (paperwork-first)

- [ ] Confirm gate evidence paths are available: `logs/behavioral/gates/gate_events.jsonl`.
- [ ] Confirm SessionMemory snapshots are present and fresh (policy + ops-awareness).
- [ ] Confirm Job 0010 stub doc exists under the `jobs` directory (PRE_JOB gate requirement).
- [ ] Confirm project Job 0010 SSOT doc exists under `projects/calamum-moltbook-observer/jobs`.

---

## Artifacts

- QuestFrame Spec: `projects/calamum-moltbook-observer/questframes/QF-CALAMUM-MOLTBOOK-OBSERVER-AUDIT-TOOLING-SECURITY-AND-PROVENANCE-UPGRADES-20260209.json`

### Job doc

- Job doc (names-only, PRE_JOB): `jobs/CALAMUM_JOB_0010_AUDIT_TOOLING_SECURITY_AND_PROVENANCE_UPGRADES_20260209.md`
- Job doc (project SSOT, Markdown): `projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0010_AUDIT_TOOLING_SECURITY_AND_PROVENANCE_UPGRADES_20260209.md`
- Job doc (project SSOT, JSON): `projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0010_AUDIT_TOOLING_SECURITY_AND_PROVENANCE_UPGRADES_20260209.json`

### Job report

- `docs/reports/operations/JOB_REPORT_QS-CALAMUM-MOLTBOOK-OBSERVER-AUDIT-TOOLING-SECURITY-AND-PROVENANCE-UPGRADES-20260209.md`

---

## Evidence pointers

- Gate evidence (canonical): `logs/behavioral/gates/gate_events.jsonl`
- QuestStack log: `logs/queststack/QS-CALAMUM-MOLTBOOK-OBSERVER-AUDIT-TOOLING-SECURITY-AND-PROVENANCE-UPGRADES-20260209_log.md`
- QuestStack evidence: `logs/queststack/QS-CALAMUM-MOLTBOOK-OBSERVER-AUDIT-TOOLING-SECURITY-AND-PROVENANCE-UPGRADES-20260209_evidence.jsonl`
