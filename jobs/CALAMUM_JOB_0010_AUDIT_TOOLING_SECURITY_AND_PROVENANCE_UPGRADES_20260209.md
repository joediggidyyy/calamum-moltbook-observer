# JOB: Calamum/Moltbook Observer - Audit Tooling Security + Provenance Upgrades

**Job ID**: CALAMUM_JOB_0010_AUDIT_TOOLING_SECURITY_AND_PROVENANCE_UPGRADES_20260209  
**Date**: 2026-02-09  
**Status**: COMPLETED  
**Owner**: ORACL-Prime  
**Frame**: 0010  

---

## 1. Objectives

Harden and standardize the Calamum audit tooling surface to match CodeSentinel + Calamum security standards while remaining school-demo friendly.

This job focuses on *audit tooling correctness*:

- Every audit is template-driven for offline reports (tracked templates).
- All audit outputs are written to `local_untracked/` (ignored).
- Every audit can run in `--dry-run` mode (no writes).
- Network access is explicitly gated (`--no-network`) for GUI audits.
- Provenance is preserved via untracked append-only JSONL logs.
- A central audit index is maintained for convenient browsing.

---

## 2. Scope

### 2.1 In-scope tools

Located under: `projects/calamum-moltbook-observer/tools/`

- `audit_repo_health.py`
- `audit_calamum_gui.py`
- `audit_runtime_artifacts.py`

### 2.2 In-scope template library

- `projects/calamum-moltbook-observer/template_library/`

Tracked templates remain in repo; runtime outputs do not.

### 2.3 In-scope offline output locations (ignored)

- `projects/calamum-moltbook-observer/local_untracked/audits/` (reports + evidence)
- `projects/calamum-moltbook-observer/local_untracked/audit_log/` (JSONL logs)

---

## 3. Core Directives

1. **No Secrets**: audits must not print or persist sensitive values. Evidence bundles must prefer hashes, sizes, timestamps, and counts.
2. **Write Isolation**: all outputs go to `local_untracked/` only.
3. **Deterministic Flags**:
   - `--dry-run` for all audits (no file writes, no JSONL appends).
   - `--no-network` for GUI audit (no HTTP calls; TCP probe optional but should be disabled under `--no-network`).
4. **Provenance Logging**:
   - each audit appends JSONL entries to an untracked log.
   - entry kinds: `snapshot` always; optional `baseline` under `--set-baseline`.
   - include git head/branch/dirty, run_id, timestamp_utc, tool id/version, findings summary.
5. **Central Audit Index**:
   - maintain `local_untracked/audit_log/audit_index.json` (untracked) pointing to latest report/evidence per audit type.
6. **Template Discipline**:
   - all audits render markdown reports from tracked templates in `template_library/reports/`.
   - templates must be registered in `template_library/INDEX.json`.

---

## 4. Work Items

### 4.1 Standardize outputs

- Normalize report outputs:
  - GUI audit -> `local_untracked/audits/gui/`
  - Runtime artifacts audit -> `local_untracked/audits/runtime/`
  - Repo health audit -> `local_untracked/audits/repo_health/` (already aligned)

### 4.2 Implement `--dry-run` for all audits

- Dry-run must:
  - run the audit logic and compute findings
  - print would-be output paths
  - avoid writing report/evidence/log/index

### 4.3 Implement `--no-network` for GUI audit

- Under `--no-network`:
  - do not perform HTTP requests
  - do not perform TCP probes
  - report should clearly say network checks were skipped by policy

### 4.4 Convert runtime artifacts audit to template-driven evidence

- Avoid printing raw log tails by default.
- Prefer safe evidence:
  - file exists
  - size bytes
  - mtime + age seconds
  - sha256 of whole file or last N bytes
  - jsonl record counts

### 4.5 Create/extend templates

Add tracked templates:

- `CALAMUM_RUNTIME_ARTIFACTS_AUDIT_TEMPLATE.md.template`
- `CALAMUM_GUI_AUDIT_TEMPLATE.md.template` (existing; may be extended)
- `CALAMUM_REPO_HEALTH_AUDIT_TEMPLATE.md.template` (already created)

### 4.6 Central audit index writer

- Implement a tiny shared helper pattern:
  - update `local_untracked/audit_log/audit_index.json` with latest artifacts per audit kind
  - include timestamp_utc, git head, and file paths

---

## 5. Acceptance Criteria

- All audits accept `--dry-run` and do not write anything when enabled.
- `audit_calamum_gui.py` accepts `--no-network` and performs no network I/O when enabled.
- All audits write:
  - a markdown report rendered from a tracked template
  - a JSON evidence bundle
  - and append a JSONL snapshot record (unless `--dry-run`)
- All audit outputs are confined to `local_untracked/`.
- `template_library/INDEX.json` includes all new/updated templates.
- Central index `local_untracked/audit_log/audit_index.json` is updated on every non-dry run.

---

## 6. Evidence Anchors

- Project manifest: `projects/calamum-moltbook-observer/PROJECT_MANIFEST.json`
- SessionMemory snapshots:
  - `.agent_session/policy_snapshot.json`
  - `.agent_session/ops_awareness.json`

---

*Planned by ORACL-Prime* (execution pending approval)
