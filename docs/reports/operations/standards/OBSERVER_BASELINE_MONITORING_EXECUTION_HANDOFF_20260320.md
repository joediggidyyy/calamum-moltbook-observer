# Observer Baseline Monitoring Execution Handoff (2026-03-20)

**Status**: active pre-execution handoff surface  
**Scope**: `projects/calamum-moltbook-observer/`  
**Driver lane**: `projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0022_MOLTBOOK_BASELINE_INTEGRATION_20260220.md`  
**Roadmap parent**: `projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0017_MOLTBOOK_OBSERVER_LIVE_COLLECTION_ROADMAP_20260211.md`  
**Governance anchor**: `projects/calamum-moltbook-observer/docs/reports/operations/audits/CURRENT_EVENTS_IMPACT_ASSESSMENT_BASELINE_AND_LIVE_MODE_20260319.md`  
**Design-contract anchors**:
- `projects/calamum-moltbook-observer/docs/plans/OBSERVERCTL_MODE_TRANSITION_MATRIX_CHAPTER_20260221.md`
- `projects/calamum-moltbook-observer/docs/reports/operations/standards/OBSERVER_RESOURCE_SPIKE_LOCKDOWN_STANDARD_20260221.md`
- `projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0026_OBSERVER_OPERATIONAL_READINESS_AUDIT_20260222.md`
- `projects/calamum-moltbook-observer/docs/CALAMUM_CODESENTINEL_JOB_EXECUTION_EXPECTATIONS.json`

---

## 1) Purpose

This handoff preserves execution intent for the **baseline monitoring uplift** required before any renewed Stage 5 live/honeypot decision gate.

This is **not** authorization to activate `live` or `honeypot`. It is a build-and-validate lane that closes the implementation gap between:

1. the now-complete **baseline command-surface cutover**, and
2. the still-incomplete **baseline monitoring design contract** required for `lockdown` posture operations.

If tomorrow starts sleepy, this document should still be enough to keep the gremlins in a compliance crate.

---

## 2) Execution intent to preserve

### Core intent

Implement baseline monitoring so that `live` and `honeypot` readiness is backed by **real retained telemetry**, **real baseline-window evidence**, **real cadence enforcement**, and **deterministic fail-closed gates**.

### What must remain true

- Stage 5 remains **decision-gate only** until the new implementation is complete and evidenced.
- `source=real` is distinct from `mode=live|honeypot`.
- Output remains **names-only**.
- The observer lane stays **threat-focused**, **fail-closed**, and **append-only**.
- No shortcut implementation should satisfy gates by merely changing config values without making the runtime producers and retention chain real.

### What this execution lane is not

- not a UI redesign lane
- not a KEYSMITH/key movement lane
- not a live activation lane
- not a permission to weaken lockdown thresholds
- not a broad refactor authorization for `observerctl.py`

---

## 3) Current verified state

### Done already

- `observerctl baseline status` and `observerctl baseline check` now default to the chunked/dynamic catalog path.
- Explicit `--baseline <path>` still routes to the legacy filesystem-hash path.
- `projects/calamum-moltbook-observer/src/tests/test_observerctl.py` passed: **43 passed**.

### Stage 5 NO-GO reasons already recorded

From `CALAMUM_JOB_0026`:

- `critical_check_failed:observer_heartbeat_stale`
- `critical_check_failed:env.moltbook_api_key`
- `critical_check_failed:watchdog_trigger_posture_invalid`
- `critical_check_failed:lockdown_heartbeat_rate_not_escalated`
- `critical_check_failed:lockdown_baseline_rate_not_escalated`

### Verified runtime posture snapshot

Current posture state file:
- `projects/calamum-moltbook-observer/logs/control/calamum/watchdog_posture_state.json`

Verified values:
- `posture_trigger: isolation`
- `heartbeat_interval_seconds: 10`
- `baseline_validation_interval_seconds: 120`

These values are incompatible with the documented `lockdown` contract for `live`/`honeypot`.

---

## 4) Critical design-to-code mismatch to resolve first

### Naming mismatch

**Docs/design contract says:**
- `resource_normal`
- `resource_baseline`

**Current `observerctl.py` implementation says:**
- `resource_normal`
- `resource_rapid`

