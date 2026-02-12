# References: Calamum Moltbook Observer

## Initial Resources (2026-02-02)

- [QuestStack: Preparation](projects/calamum-moltbook-observer/queststacks/QS-CALAMUM-MOLTBOOK-OBSERVER-PREP-20260201.md)
- [QuestFrame: Preparation](projects/calamum-moltbook-observer/questframes/QF-CALAMUM-MOLTBOOK-OBSERVER-PREP-20260201.json)
- [Job: Preparation](projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0001_MOLTBOOK_OBSERVER_PREPARATION_AND_SETUP_20260201.md)
- [Plan: Experiment Plan](projects/calamum-moltbook-observer/planning/CALAMUM_MOLTBOOK_OBSERVER_EXPERIMENT_PLAN_20260201.md)

## Live Collection (Stage 4 / Job 0017)

- Job (project SSOT, Markdown): `projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0017_MOLTBOOK_OBSERVER_LIVE_COLLECTION_ROADMAP_20260211.md`
- Job (project SSOT, JSON): `projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0017_MOLTBOOK_OBSERVER_LIVE_COLLECTION_ROADMAP_20260211.json`
- QuestStack (execution narrative): `projects/calamum-moltbook-observer/queststacks/QS-CALAMUM-MOLTBOOK-OBSERVER-LIVE-COLLECTION-ROADMAP-20260211.md`
- QuestStack log (names-only): `logs/queststack/QS-CALAMUM-MOLTBOOK-OBSERVER-LIVE-COLLECTION-ROADMAP-20260211_log.md`
- QuestStack evidence (names-only): `logs/queststack/QS-CALAMUM-MOLTBOOK-OBSERVER-LIVE-COLLECTION-ROADMAP-20260211_evidence.jsonl`
- Job report (names-only): `docs/reports/operations/JOB_REPORT_QS-CALAMUM-MOLTBOOK-OBSERVER-LIVE-COLLECTION-ROADMAP-20260211.md`

## External References Visited

- Durable ledger (annotated, non-volatile): `docs/external/AGENT_EXTERNAL_LINKS_VISITED_LEDGER.md`

- Moltbook API base URL (default live client host): https://api.moltbook.com/v1
- Moltbook Identity docs (identity-token / verify-identity): https://moltbook.com/api/v1

## Local Operational Endpoints (for audits)

- Calamum ops dashboard / Ghost Console (default): http://127.0.0.1:8899
- Alternate loopback form used in logs/audits: http://localhost:8899/

## Next steps toward live-collection

1. **Confirm environment is ready (no secrets in repo)**
	- Ensure `projects/calamum-moltbook-observer/.env` remains local-only and untracked.
	- Prefer VAULT/OS secret store loading for `MOLTBOOK_API_KEY`.

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
