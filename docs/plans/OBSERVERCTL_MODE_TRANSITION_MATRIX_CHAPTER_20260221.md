# ObserverCTL Mode Transition Matrix — Implementation Specification

> **Document ID**: OBSERVERCTL_MODE_TRANSITION_MATRIX_SPEC_20260221  
> **Project**: Calamum Moltbook Observer  
> **CLI Surface**: `observerctl`  
> **Author**: ORACL-Prime  
> **Date**: 2026-02-21  
> **Status**: Draft for implementation sign-off

## 1) Purpose and authority

This is the standalone, implementation-grade specification for mode/source transition control in `observerctl`.

It defines:
- canonical runtime states,
- exhaustive transition classes,
- gate profiles and check requirements,
- denial reason codes,
- evidence packet obligations,
- rollback and safety behavior,
- test coverage requirements.

This specification is normative for `observerctl ops mode gate --to <mode>` and `observerctl ops mode set --to <mode>` behavior in the current release.

## 2) Scope boundaries

- **Observer runtime surface**: governed by `observerctl`.
- **CodeSentinel**: external governance/orchestration harness only (the only development harness; not a runtime command host).
- **Security posture**: fail-closed by default.
- **No secrets**: names-only outputs; no secret values in logs/packets/stdout.

Command-scope clarification (normative):
- Commands defined in this specification are observer runtime/security operations commands.
- They are not development-scoped commands and must not imply observer is a dev platform.

## 3) Canonical state model

A runtime state is the tuple:

$$
S = (source, mode)
$$

Where:
- $source \in \{sim, real\}$
- $mode \in \{watch, canary, live, honeypot\}$

### 3.1 State identifiers

| ID | State tuple | Label | Eligibility |
|---|---|---|---|
| S1 | (`sim`, `watch`) | `SIM_WATCH` | allowed |
| S2 | (`sim`, `canary`) | `SIM_CANARY` | allowed |
| S3 | (`sim`, `live`) | `SIM_LIVE` | allowed |
| S4 | (`sim`, `honeypot`) | `SIM_HONEYPOT` | allowed |
| S5 | (`real`, `watch`) | `REAL_WATCH` | allowed |
| S6 | (`real`, `canary`) | `REAL_CANARY` | allowed |
| S7 | (`real`, `live`) | `REAL_LIVE` | allowed |
| S8 | (`real`, `honeypot`) | `REAL_HONEYPOT` | allowed |

### 3.2 Unknown-state handling

If current state cannot be inferred deterministically, transitions fail with:
- exit code: `2`
- reason code: `critical_check_failed:mode_current_unknown`

## 4) Transition taxonomy

For transition $T: S_i \rightarrow S_j$:

- **No-op**: $S_i = S_j$
- **Lateral**: same source, different mode
- **Source escalation**: `sim -> real`
- **Source de-escalation**: `real -> sim`
- **Compound escalation**: source escalation plus riskier mode change
- **Compound de-escalation**: source de-escalation plus less risky mode

## 5) Gate profiles

Each transition resolves to one gate profile (`GP-*`).

| Profile | Risk band | Typical transition | Default decision policy |
|---|---|---|---|
| GP-0 | No-op | `Sx -> Sx` | deny (operator-intent guard) |
| GP-1 | Low | same-source transitions ending at `watch`/`canary` | allow on core readiness |
| GP-2 | Medium | same-source transitions ending at `live` | require triad + stronger checks |
| GP-3 | High | cross-source transitions to `real` with target `watch`/`canary` | require real-readiness and approval checkpoint |
| GP-4 | Critical | any transition targeting `real/live` or any `honeypot` | strictest checks + full publish-grade triad |
| GP-X | Forbidden | policy-blocked transition from policy profile | deny unconditionally |

## 6) Check catalog (exhaustive)

All checks are names-only and deterministic.

