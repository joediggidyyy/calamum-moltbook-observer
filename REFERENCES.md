# References: Calamum Moltbook Observer

This index now distinguishes between **public-kept references** and **local-only lineage surfaces**.

Public-lockdown note:

- local execution/history lanes such as `jobs/`, `planning/`, `questframes/`, `queststacks/`, and `docs/reports/operations/` are retained locally / untracked and are not part of the locked-down public-tracked surface
- references to those lanes below are lineage/context notes only, not claims that those paths remain public-tracked

## Public-kept references

- [Operations Policy (CodeSentinel-managed execution expectations)](projects/calamum-moltbook-observer/docs/CALAMUM_CODESENTINEL_JOB_EXECUTION_EXPECTATIONS.md)
- [ObserverCTL CLI Transition Operator Guide](projects/calamum-moltbook-observer/docs/OBSERVERCTL_CLI_TRANSITION_OPERATOR_GUIDE_20260221.md)
- [Data Methodology](projects/calamum-moltbook-observer/DATA_METHODOLOGY.md)
- [Project-local Template Library](projects/calamum-moltbook-observer/template_library/README.md)

## Local-only lineage references (retained locally / untracked)

These paths remain useful for internal lineage and operator continuity, but they are not part of the public-tracked repo surface:

- `projects/calamum-moltbook-observer/queststacks/QS-CALAMUM-MOLTBOOK-OBSERVER-PREP-20260201.md`
- `projects/calamum-moltbook-observer/questframes/QF-CALAMUM-MOLTBOOK-OBSERVER-PREP-20260201.json`
- `projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0001_MOLTBOOK_OBSERVER_PREPARATION_AND_SETUP_20260201.md`
- `projects/calamum-moltbook-observer/planning/CALAMUM_MOLTBOOK_OBSERVER_EXPERIMENT_PLAN_20260201.md`
- `projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0017_MOLTBOOK_OBSERVER_LIVE_COLLECTION_ROADMAP_20260211.md`
- `projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0017_MOLTBOOK_OBSERVER_LIVE_COLLECTION_ROADMAP_20260211.json`
- `projects/calamum-moltbook-observer/queststacks/QS-CALAMUM-MOLTBOOK-OBSERVER-LIVE-COLLECTION-ROADMAP-20260211.md`
- `docs/reports/operations/JOB_REPORT_QS-CALAMUM-MOLTBOOK-OBSERVER-LIVE-COLLECTION-ROADMAP-20260211.md`

## External References Visited

- Durable ledger (annotated, non-volatile): `docs/external/AGENT_EXTERNAL_LINKS_VISITED_LEDGER.md`

- Moltbook API base URL (default live client host): https://api.moltbook.com/v1
- Moltbook Identity docs (identity-token / verify-identity): https://moltbook.com/api/v1

## Local Operational Endpoints (operator-local)

- Calamum ops dashboard / Ghost Console (default): http://127.0.0.1:8899
- Alternate loopback form used in logs/audits: http://localhost:8899/

## Operator-local live-collection checkpoints

These checkpoints rely on local runtime/evidence surfaces and are not a public-orientation map of the locked-down repo.

1. **Confirm environment is ready (no secrets in repo)**
	- Do not store `MOLTBOOK_API_KEY` in any tracked file (including `.env`).
	- Use VAULT / OS secret storage and inject via environment variables (presence-only checks; never echo values).
	- Credential acquisition must follow KEYSMITH doctrine (claim_url-only humans; sealed-drop secret handling). See:
	  - `projects/calamum-moltbook-observer/docs/CALAMUM_CODESENTINEL_JOB_EXECUTION_EXPECTATIONS.md`

2. **Set the live-collection toggles (air-gapped injection)**
	- `CALAMUM_MOLTBOOK_SOURCE=live`
	- `CALAMUM_OPS_MODE` set to a non-CANARY mode (for Stage 4 / Job 0017 validation).
	- `MOLTBOOK_API_KEY` set (presence-only; never echo the value).
	- Optional: `MOLTBOOK_HOST` only if the default host/version differs.

3. **Run the observer in non-CANARY + live mode**
	- Verify the canonical stream is produced at:
	  - `projects/calamum-moltbook-observer/logs/data/calamum/moltbook_live_metrics.jsonl`

4. **Validate evidence freshness and content**
	- File exists, is non-empty, and contains new records for the current run window.
	- Confirm names-only output discipline (no raw message content, no tokens).

5. **Run the CRITICAL watcher / operational checks**
	- Execute the Job 0017 watcher steps and capture a diagnostics bundle under `report_tmp/`.
	- Ensure gate evidence is present under `logs/behavioral/gates/gate_events.jsonl` for the run.
