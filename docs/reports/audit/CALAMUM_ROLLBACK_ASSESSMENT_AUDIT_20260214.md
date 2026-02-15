# Calamum / CodeSentinel — Rollback-Assessment Audit (Operator-defined session)

Policy (names-only): `projects/calamum-moltbook-observer/docs/CALAMUM_CODESENTINEL_JOB_EXECUTION_EXPECTATIONS.md`

Timestamp (UTC): 2026-02-14T00:00:00Z
Run ID: CALAMUM_ROLLBACK_ASSESSMENT_AUDIT_20260214
Auditor: ORACL-Prime

## Scope

Operator-defined session window for review:

- Boundary time: 2026-02-13 12:00:00 (local operator definition)
- Baseline commit (last commit before boundary): `e7c8d3df8a0167eeb45d41a76ab3da089466c838`
- Current branch at audit time: `main`

This audit is **analysis-only**. It does not authorize remediation actions.

## Policy re-alignment checkpoints (evidence)

From `CALAMUM_CODESENTINEL_JOB_EXECUTION_EXPECTATIONS.md`:

- SessionMemory artifacts should remain present/fresh during execution:
  - `.agent_session/policy_snapshot.{json,md}`
  - `.agent_session/ops_awareness.{json,md}`
- KEYSMITH doctrine (security emphasis):
  - "For LIVE collection, `MOLTBOOK_API_KEY` must be obtained without operator handling the secret and without the host system interacting with the moltbook vendor directly."
  - KEYSMITH mints/obtains the key inside a sandbox.
  - Humans may complete a vendor claim ceremony using claim_url only.
  - "The secret is transferred via sealed drop and imported into VAULT / OS secret storage."

Observed in workspace at audit time:

- `.agent_session/policy_snapshot.json` exists
- `.agent_session/ops_awareness.json` exists

## Change surface within the session window (facts)

Commits since boundary (HEAD order):

- `8422ce7f` Calamum: sandbox-only Moltbook interactions (fail closed)
- `ae2ddb06` Calamum/Moltbook: enforce www API base defaults (skill.md)
- `6c88b7de` Calamum: close Job 0018 docs; refresh Job 0017 evidence
- `430606f3` SSOT: close calamum-moltbook-keysmith-implementation-20260212
- `8b38129c` Calamum: fail-closed path overrides; KEYSMITH repo-safe export dir
- `18f49606` git: update .gitignore

Uncommitted changes present at audit time:

- `docs/reports/operations/JOB_REPORT_QS-CALAMUM-MOLTBOOK-KEYSMITH-IMPLEMENTATION-20260212.md`
- `projects/calamum-moltbook-observer/queststacks/QS-CALAMUM-MOLTBOOK-KEYSMITH-IMPLEMENTATION-20260212.md`

## Findings (drift assessment)

### F1 — Job 0018 report contains unapproved host-output doctrine (UNCOMMITTED)

File: `docs/reports/operations/JOB_REPORT_QS-CALAMUM-MOLTBOOK-KEYSMITH-IMPLEMENTATION-20260212.md`

Observed wording (current working tree) states KEYSMITH outputs "MUST be written outside the git working tree" and enumerates OS user-data directories (host locations).

Operator direction (current):

- KEYSMITH must never write anything outside its sandbox.
- No host directory should ever see data that came directly from Moltbook.

Status:

- This wording is **not committed** and is identified by the operator as **not approved**.

### F2 — Project README documents a non-container observer lane (PRE-EXISTING)

File: `projects/calamum-moltbook-observer/README.md`

Observed section:

- "For local testing without a live container, `src/calamum_observer_agent.py` can: ..."

Operator direction (current):

- There should never be an observer running outside of the observer container.

Status:

- This language appears in the README in the current tree and was not modified during this audit run.

### F3 — KEYSMITH implementation currently writes sealed-drop artifacts to a host path by default (CODE)

File: `projects/calamum-moltbook-observer/src/keysmith.py`

Observed behavior:

- `_default_output_dir()` selects a host OS user-data directory (Windows: `LOCALAPPDATA` / `APPDATA` / home) and writes artifacts there.
- `run_keysmith()` writes `sealed_drop.bin` (secret) to `output_dir`.
- The module emits PowerShell helper scripts intended to import/persist the key on the host.

Operator direction (current):

- KEYSMITH must drop only inside sandbox, then be programmatically validated, checked for tampering, and extracted directly into env var.
- No host directory should ever see Moltbook-originated secret material.

Status:

- This is a substantive divergence between current operator doctrine and current code behavior.

### F4 — KEYSMITH proposal document contains host-mount language (INTERPRETATION-SENSITIVE)

File: `projects/calamum-moltbook-observer/docs/reports/CALAMUM_KEYSMITH_SANDBOXED_MOLTBOOK_KEY_MINTING_PROPOSAL_20260212.md`

Observed text ("Option A") describes:

- KEYSMITH writes the secret inside container export dir, then that directory is "mounted to a host path that is not tracked" (examples include `local_untracked/` or "outside-repo").

Operator clarification (current):

- This should be treated as an early-stage feasibility/demo concept, not matured or approved production scope.
- It must not be interpreted as authorization for host contact with Moltbook real-estate or host persistence of Moltbook-originated data.

Status:

- The document contains language that can be read as permitting host-mounted export; operator indicates this is not intended for the matured scope.
- This is a documentation-risk issue independent of the session window.