| Check ID | Name | Description | Blocking severity |
|---|---|---|---|
| C01 | `observer_heartbeat_fresh` | observer liveness marker within freshness window | critical |
| C02 | `watchdog_heartbeat_fresh` | watchdog liveness marker within freshness window | critical |
| C03 | `baseline_ready` | baseline marked ready and not stale | critical |
| C04 | `graph_integrity_ok` | graph/index consistency check passes | major |
| C05 | `store_pointer_consistent` | active mode-store pointer resolves cleanly | critical |
| C06 | `store_integrity_ok` | mode-store manifest/hash checks pass | critical |
| C07 | `retention_policy_valid` | retention map valid for target mode/source | major |
| C08 | `policy_profile_loaded` | effective policy profile present and parseable | critical |
| C09 | `policy_transition_allowed` | transition permitted by policy table | critical |
| C10 | `env_real_key_present` | `MOLTBOOK_API_KEY` present for real-source target (presence-only) | critical |
| C11 | `source_selector_consistent` | source selector resolves to target source | major |
| C12 | `mode_target_supported` | target mode exists in current release | critical |
| C13 | `evidence_index_writable` | evidence index can append names-only entry | major |
| C14 | `triad_schema_available` | triad schema contract available and current | major |
| C15 | `approval_checkpoint_recorded` | explicit go/no-go checkpoint present when required | critical |
| C16 | `rate_safety_ok` | throughput/rotation safety thresholds not violated | major |
| C17 | `reason_catalog_loaded` | reason-code map present for deterministic output | major |
| C18 | `clock_utc_sane` | UTC monotonicity/timestamp validity for packeting | major |
| C19 | `watchdog_trigger_posture_valid` | watchdog trigger posture matches target mode (`isolation` for watch/canary, `lockdown` for live/honeypot) | critical |
| C20 | `run_security_report_linked` | `run_id` references a security report artifact for this run | critical |
| C21 | `heartbeat_rate_escalated` | watchdog/observer heartbeat cadence is elevated in lockdown posture | critical |
| C22 | `baseline_validation_rate_escalated` | baseline validation cadence is elevated in lockdown posture | critical |

## 7) Evidence obligations by profile

| Profile | Minimum evidence requirement | Packet expectation |
|---|---|---|
| GP-0 | gate packet only | decision + reason code |
| GP-1 | gate packet + check snapshot | compact triad optional |
| GP-2 | full triad required | provenance + methodology + process |
| GP-3 | full triad + approval checkpoint | triad must include live-readiness section |
| GP-4 | full triad + approval + rollback anchor + lockdown packet | triad must include rollback metadata and reviewer linkage |
| GP-X | gate denial packet | policy denial reason, no side effects |

## 8) Exhaustive transition matrix

Legend:
- `DENY-X` = forbidden by active policy profile (`GP-X`)
- `DENY-0` = no-op denied by intent guard (`GP-0`)
- `GP-1/2/3/4` = run gate checks for that profile
- `*` = requires exit `0` to proceed to `mode set`

### 8.1 State-to-state map

| From \ To | S1 | S2 | S3 | S4 | S5 | S6 | S7 | S8 |
|---|---|---|---|---|---|---|---|---|
| **S1 `SIM_WATCH`** | DENY-0 | GP-1* | GP-2* | GP-4* | GP-3* | GP-3* | GP-4* | GP-4* |
| **S2 `SIM_CANARY`** | GP-1* | DENY-0 | GP-2* | GP-4* | GP-3* | GP-3* | GP-4* | GP-4* |
| **S3 `SIM_LIVE`** | GP-1* | GP-1* | DENY-0 | GP-4* | GP-3* | GP-3* | GP-4* | GP-4* |
| **S4 `SIM_HONEYPOT`** | GP-1* | GP-1* | GP-2* | DENY-0 | GP-3* | GP-3* | GP-4* | GP-4* |
| **S5 `REAL_WATCH`** | GP-1* | GP-1* | GP-2* | GP-4* | DENY-0 | GP-1* | GP-4* | GP-4* |
| **S6 `REAL_CANARY`** | GP-1* | GP-1* | GP-2* | GP-4* | GP-1* | DENY-0 | GP-4* | GP-4* |
| **S7 `REAL_LIVE`** | GP-1* | GP-1* | GP-2* | GP-4* | GP-1* | GP-1* | DENY-0 | GP-4* |
| **S8 `REAL_HONEYPOT`** | GP-1* | GP-1* | GP-2* | GP-4* | GP-1* | GP-1* | GP-2* | DENY-0 |

### 8.2 Critical-path transitions (priority)

| Transition | Profile | Mandatory checks | Mandatory evidence | Typical denial reasons |
|---|---|---|---|---|
| `sim -> real` (same mode family) | GP-3/GP-4 | C01,C02,C03,C05,C06,C08,C09,C10,C11,C13,C14,C15,C18,C20 | full triad + approval checkpoint + run security link | missing real key, policy deny, stale heartbeat |
| `canary -> honeypot` (same source) | GP-4 | C01,C02,C03,C05,C06,C08,C09,C12,C16,C17,C19,C20,C21,C22 | full triad + lockdown packet | mode unsupported, retention invalid, safety threshold breach |
| `watch -> canary` | GP-1/GP-3 (if source changes) | C01,C02,C03,C05,C06,C08,C09,C12,C18 | gate packet (+triad if source change) | policy deny, baseline not ready |
| any `* -> real/live` or `* -> */honeypot` | GP-4 | C01..C22 except non-applicable fields; C10/C15/C19/C20/C21/C22 mandatory | full triad + rollback anchor + reviewer linkage | any critical check failure |

