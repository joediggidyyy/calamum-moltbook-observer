# Job 0022: Moltbook Baseline Integration

> **ID**: CALAMUM_JOB_0022_MOLTBOOK_BASELINE_INTEGRATION_20260220
> **State**: COMPLETED
> **Status**: completed
> **Owner**: ORACL-Prime
> **Date**: 2026-02-20

## Scope
Bind baseline readiness outputs from CodeSentinel into observer/Keymaster operational gates under watchdog-authoritative posture control.

## 2026-03-19 current-events impact reference
- Linked assessment: `projects/calamum-moltbook-observer/docs/reports/operations/audits/CURRENT_EVENTS_IMPACT_ASSESSMENT_BASELINE_AND_LIVE_MODE_20260319.md`
- Carry-forward note: baseline-ready contract remains valid, but any future refresh of this integration should preserve new packet fields for policy snapshot, identity-assurance, operator responsibility, external dependency, and platform-drift context.

## 2026-03-19 status ambiguity note
- Work product for this lane is complete and documented.
- `operations/tasks.json` currently still carries this task as `open` with status reason `test job-lineage state mutaion`.
- Until SSOT is normalized, treat this lane as **implementation-complete with SSOT cleanup pending**, not as an active blocker to readiness-state analysis.

## Required integration outputs
- Baseline-ready contract checks embedded in lane decisions.
- Watchdog posture receipt fields bound and evidence-linked.
- Fail-closed denial path for stale/failed/timeout baseline conditions.

## Dependency
- `codesentinel-baseline-local-stabilization-20260220` must provide `baseline_posture_inputs_v0` references before this lane transitions from planned to in-progress.

## 2026-02-20 implementation notes
- Added canonical terminal lane registration helper: `semantics_staging/ops_register_terminal_lanes.ps1`
- Fail-closed terminal prune behavior is active in: `semantics_staging/ops_prune_vscode_pwsh_shells.ps1`
- Incident trace and policy canonization linked in lane report.

## 2026-03-20 baseline command-surface cutover
- Implemented and validated: `_baseline_status()` and `_baseline_check()` in `observerctl.py` now route to chunked/dynamic catalog by default.
- Legacy filesystem-hash path preserved under explicit `--baseline <path>` argument for integrity/drift use.
- Test evidence: `projects/calamum-moltbook-observer/src/tests/test_observerctl.py` — 43 passed, no regressions.
- Remaining open item: archive of generated legacy baseline artifacts (cutover inventory, pending operator approval).
- This completes the implementation scope of this lane. SSOT cleanup (`tasks.json`) remains a separate deferred item per the 2026-03-19 status note.

## 2026-03-20 baseline monitoring implementation gap register

This section records the remaining gap between the **implemented baseline command surface** and the **planned live/honeypot baseline-monitoring design contract**.

Authority / design anchors:

- `projects/calamum-moltbook-observer/docs/plans/OBSERVERCTL_MODE_TRANSITION_MATRIX_CHAPTER_20260221.md`
- `projects/calamum-moltbook-observer/docs/reports/operations/standards/OBSERVER_RESOURCE_SPIKE_LOCKDOWN_STANDARD_20260221.md`
- `projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0026_OBSERVER_OPERATIONAL_READINESS_AUDIT_20260222.md`
- `projects/calamum-moltbook-observer/docs/CALAMUM_CODESENTINEL_JOB_EXECUTION_EXPECTATIONS.json`

Morning execution handoff:

- `projects/calamum-moltbook-observer/docs/reports/operations/standards/OBSERVER_BASELINE_MONITORING_EXECUTION_HANDOFF_20260320.md`

### Gap table — baseline monitoring vs design specification

