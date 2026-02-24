# Ops Awareness Snapshot
**Snapshot:** 2026-02-23T16:34:28.606667Z  
**Session:** 20260223113428-calamum-moltbook-observer  
**Hash:** `e3b7cc66ad94...`

## Up next (QuestStack)
- up next: (none)

## Job execution pipeline (canonical)
- Preferred: use the job orchestrators (start/close).
- Start: `codesentinel job start <task_id>`
- Close: `codesentinel job close <task_id>`

### Gate runner (IDE-agnostic; names-only)
- Preflight: `codesentinel gate preflight --timeout-sec 900 --lock-key gate_preflight`
- Pre-job: `codesentinel gate pre-job <task_id> --timeout-sec 900 --lock-key pre_job_<task_id>`
- Post-job: `codesentinel gate post-job --task-id <task_id> --rebuild-graph --timeout-sec 900 --lock-key post_job_rebuild_graph`

### Daily gates (standalone)
- BOD: `codesentinel gate bod --timeout-sec 900 --lock-key gate_bod`
- EOD (explicit): `codesentinel gate eod --explicit --timeout-sec 900 --lock-key gate_eod_explicit`

### Evidence surfaces
- Gate events: `logs/behavioral/gates/gate_events.jsonl`
- Reports: `logs/health_reports/operations`

## Search discipline (canonical)
- Quick reference: `docs/quick_reference/ORACALL_SEARCH_DISCIPLINE.md`
- Order: ORACall -> meaning-based -> file-glob -> exact string -> regex (last resort only)
- ORACall entrypoints:
  - search: `codesentinel oracall search`
  - trace: `codesentinel oracall trace`
  - stats: `codesentinel oracall stats`

## QuestStack scaffold-first (multi-frame jobs)
- Rule: For multi-frame jobs, create QuestStack doc/log/evidence before substantive work.
- Script: `operations/checklists/scripts/create_queststack_scaffold.py`

## Canonical checklist location
- `operations/checklists`

## Hard gates (canonical)
- Scripts directory: `tools/codesentinel/gates`
- Evidence stream: `logs/behavioral/gates/gate_events.jsonl`
- Evidence quick reference: `docs/quick_reference/GATE_EVIDENCE_LOCATIONS.md`

### Gate entrypoints
- BOD: `tools/codesentinel/gates/gate_bod.py`
- Preflight: `tools/codesentinel/gates/gate_preflight.py`
- Post-job: `tools/codesentinel/gates/gate_post_job.py`
- EOD: `tools/codesentinel/gates/gate_eod.py`

### BOD semantics (sticky)
- BOD is once per UTC day and satisfies all jobs for that day.
- Dedupe: UTC day (YYYY-MM-DD). Subsequent invocations are deduplicated.
- Evidence: `logs/behavioral/gates/gate_events.jsonl`
- Emergency repeat (not recommended): set `CODESENTINEL_ALLOW_REPEAT_BOD`=1

### Hard-gate rules

- BOD is once per UTC day; it satisfies all jobs for that day. Do not rerun BOD per job; reference the day's BOD evidence record instead. Emergency repeat only with CODESENTINEL_ALLOW_REPEAT_BOD=1.
- Use the hard-gate scripts (or VS Code tasks) for the correct scope: daily standalone gates (BOD, EOD) and per-run/per-job gates (Preflight, Post-job). EOD MUST NOT be treated as part of any per-job pipeline.
- Gates are fail-closed, non-interactive, timeout-bounded, and write exactly one JSONL evidence record per invocation.
- Do not rely on editor search to find gate evidence under logs/; use canonical paths instead.

## Core rules (recall)
- No plaintext sensitive identifiers (hosts, IPs, usernames, tokens, keys, passwords).
- Credentials are environment variables only (names-only in docs/logs).
- Archive-first: never delete; use quarantine_legacy_archive/.
- Prefer scripts over fragile one-liners (avoid CLI injection pitfalls).
- QuestStacks + evidence: track operational work with running doc + log + evidence.
- Run tests early/often; run full suite for policy-critical changes.
- Templates are governed artifacts: use VAULT templates or template pointers; do not invent ad-hoc report formats.

## Env var names (SSOT + adjunct; reference)
- SSOT: `tools/config/env/expected_env_vars.json`
- SSOT CLI: `codesentinel vault env ssot --profile <profile> --json`
- Validate CLI: `codesentinel vault env validate --profile <profile> --json`

## Active projects (quick index)
- `calamum-moltbook-observer` - Calamum Moltbook Observer (status: down)
  - Description: Security research observer stack with Ghost Console dashboard, watchdog supervision, and obfuscated telemetry collection.
  - Root: `projects/calamum-moltbook-observer`
  - Often used commands:
    - dashboard_launch: `powershell -File projects/calamum-moltbook-observer/launch_ghost_console.ps1`
    - observer_run: `python projects/calamum-moltbook-observer/src/calamum_observer_agent.py --mode canary --source sim`
    - tests: `pytest projects/calamum-moltbook-observer/src/tests/`
    - watchdog_run: `python projects/calamum-moltbook-observer/src/calamum_watchdog.py`
  - Entrypoints:
    - dashboard: `projects/calamum-moltbook-observer/src/ops_dashboard.py`
    - observer_agent: `projects/calamum-moltbook-observer/src/calamum_observer_agent.py`
    - readme: `projects/calamum-moltbook-observer/README.md`
    - watchdog: `projects/calamum-moltbook-observer/src/calamum_watchdog.py`