Relevant code observations:
- `_baseline_collect(... profile='normal|rapid' ...)` emits `stream_type = resource_<profile>`
- `_baseline_analyze(...)` counts `resource_normal` and `resource_rapid`
- `baseline overnight-run` also uses `normal` + `rapid`

### Decision required at implementation start

Before changing behavior, lock in **one canonical vocabulary**:

#### Option A — promote code vocabulary to match design docs
- rename `rapid` -> `baseline`
- rename `resource_rapid` -> `resource_baseline`
- update all gate/evidence docs and tests accordingly

#### Option B — preserve current code vocabulary and update design docs
- keep `rapid` as the implementation term
- add explicit equivalence language: `resource_baseline == resource_rapid`
- update all design surfaces so no ambiguity remains

### Recommended direction

**Option A** is cleaner if tomorrow includes implementation changes anyway. The design-doc vocabulary is already the more semantically precise execution target.

This should be treated as the **first lock decision** of the morning. Do not let the code and docs keep talking past each other.

### 2026-03-22 locked implementation decisions

The following choices are now fixed for the current implementation push:

1. **Canonical term**: `resource_baseline`
   - `resource_rapid` remains a compatibility alias only while old artifacts age out
2. **Continuous producer owner**: `observerctl`-managed monitor process
   - started/stopped with the observer runtime lane
   - always emits `resource_normal` while the stack is healthy
3. **Baseline-window producer owner**: same monitor process
   - emits `resource_baseline` windows on lockdown cadence
4. **Retention path model**: reuse existing `archive/` segmented JSONL conventions
   - no second archive tree
   - librarian continues to own compression/index continuity over those artifacts
5. **Gate truth source**: retained evidence + control-state readback
   - resource index continuity
   - latest baseline-analysis packet
   - watchdog posture/resource packets
6. **Lockdown defaults**:
   - `heartbeat_interval_seconds = 4`
   - `baseline_validation_interval_seconds = 45`

These choices keep the lane inside the approved scope: implement the monitoring contract, do not redesign the entire runtime.

---

## 5) Verified implementation surfaces

### Primary code surfaces

#### `projects/calamum-moltbook-observer/src/observerctl.py`
Key relevant areas:
- posture + resource checks in gate evaluation (`~900-1120`)
- chunked baseline default routing (`~2170+`)
- `_baseline_collect(...)` (`~2200+`)
- `_baseline_analyze(...)` (`~2440+`)
- `baseline overnight-run` planning/execution (`~2619+`, `~2845+`)
- CLI parser surface for baseline subcommands (`~3561+`, `~3722+`)

Current facts:
- resource collection producers already exist in plan-execution CLI form
- gate checks currently consume `watchdog_posture_state.json` and `watchdog_resource_state.json`
- gate logic enforces lockdown cadence bands but does not by itself make the producer chain always-on

#### `projects/calamum-moltbook-observer/src/calamum_librarian.py`
Current facts:
- librarian watches `archive/` and processes raw `.jsonl` files into `.gz`
- manifest + adaptive rotation policy already exist
- current implementation is generic and may be reusable, but resource-stream integration is not yet explicitly documented end-to-end

#### `projects/calamum-moltbook-observer/src/ops_dashboard.py`
Current facts:
- dashboard already tracks librarian presence/heartbeat
- useful verification surface for operator confirmation, but not the primary implementation target for this lane

#### `projects/calamum-moltbook-observer/src/ops/telemetry.py`
Current facts:
- telemetry surface already reads librarian heartbeat freshness
- useful if runtime health reporting needs extension for the new stream classes

### Primary state/evidence surfaces

- `projects/calamum-moltbook-observer/logs/control/calamum/watchdog_posture_state.json`
- `projects/calamum-moltbook-observer/logs/control/calamum/watchdog_resource_state.json`
- resource index path emitted by `observerctl`
- evidence index path emitted by `observerctl`
- baseline catalog path used by chunked baseline routing

---

## 6) What is already present but not yet sufficient

This matters because tomorrow is **not** greenfield.

### Present today

- CLI producers for baseline collection
- CLI analysis for lookback-based baseline readiness
- overnight-run orchestration surface
- control-state packet writing for watchdog consumption
- chunked baseline catalog and active baseline pointer

### Still insufficient for design-spec readiness

- no confirmed always-on continuous producer bound to runtime posture
- no locked documentation that the producer chain runs automatically during `lockdown`
- no explicit proof that librarian lifecycle covers the resource stream classes end-to-end
- no locked canonical naming between `resource_baseline` and `resource_rapid`
- no morning-ready implementation note that says which component owns what