| Area | Design specification | Current implementation state | Gap / failure mode | Required implementation outcome |
|---|---|---|---|---|
| Posture trigger for `live` / `honeypot` | `lockdown` posture is mandatory for `live` and `honeypot` | `logs/control/calamum/watchdog_posture_state.json` currently records `posture_trigger: isolation` | Stage 5 fails `critical_check_failed:watchdog_trigger_posture_invalid` | Route/state mutation into `live`/`honeypot` must atomically switch watchdog posture to `lockdown` and persist receipt/evidence |
| Lockdown baseline cadence | `baseline_validation_interval_seconds` must be in the 30-60s band | Current posture file records `baseline_validation_interval_seconds: 120` | Stage 5 fails `critical_check_failed:lockdown_baseline_rate_not_escalated` | Lockdown posture profile must persist 30-60s cadence and surface exact configured value in gate packets |
| Lockdown heartbeat cadence | `heartbeat_interval_seconds` must be in the 3-5s band | Current posture file records `heartbeat_interval_seconds: 10` under isolation | Stage 5 fails `critical_check_failed:lockdown_heartbeat_rate_not_escalated` | Live/honeypot route application must elevate watchdog + observer heartbeat cadence and persist proof-of-application |
| Always-on resource stream (`resource_normal`) | Continuous resource telemetry retained regardless of active collection state | Resource metrics are written opportunistically into watchdog resource state during operator-invoked analysis flows; no continuous retained stream is documented as active | C24 contract (`resource_stream_retention_ready`) is not satisfied end-to-end | Implement scheduled continuous resource sampling with append-only retained stream and librarian lifecycle support |
| Rapid baseline stream (`resource_baseline`) | Rapid-sampling bursts produce baseline-window evidence and derived envelope metrics | No documented dedicated `resource_baseline` stream writer or burst-window orchestrator is currently present | C25 contract (`resource_baseline_window_ready`) cannot be proven | Implement burst sampler, baseline-window metadata, derived envelope packet, and retention/index continuity |
| Automated baseline revalidation loop | Baseline validation cadence must execute repeatedly while in lockdown posture, not just be declared in config | Baseline refresh currently depends on operator-invoked analysis/overnight commands; no confirmed automatic loop is documented in active runtime | Configured cadence can exist without real execution | Add a timer-driven or service-driven baseline validation loop tied to posture mode and evidence logging |
| Stream metadata contract | Resource streams must carry `stream_type`, `sampling_profile_id`, `mode_at_capture`, `source_axis`, and `baseline_window_id` for rapid segments | Current watchdog resource state is a compact state packet, not a full retained stream-class record surface | Stream-class replay/audit semantics are incomplete | Emit structured records with required metadata for `resource_normal` and `resource_baseline` |
| Librarian lifecycle coverage | Librarian must rotate/compress/index all resource stream classes | Existing librarian handling is not yet documented here as owning `resource_normal` and `resource_baseline` end-to-end | Retention health cannot be demonstrated for Stage 5 contract | Extend librarian lifecycle/index pipeline to both resource stream classes and expose health/status checks |
| Gate enforcement completeness | Stage 5 gate must enforce C22/C24/C25 with deterministic reason codes and evidence linkage | Stage 5 contract exists and historical denial recorded; this lane has not yet documented the complete producer-side implementation needed to satisfy those checks | Re-gate would rely on incomplete production plumbing | Implement verifiable producer-side readiness surfaces before any renewed Stage 5 decision gate |
| Baseline-window completeness proof | Live/honeypot readiness requires a complete rapid baseline window and derived metrics | Current baseline status/check cutover proves catalog readiness, but not continuous baseline-window completion for lockdown operations | Baseline-ready and baseline-window-ready are not the same thing | Add explicit baseline-window completeness criteria, artifacts, timestamps, and fail-closed check semantics |

### Roadmap checklist — baseline monitoring uplift to design-spec readiness

### 2026-03-22 execution lock decisions

These decisions are now locked for the baseline-monitoring uplift lane and are the authoritative implementation choices unless joediggidyyy explicitly supersedes them.

1. **Canonical stream term**
	- use `resource_baseline`
	- treat legacy `resource_rapid` as a compatibility alias only
