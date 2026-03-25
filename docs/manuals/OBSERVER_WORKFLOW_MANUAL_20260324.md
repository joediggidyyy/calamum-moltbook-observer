# Observer Workflow Manual

**Document ID**: `OBSERVER_WORKFLOW_MANUAL_20260324`  
**Status**: Public workflow manual  
**Owner**: ORACL-Prime  
**Project**: Calamum Moltbook Observer  
**Last updated**: 2026-03-24

---

## Purpose and reader contract

This manual is the guided end-to-end operating companion for **Calamum Moltbook Observer**.

It is written for readers who need a confident, practical path through the observer from preparation to analysis. It explains what to have ready, how to approach the system safely, and how the guided operating path connects runtime work to baseline evaluation and downstream analysis.

## Quick navigation

### Orientation

- [Before touching the system](#before-touching-the-system)

### Baseline leg

- [Resource baseline preparation](#resource-baseline-preparation)

### Execution leg

- [First safe execution path](#first-safe-execution-path)

### Analysis leg

- [Preparing retained outputs for analysis](#preparing-retained-outputs-for-analysis)
- [Resource baselining analysis and comparison readiness](#resource-baselining-analysis-and-comparison-readiness)
- [Regression and comparative analysis](#regression-and-comparative-analysis)
- [Interpretation and reporting handoff](#interpretation-and-reporting-handoff)

### Troubleshooting leg

- [Troubleshooting and failure paths](#troubleshooting-and-failure-paths)

### Quick-reference leg

- [Quick-reference execution summary](#quick-reference-execution-summary)

### Who this manual is for

This manual is for three overlapping public audiences:

| Audience | Why this surface is useful |
|---|---|
| Operators | Provides a clear step-by-step path through the system. |
| Technical reviewers | Shows the complete operating flow without forcing the reader to reconstruct it from multiple surfaces. |
| Analysts | Explains how runtime outputs become inputs for baseline comparison, regression, and interpretation work. |

The manual is intended to be readable by a first-time technical user while preserving the real operating structure of the system.

### What this manual covers

This manual covers the practical guided path through the observer:

| Workflow leg | What the reader gets |
|---|---|
| Readiness and prerequisites | What must be in place before any baseline or runtime work begins. |
| Safety boundary | The approval, posture, and evidence rules that govern safe use. |
| Resource baseline preparation | How baseline evidence is gathered, processed, and judged usable. |
| First safe runtime execution | The canonical first execution path and what to check around it. |
| Analysis preparation | How runtime outputs are prepared for later analytical use. |
| Baseline comparison and regression framing | How the workflow connects operational outputs to comparison and model-facing analysis work. |
| Interpretation and reporting handoff | How the guided path hands off into interpretation and reporting surfaces. |
| Common interruption points | The failure paths most likely to interrupt the guided flow. |
| Quick-reference summary | A compact ordered checklist of the canonical path for readers who have completed the manual once. |

The goal is to help the reader move through the application in the right order with the right expectations at each step.

### Related reference surfaces

This manual works alongside the adjacent reference surfaces.

| Surface | Use it for |
|---|---|
| [`OBSERVER_SECURITY_MODEL_20260324.md`](OBSERVER_SECURITY_MODEL_20260324.md) | Security architecture, posture design, and enforcement model detail. |
| [`OBSERVERCTL_MODE_TRANSITION_MATRIX_20260221.md`](OBSERVERCTL_MODE_TRANSITION_MATRIX_20260221.md) | The formal runtime transition and gate contract. |
| [`OBSERVERCTL_RUNTIME_OPERATOR_GUIDE_20260221.md`](OBSERVERCTL_RUNTIME_OPERATOR_GUIDE_20260221.md) | Broader command-family reference, deeper operator playbooks, and expanded troubleshooting detail. |

### Suggested companion surfaces

Use these public surfaces alongside this workflow manual when you need deeper context:

| Surface | Role |
|---|---|
| [`../../README.md`](../../README.md) | Project scope and first-pass orientation. |
| [`../../SECURITY.md`](../../SECURITY.md) | Trust boundary, policy posture, and names-only security doctrine. |
| [`../../DATA_METHODOLOGY.md`](../../DATA_METHODOLOGY.md) | Telemetry, packet, and methodology contract detail. |
| [`OBSERVER_SECURITY_MODEL_20260324.md`](OBSERVER_SECURITY_MODEL_20260324.md) | Deeper security architecture and posture model detail. |
| [`OBSERVERCTL_MODE_TRANSITION_MATRIX_20260221.md`](OBSERVERCTL_MODE_TRANSITION_MATRIX_20260221.md) | Runtime transition and denial semantics reference. |
| [`OBSERVERCTL_RUNTIME_OPERATOR_GUIDE_20260221.md`](OBSERVERCTL_RUNTIME_OPERATOR_GUIDE_20260221.md) | Deeper CLI workflow, variant coverage, and troubleshooting. |
| [`INDEX.md`](INDEX.md) | Manual-set catalog and reading order. |
| [`../INDEX.md`](../INDEX.md) | Top-level documentation router. |

---

## Before touching the system

The observer is designed to be used deliberately. Before you gather baseline inputs, run commands, or prepare analysis inputs, confirm that the environment, safety posture, and evidence discipline are understood.

### Environment prerequisites

Before starting guided workflow steps, confirm the following foundation:

| Requirement | Why it matters |
|---|---|
| A working checkout with the public documentation surfaces available | The workflow assumes the reader can move between this manual and the adjacent public references. |
| A project-appropriate Python environment | The observer command surface depends on a usable runtime environment. |
| Access to the observer command surface in that environment | The guided path expects the canonical commands to be runnable where the work is being performed. |
| Access to any operator-local configuration or credentials required for the intended lane | Stricter runtime lanes depend on local readiness that is not embedded in the public repo. |
| Clear understanding of public docs versus local runtime evidence | The workflow depends on keeping public documentation and local evidence in their correct roles. |
| Permission to create and review local runtime artifacts | Guided execution and evidence review both depend on local artifact access. |

If the intended work involves stricter or real-source operation, the required configuration and credential presence checks must be satisfied before that lane begins.

### Approval and safety prerequisites

The observer should be approached with a simulation-first mindset unless a stricter lane is explicitly justified and approved.

Before continuing, use the following operating rules as the safety frame for the workflow:

| Rule | Meaning in practice |
|---|---|
| Upstream inputs are treated as hostile by default | The workflow assumes containment, verification, and guarded progression rather than casual trust. |
| Fail-closed denials are useful operating feedback | A denial is a signal to resolve a condition, not a cue to bypass the control. |
| Denied gate or transition checks should be resolved before continuing | Safe operation depends on interpreting and satisfying the gate, not skating around it. |
| Higher-risk lanes require stronger readiness and approval discipline | The workflow raises expectations as the source or posture becomes stricter. |
| Real-source and stricter posture work belongs after prerequisites are satisfied and understood | The safest first contact remains the simulation-first path unless stronger conditions are explicitly warranted. |

The workflow in this manual treats safety controls as part of the operating contract and everyday operating practice.

### Names-only and evidence discipline

All guided work in this manual assumes the project's names-only handling model.

In practical terms, that model means:

| Principle | Practical meaning |
|---|---|
| Public docs describe the contract and the safe operating path | The tracked repo explains how to work, not the raw evidence generated while working. |
| Runtime evidence remains local runtime output | Guided runs produce local evidence surfaces that support later review without becoming tracked public artifacts. |
| Raw content remains outside the normal persisted workflow | The workflow protects the names-only boundary throughout collection, review, and interpretation. |
| Each run preserves structured evidence for later review | The workflow remains auditable without weakening the project's evidence-handling discipline. |

Later sections build on this rule set. The reader should treat names-only handling, local evidence retention, and fail-closed execution as baseline operating assumptions from the first step onward.

[Back to top](#quick-navigation)

---

## Resource baseline preparation

Baseline preparation establishes the resource and readiness evidence needed for later execution and analysis work. In this system, a baseline is the retained reference point used to judge whether the observer has enough current resource evidence to support later comparison and higher-confidence operating decisions.

### What must be baselined

The baseline in this workflow is a names-only resource telemetry baseline.

It is built from the observer's resource-focused sampling streams so the reader can compare current operating conditions against a recent, structured reference window. The practical target is the resource behavior that later readiness checks, comparison work, and analysis steps depend on.

For guided baseline preparation, the important baseline inputs are:

| Baseline input | Role in the workflow |
|---|---|
| Normal resource stream | Captures ordinary resource behavior over the chosen collection window. |
| Baseline resource window | Captures tighter baseline-focused sampling for later comparison and readiness checks. |
| Analysis packet | Summarizes whether the collected baseline is sufficient to use. |

The baseline should therefore be understood as a small, structured set of resource observations plus a readiness judgment about whether that evidence is usable.

### How to gather baseline inputs

Gather baseline inputs in two deliberate phases:

1. collect a baseline-focused resource window,
2. collect a normal resource stream for the same operating lane.

**Canonical collection command — baseline window**

```text
observerctl baseline collect --source <sim|real> --mode <watch|canary|live|honeypot> --profile baseline --duration-sec <seconds> --interval-sec <seconds> --window-id <window_id> --json
```

Use the same command family with `--profile normal` to capture the normal stream for the same source and mode.

**Canonical collection command — normal stream**

```text
observerctl baseline collect --source <sim|real> --mode <watch|canary|live|honeypot> --profile normal --duration-sec <seconds> --interval-sec <seconds> --window-id <window_id> --json
```

For the guided path, treat the collection step as successful only when the collection packet returns a `go` decision and reports a non-zero sample count. The collection packet should also report the active profile, the collection window identifier, and the generated segment list for that collection run.

When a longer overnight or multi-phase baseline window is appropriate, the planning and collection flow should still remain grounded in the same baseline namespace: collect the baseline-focused window, collect the normal stream, then analyze the resulting lookback window before continuing.

### How to process baseline inputs

After gathering the baseline-focused and normal streams, process them through the baseline analysis step so the baseline is ready for later use.

**Canonical analysis command**

```text
observerctl baseline analyze --source <sim|real> --mode <watch|canary|live|honeypot> --hours <lookback_hours> --min-normal-samples <count> --min-baseline-samples <count> --json
```

This step converts the retained resource telemetry into a baseline-readiness packet that summarizes:

| Packet field family | What it tells the reader |
|---|---|
| Usable normal sample counts | How much ordinary resource evidence is available for the lookback window. |
| Usable baseline-window sample counts | How much baseline-focused evidence is available for comparison and readiness checks. |
| Baseline readiness decision | Whether the collected baseline is ready for later workflow use. |
| Evaluated baseline window | Which prepared baseline window the analysis is actually judging. |
| Resource statistics | The summary values later comparison work depends on. |

For workflow purposes, a baseline is processed and ready when the analysis packet returns a `go` decision, reports `baseline_ready = true`, and confirms that the minimum required normal and baseline-window sample counts have been satisfied.

Use the baseline for later workflow steps only when the analysis packet confirms that result. When confirmation is incomplete, extend or recollect the baseline before continuing.

### Baseline quality checks

Before moving on, confirm that the baseline is usable.

At minimum, check the following:

| Check | What to confirm |
|---|---|
| Collection success | The collection step succeeded for the intended source and mode. |
| Stream coverage | Both the normal stream and the baseline-focused window were collected. |
| Analysis decision | The analysis packet returned a `go` decision. |
| Sample sufficiency | The reported sample counts satisfy the required minimums. |
| Window identity | The baseline window being analyzed is the one you intended to prepare. |

The baseline needs more work when any of the following are true:

- collection returns a fail-closed denial,
- the analysis step reports that the baseline window is incomplete,
- the normal or baseline-window sample counts are below the required threshold,
- the reported window or mode differs from the intended operating lane, or
- the results are too thin or incoherent to support confident evidence-based comparison.

When that happens, recollect or extend the baseline window before continuing. A weak baseline should be fixed at the baseline stage rather than carried downstream into execution, comparison, and regression work.

[Back to top](#quick-navigation)

---

## First safe execution path

This section begins after baseline preparation is complete. The goal is to move into the first real execution leg with a path that is guarded, observable, and easy to verify.

For this guided manual, the default first execution lane is a **simulation-first canary run**. That lane exercises the transition and evidence workflow under `isolation` posture without requiring the stricter dependency and approval burden that comes with real-source work.

### Choose the starting lane

Use the following lane choice as the decision frame for a first run:

| Lane | When to choose it | Why it is or is not the default |
|---|---|---|
| `sim:canary` | Default first guided run | Exercises the guarded transition path, evidence packet generation, and runtime checks while staying inside the simulation-first boundary. |
| `sim:watch` | Lighter inspection or lower-intensity runtime validation | Useful for gentler observation, but this manual prefers `sim:canary` for the first full guided execution because it more clearly exercises the runtime path readers need to learn. |
| `real:*` | Only after stronger prerequisites, dependency checks, and explicit approval are already in place | Real-source work belongs later in the progression and should not be treated as the normal first-contact lane. |

For most readers, begin with `sim:canary` unless an approved execution plan clearly calls for a different lane.

### Run preflight and gate checks

Move from readiness into execution with a small guarded sequence.

**Canonical preflight command**

```text
observerctl ops preflight --source sim --json
```

**Canonical mode-gate command**

```text
observerctl ops mode gate --to canary --source sim --json
```

Use the outputs in this way:

| Step | What to confirm in the result | What to do if it denies |
|---|---|---|
| Preflight | The runtime packet is readable and the current runtime surfaces are coherent enough to evaluate. | Stop and resolve the reported fail-closed conditions before attempting a transition. |
| Mode gate | `decision = go` for the requested `sim:canary` target lane. | Read the `reason_codes`, resolve the blocking condition, and re-run the gate rather than forcing the transition. |

The gate stage is the formal go/no-go decision for the requested lane. Treat it as the authoritative checkpoint before any state-changing command is run.

### Perform the first collection window

Once preflight and gate checks are clean, perform the first guided execution leg with the guarded transition workflow.

**Canonical transition command**

```text
observerctl ops mode transition --to canary --source sim --event first-safe-run --json
```

Read the result as a short operating sequence:

| Sequence point | Expected result |
|---|---|
| Transition decision | The packet returns `decision = go`. |
| Target state | The packet reflects the requested `sim:canary` destination. |
| Evidence emission | The transition writes structured names-only evidence as part of the guarded workflow. |
| Stop condition | If the transition does not return a clean `go` decision, stop here and work from the returned `reason_codes` instead of improvising the next step. |

This manual uses the atomic transition command because it keeps gate, state change, and evidence emission in one guarded path. Deeper variants and alternate playbooks remain in the operator guide.

### Capture closure evidence

Treat the run as complete only after closure evidence confirms that the lane is in the expected state and the evidence surface is present.

Use the following closeout checks:

**Current-state check**

```text
observerctl ops mode current --json
```

**Evidence-index check**

```text
observerctl ops evidence index --json
```

**Closure health check**

```text
observerctl health full --json
```

Review them with this closeout gate:

| Closeout check | What a healthy close looks like | What to do if it is incomplete |
|---|---|---|
| Current state | The current runtime state reflects the intended `sim:canary` lane. | Do not assume the transition settled correctly; stop and review the transition output and reason codes. |
| Evidence index | The evidence surface shows the new transition/evidence packet for the run you just performed. | Treat the run as still open until the evidence path is present and reviewable. |
| Full health packet | The runtime, baseline, librarian, watchdog, and policy surfaces remain readable enough to support the next step. | Resolve the fail-closed condition before treating the run as a stable completed lane. |

The first safe execution path is complete when the transition succeeds, the target lane is visible in current state, and closure evidence is present and reviewable.

[Back to top](#quick-navigation)

---

## Preparing retained outputs for analysis

Once the first safe execution path is closed, the next job is to gather the retained lane surfaces that analysis work actually depends on. This is the bridge between a successfully completed run and a comparison-ready dataset.

The goal is not to read every local artifact by hand. The goal is to confirm that the correct lane surfaces exist, that they belong to the intended source and mode, and that they are coherent enough to support baseline-aware comparison.

### Identify the retained outputs for the executed lane

Use the retained output families below as the primary analysis handoff set for the lane you just ran.

| Output family | Canonical surface | Role in the workflow |
|---|---|---|
| Observer-derived metrics stream | `logs/data/calamum/observer_derived/<source>/<mode>/moltbook_metrics.jsonl` | Primary names-only runtime stream for the executed lane. This is the main lane-scoped metrics input for later comparison and interpretation work. |
| Evidence index | `logs/data/calamum/observer_derived/<source>/<mode>/evidence/index.jsonl`, summarized by `observerctl ops evidence index --json` | Lane-scoped catalog of retained observerctl evidence packets and the quickest way to confirm the latest recorded event in the current lane. |
| Observerctl evidence packets | `logs/data/calamum/observer_derived/<source>/<mode>/evidence/observerctl_<event>_<timestamp>.json` | Per-run operational evidence for gate, transition, closeout, and baseline-analysis steps, including run-linkage and decision fields. |
| Resource retention index | `logs/data/calamum/observer_derived/<source>/<mode>/resource/index.jsonl` | Retained index for the resource segments that support baseline-aware readiness and comparison review. |
| Baseline-analysis packet family | Emitted by `observerctl baseline analyze --source <sim|real> --mode <mode> ... --json` and retained under the lane `evidence/` surface | Supplies the explicit baseline-ready judgment, sample sufficiency view, and resource summary fields used to decide whether comparison work should proceed. |
| Public report surfaces | `docs/reports/` | Reader-facing summaries and reporting references. These are downstream interpretation surfaces, not the primary retained inputs for immediate lane analysis. |

The key distinction is simple: runtime outputs and evidence packets are the working inputs for the analysis leg, while public reports remain reader-facing outputs that may later summarize what those lane surfaces show.

### Retrieve and verify the correct lane surfaces

Retrieve the lane summary first, then confirm the evidence view for that same lane.

**Canonical lane-census command**

```text
observerctl librarian stats --json
```

**Canonical evidence-index command**

```text
observerctl ops evidence index --json
```

**Optional current-state confirmation**

```text
observerctl ops mode current --json
```

Read the lane-census result with the following checks:

| Check in `librarian stats` output | Why it matters |
|---|---|
| The row for the intended mode is the active ingest lane (`ingest_mode_active = true`) | Confirms you are reading the currently active lane rather than a neighboring mode. |
| `ingest_source_scope` matches the intended source axis | Prevents mixing `sim` and `real` outputs during later analysis. |
| `session_records_display` is present and plausible for the recent run | Confirms the lane has current-session material rather than only a historical shell. |
| `records_total_display` is interpreted alongside `archive_records` | Helps the reader separate current lane activity from older retained history. |
| The mode row you plan to analyze is the same lane you just executed | Keeps comparison work tied to the intended run context. |

Read the evidence-index result with the following checks:

| Check in `ops evidence index` output | Why it matters |
|---|---|
| `scope.source` matches the intended lane source | Confirms the evidence catalog belongs to the correct source axis. |
| `scope.mode` matches the intended lane mode | Confirms the evidence catalog belongs to the correct runtime lane. |
| `records` is non-zero when a completed run should already have emitted evidence | Confirms there is retained observerctl evidence to review. |
| `latest.event` and `latest.packet_path` correspond to the expected run window | Helps avoid carrying forward stale or unrelated evidence. |
| The latest packet is reviewable and the event type makes sense for the step just completed | Confirms the retained evidence surface is usable, not merely present. |

Use `observerctl ops mode current --json` when you want one extra confidence check that the currently visible runtime state still agrees with the lane you intend to analyze.

If the source, mode, event timing, or retained counts do not line up, stop here and re-establish the correct lane context before continuing. A mixed-lane retrieval step produces weak analysis even when every individual command succeeds.

### Prepare runtime outputs for analysis use

In this workflow, “prepared for analysis” means the retained lane surfaces are coherent enough to support baseline-aware review and later comparison work. It does not mean the system has already converted the lane into a final model-ready dataset.

Use the following preparation sequence:

| Preparation step | What to do | Result you want |
|---|---|---|
| Lock the lane identity | Carry forward one intended `source`, `mode`, and run context from the retrieval step. | Every retained surface you use belongs to the same lane. |
| Treat the lane metrics stream as the primary runtime input | Use the lane-scoped `moltbook_metrics.jsonl` stream as the main execution-output surface. | Runtime observations are anchored to the executed lane rather than to an aggregate summary. |
| Use evidence packets to verify context and closeout | Confirm that the latest retained packets align with the completed run and its closeout checks. | The analysis leg inherits a reviewable operational context instead of a floating dataset. |
| Use the resource index as the baseline-facing companion surface | Keep the resource retention view alongside the runtime metrics stream. | Later baseline-aware comparison has the resource context it depends on. |
| Separate current-session interpretation from archive totals | Read display-safe totals and archive totals together rather than assuming every count is new ingest. | Density and record-count interpretation stays grounded in the actual lane mix. |

The preparation leg is complete when the reader can point to one coherent lane package: the runtime metrics stream, the evidence index and latest reviewable packet, and the retained resource view for that same source and mode.

[Back to top](#quick-navigation)

---

## Resource baselining analysis and comparison readiness

After the lane outputs are retrieved and prepared, use the baseline-analysis surface to decide whether the dataset is strong enough for comparison work. This stage reconnects the completed execution leg to the baseline contract established earlier in the manual.

### Run resource baselining analysis on the prepared lane

Use the same canonical baseline-analysis surface introduced in the baseline-preparation leg.

**Canonical baseline-analysis command**

```text
observerctl baseline analyze --source <sim|real> --mode <watch|canary|live|honeypot> --hours <lookback_hours> --min-normal-samples <count> --min-baseline-samples <count> --json
```

After a completed run, this packet tells the reader whether the lane now has enough retained resource evidence to support baseline-aware comparison rather than only operational closeout.

Focus on the following packet signals:

| Packet signal | What it tells the reader |
|---|---|
| `decision` | Whether the analysis step clears or denies the lane for continued use. |
| `baseline_ready` | Whether the current retained evidence is explicitly judged usable for baseline-aware work. |
| `sample_counts` | Whether the normal and baseline-window counts are strong enough for the requested thresholds. |
| `minimum_requirements` | What the packet expected the lane to satisfy before returning a `go` decision. |
| `baseline_window_id` | Which baseline window the packet is actually evaluating. |
| `resource_statistics` | The summary values that later comparison and interpretation work will rely on. |
| `reason_codes` | The exact signals explaining why more collection, baseline work, or verification is needed. |

When the packet returns `decision = go` and `baseline_ready = true`, the reader has a baseline-aware confirmation that the prepared lane is ready to support the next analytical step.

### Decide whether the prepared dataset is fit for comparison work

Operational success and analytical usefulness are related, but they are not identical. A run can complete cleanly and still need more baseline support or better lane coherence before it is ready for meaningful comparison.

Use the following fit-for-comparison gate:

| Signal | Meaning | Next action |
|---|---|---|
| `decision = go` and `baseline_ready = true` | The retained lane satisfies the current baseline-readiness contract. | Proceed to the next comparison or regression-focused step. |
| Lane scope agrees across `librarian stats`, `ops evidence index`, and the baseline-analysis packet | The prepared dataset belongs to one coherent source/mode lane. | Proceed with confidence that you are not mixing lanes. |
| `session_records_display` is plausible and the retained packet paths are reviewable | The lane has usable current-session material plus reviewable evidence context. | Continue into comparison work. |
| Baseline analysis returns `no-go` or reports incomplete sample coverage | The lane is operationally present but not yet baseline-ready for comparison. | Extend or recollect the baseline inputs, then re-run analysis. |
| Source, mode, or event context is mismatched across retrieval surfaces | The prepared dataset is not lane-coherent. | Stop, retrieve the correct lane surfaces, and rebuild the analysis handoff. |
| Archive totals dominate the visible counts and current-session context is too thin to interpret safely | The lane may be too sparse or too mixed for a clean next-step comparison. | Narrow the scope, extend the lane, or gather additional current-session material before continuing. |

Treat the dataset as fit for comparison only when both conditions hold:

1. the run closed successfully as an operational event,
2. the retained lane also clears the baseline-readiness and coherence checks needed for analysis.

That distinction keeps the analysis leg honest. It ensures that later comparison, regression, and reporting work starts from a dataset that is not only present, but genuinely usable.

[Back to top](#quick-navigation)

---

## Regression and comparative analysis

Once the prepared lane clears the baseline-readiness and coherence checks, the next step is a comparative read. In this manual, comparative analysis means a disciplined review of how the lane differs from its baseline-aware reference surfaces, not an automatic declaration that the system has completed a full model-evaluation campaign.

### Frame comparative analysis in public-safe workflow terms

Use the comparison surface map below to keep this stage grounded in what the current public contract actually supports.

| Comparison surface | What it supports | What it does not yet prove |
|---|---|---|
| Lane-scoped `moltbook_metrics.jsonl` stream | Shows the current names-only runtime observations for the lane under review. | It does not by itself prove whether observed differences are statistically durable or analytically meaningful. |
| `observerctl librarian stats --json` | Shows the current lane census, display-safe totals, and archive context needed to interpret scale correctly. | It does not by itself distinguish strong comparative signals from thin or mixed evidence. |
| `observerctl ops evidence index --json` plus latest reviewable packet | Confirms the comparative read remains tied to the intended source, mode, and recent event context. | It does not by itself establish whether the lane differences justify a strong analytical claim. |
| `observerctl baseline analyze ... --json` packet | Shows whether the lane has enough retained resource evidence to support baseline-aware comparison. | It does not by itself explain every runtime difference or replace analyst judgment. |
| [`../reports/AGGREGATE_REPORT.md`](../reports/AGGREGATE_REPORT.md) | Supplies public-facing runtime and family-level context that can help frame interpretation. | It is not the primary per-lane evidence surface for the comparison step. |

In practical terms, this workflow uses the word **regression** in a narrow and public-safe sense: a difference that remains meaningful after the lane, baseline, and reporting context have been checked together. That is a stronger claim than “something changed,” and a narrower claim than “the whole analytical pipeline has fully validated a model-facing conclusion.”

### Run the comparative review on the prepared lane

Read the prepared lane surfaces together rather than one at a time.

| Surface combination | What to look for | Why it matters |
|---|---|---|
| Lane metrics stream + baseline-analysis packet | Whether the lane differences are accompanied by a baseline-ready packet with adequate sample support. | Keeps comparison tied to a dataset that is strong enough to compare responsibly. |
| `librarian stats` + operator-guide density rules | Whether the displayed counts reflect current-session activity, archive-heavy totals, or a mixed view. | Prevents the reader from mistaking stored volume for fresh comparative evidence. |
| Evidence index + latest reviewable packet | Whether the lane context still matches the intended source, mode, and event window. | Prevents stale or neighboring-lane evidence from contaminating the comparison. |
| Lane metrics stream + aggregate runtime snapshot | Whether the local lane picture fits the broader current runtime posture. | Helps the reader interpret a lane-level difference inside the current public headline rather than in isolation. |
| Baseline-analysis packet + threshold-calibration snapshot | Whether the lane’s current differences deserve extra attention when read against the current anomaly-calibration context. | Keeps threshold material in its proper role as context, not as the only decision rule. |

When you read these surfaces, use the density sanity rule already established elsewhere in the docs:

1. verify the current source and mode,
2. separate active-session totals from archived totals,
3. check whether the visible density is window-based rather than direct current ingest,
4. confirm that mixed historical streams are not doing most of the talking.

Pause the comparative read when any of the following are true:

- the lane identity is not consistent across the retained surfaces,
- archive totals dominate the visible signal but current-session material is thin,
- the baseline-analysis packet is not ready,
- the latest evidence packet is stale or clearly belongs to another event window, or
- the current runtime posture is degraded enough that interpretation should stay provisional.

### Decide whether the observed differences are analytically meaningful

Use the following judgment gate before carrying a difference forward into interpretation.

| Signal | Interpretation | Next move |
|---|---|---|
| The lane is baseline-ready, lane-coherent, and the comparative difference persists across the retained surfaces | The observed difference is strong enough to carry into the interpretation step. | Proceed to a public-safe interpretation summary. |
| The lane shows an interesting difference, but the baseline support or current-session depth is marginal | The difference is plausible but still too thin for a strong comparative claim. | Extend the lane, improve the baseline support, or gather more current-session evidence first. |
| The difference appears only when archive totals dominate the picture | The visible change may be storage-mix or history-weight driven rather than a clean current-lane signal. | Narrow the scope and re-read the current-session lane context before proceeding. |
| The retained surfaces disagree about source, mode, event, or timing | The comparative read is not yet trustworthy. | Rebuild the lane package and repeat the comparison step. |
| The aggregate/public context and the lane-level context point in materially different directions | The result needs cautious interpretation and should remain provisional. | Continue only with explicit caveats, or gather additional evidence first. |

At this stage, treat a difference as analytically meaningful only when it survives both checks:

1. it appears in a coherent, baseline-ready lane package,
2. it still makes sense when read against the current public runtime and reporting context.

That standard helps the workflow manual stay honest. It encourages readers to carry forward disciplined comparative results rather than any change that happens to look dramatic on first glance.

[Back to top](#quick-navigation)

---

## Interpretation and reporting handoff

Once the comparative read is strong enough to carry forward, the next job is to express the result clearly and route it into the correct reporting surface. This part of the workflow is about disciplined interpretation and routing, not about copying local runtime artifacts into tracked public docs.

### Interpret comparative results with public-safe language

Use the following interpretation guide when summarizing a comparative result.

| Finding class | Safe public phrasing | Overreach to avoid |
|---|---|---|
| Stronger-than-baseline difference with coherent lane support | “The prepared lane shows a stronger-than-baseline difference that remains visible across the retained runtime and baseline-review surfaces.” | Do not claim that one lane alone proves a universal behavioral rule. |
| Mixed or provisional difference | “The current lane shows a mixed signal that warrants cautious interpretation and may benefit from additional evidence.” | Do not present a provisional result as if it were settled. |
| Archive-heavy or thin-current-session signal | “The current comparison is influenced by archive-weighted or thin-session context, so the result should be treated as preliminary.” | Do not imply that displayed totals automatically represent fresh current-run intensity. |
| Runtime posture conflict during interpretation | “The comparative signal is being read alongside a runtime posture that still shows unresolved health or gate concerns.” | Do not write as though the runtime environment were fully stable when it is not. |
| Threshold-calibration context only | “The current threshold-calibration snapshot provides contextual support for interpretation.” | Do not treat the threshold snapshot as a complete substitute for the lane comparison itself. |

Keep interpretation tied to what the public-safe surfaces actually show:

- current-state interpretation should stay anchored to the lane package and current runtime context,
- broader public interpretation should stay anchored to aggregate and ledger surfaces,
- causal or sweeping claims should remain proportionate to the evidence currently in hand.

### Hand off into reporting surfaces

After the interpretation is stated clearly, route the result to the surface that best matches its role.

| Handoff target | When to use it | What it contains |
|---|---|---|
| [`../reports/AGGREGATE_REPORT.md`](../reports/AGGREGATE_REPORT.md) | When the reader needs the current public runtime headline plus bounded cross-family analytical context. | Public-facing synthesis of runtime evidence and selected report-family context. |
| [`../reports/PUBLIC_RUN_LEDGER.md`](../reports/PUBLIC_RUN_LEDGER.md) | When the reader needs a stable public snapshot of what reporting families exist and how large or current they are. | Runtime-first public ledger snapshot plus family-level census context. |
| [`../reports/GENERATED_REPORT_SURFACES.md`](../reports/GENERATED_REPORT_SURFACES.md) | When the reader needs to know which generated families exist and what role each plays. | Public reference for generated report families and their routing. |
| [`../reports/AGGREGATE_REPORT_SCHEMA.md`](../reports/AGGREGATE_REPORT_SCHEMA.md) | When the reader needs the contract for how a bounded aggregate report should be structured. | Public schema and analytical contract for aggregate reports. |
| Local runtime evidence surfaces | When the reader is still validating or extending the comparison before any broader public summary is warranted. | The lane-scoped evidence, metrics, and baseline packets used during the workflow itself. |

Use this handoff rule:

- keep local lane evidence as the working proof surface,
- use public tracked docs to summarize, route, and contextualize,
- promote only the bounded public-safe conclusions that the tracked reporting surfaces are meant to carry.

That division preserves the repo’s public/local boundary while still giving the reader a complete end-to-end path from preparation through reporting handoff.

[Back to top](#quick-navigation)

---

## Troubleshooting and failure paths

The workflow in this manual runs through six legs: baseline preparation, first safe execution, data retrieval and analysis preparation, resource baselining analysis, regression and comparative analysis, and interpretation and reporting handoff. Each leg has a small set of interruption signatures that typically require the reader to stop and check something before continuing.

This section maps those signatures to fast first-check actions and routes more complex resolution work to the appropriate deeper reference surface.

### Interrupt-point taxonomy

The table below maps each guided workflow leg to its most common interrupt signature. A reader who is currently in a specific leg can scan to that row to orient quickly.

| Workflow leg | Interrupt signature | First-check action | Escalation pointer |
|---|---|---|---|
| Baseline preparation | Gate or baseline check returns `no-go`; baseline marked not ready | `observerctl baseline status --json` | Transition matrix — `critical_check_failed:baseline_not_ready` |
| First safe execution | Mode transition denied; heartbeat or posture check failed | `observerctl health quick --json` | Transition matrix — `critical_check_failed:observer_service_heartbeat_stale`, `watchdog_heartbeat_stale`, or `watchdog_trigger_posture_invalid` |
| Data retrieval and analysis preparation | Evidence file appears missing from the expected canonical path | Confirm source/mode scope; check `index.jsonl` in the corresponding evidence directory | Operator guide — evidence-file missing procedure |
| Resource baselining analysis | No usable baseline package available for comparison; comparison surface is blank or incomplete | `observerctl baseline status --json`; confirm a ready package exists for the lane being compared | Operator guide — baseline readiness procedure |
| Regression and comparative analysis | Gate packet stale; comparison run denied before it starts | `observerctl ops gate-check --source <sim\|real> --json`; inspect `reason_codes` | Transition matrix — `critical_check_failed:gate_packet_missing_or_stale` |
| Interpretation and reporting handoff | Closure gate fails; finalization attempt denied | `observerctl health quick --json`; check working tree state | Operator guide — closure gate failure procedure |

### Resolution path per interrupt class

For each interrupt class above, the table below provides the minimal resolution flow.

| Symptom | First check | Clearing indicator | Re-entry point |
|---|---|---|---|
| Baseline not ready | `observerctl baseline status --json`; review the `ready` field and any listed blockers | `baseline.ready: true` with no unresolved blockers | Return to [Resource baseline preparation](#resource-baseline-preparation) to confirm the full baseline package is in order, then continue to [First safe execution path](#first-safe-execution-path). |
| Heartbeat or posture check failure | `observerctl health quick --json`; inspect command families showing unhealthy state | All health checks returning a passing state | Return to the [First safe execution path](#first-safe-execution-path) gate sequence and re-run preflight before the mode gate. |
| Evidence file missing | Confirm source/mode scope; check `index.jsonl` in the expected evidence path | Target evidence entry appears in `index.jsonl` with the correct event tag and timestamp | Return to [Preparing retained outputs for analysis](#preparing-retained-outputs-for-analysis) and re-run the evidence index command to confirm retrieval. |
| No usable baseline for comparison | `observerctl baseline status --json`; confirm the baseline scope matches the lane being compared | A positioned, ready baseline package matching source/mode is present | Return to [Resource baseline preparation](#resource-baseline-preparation) to complete baseline preparation before proceeding to [Resource baselining analysis and comparison readiness](#resource-baselining-analysis-and-comparison-readiness). |
| Gate packet missing or stale | `observerctl ops gate-check --source <sim\|real> --json`; check `reason_codes` for the specific denial | Gate returns `decision: go` with a fresh timestamp | Run a fresh gate before re-attempting the comparison sequence in [Regression and comparative analysis](#regression-and-comparative-analysis). |
| Closure gate failure | `observerctl health quick --json`; check working tree and memory health state | All checks pass; no unresolved fail-closed conditions remain | Return to [Interpretation and reporting handoff](#interpretation-and-reporting-handoff) and confirm the reporting target is correct before closing. |

### Are you ready to continue?

| Condition | Gate decision |
|---|---|
| None of the interrupt signatures above describe your current situation | Cleared — continue to [Quick-reference execution summary](#quick-reference-execution-summary) or return to the workflow leg you were in. |
| One or more interrupt signatures apply and the resolution path has not yet cleared | Blocked — work through the corresponding resolution path before continuing. |
| Your situation is not covered by the tables above | Route to the operator guide for expanded troubleshooting detail. |

The operator guide (`OBSERVERCTL_RUNTIME_OPERATOR_GUIDE_20260221.md`) is the next escalation surface for anything that falls outside the patterns above.

[Back to top](#quick-navigation)

---

## Quick-reference execution summary

The following checklist covers the canonical path from readiness confirmation through reporting handoff. One primary action per step. Use this section when you have already read the full manual once and want a fast-scan companion for re-running the workflow.

### Canonical path checklist

1. **Confirm prerequisites**

   ```
   observerctl health quick --json
   ```

   Passing indicator: clean health check with no unresolved posture concerns.

2. **Gather the resource baseline**

   ```
   observerctl baseline status --json
   ```

   Passing indicator: `baseline.ready: true` with no unresolved blockers.

3. **Run preflight and mode gate**

   ```
   observerctl ops preflight --source <sim|real> --json
   observerctl ops mode gate --to <watch|canary> --source <sim|real> --json
   ```

   Passing indicator: gate returns `decision: go`.

4. **Execute the mode transition**

   ```
   observerctl ops mode transition --to <watch|canary> --source <sim|real> --event <event> --json
   ```

   Passing indicator: evidence packet written; `from_state` and `to_state` fields present.

5. **Index the evidence**

   ```
   observerctl ops evidence index --json
   ```

   Passing indicator: target evidence entry appears in the index with the correct event tag.

6. **Prepare retained outputs for analysis**

   Confirm source/mode scope. Verify `index.jsonl` is current. Apply the density-sanity check to any aggregate display before comparing: confirm the active-versus-archived split and confirm whether reported density is window-based or reflects direct ingestion rate.

7. **Run the baseline comparison**

   Position the ready baseline package against the retained lane. Check for archive-weighting and confirm the comparison is not influenced by thin current-session data before treating the result as stable.

8. **State the comparative finding**

   Use the finding-class language from [Regression and comparative analysis](#regression-and-comparative-analysis). Confirm the signal is strong enough to carry forward before routing.

9. **Route to the reporting handoff surface**

   Match the finding type to the handoff target from [Interpretation and reporting handoff](#interpretation-and-reporting-handoff). Keep local lane evidence as the working proof surface. Promote only public-safe bounded conclusions to the tracked reporting surfaces.

That is the end of the canonical path. For any step that does not pass cleanly, see [Troubleshooting and failure paths](#troubleshooting-and-failure-paths).

[Back to top](#quick-navigation)