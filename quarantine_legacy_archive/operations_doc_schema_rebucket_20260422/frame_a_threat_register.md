# Frame A threat register and stop-condition vocabulary

## Metadata

- Generated at (UTC): `2026-04-21T03:28:56.9561330Z`
- Task ID: `calamum-moltbook-observer-job-0001-docs_general-20260420`
- Lane label: `OBSERVER_JOB_0001`
- Frame: `A`
- Artifact role: `local names-only Frame A contract packet`
- Authority posture: supporting evidence for the active frame; does not replace `operations/tasks.json`, `JOB.json`, `QS.json`, or `QF.md`
- Runtime surface: `observerctl sandbox`
- Scope posture: `observer security audit only`
- Scenario execution claimed: `false`
- Companion machine-readable contract: `projects/calamum-moltbook-observer/local_untracked/reports/operations/frame_a_result_matrix.json`

## A1 - authority and scope confirmation

### Current-state authority note

Current authority lives in:

- `operations/tasks.json`
- `projects/calamum-moltbook-observer/jobs/JOB_0001_CALAMUM-MOLTBOOK-OBSERVER_AUDIT_DOCS-GENERAL_20260420/JOB.json`
- `projects/calamum-moltbook-observer/jobs/JOB_0001_CALAMUM-MOLTBOOK-OBSERVER_AUDIT_DOCS-GENERAL_20260420/QS.json`
- `projects/calamum-moltbook-observer/jobs/JOB_0001_CALAMUM-MOLTBOOK-OBSERVER_AUDIT_DOCS-GENERAL_20260420/QF.md`

Current project-goal and security-contract sources used for Frame A:

- `projects/calamum-moltbook-observer/planning/CALAMUM_OBSERVER_AGGRESSIVE_SECURITY_AUDIT_PROPOSAL_20260419.md`
- `projects/calamum-moltbook-observer/SECURITY.md`
- `projects/calamum-moltbook-observer/docs/manuals/reference/SECURITY_MODEL.md`

Current lane facts confirmed during Frame A execution:

- task status remains `in-progress`
- current focus frame remains `A`
- `observerctl sandbox` remains the canonical orchestration surface for the security audit
- this artifact is contract-locking evidence only and does not claim that any `S1-S14` scenario has already been run

### Active-scope confirmation note

- Frame A remains contract-locking and tranche-preparation work only.
- The first widening boundary after Frame A is the `A -> B -> C` tranche only.
- Publication, journal, conference, and unrelated remediation work remain deferred.
- High-risk later-frame work (`D-G`) stays deferred until the `A/B/C` tranche is reviewed as safe to widen.
- Names-only persistence, fail-closed denial, and retained-evidence truthfulness remain non-negotiable.

## Locked threat-class register

| Threat class                | Covered scenarios | Boundary under test                                                                   | Required truth signal                                                             |
| --------------------------- | ----------------- | ------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| `TC_POSTURE_GATE`           | `S1-S2`           | posture transitions, gate freshness, replay resistance, run-linkage discipline        | denials and stale-state rejections stay legible, linked, and fail-closed          |
| `TC_NAMES_ONLY_TRUTH`       | `S3-S4`           | names-only persistence, packet/artifact/report agreement, packet narration discipline | no raw leakage survives and no packet-only success claim outranks artifacts       |
| `TC_RUNTIME_CHAOS`          | `S5-S6`           | watchdog liveness, runtime spoof resistance, lockdown behavior under pressure         | spoofed or stressed runtime state degrades or denies truthfully                   |
| `TC_AUTHORITY_LINEAGE`      | `S7-S8`           | baseline authority creation, lineage integrity, manifest-backed routing               | convenience paths fail closed and lineage drift is surfaced instead of normalized |
| `TC_DELEGATION_MAINTENANCE` | `S9-S10`          | delegated release, vault posture, maintenance sequencing                              | malformed or missequenced requests are denied with explicit reason codes          |
| `TC_PROOF_IDENTITY`         | `S11`             | same-version / same-build security proof integrity                                    | mismatched proof is rejected or flagged before promotion claims are made          |
| `TC_PUBLICATION_BOUNDARY`   | `S12`             | public report boundary, local/public split, names-only publication discipline         | publication remains derived, human-facing, and names-only                         |
| `TC_BOOTSTRAP_CATALOG`      | `S13-S14`         | bootstrap-root readiness and exact-name sandbox catalog authority                     | missing roots fail closed and catalog drift remains visible to the operator       |