2. **Continuous-stream owner**
	- use an `observerctl`-managed baseline monitor process started/stopped with the observer runtime lane
3. **Baseline-window owner**
	- use the same `observerctl`-managed monitor process with a profile switch rather than a separate burst-only service
4. **Retention path model**
	- keep existing `archive/` conventions and segmented JSONL resource artifacts; do not invent a second retention tree
5. **Gate truth source**
	- use retained evidence plus control-state readback:
	  - resource index continuity
	  - latest baseline-analysis packet
	  - watchdog posture/resource state packets
6. **Exact lockdown defaults**
	- `heartbeat_interval_seconds = 4`
	- `baseline_validation_interval_seconds = 45`

These decisions intentionally favor the smallest ownership surface that can satisfy the design contract without reopening a broad `observerctl` refactor lane.

### 2026-03-22 runtime monitor transition hardening

- Implemented additional ownership enforcement for the `observerctl`-managed baseline monitor:
	- `_ops_runtime_start()` now fails closed if baseline monitor startup is not verified
	- `_ops_mode_switch()` now requires postflight `runtime.baseline_monitor` health instead of assuming monitor continuity
	- `runtime-stop` already treated baseline monitor shutdown as first-class and remains unchanged in that respect
- Added/updated focused lifecycle coverage in `projects/calamum-moltbook-observer/src/tests/test_observerctl.py` for:
	- runtime start fail-closed when monitor startup fails
	- mode-switch fail-closed when postflight monitor health is inactive
	- existing mode-switch tests updated to declare healthy monitor state explicitly
- Validation result: `test_observerctl.py` -> **47 passed** on 2026-03-22
- Interpretation: the runtime-ownership lane is now stricter and more explicit, but live/honeypot readiness still remains gated on the broader baseline-monitoring checklist below.

### 2026-03-22 non-activation readiness evidence projection

- Extended `observerctl ops evidence pack` so it can evaluate a **target mode without activation** using `--to <mode>`.
- Evidence packets now include retained-artifact readiness surfaces rather than only the coarse status + gate pair:
	- posture receipt path and configured cadence values
	- watchdog resource-state path
	- baseline monitor heartbeat/pid/state paths
	- resource retention index + latest segment path
	- latest baseline-window packet path and sample counts
	- librarian retention pointer/state summary
- This gives the operator a names-only proof surface for `canary -> live` or `canary -> honeypot` readiness analysis without activating those modes.
- Focused validation updated: `projects/calamum-moltbook-observer/src/tests/test_observerctl.py` -> **48 passed** on 2026-03-22
- Interpretation: the operator-proof lane is now materially stronger; readiness can be projected from retained artifacts before any live-mode action.

### 2026-03-22 Stage 5 prerequisite proof mapping

- Extended the non-activation evidence packet so it maps retained readiness surfaces into explicit Stage 5 prerequisite classes instead of leaving that translation to the operator.
- Current proof mapping now includes:
	- `C22_baseline_validation_rate_escalated`
	- `C24_resource_stream_retention_ready`
	- `C25_resource_baseline_window_ready`
	- `baseline_monitor_runtime_ready`
	- packet-level `overall` prerequisite status
- This keeps the proof lane names-only while making the packet substantially clearer as a pre-live decision surface.
- Focused validation remained green: `projects/calamum-moltbook-observer/src/tests/test_observerctl.py` -> **48 passed** on 2026-03-22 after Stage 5 mapping additions.

### 2026-03-23 checklist reconciliation update

- Revalidated the current uplift state against the live checklist using:
	- `report_tmp/job0022_baseline_monitor_runtime_probe/runs/job0022-baseline-monitor-runtime-20260323T041355Z/job0022_baseline_monitor_runtime_probe.md`
	- `projects/calamum-moltbook-observer/src/tests/test_observerctl.py` -> **49 passed**
