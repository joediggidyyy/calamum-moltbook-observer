# ObserverCTL CLI Operator Manual (Collaborative Runtime Guide)

> Audience: joediggidyyy + ORACL-Prime
>
> Scope: CLI-driven observer operations under `projects/calamum-moltbook-observer/`
>
> Status: Active runbook (living manual)

> Public-lockdown note (2026-03-24): this guide remains a tracked operator/reference surface, but some historical execution-lineage references inside it point to local-only / untracked project lanes (for example `planning/` and `jobs/`). Treat those as internal lineage context rather than as the public-facing repo map.

---

## 1) Purpose

This manual is the user-friendly, day-to-day guide for CLI-driven observer operations.

It covers:

- runtime execution workflow and evidence checkpoints,
- observer runtime operations with `observerctl`,
- transition safety (sim/real + posture),
- evidence and data path consistency,
- collaborative execution protocol.

This guide is designed to be updated as execution matures (especially simulation operations).

Primary policy anchors:

- `docs/CALAMUM_CODESENTINEL_JOB_EXECUTION_EXPECTATIONS.md`
- local-only lineage reference: `planning/OBSERVERCTL_MODE_TRANSITION_MATRIX_CHAPTER_20260221.md`
- local-only lineage reference: `jobs/CALAMUM_JOB_0023_OBSERVERCTL_COMMAND_SURFACE_PLANNING_20260221.md`

---

## 2) Core guardrails (always on)

1. Runtime source axis is `sim | real`.
2. Runtime mode axis is `watch | canary | live | honeypot`.
3. Names-only outputs only (no secret values).
4. `observerctl` is the runtime command surface for this repository.
5. No force-running simulations without explicit operator approval.

Simulation policy:

- Background simulations are allowed.
- Full life-like simulations require active observer feed shutdown before transition.

---

## 3) Operating model: who does what

- **joediggidyyy**: approval authority for execution windows (go/no-go).
- **ORACL-Prime**: prepares runbooks, performs approved CLI execution, captures evidence.
- **Both**: maintain chain-of-custody in quest/gate evidence streams.

---

## 4) Standard runtime workflow

Use this for any active lane:

1. Record task start in your local tracker/run log or other approved local-only execution surface.
2. Execute runtime work using `observerctl` commands.
3. Keep evidence/log/report artifacts current while work proceeds.
4. Record task close in your local tracker/run log.
5. Capture closure health evidence from the observer runtime surfaces.

If closure checks fail, treat the task as still open/in-progress until gates pass (or an approved override is explicitly recorded).

---

## 5) ObserverCTL command families (quick map)

- `observerctl ops *` -> preflight, gate checks, mode transition, evidence packets.
- `observerctl baseline *` -> baseline/graph readiness checks.
- `observerctl librarian *` -> runtime + mode-store controls (`status`, `check`, `restart`, `stats`, `stores`, `rotate`, `compact`, `verify`).
- `observerctl watchdog *` -> heartbeat/posture checks and reason catalog.
- `observerctl health *` -> quick/full diagnostics and reason explanation.
- `observerctl policy *` -> read-only policy introspection.

Dashboard control-plane note:

- Ghost Console banner route indicators (`MODE`, `SRC`, `ROUTE`) are SSOT-driven from `logs/control/calamum/observerctl_state.json`.
- Control Deck now exposes a gated runtime route control (`SOURCE` + `MODE` + `APPLY ROUTE (GATED)`) which executes `observerctl ops mode transition` (event=`gui-control`).
- Route changes from the dashboard remain fail-closed and surface gate reason codes in-system-log and UI notification channels.

Exit-code contract:

- `0` success/go
- `2` fail-closed/no-go
- `3` schema/contract invalid
- `4` dependency/context missing
- `5` runtime I/O failure

---

## 6) Runtime transition playbooks

## 6.1 Background simulation (non-exclusive)

Use for low-risk validation while active observer feed may remain online.

Recommended flow:

1. `observerctl ops preflight --source sim --json`
2. `observerctl ops mode gate --to <watch|canary> --source sim --json`
3. `observerctl ops mode transition --to <watch|canary> --source sim --event <event> --json`
4. `observerctl ops evidence index --json`