Interpretation:

**Tomorrow’s job is not “invent baseline monitoring from zero.”**  
It is **to operationalize, normalize, and lock the already-partial producer chain to the documented design contract**.

---

## 7) Phased execution plan (lockable)

### Phase 0 — lock the contract before touching behavior

Exit criteria:
- one canonical stream vocabulary chosen
- one canonical ownership model chosen
- one canonical posture/cadence contract confirmed

Must lock:
- `resource_baseline` vs `resource_rapid`
- who owns continuous sampling:
  - `observerctl` loop
  - watchdog
  - dedicated sampler process/service
- whether `baseline overnight-run` becomes reusable substrate or remains a separate batch tool
- whether librarian ingests from existing archive conventions unchanged or requires resource-stream-specific partitioning/index metadata

Do not proceed into code mutation until these are written down in the active job surface.

### Phase 1 — posture mutation and lockdown contract

Goal:
Make route transitions into `live`/`honeypot` apply a real `lockdown` posture packet and fail closed if not persisted.

Implementation targets:
- posture write path
- posture reload/readback verification
- evidence receipt path
- route transition linkage

Parameters to enforce:
- `posture_trigger = lockdown`
- `heartbeat_interval_seconds in [3, 5]`
- `baseline_validation_interval_seconds in [30, 60]`

Exit criteria:
- transition path writes lockdown posture atomically
- readback verifies persisted values
- evidence packet emitted
- rollback path defined on write/reload failure

### Phase 2 — continuous resource stream

Goal:
Promote `resource_normal` from CLI-capable sampling to continuously retained operational telemetry.

Implementation targets:
- long-running producer or scheduled loop
- append-only segment write path
- metadata completeness
- health/freshness reporting

Required per-sample metadata:
- `stream_type`
- `sampling_profile_id`
- `mode_at_capture`
- `source_axis`
- UTC timestamp
- `run_id`
- `security_report_ref` if contract requires linkage at this layer

Exit criteria:
- stream is continuously written while stack is healthy
- stale/unwritable cases fail closed
- index continuity exists

### Phase 3 — rapid baseline window producer

Goal:
Promote rapid/baseline sampling from CLI batch behavior into a formally specified readiness window contract.

Must define explicitly:
- sample interval
- minimum sample count
- window freshness
- allowable missing-sample tolerance
- derived envelope metrics required for gate readiness

Exit criteria:
- a completed baseline window can be identified deterministically
- derived baseline packet exists
- freshness/expiry rules are machine-checkable

### Phase 4 — automatic validation loop

Goal:
Ensure baseline validation cadence executes because the runtime is doing it, not because a human remembered to type a nice command.

Requirements:
- loop or scheduler tied to posture mode
- cadence bound to `baseline_validation_interval_seconds`
- append-only run record for each cycle
- restart-safe continuity semantics

Exit criteria:
- validation executes automatically in the correct posture
- each cycle leaves evidence
- recovery after restart is deterministic

### Phase 5 — librarian integration

Goal:
Make resource streams first-class retention citizens.

Requirements:
- rotation/compression/index continuity for continuous and rapid/baseline streams
- preserved stream metadata during archive lifecycle
- health surface proving retention is healthy

Exit criteria:
- librarian can process both stream classes without losing replay context
- retention health can be referenced by Stage 5 gates

### Phase 6 — gate hardening and reason-code proof

Goal:
Make C22, C24, and C25 provable against real artifacts.

Checks to satisfy:
- C22 `baseline_validation_rate_escalated`
- C24 `resource_stream_retention_ready`
- C25 `resource_baseline_window_ready`

Exit criteria:
- gate denial reasons arise from retained evidence, not inferred wishful thinking
- reason-code ordering remains deterministic
- evidence refs are names-only and resolvable

### 2026-03-22 progress note — operator proof surface improved

- `observerctl ops evidence pack` now supports `--to <mode>` for non-activation readiness projection.
- The evidence packet now surfaces retained readiness references directly:
   - posture receipt
   - watchdog resource state
   - baseline monitor heartbeat/pid/state
   - resource retention index + latest segment
   - baseline-window packet
   - librarian retention pointer/state
- This does **not** reopen live-mode authorization; it improves the proof surface used before any such decision.

