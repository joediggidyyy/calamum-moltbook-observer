# Calamum Moltbook Template Library

This folder is the **project-local template library** for the Calamum Moltbook Observer.

## Goals

- Keep reporting/audit templates *inside the Moltbook subtree* so contributors can run audits and generate deliverables without hunting across the monorepo.
- Seed from the canonical CodeSentinel VAULT templates (copied, not referenced live) so this project remains usable even when extracted/published standalone.

## Normalized documentation pointers (Calamum)

When authoring or rendering documents from these templates, follow the project’s normalized execution expectations:

- **Operations policy (CodeSentinel-managed execution; names-only)**:
	- `projects/calamum-moltbook-observer/docs/CALAMUM_CODESENTINEL_JOB_EXECUTION_EXPECTATIONS.md`

This includes the KEYSMITH doctrine for `MOLTBOOK_API_KEY` (claim_url-only human ceremony; sealed-drop secret handling; presence-only env validation).

## Structure

- `reports/` — Markdown/JSON report templates used by Moltbook tools.
- `job_complexity_templates/` — Lightweight planning prompts and checklists.
- `ssot/` — SSOT (single-source-of-truth) canonical template stubs.

ObserverCTL operational templates added for immediate Job0023 execution:

- `reports/OBSERVERCTL_MODE_TRANSITION_RUN_TEMPLATE.{md,json}.template`
- `reports/OBSERVERCTL_SECURITY_POSTURE_VALIDATION_TEMPLATE.{md,json}.template`

## Syncing from VAULT

Use the project-local sync tool:

- `local_untracked/tools/sync_template_library_from_vault.py` (intentionally not tracked; depends on parent CodeSentinel-1 repo)

It copies a curated subset of templates from:

- `REPO:codesentinel/assets/VAULT_templates/`

…into this `template_library/` tree.

Notes:
- The sync tool is **additive** by default (won't overwrite existing files unless `--force` is provided).
- The sync tool never deletes files (SEAM minimalism / archive-first).