## Risk statement (names-only)

Highest-risk drift relative to operator doctrine:

- Any path that results in Moltbook-originated secret material existing on the host filesystem.
- Any observer execution lane outside the hardened container.

## Remediation decision support (analysis-only)

Two viable remediation directions exist, pending operator choice:

- Patch-forward: revise KEYSMITH + docs to enforce "no host secret persistence" and "observer container-only".
- Rollback then patch: revert the post-boundary commits that introduced host-output defaults and related helper scripts, then implement the corrected sandbox-only scheme.

This audit does not select a remediation path.

## Conclusion (brief)

Within the operator-defined session window, there is confirmed drift in **documentation (uncommitted Job 0018 report language)** and in **code (KEYSMITH default host output path)** relative to current operator doctrine (sandbox-only; no host exposure). Additionally, there is pre-existing documentation language that describes non-container observer testing lanes.

## Addendum — 2026-02-15 execution update (job-doc continuation)

This section extends the audit as the active job document for remediation sequencing.

### Current status snapshot

- Knowledge graph rebuild is fresh (operator-confirmed in session).
- Superproject `main` shows a dangling modified sub-repo working tree at:
  - `projects/netgear-ax1800-linux-config`
- Root cause (fact): inside that sub-repo, `README.md` has an unstaged formatting delta:
  - `<p align="center">` -> `<p>`
- This dangling state is operationally separate from Calamum rollback findings F1-F4, but it blocks a clean superproject status and can confuse remediation evidence.

### Resolution track (recommended)

1. **Stabilize repository hygiene first (non-Calamum blocker):**
  - Resolve the `netgear-ax1800-linux-config` `README.md` delta by either:
    - restoring the file to `HEAD` (preferred if accidental), or
    - committing the change inside the sub-repo with an explicit message (if intentional).
2. **Contain doctrine drift artifacts (Calamum):**
  - Reconcile unapproved wording in:
    - `docs/reports/operations/JOB_REPORT_QS-CALAMUM-MOLTBOOK-KEYSMITH-IMPLEMENTATION-20260212.md`
    - `projects/calamum-moltbook-observer/queststacks/QS-CALAMUM-MOLTBOOK-KEYSMITH-IMPLEMENTATION-20260212.md`
3. **Patch documentation authority boundaries:**
  - Update `projects/calamum-moltbook-observer/README.md` with explicit observer container-only language.
  - Mark host-mount language in `CALAMUM_KEYSMITH_SANDBOXED_MOLTBOOK_KEY_MINTING_PROPOSAL_20260212.md` as legacy feasibility/non-authoritative for current doctrine.
4. **Patch KEYSMITH behavior (code):**
  - Enforce sandbox-only output/drop handling and fail-closed semantics for host-path targets in `src/keysmith.py`.
5. **Validate and close:**
  - Confirm clean status in both superproject and affected sub-repos.
  - Run targeted tests for key handling/path guardrails.
  - Capture final policy-alignment evidence and closing SessionMemory health entry.

### Operator-facing decision note

Given the rollback handoff guidance requiring per-file scrutiny, this addendum maintains a **patch-forward, evidence-led** path (not blanket rollback), with explicit containment before behavior changes.

### Execution progress logged (2026-02-15)

Actions executed in this continuation:

- Audit/job document updated with addendum and sequenced remediation track.
- Superproject dangling blocker cleared by restoring unintended sub-repo delta in:
  - `projects/netgear-ax1800-linux-config/README.md`
- Doctrine containment edits applied:
  - `projects/calamum-moltbook-observer/README.md`
    - Added explicit note: local demo lane is telemetry simulation only; Moltbook-facing execution is container-only.
  - `projects/calamum-moltbook-observer/docs/reports/CALAMUM_KEYSMITH_SANDBOXED_MOLTBOOK_KEY_MINTING_PROPOSAL_20260212.md`
    - Added doctrine-alignment addendum marking host-mounted secret export wording as non-authoritative legacy feasibility text.

Outstanding high-priority remediation still open after this continuation:

- F3 code-path correction in `src/keysmith.py` (sandbox-only secret output semantics).
- Reconciliation of unapproved wording in Job 0018 report + queststack references.

### Execution progress logged (2026-02-15, F3 code remediation)

F3 has been advanced in-code with targeted, doctrine-aligned changes:

- `projects/calamum-moltbook-observer/src/keysmith.py`
  - Default output behavior now prefers a sandbox-local root when `KEYSMITH_SANDBOX=1` (via `KEYSMITH_SANDBOX_OUTPUT_ROOT`, default `/tmp/calamum_keysmith_exports`).
  - Added fail-closed guard: sandbox runs reject `output_dir` outside `KEYSMITH_SANDBOX_OUTPUT_ROOT`.
  - Removed host-oriented helper artifact emission (`Import-MoltbookApiKeyFromSealedDrop.ps1`, `Persist-MoltbookApiKeyToUserEnv.ps1`).
  - Updated result/audit metadata to reflect sandbox-contained sealed-drop handoff and no host helper script generation.

- `projects/calamum-moltbook-observer/src/tests/test_keysmith.py`
  - Updated artifact expectations (helper scripts no longer expected).
  - Added fail-closed test for sandbox output root enforcement.

Validation evidence:

- Targeted test run PASS:
  - `pytest -q projects/calamum-moltbook-observer/src/tests/test_keysmith.py`
  - Result: `5 passed`