## 8.3 Watchdog posture elevation contract

Trigger posture model:
- `isolation` posture is required for target modes `watch` and `canary`.
- `lockdown` posture is required for target modes `live` and `honeypot`.

Isolation reaction profile (`watch`/`canary`):
- quarantine container,
- block ingress/egress (`no data in or out`),
- suspend collector/interactor processes,
- allow only local health + names-only audit evidence.

Lockdown reaction profile (`live`/`honeypot`, same severity level):
- apply full isolation controls,
- increase heartbeat cadence (watchdog + observer),
- tighten stale detection threshold,
- increase baseline validation cadence,
- freeze all non-essential writes except append-only evidence stream,
- deny promotion transitions until recovery checks pass.

Suggested operational parameters for lockdown:
- heartbeat interval target: 3-5 seconds,
- stale threshold: at most 2 missed beats,
- baseline validation interval: 30-60 seconds,
- recovery unlock requirement: 3 consecutive clean validation cycles.

Gate behavior:
- If target mode is `watch` or `canary`, gate must verify trigger posture `isolation` is configured.
- If target mode is `live` or `honeypot`, gate must verify trigger posture `lockdown` is configured and active controls are enforceable.
- Failure returns exit `2` with reason code `critical_check_failed:watchdog_trigger_posture_invalid`.

## 9) Command-level execution contract

### 9.1 `observerctl ops mode gate --to <mode> --json`

Required behavior:
1. infer current state deterministically,
2. resolve target state from `<mode>` + active source strategy,
3. map transition to gate profile,
4. execute profile check set,
5. emit deterministic gate packet,
6. return fail-closed exit code.

Output minimum fields:
- `timestamp_utc`
- `decision` (`go` or `no-go`)
- `from_state`
- `to_state`
- `profile`
- `checks` (id, status, severity)
- `reason_codes`
- `next_step` (e.g., `ops mode set` allowed or denied)

### 9.2 `observerctl ops mode set --to <mode> --json`

Required behavior:
- MUST require immediately preceding successful gate packet (freshness-bounded).
- MUST refuse state mutation if gate packet missing/stale.
- MUST emit post-set process packet with resulting state pointer.

## 10) Exit-code and denial semantics

| Exit code | Meaning | Mutation allowed |
|---:|---|---|
| 0 | success / gate `go` | yes (for `mode set`) |
| 2 | fail-closed denial / policy no-go | no |
| 3 | schema/contract invalid | no |
| 4 | dependency/context missing | no |
| 5 | runtime I/O / artifact access failure | no |

## 11) Reason-code catalog (normalized)

### 11.1 Transition/policy reasons
- `policy_denied:no_state_change_requested`
- `policy_denied:target_mode_unsupported`
- `policy_denied:profile_resolution_failed`

### 11.2 Critical readiness failures
- `critical_check_failed:mode_current_unknown`
- `critical_check_failed:observer_heartbeat_stale`
- `critical_check_failed:watchdog_heartbeat_stale`
- `critical_check_failed:baseline_not_ready`
- `critical_check_failed:store_pointer_inconsistent`
- `critical_check_failed:store_integrity_failed`
- `critical_check_failed:policy_not_loaded`
- `critical_check_failed:policy_transition_disallowed`
- `critical_check_failed:real_key_missing`
- `critical_check_failed:approval_checkpoint_missing`
- `critical_check_failed:watchdog_trigger_posture_invalid`
- `critical_check_failed:run_security_report_missing`
- `critical_check_failed:lockdown_heartbeat_rate_not_escalated`
- `critical_check_failed:lockdown_baseline_rate_not_escalated`

### 11.3 Major failures (still deny when profile requires)
- `major_check_failed:graph_integrity_failed`
- `major_check_failed:retention_policy_invalid`
- `major_check_failed:evidence_index_unwritable`
- `major_check_failed:triad_schema_missing`
- `major_check_failed:rate_safety_exceeded`
- `major_check_failed:reason_catalog_missing`
- `major_check_failed:clock_utc_invalid`

## 12) Rollback and recovery contract