### 2026-03-22 progress note — proof packet now speaks Stage 5 directly

- The non-activation evidence packet now includes explicit prerequisite-class rows rather than only raw retained-surface summaries.
- Current mapped classes:
   - `C22_baseline_validation_rate_escalated`
   - `C24_resource_stream_retention_ready`
   - `C25_resource_baseline_window_ready`
   - `baseline_monitor_runtime_ready`
   - `overall`
- Result: a reviewer can now see both the raw retained surfaces and the packet’s direct Stage 5 prerequisite interpretation in one names-only artifact.

### Phase 7 — test and publication-grade evidence lane

Goal:
Prove the uplift without activating `live` mode.

Must include:
- automated tests for posture/cadence enforcement
- automated tests for stream creation and stale detection
- automated tests for baseline-window completeness and expiry
- librarian lifecycle tests
- deterministic reason-code tests
- publish-grade validation packet

Exit criteria:
- test lane green
- evidence bundle ready
- no activation performed

---

## 8) Morning implementation order (recommended)

1. **Lock terminology and ownership model**
2. **Patch posture mutation/readback path**
3. **Wire or normalize continuous producer ownership**
4. **Wire or normalize rapid/baseline window ownership**
5. **Extend librarian/index continuity**
6. **Harden gate checks against real artifacts**
7. **Expand tests**
8. **Run non-activation validation pass**
9. **Update job + audit + checklist surfaces with evidence**

This order matters: it prevents premature test-writing against a vocabulary or ownership model that changes halfway through the lane.

---

## 9) Exact decisions to record tomorrow before implementation

These should be written into the active job surface before any broad code edits:

1. **Canonical term**:
   - `resource_baseline`
   - or `resource_rapid`
2. **Producer owner for continuous stream**:
   - watchdog
   - dedicated sampler service
   - `observerctl`-launched managed process
3. **Producer owner for baseline-window stream**:
   - shared sampler with mode/profile switch
   - separate burst process
4. **Retention path model**:
   - existing `archive/` conventions unchanged
   - or stream-class partitioned archive tree
5. **Gate truth source**:
   - direct retained-stream inspection
   - retained-stream analysis packet
   - hybrid state + retained evidence
6. **Lockdown cadence values** if choosing explicit defaults inside allowed bands:
   - heartbeat exact default
   - baseline validation exact default

If these six decisions are not locked first, ambiguity will leak into tests, evidence packets, and operator documentation.

---

## 10) Non-goals / anti-drift rules

Do **not** accidentally turn this lane into:

- a general observer runtime overhaul
- a ghost console redesign lane
- a key-management lane
- a stage authorization change
- a collection-semantics rethink unrelated to baseline monitoring

Also preserve:
- no secret values in output
- no payload-body collection creep
- no weakening of lockdown requirements to “make the tests easier”

---

## 11) Validation package expected at end of execution

Minimum expected evidence:

- updated job surface(s)
- updated checklist surface(s)
- updated parent roadmap/audit references where needed
- test evidence for new/changed checks
- names-only packet proving:
  - lockdown posture write/readback
  - continuous stream active
  - baseline window complete
  - librarian retention healthy
  - Stage 5 prerequisite checks now satisfiable in non-activation mode

Preferred validation command families:
- targeted `pytest` for `test_observerctl.py`
- any new tests for librarian/telemetry/runtime ownership surfaces
- `observerctl` non-activation packets demonstrating readiness prerequisites

---

## 12) Recommended doc updates during or after implementation

These should be refreshed as execution lands:

- `CALAMUM_JOB_0022_MOLTBOOK_BASELINE_INTEGRATION_20260220.md`
- `CALAMUM_JOB_0017_MOLTBOOK_OBSERVER_LIVE_COLLECTION_ROADMAP_20260211.md`
- `CURRENT_EVENTS_IMPACT_ASSESSMENT_BASELINE_AND_LIVE_MODE_20260319.md`
- `OBSERVER_BASELINE_DRIVER_REALIGNMENT_EXECUTION_CHECKLIST_20260320.md`

---

## 13) Final operator-facing summary

The mission for tomorrow is:

> Convert the partially implemented baseline collection machinery into a fully locked, continuously evidenced, lockdown-compatible baseline monitoring system that satisfies the documented live/honeypot readiness design contract **without** activating live mode.

If the end result does not make C22, C24, and C25 provable from real retained evidence, the lane is not done.