- The checklist below is now updated only for items directly supported by retained probe evidence, current code surfaces, and passing automated coverage.
- Items that remain partially implemented stay unchecked here even when adjacent groundwork is in place. In other words: no checkbox cosplay.

### 2026-03-23 Frame 1 landing note — atomic lockdown posture write/readback

- Completed the Frame 1 seam for activation-path posture proof tightening.
- `observerctl ops mode set --to live` now returns posture-proof fields that surface:
	- applied posture state path
	- emitted posture receipt path
	- explicit `readback_verified` status
- Validation evidence:
	- targeted Frame 1 slice: **4 passed, 45 deselected**
	- full `projects/calamum-moltbook-observer/src/tests/test_observerctl.py`: **49 passed**
- Constraint preserved: this was a proof-surface tightening only; rollback hardening remains a separate Frame 2 item.

### 2026-03-23 Frame 2 landing note — fail-closed rollback proof on posture failure

- Completed the Frame 2 seam for posture-application failure handling during `ops mode set` / `ops mode transition`.
- `_ops_mode_set()` now surfaces deterministic rollback proof fields when posture application fails:
	- attempted target state
	- rollback anchor
	- rollback applied status
	- restored state
	- restored readback state
- `_ops_mode_transition()` now cleanly propagates that rollback failure packet when the transition gate passes but posture application fails during mode set.
- Validation evidence:
	- targeted Frame 2 slice: **5 passed, 46 deselected**
	- full `projects/calamum-moltbook-observer/src/tests/test_observerctl.py`: **51 passed**
- Constraint preserved: this remained a narrow failure-path hardening change; broader runtime/baseline-monitor behavior was not expanded in this frame.

### 2026-03-23 Frame 3 landing note — `resource_normal` continuity proof under idle semantics

- Completed the narrow continuity-proof tightening for the always-on `resource_normal` stream.
- `_resource_index_health()` now treats fresh `resource_normal` retention as the qualifying continuity signal rather than accepting any fresh resource stream row.
- This closes the false-positive seam where a fresh `resource_baseline` entry could masquerade as continuous `resource_normal` health.
- Added focused regression coverage proving:
	- non-activation live-readiness keeps `C24_resource_stream_retention_ready` green when collection semantics are idle/warmup-compatible and fresh `resource_normal` retention exists
	- the same proof surface fails closed with deterministic `critical_check_failed:resource_stream_retention_unavailable` when only `resource_baseline` freshness exists
- Validation evidence:
	- targeted Frame 3 slice: **4 passed, 49 deselected**
	- full `projects/calamum-moltbook-observer/src/tests/test_observerctl.py`: **53 passed**
- Constraint preserved: this frame tightened continuity proof only; broader Phase B runtime guarantees (including explicit `stopped`-state producer proof and metadata-contract completion) remain open.

#### Phase A — posture and cadence control surface

- [x] Lock the canonical lockdown defaults already adopted by the implementation and handoff surfaces:
	- `posture_trigger: lockdown`
	- `heartbeat_interval_seconds = 4`
	- `baseline_validation_interval_seconds = 45`
- [ ] Finalize and record the recovery unlock requirement:
	- `3` consecutive clean validation cycles where that remains the current policy anchor, or `5` if the standard remains mode-equalized at lockdown severity
- [x] Confirm where posture mutation is authored and persisted:
	- source of truth file/path
	- writer function(s)
	- runtime reload semantics
	- evidence receipt path
- [x] Implement atomic posture escalation on route transitions into `live` and `honeypot`.
- [x] Implement fail-closed posture rollback if any required lockdown parameter fails to persist or reload.
- [x] Emit names-only receipt/evidence artifacts proving the applied posture values and UTC timestamps.

#### Phase B — continuous resource stream (`resource_normal`)