## Locked scenario register

| ID    | Frame | Threat class                | Adversarial goal                                                                                         | Required test classes                 | Expected safe outcome                                                   |
| ----- | ----- | --------------------------- | -------------------------------------------------------------------------------------------------------- | ------------------------------------- | ----------------------------------------------------------------------- |
| `S1`  | `B`   | `TC_POSTURE_GATE`           | force a stricter mode or source transition without satisfying prerequisites                              | `sandbox-run`, `pytest-regression`    | denied transition with truthful reason codes and retained evidence      |
| `S2`  | `B`   | `TC_POSTURE_GATE`           | reuse stale gate packets, stale run context, or stale report linkage to clear a gate                     | `sandbox-run`, `fault-injection`      | stale or replayed state rejected rather than silently reused            |
| `S3`  | `C`   | `TC_NAMES_ONLY_TRUTH`       | coerce raw content, raw payload fragments, or secret-like values into retained outputs                   | `sandbox-run`, `secret-boundary-scan` | outputs remain names-only and no secret or raw material persists        |
| `S4`  | `C`   | `TC_NAMES_ONLY_TRUTH`       | make packets claim artifacts or success states that artifacts and reports do not support                 | `sandbox-run`, `diff-contract-review` | no false-success narrative survives cross-surface review                |
| `S5`  | `D`   | `TC_RUNTIME_CHAOS`          | appear healthy through forged, stale, future-skewed, or partial heartbeat state                          | `sandbox-run`, `fault-injection`      | spoofed liveness rejected or degraded explicitly                        |
| `S6`  | `D`   | `TC_RUNTIME_CHAOS`          | continue optimistically under synthetic CPU, RAM, or cadence stress that should trigger stronger posture | `sandbox-run`, `chaos-stress`         | lockdown or denial path triggers truthfully                             |
| `S7`  | `E`   | `TC_AUTHORITY_LINEAGE`      | create reviewed or comparison-baseline authority through an ordinary convenience path                    | `sandbox-run`, `pytest-regression`    | authority creation remains manifest-backed and fail-closed              |
| `S8`  | `E`   | `TC_AUTHORITY_LINEAGE`      | emit report or review outputs that point to forged or mismatched run lineage                             | `sandbox-run`, `diff-contract-review` | lineage drift is surfaced instead of normalized                         |
| `S9`  | `F`   | `TC_DELEGATION_MAINTENANCE` | obtain a protected-source release with malformed requester, attestation, or source linkage               | `sandbox-run`, `pytest-regression`    | malformed delegated release requests are refused                        |
| `S10` | `F`   | `TC_DELEGATION_MAINTENANCE` | mutate protected state while vault posture or maintenance sequencing should deny the action              | `sandbox-run`, `fault-injection`      | lock, unlock, relock, and rebaseline rules remain explicit and enforced |
| `S11` | `F`   | `TC_PROOF_IDENTITY`         | present security-adjacent proof from the wrong build identity or outside the sandbox lane                | `sandbox-run`, `artifact-forensics`   | version/build mismatch or non-sandbox proof is rejected or flagged      |
| `S12` | `G`   | `TC_PUBLICATION_BOUNDARY`   | leak local runtime authority, raw residue, or sensitive lineage into reader-facing report routes         | `sandbox-run`, `secret-boundary-scan` | publication remains derived, reader-facing, and names-only              |
| `S13` | `G`   | `TC_BOOTSTRAP_CATALOG`      | break or starve runtime/bootstrap roots and see whether the stack invents fallback health                | `sandbox-run`, `fault-injection`      | missing roots become truthful no-go or degraded state                   |
| `S14` | `G`   | `TC_BOOTSTRAP_CATALOG`      | make unregistered, alias-colliding, or mismatched sandbox definitions look canonical                     | `sandbox-run`, `pytest-regression`    | exact-name catalog discipline holds and drift stays visible             |

## Stop conditions

Immediate stop and review is required if any lane attempts or implies:

- raw Moltbook-content persistence
- uncontrolled third-party probing
- unsandboxed host mutation
- reviewer-facing claims unsupported by retained audit evidence
- packet/report/artifact disagreement that is not explicitly surfaced as a failure
- widening beyond the `A/B/C` tranche without explicit review

Interpretation guardrails that remain locked:

- denied, blocked, and fail-closed outcomes are positive security findings when retained evidence supports them
- no scenario advances into broader pressure if packet, artifact, and report agreement is already broken in the current tranche
- no machine-readable reason-code field should carry freeform narrative, raw content, secret material, or unredacted local authority residue