For any successful mutation (`mode set`):
- persist `pre_state` and `post_state` pointers,
- write rollback anchor metadata,
- include recovery command hint in process packet,
- deny automatic rollback if current state cannot be inferred.

Rollback trigger classes:
- immediate critical check regression after set,
- watchdog posture critical within stabilization window,
- policy invalidation detected post-mutation.

## 13) Determinism and idempotency rules

- Gate evaluation is read-only and idempotent for unchanged inputs.
- `mode set` is single-mutation; repeated request to current state returns no-op denial.
- Check ordering is deterministic and stable across runs.
- Reason-code ordering in output is deterministic.

## 14) Security and observability constraints

- Names-only output only; no payload/raw message content.
- Presence-only checks for secrets (never value materialization).
- All packets timestamped in UTC and hash-addressable.
- Gate and set events must be append-only in evidence index.

## 14.1 Collection data contract by mode

All collection records (all modes) must include:
- `schema_version`
- `run_id`
- `posture_trigger_id`
- `ts_utc`
- `source` (`sim|real`)
- `mode` (`watch|canary|live|honeypot`)
- `record_class` (`telemetry|gate|evidence`)
- `runtime_cli_surface` (`observerctl`)
- `integrity` (hash/signing id names-only)
- `security_report_ref` (path/identifier linking this `run_id` to its security report)
- `posture_trigger` (`isolation|lockdown`)

Mode-specific minimums:
- `watch`: aggregate counts + liveness counters only.
- `canary`: metadata-only stream (non-interactive), baseline-ready counters.
- `live`: interaction metadata + policy decision tags.
- `honeypot`: live metadata + lure/tactic signal tags + containment flags.

Global forbiddance:
- no raw target payload bodies,
- no secret values,
- no unredacted identifiers.

## 15) Test matrix requirements

Minimum automated test groups:
1. **Profile resolution tests**: all legal/forbidden transitions map to expected profile.
2. **Check enforcement tests**: each critical check can independently force no-go.
3. **Reason-code determinism tests**: same inputs => same ordered reason code list.
4. **No-op guard tests**: same-state set/gate returns no-go + `policy_denied:no_state_change_requested`.
5. **Policy-forbidden tests**: policy-blocked transitions return `DENY-X`.
6. **Evidence completeness tests**: GP-2+ requires triad sections.
7. **Mutation-gate linkage tests**: `mode set` denied without fresh successful gate packet.
8. **Rollback anchor tests**: successful set emits rollback metadata.
9. **Watchdog posture tests**: `live` requires `W1+`; `honeypot` requires `W2+`.
10. **Run-linkage tests**: every gate/evidence record includes `run_id` + `security_report_ref`.
11. **Trigger-posture tests**: `watch/canary` require `isolation`; `live/honeypot` require `lockdown`.
12. **Lockdown-parameter tests**: heartbeat and baseline cadence escalations are enforced for `live/honeypot`.

## 16) Implementation notes for current release

- `--from` remains out-of-scope by design.
- Current-mode inference is mandatory and fail-closed.
- Scheduler-specified source-mode transitions are deferred to a future phase.
- Multi-modal simulation is first-class in this release (all modes may run under `sim` for validation).

## 17) Sign-off checklist (acceptance)

- [ ] All 8x8 transitions resolve to exactly one profile or explicit denial class.
- [ ] GP-3 and GP-4 always require approval checkpoint and full triad.
- [ ] `watch/canary` transitions enforce trigger posture `isolation`.
- [ ] `live/honeypot` transitions enforce trigger posture `lockdown`.
- [ ] Exit-code mapping conforms to `0/2/3/4/5` contract.
- [ ] All denial paths emit at least one normalized reason code.
- [ ] `mode set` is impossible without fresh successful gate packet.
- [ ] No secret value can appear in any output path.
- [ ] Every collection/gate/evidence record links `run_id` to `security_report_ref`.
- [ ] Every collection/gate/evidence record includes `posture_trigger_id` and `posture_trigger`.

## 18) Next actions (declared)

1. Update Job 0023 Markdown + JSON artifacts to mirror this trigger-posture model and data contract fields.
2. Implement `observerctl ops mode gate` checks for `C19`-`C22` with fail-closed reason codes.
3. Extend gate/evidence packet schemas to require `posture_trigger_id`, `posture_trigger`, `run_id`, and `security_report_ref`.
4. Add automated tests for isolation/lockdown posture mapping and lockdown parameter enforcement.
5. Produce a sample names-only security report artifact and validate `run_id -> security_report_ref` linkage end-to-end.