- [x] Implement a continuous resource telemetry producer for the always-on stream.
- [x] Define the write target, file naming, and index/segment policy for `resource_normal`.
- [x] Set the sampling interval explicitly and bind it to documented posture/runtime policy.
- [ ] Ensure the producer runs when the observer stack is healthy even if collection state is `idle`, `warmup`, or `stopped`.
- [ ] Record required metadata on every sample:
	- `stream_type=resource_normal`
	- `sampling_profile_id`
	- `mode_at_capture`
	- `source_axis`
	- UTC timestamp
	- derived health/context fields needed by watchdog/librarian
- [ ] Define fail-closed behavior for:
	- unwritable stream target
	- stale sampler
	- malformed samples
	- index discontinuity

#### Phase C — rapid baseline stream (`resource_baseline`)

- [x] Implement a burst-mode resource sampler for baseline-window capture.
- [ ] Define the baseline-window contract in concrete terms:
	- minimum sample count
	- sampling frequency during burst
	- acceptable missing-sample tolerance
	- derived envelope/statistics required for window completion
- [x] Introduce a `baseline_window_id` and preserve it across all burst records and derived packets.
- [ ] Emit structured burst records with required metadata:
	- `stream_type=resource_baseline`
	- `baseline_window_id`
	- `sampling_profile_id`
	- `mode_at_capture`
	- `source_axis`
	- UTC timestamp
- [x] Compute and persist derived baseline-envelope outputs needed by readiness gates.
- [x] Define freshness/expiry rules for the resulting baseline window.

#### Phase D — automated baseline validation execution

- [x] Implement a scheduler or long-running loop that executes baseline validation automatically while posture is `lockdown`.
- [x] Bind execution cadence to `baseline_validation_interval_seconds` rather than an undocumented fixed constant.
- [x] Ensure the loop is suspended or downgraded correctly outside `live`/`honeypot` posture if policy requires posture-specific behavior.
- [ ] Emit append-only validation run records for each cycle including:
	- run timestamp
	- posture mode at execution
	- baseline window used
	- decision/result
	- normalized reason codes
- [ ] Define safe restart/recovery behavior so a process restart does not silently lose baseline-monitoring continuity.

#### Phase E — librarian retention and replay integrity

- [ ] Extend librarian retention/rotation logic to `resource_normal` segments.
- [ ] Extend librarian retention/rotation logic to `resource_baseline` segments.
- [ ] Preserve stream-class metadata during rotation, compression, compaction, and replay/index operations.
- [ ] Expose librarian health/status surfaces that can prove stream retention is healthy for Stage 5 gates.
- [ ] Validate replay/audit continuity after rotation so readiness evidence remains publication-grade.

#### Phase F — gate and evidence integration

- [x] Implement or verify C22, C24, and C25 producer-side readiness checks against real retained artifacts rather than inferred state alone.
- [ ] Require deterministic reason-code emission for each failure class:
	- `critical_check_failed:lockdown_baseline_rate_not_escalated`
	- `critical_check_failed:resource_stream_retention_unavailable`
	- `critical_check_failed:resource_baseline_window_incomplete`
	- any adjacent freshness/validity codes already declared by standards surfaces
- [ ] Ensure gate packets link to names-only evidence refs for:
	- posture receipt
	- resource stream health
	- baseline-window packet
	- librarian retention health
- [x] Preserve the rule that service heartbeat semantics are evaluated independently from collection-state semantics.

#### Phase G — runtime orchestration and operational safety

- [x] Define which runtime component owns each responsibility:
	- watchdog
	- observerctl command layer
	- separate sampler service/process
	- librarian
- [x] Define startup order and stop order for the monitoring stack.
- [ ] Finalize crash-recovery behavior for the monitoring stack.
- [ ] Ensure no live/honeypot activation path can proceed if baseline monitoring producers are not healthy.
- [ ] Ensure append-only evidence survives restarts and mode transitions.
- [ ] Confirm no secret-bearing data enters the resource streams or evidence packets.

#### Phase H — test matrix and validation evidence