## Reason-code vocabulary

Reason codes remain allowlisted lowercase names-only tokens in `family:detail` form. Machine-readable packets should carry tokens, while explanatory prose stays in `findings` or review notes.

| Reason code                            | Meaning                                                                       | Required handling                                                  |
| -------------------------------------- | ----------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| `frame_a:authority_chain_confirmed`    | current authority chain was re-grounded before contract locking               | keep as Frame A provenance only; do not reuse as scenario evidence |
| `frame_a:scope_confirmed`              | active scope remained bounded to the observer security audit lane             | carry with Frame A handoff packet when scope discipline matters    |
| `frame_a:threat_register_locked`       | the threat register is the current approved vocabulary surface                | cite when later rows inherit this register                         |
| `frame_a:result_matrix_locked`         | the machine-readable row contract is frozen for first-tranche use             | cite when later rows inherit the matrix contract                   |
| `outcome:denied_as_designed`           | the stack refused an action for the expected safety reason                    | pair with concrete evidence and agreement checks                   |
| `outcome:blocked_as_designed`          | the stack prevented the attempted action before unsafe widening               | pair with the blocking condition and retained review evidence      |
| `outcome:fail_closed_as_designed`      | the stack terminated or degraded rather than continuing optimistically        | pair with the explicit fail-closed trigger                         |
| `outcome:inconclusive_review_required` | the run did not support a clean safety claim or a clean vulnerability claim   | keep the row open and require retained review before widening      |
| `outcome:widening_requires_review`     | additional pressure would exceed the currently locked boundary without review | stop widening and route the decision explicitly                    |
| `stop:raw_content_persistence_risk`    | raw-content persistence risk was observed or would have been required         | stop immediately and keep the result names-only                    |
| `stop:names_only_boundary_at_risk`     | names-only retention or secret-boundary discipline is at risk                 | stop and review the artifact set before any more pressure          |
| `stop:packet_artifact_divergence`      | packet claims and artifact reality disagree                                   | treat as a failure of truthfulness until resolved                  |
| `stop:unsandboxed_mutation_requested`  | a requested action would exceed sandbox containment                           | deny and route for explicit approval instead                       |
| `stop:external_probe_out_of_scope`     | a requested action would widen into external or third-party probing           | deny and keep the lane local-only                                  |
| `stop:security_report_linkage_missing` | a required run-linkage or security-report field is absent or incoherent       | deny the claim and require linkage repair                          |
| `stop:baseline_freshness_missing`      | freshness, baseline sufficiency, or dependency evidence is stale or absent    | deny escalation and preserve fail-closed behavior                  |
| `handoff:frame_b_seed_ready`           | the `S1-S4` seed map is locked and Frame B can begin bounded preparation      | use only after readback confirms the same story across artifacts   |
| `handoff:frame_b_widening_not_ready`   | Frame B preparation is still blocked by a contract or evidence issue          | keep current focus on contract repair instead of scenario widening |

## Names-only and retained-evidence expectations

- Every future scenario review packet must include `findings`, `artifact_paths`, `result_matrix`, `provenance`, `methodology`, and `process` sections.
- Run-linkage fields remain required when a gate or posture transition contract applies: `run_id`, `posture_trigger_id`, `posture_trigger`, and `security_report_ref`.
- Every admitted scenario must include `sandbox-run` plus at least one additional test class.
- High-risk scenarios should target three proof lanes when practical.
- Packet, artifact, report, and lineage surfaces must agree before any success claim graduates out of the lane.
- No raw content, secret material, or reader-facing shadow authority should persist in these local evidence artifacts.

## Bounded Frame B handoff

Current Frame A outputs now locked:

- threat-class register covering `S1-S14`
- stop-condition and reason-code vocabulary
- retained review packet contract
- machine-readable result-matrix contract
- first-tranche `S1-S4` seed mapping

Frame B may begin bounded preparation only when:

- `JOB.json`, `QS.json`, `QF.md`, and the Frame A evidence artifacts still tell one coherent story
- each `S1-S4` row retains at least two named proof tactics
- required agreement checks remain attached to each row
- no request widens the lane beyond the `A/B/C` tranche without explicit review

Current handoff posture: `ready_for_frame_b_preparation`

Native next step when the operator chooses to begin `S1/S2` work: use the canonical frame-transition path to advance from `A` into `B`.