## 6.2 Full life-like simulation (exclusive)

Use for production-like simulation windows.

Mandatory controls:

1. Approval checkpoint recorded.
2. Active observer feed shutdown checkpoint recorded.
3. Transition and evidence commands executed.
4. Run-linkage fields verified in output (`run_id`, `posture_trigger_id`, `posture_trigger`, `security_report_ref`).

Recommended flow:

1. Record go/no-go approval.
2. Stop active observer feed and log the shutdown checkpoint.
3. `observerctl ops preflight --source sim --json`
4. `observerctl ops mode gate --to canary --source sim --json` (or approved mode)
5. `observerctl ops mode transition --to canary --source sim --event full-lifelike-sim --json`
6. `observerctl ops evidence pack --source sim --event full-lifelike-sim --json`
7. `observerctl ops evidence index --json`

## 6.3 Real-source transitions

For `source=real` transitions, ensure required runtime dependencies (including presence checks) are satisfied before attempting mode changes.

Never bypass fail-closed denials without explicit operator decision and recorded rationale.

---

## 7) Posture expectations by mode

- `watch`, `canary` -> `isolation`
- `live`, `honeypot` -> `lockdown`

If posture mismatches target mode, transition must deny with normalized reason codes.

For lockdown transitions, cadence-escalation checks must be satisfied.

---

## 8) Canonical output and evidence paths

All paths in this section are operator/runtime paths. Their presence here does not imply they belong to the public-tracked repo surface.

Observer-derived metrics:

- `logs/data/calamum/observer_derived/<source>/<mode>/moltbook_metrics.jsonl`

Observerctl evidence packets:

- `logs/data/calamum/observer_derived/<source>/<mode>/evidence/observerctl_<event>_evidence_<timestamp>.json`

Observerctl evidence index:

- `logs/data/calamum/observer_derived/<source>/<mode>/evidence/index.jsonl`

Governance evidence (repo-root):

- `logs/behavioral/gates/gate_events.jsonl`
- `logs/queststack/<QS-ID>_log.md`
- `logs/queststack/<QS-ID>_evidence.jsonl`

Dashboard snapshot counters (`/_ghost_console/snapshot`) schema:

- `total_records`: raw stream total (session + archival lineage, internal telemetry basis)
- `records_total_display`: display-safe aggregate from telemetry layer
- `display_main_records`: primary banner counter value
	- `source=sim` -> session-only display
	- `source=real` -> display aggregate
- `records_breakdown`:
	- `session`, `archive` (display values)
	- `session_raw`, `archive_raw` (raw values)
- `records_breakdown_display`:
	- `session`, `archive`, `main` (explicit UI-facing cache contract)

---

## 9) Data-volume interpretation and density sanity

When density appears unusually high (for example, burst bars), do not assume current-run throughput.

Perform this interpretation order:

1. Verify current source/mode scope.
2. Separate active vs archived totals.
3. Validate whether reported density is window-based rather than direct ingestion rate.
4. Check if mixed historical streams or rotated archives are influencing the view.

Use evidence/index and manifest-backed counts to ground conclusions.

---

## 10) Collaborative execution protocol

For each approved runtime window, record:

- who approved,
- execution goal,
- command surface used,
- expected output locations,
- abort conditions,
- closeout evidence pointers.

This makes sessions replayable and reduces ambiguity between operator intent and runtime actions.

---

## 11) Troubleshooting quick-reference

If transition returns `no-go`:

1. Do not force transition.
2. Inspect `reason_codes`.
3. Resolve posture/linkage/dependency checks.
4. Re-run gate before set/transition.

If evidence file appears missing:

1. Confirm canonical source/mode/evidence path.
2. Check corresponding `index.jsonl` in same scope.
3. Confirm event tag and timestamp window.

If closure gates fail:

1. Check memory health and working tree state.
2. Resolve fail-closed checks first.
3. Use override only when explicitly approved and fully documented.

---

## 12) Living-manual updates

This manual is intentionally iterative.

As new simulation phases are executed, update this document with:

- validated command sequences,
- known-good thresholds/expectations,
- common failure signatures and mitigations,
- clarified operator checkpoints.

The goal is a stable, operator-first runtime playbook that remains aligned with policy and implementation.