- [x] Add automated tests for lockdown posture persistence and parameter enforcement.
- [x] Add automated tests for continuous `resource_normal` stream creation.
- [x] Add automated tests for `resource_normal` stale-stream denial / continuity break handling.
- [x] Add automated tests for `resource_baseline` burst-window completeness.
- [ ] Add automated tests for `resource_baseline` expiry handling.
- [ ] Add automated tests for scheduler/loop cadence honoring configured intervals.
- [ ] Add automated tests for librarian rotation/compression/index continuity for both resource stream classes.
- [ ] Add automated tests for deterministic reason-code ordering on all new denial paths.
- [x] Produce a non-activation validation bundle demonstrating end-to-end Stage 5 prerequisite satisfaction without activating live mode.

#### Phase I — closure and follow-through prerequisites

- [ ] Do not reopen live-readiness gating until Phases A-H are implemented and evidenced.
- [ ] Archive or clearly supersede any interim/local-only runtime artifacts generated during uplift work.
- [ ] Record the final design-to-implementation mapping back into the governing roadmap surfaces before any execution lock-in.
- [x] Keep this lane documented as **baseline integration complete, baseline monitoring uplift pending** until the above checklist is closed.

### 2026-03-23 bite-size execution frames for the remaining uplift

Use the remaining lane as a sequence of **small, testable frames**. Each frame should make the minimum effective edit needed to close one seam, then stop for validation before continuing.

#### Frame cadence rules (mandatory)

At the **start of every frame**:

- re-read this job surface:
	- `projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0022_MOLTBOOK_BASELINE_INTEGRATION_20260220.md`
- re-read the primary planning/spec surface:
	- `projects/calamum-moltbook-observer/docs/plans/OBSERVERCTL_MODE_TRANSITION_MATRIX_CHAPTER_20260221.md`
- re-check the active handoff/standards surface when touching monitoring semantics:
	- `projects/calamum-moltbook-observer/docs/reports/operations/standards/OBSERVER_BASELINE_MONITORING_EXECUTION_HANDOFF_20260320.md`
- review session-memory awareness artifacts, but treat them as advisory when they diverge from job/planning SSOT:
	- `.agent_session/ops_awareness.md`
	- `.agent_session/policy_snapshot.md`
	- `/memories/repo/ops_awareness_local_staleness_findings.md`
	- `/memories/repo/session_memory_pin_refresh_findings.md`

At the **end of every frame**:

- update the job checklist only for what the frame actually proved
- run the smallest targeted tests first, then broader validation if the seam is policy-relevant
- capture or refresh names-only evidence if the frame changes proof surfaces
- do a short awareness recheck before the next frame so drift gets caught early instead of becoming an interpretive art project

#### Frame 1 — atomic lockdown posture write/readback

- **Goal**: close the smallest remaining Phase A seam
- **Edit target**: posture mutation path for `ops mode set` / transition into `live` and `honeypot`
- **Required work**:
	- write real `lockdown` posture on activation-path mutation
	- verify immediate readback of persisted values
	- emit/update names-only receipt on successful application
- **Review before editing**:
	- job surface
	- mode transition spec
	- handoff surface
	- `.agent_session/ops_awareness.md`
- **Validation cadence**:
	- targeted tests for posture persistence and parameter enforcement
	- add a direct activation-path test that proves the write/readback path, not just non-activation projection
- **Exit criteria**:
	- `live` / `honeypot` transition path writes `lockdown`, `heartbeat=4`, `baseline_validation=45`
	- proof is visible in receipt/state artifacts

#### Frame 2 — fail-closed rollback on posture application failure

- **Goal**: finish the second half of the same Phase A seam before touching broader runtime behavior
- **Edit target**: transition/set rollback branch only
- **Required work**:
	- fail closed on readback mismatch or persistence failure
	- preserve pre-state / rollback anchor semantics
	- keep changes narrowly scoped to posture application failure handling
- **Periodic review checkpoint**:
	- re-read job + mode transition spec before coding this frame even if done in the same session
	- re-check `.agent_session/policy_snapshot.md`