- `cids-ecosystem` - CIDS Ecosystem Operations (status: degraded)
  - Description: CIDS gate orchestration, watchdog supervision, and node-facing operational surfaces.
  - Root: `.`
  - Often used commands:
    - gate_bod: `codesentinel gate bod --timeout-sec 900 --lock-key gate_bod`
    - gate_preflight: `codesentinel gate preflight --timeout-sec 900 --lock-key gate_preflight`
    - memory_health: `codesentinel memory health --json`
    - ops_reacclimate: `codesentinel ops reacclimate`
  - Entrypoints:
    - deployment: `deployment/README.md`
    - gate_scripts: `tools/codesentinel/gates`
    - sentry_watchdog: `services/sentry_watchdog/README.md`
- `brain2-workspace` - Brain2 Workspace (status: planned)
  - Description: Tracked Brain/Brain2 planning, operations, policy, and split-ready documentation workspace.
  - Root: `brain`
  - Often used commands:
    - memory_health: `codesentinel memory health --json`
    - memory_show: `codesentinel memory show`
    - read_plan_map: `codesentinel memory project brain2`
  - Entrypoints:
    - execution_plan: `brain/EXECUTION_PLAN.md`
    - plan_map: `brain/PLAN_MAP.md`
    - readme: `brain/README.md`
- `codesentinel-core` - CodeSentinel Core (status: active)
  - Description: Primary governance, CLI, policy, and automation surface for the repository.
  - Root: `.`
  - Often used commands:
    - full_tests: `python run_tests.py`
    - memory_health: `codesentinel memory health --json`
    - preflight: `codesentinel gate preflight --timeout-sec 900 --lock-key gate_preflight`
  - Entrypoints:
    - copilot_instructions: `.github/copilot-instructions.md`
    - primary_agent_instructions: `codesentinel/AGENT_INSTRUCTIONS.md`
    - tasks_ssot: `operations/tasks.json`
- `data-science-script-library` - Data Science Script Library (status: active)
  - Description: Standalone educational scripts for data science workflows, profiling, docs, and ML utilities.
  - Root: `projects/data-science-script-library`
  - Often used commands:
    - repo_readme: `codesentinel memory project data-science-script-library`
  - Entrypoints:
    - readme: `projects/data-science-script-library/README.md`
- `unc-data-science-notes` - UNC Data Science Notes (status: active)
  - Description: Accessibility-first public class notes repository with maintenance and publication safeguards.
  - Root: `projects/unc-data-science-notes`
  - Often used commands:
    - maintenance: `python projects/unc-data-science-notes/maintain.py`
  - Entrypoints:
    - readme: `projects/unc-data-science-notes/README.md`

## Non-active / on-hold portfolio (condensed)
- Active count: 6
- projects/ discovered: 0
- On-hold/background entries:
  - `polymath-global-website` (status: background, root: `projects/polymath-global-website`) - Included as condensed portfolio entry; treat as non-core/background unless explicitly activated.

## VAULT template library (mandatory)
- Root: `codesentinel/assets/VAULT_templates`
- Registry: `codesentinel/assets/VAULT_templates/INDEX.json`
- README: `codesentinel/assets/VAULT_templates/README.md`
- Agent instructions: `codesentinel/assets/VAULT_templates/AGENT_INSTRUCTIONS.md`

### Canonical report templates (examples)
- Job: `codesentinel/assets/VAULT_templates/reports/JOB_TEMPLATE.json.template` (paired: `codesentinel/assets/VAULT_templates/reports/JOB_TEMPLATE.md.template`)
- Job report: `codesentinel/assets/VAULT_templates/reports/JOB_REPORT_TEMPLATE.json.template` (paired: `codesentinel/assets/VAULT_templates/reports/JOB_REPORT_TEMPLATE.md.template`)
- Plan: `codesentinel/assets/VAULT_templates/reports/PLAN_TEMPLATE.json.template` (paired: `codesentinel/assets/VAULT_templates/reports/PLAN_TEMPLATE.md.template`)

### Template pointer conventions
- Markdown: `<!-- CODESENTINEL_TEMPLATE_POINTER: relative/or/absolute/path -->`
- JSON: `{'__codesentinel_template_pointer__': 'relative/or/absolute/path'}`
- Helper: `codesentinel/utils/template_pointers.py`

### Validation
- Validator: `tools/codesentinel/validate_reporting_templates.py`

---
_Auto-generated by SessionMemory_