- **Validation cadence**:
	- targeted rollback-path tests
	- targeted reason-code checks
- **Exit criteria**:
	- failed posture mutation leaves no partial success path
	- rollback evidence and denial reason are deterministic

#### Frame 3 — `resource_normal` continuity under idle/warmup semantics

- **Goal**: close the main open Phase B behavioral proof gap without broad sampler redesign
- **Edit target**: baseline monitor continuity logic and/or targeted tests
- **Required work**:
	- prove the producer remains healthy when runtime is alive but collection is `idle` or `warmup`
	- add fail-closed stale-stream denial where continuity breaks
- **Review checkpoint**:
	- job surface
	- handoff surface
	- `.agent_session/ops_awareness.md` with the repo-memory reminder that it may point at another lane
- **Validation cadence**:
	- targeted `resource_normal` continuity + stale denial tests
	- rerun the narrow baseline-monitor probe if proof surfaces change
- **Exit criteria**:
	- continuity is proven from retained artifacts
	- stale or missing continuity yields deterministic denial

#### Frame 4 — finish per-record metadata contract for both resource streams

- **Goal**: close the remaining Phase B/C metadata gap with minimal schema edits
- **Edit target**: record emission only; do not redesign retention layout
- **Required work**:
	- ensure `resource_normal` and `resource_baseline` records carry the required metadata contract
	- preserve compatibility alias handling without reopening naming drift
- **Periodic review checkpoint**:
	- re-read job surface
	- re-read mode transition spec section `14.2 Resource telemetry retention and baseline contract`
	- re-check session-memory artifacts for awareness drift
- **Validation cadence**:
	- targeted record-shape tests
	- targeted replay/readback checks from retained artifacts
- **Exit criteria**:
	- retained records are complete enough for replay/audit and gate proof

#### Frame 5 — append-only validation-cycle records

- **Goal**: move Phase D from cadence configuration to explicit runtime evidence
- **Edit target**: baseline monitor validation record emission only
- **Required work**:
	- emit append-only validation run entries for each automatic cycle
	- include posture mode, baseline window, result, and normalized reasons
- **Review checkpoint**:
	- job surface
	- handoff surface
	- `.agent_session/policy_snapshot.md`
- **Validation cadence**:
	- targeted monitor-loop tests
	- targeted packet/evidence index checks
- **Exit criteria**:
	- every automatic validation cycle leaves an append-only evidence trail

#### Frame 6 — restart-safe monitor continuity

- **Goal**: finish the other open Phase D seam before touching librarian retention
- **Edit target**: restart/recovery path only
- **Required work**:
	- prove restart does not silently lose monitor continuity
	- preserve window linkage and validation history across restart
- **Periodic review checkpoint**:
	- re-read job + handoff surfaces
	- re-read `/memories/repo/session_memory_pin_refresh_findings.md` as a reminder that awareness snapshots are not self-healing after state mutation
- **Validation cadence**:
	- targeted restart simulation tests
	- rerun the baseline-monitor probe if the runtime-ready proof surface changes
- **Exit criteria**:
	- restart path is deterministic and append-only evidence continuity survives

#### Frame 7 — librarian rotation/index coverage for `resource_normal`

- **Goal**: begin Phase E with the lower-risk stream first
- **Edit target**: librarian handling for `resource_normal` only
- **Required work**:
	- extend rotation/compression/index continuity
	- preserve stream metadata during lifecycle operations
- **Review checkpoint**:
	- job surface
	- handoff surface
	- current librarian-related tests before editing
- **Validation cadence**:
	- targeted librarian rotation/compression/index tests for `resource_normal`
- **Exit criteria**:
	- rotated `resource_normal` artifacts remain replayable and evidence-linkable

#### Frame 8 — librarian rotation/index coverage for `resource_baseline`

- **Goal**: complete Phase E after Frame 7 proves the pattern on the safer stream
- **Edit target**: librarian handling for `resource_baseline` only
- **Required work**:
	- extend the same lifecycle coverage to baseline-window artifacts
	- preserve baseline-window metadata and replay context
- **Periodic review checkpoint**:
	- re-read job surface
	- re-read mode transition spec `14.2`
	- re-check `.agent_session/ops_awareness.md` and `.agent_session/policy_snapshot.md`
- **Validation cadence**:
	- targeted librarian continuity tests for `resource_baseline`
	- evidence lookup tests from Stage 5 proof surfaces
- **Exit criteria**:
	- both stream classes survive rotation/compression without losing proof value

#### Frame 9 — raw gate hardening and evidence refs

- **Goal**: finish the open Phase F/G activation-path hardening after producer + retention proof exists
- **Edit target**: raw gate/evidence linkage only
- **Required work**:
	- require activation-path denial on unhealthy producers / missing windows / broken retention
	- ensure gate packets link posture, resource stream, baseline-window, and librarian evidence refs
	- tighten deterministic reason-code ordering for the remaining denial surfaces
- **Review checkpoint**:
	- job surface
	- mode transition spec
	- handoff surface
	- session-memory awareness artifacts
- **Validation cadence**:
	- targeted gate tests
	- targeted reason-order tests
	- rerun non-activation evidence proof after linkage changes
- **Exit criteria**:
	- raw activation paths are fail-closed for the same artifacts the proof path already uses

#### Frame 10 — closure bundle and document sync

- **Goal**: finish Phase H/I without inflating the implementation lane into a new architecture project
- **Edit target**: docs/tests/evidence only unless a final bug fix is discovered
- **Required work**:
	- run remaining targeted + broader validation needed for closure confidence
	- archive or clearly supersede interim/local-only uplift artifacts
	- sync the final state back into the job and the governing planning/report surfaces
- **Periodic review checkpoint**:
	- job surface
	- planning spec
	- handoff surface
	- session-memory artifacts one last time before closure notes
- **Validation cadence**:
	- targeted pytest surfaces first
	- broader observer validation after targeted green
	- refresh publish-grade non-activation evidence bundle
- **Exit criteria**:
	- remaining unchecked items are either proven closed or explicitly left open with reason
	- the lane can be described cleanly without hand-wavy “mostly done” energy

#### Scheduled review rhythm across all frames

- **Every frame start**: job + planning doc + session-memory awareness review
- **Every frame end**: checklist reconciliation + targeted tests + artifact audit
- **Every second frame**: re-read the handoff/standards surface before editing again
- **Any time runtime-state mutation logic changes**: re-check `.agent_session/policy_snapshot.md` and the repo-memory note about session-memory refresh assumptions
- **Any time proof semantics change**: rerun the non-activation probe before proceeding to the next frame

Recommended next bite from here: **Frame 1, then Frame 2 immediately after if and only if Frame 1 lands green with narrow tests**.

## 2026-02-21 completion notes
- Baseline-ready contract evaluated and recorded in publish-grade packet:
	- `projects/calamum-moltbook-observer/local_untracked/evidence/baseline_integration/baseline_integration_publish_grade_20260221T082452Z.json`
- Watchdog posture receipt fields captured (names-only):
	- `projects/calamum-moltbook-observer/local_untracked/evidence/baseline_integration/watchdog_posture_receipt_20260221T082534Z.json`
- Final SessionMemory health evidence captured:
	- `projects/calamum-moltbook-observer/local_untracked/evidence/baseline_integration/baseline_integration_memory_health_20260221T082538Z.json`
- Quest evidence ledger updated with run linkage (`run_id`, `posture_trigger_id`, `posture_trigger`, `security_report_ref`).

## Metadata

- Updated By: `joediggidyyy`
- Last Transition (UTC): `2026-02-28T13:11:17.600438Z`
- Status Authority: `operations/tasks.json`
- Task ID: `calamum-moltbook-baseline-integration-20260220`
- Status: `open`
