# Simulation Sandbox CLI Surface Plan

> **Document ID**: SIMULATION_SANDBOX_CLI_SURFACE_PLAN_20260323  
> **Project**: Calamum Moltbook Observer  
> **Primary stakeholder / approver**: joediggidyyy  
> **Author**: ORACL-Prime  
> **Date**: 2026-03-23  
> **Status**: planned surface lock (pre-implementation detail capture)

## 1) Purpose

This document records the **planned human-facing CLI surface** for the sandbox/test-definition family.

The current local proof entrypoint lives at:

- `projects/calamum-moltbook-observer/src/simulation/run_simulation.py`

But the intended **operator-facing namespace** is:

- `observerctl sandbox *`

The goal is to stop design drift before the next implementation bite.

This surface is intended to:

- inventory sandbox/test definitions cleanly,
- show one definition in detail without crowding catalog views,
- execute sandbox probes via a script-first entrypoint,
- preserve names-only evidence discipline, and
- align human output frames with existing CodeSentinel CLI expectations.

## 2) Alignment surfaces reviewed before locking this plan

### 2.1 Session / awareness artifacts reviewed

- `.agent_session/policy_snapshot.md`
- `.agent_session/ops_awareness.md`
- `/memories/repo/ops_awareness_local_staleness_findings.md`
- `/memories/repo/session_memory_pin_refresh_findings.md`

### 2.2 Project and adjacent authority surfaces reviewed

- `projects/calamum-moltbook-observer/docs/CALAMUM_CODESENTINEL_JOB_EXECUTION_EXPECTATIONS.md`
- `projects/calamum-moltbook-observer/docs/OBSERVERCTL_CLI_TRANSITION_OPERATOR_GUIDE_20260221.md`
- `projects/calamum-moltbook-observer/docs/plans/OBSERVERCTL_MODE_TRANSITION_MATRIX_CHAPTER_20260221.md`
- `projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0023_OBSERVERCTL_COMMAND_SURFACE_PLANNING_20260221.md`
- `projects/calamum-moltbook-observer/src/simulation/README.md`
- `projects/calamum-moltbook-observer/src/tests/test_simulation_runner.py`
- `jobs/OPS_JOB_0031_JOB_EXECUTION_AUTOMATION_HARDENING_20260108.md`
- `jobs/JOB_0009_CODESENTINEL-CORE_IMPLEMENTATION_CLI-CHALLENGE-MESSAGING_20260306.md`
- `docs/planning/CLI_JOB_COMMAND_SURFACE_ROADMAP_20260303.md`

### 2.3 Alignment conclusions

1. **The intended operator namespace is `observerctl sandbox *`.**  
   The prior version of this plan scoped that point incorrectly. The sandbox/test-definition family should live under the observer CLI namespace rather than as a separate public runner-only surface.

2. **Implementation should be modular, not monolithic.**  
   Putting the public surface under `observerctl` does **not** imply stuffing more behavior into the existing monolithic `observerctl.py`. The preferred shape is a thin `observerctl` registration/router layer backed by modular sandbox helpers.

3. **Session awareness is advisory, not routing authority.**  
   Session snapshots were reviewed for drift awareness, but local authority for this lane remains the project docs/jobs above.

4. **Human CLI views must follow classed output-frame rules.**  
   Per adjacent CodeSentinel command-surface guidance, output frames are classed templates adapted to command intent while preserving schema invariants.

5. **`run_simulation.py` is the current local proof surface, not the target public family.**  
   The sandbox lane may continue to use the local runner while implementation is in flight, but the intended public/operator family is still `observerctl sandbox *`.

## 3) Scope boundary and non-goals

### 3.1 In scope

- a catalog/list surface for available sandbox definitions,
- a single-definition detail surface,
- a run surface for executing one definition,
- a run-review surface for already-produced artifacts,
- modular implementation boundaries behind `observerctl`,
- human + JSON output framing expectations.

### 3.2 Out of scope

- inventing a new top-level `codesentinel sandbox` production lifecycle family **instead of** the intended `observerctl sandbox *` family,
- implementing sandbox behavior by growing the existing `observerctl.py` monolith as the sole logic home,
- broad refactors unrelated to sandbox catalog/show/run ergonomics and modular extraction,
- raw shell orchestration as the primary user surface,
- secret-bearing outputs or environment-value printing.

## 4) Canonical nouns

To avoid future vocabulary drift, this lane locks the following nouns:

- **sandbox definition**: one named, runnable validation/probe target exposed through `observerctl sandbox *`
- **canonical definition id**: the authoritative selector string for one definition
- **run**: one execution instance of a sandbox definition
- **run review**: names-only summary of a previously written run artifact bundle

This plan uses **definition** consistently throughout.

## 5) Planned command topology

The planned structured surface is:

### 5.1 Primary family

- `observerctl sandbox list`
- `observerctl sandbox show <definition>`
- `observerctl sandbox run <definition>`
- `observerctl sandbox runs list`
- `observerctl sandbox runs show <run_id>`

### 5.2 Current local proof surface

Until the `observerctl sandbox` family lands, the local proof commands are:

- `run_simulation.py --list-definitions`
- `run_simulation.py <definition>`

Those local proof commands should use the **same canonical definition ids** as the intended `observerctl sandbox *` family. This lane does **not** plan a secondary naming layer.

## 6) Definition selector model

### 6.1 Canonical ids (currently known)

The currently observed canonical definition ids are:

- `feedback-loop`
- `metadata-contract`
- `baseline-monitor-runtime`

### 6.2 Exact selector rule

This lane should use **exact canonical definition ids only**.

There is no planned secondary naming table, no fuzzy selector layer, and no lineage shorthand in the public surface.

### 6.3 Resolution rules

Selector behavior should stay simple:

1. docs, help, list output, and JSON should all use the same canonical ids;
2. operator input should match the canonical id exactly;
3. unknown ids should fail closed;
4. human and JSON output should echo the selected canonical id without secondary resolution metadata.

## 7) The operator redline locked in this pass

### 7.1 Catalog compactness rule

**Compact catalog/list views should show canonical definitions only and should stay scan-first.**

This rule is now explicit and should be treated as a design lock unless joediggidyyy later changes it.

### 7.2 Reason

List/catalog views are plural surfaces and should optimize for:

- scanability,
- fast selection,
- minimal vertical noise,
- stable column alignment.

Compact inventory pages lose value quickly when they start carrying explanation fields that belong on single-target pages.

## 8) Planned output-frame classes by command intent

Following the adjacent CodeSentinel CLI guidance, human output frames should be adapted per command intent.

### 8.1 `observerctl sandbox list`

- **template_class**: `decision`
- **template_variant**: `catalog`
- **intent**: choose one definition from a compact inventory

Human output should be compact and scan-oriented.

### 8.2 `observerctl sandbox show <definition>`

- **template_class**: `validation`
- **template_variant**: `definition_detail`
- **intent**: inspect one definition thoroughly before execution

Human output should be the place where richer explanatory fields appear.

### 8.3 `observerctl sandbox run <definition>`

- **template_class**: `transition`
- **template_variant**: `execution`
- **intent**: launch one run and summarize where evidence landed

Human output should emphasize execution result, run id, output locations, and next review action.

### 8.4 `observerctl sandbox runs list`

- **template_class**: `validation`
- **template_variant**: `run_catalog`
- **intent**: inspect recent run inventory

### 8.5 `observerctl sandbox runs show <run_id>`

- **template_class**: `validation`
- **template_variant**: `run_review`
- **intent**: inspect one retained run bundle in detail

## 9) Human-output rules

### 9.1 Catalog/list surfaces (`observerctl sandbox list`, `observerctl sandbox runs list`)

Plural catalog pages should remain compact.

They should show only fields justified by the command intent, for example:

- canonical definition id / run id,
- short title or summary,
- status/stability,
- primary purpose,
- primary evidence/report target,
- last validation signal only if real data exists.

They should **not** show by default:

- template metadata,
- long methodology prose,
- redundant path explosions,
- JSON-schema housekeeping rows.

### 9.2 Single-target detail surfaces (`observerctl sandbox show`, `observerctl sandbox runs show`)

Single-target pages may expand into labeled sections such as:

- identity,
- purpose,
- selected definition,
- execution contract,
- output paths,
- evidence expectations,
- implementation notes / guardrails.

This is the correct place to show:

- definition-specific warnings,
- path conventions,
- run-review interpretation fields.

## 10) Planned `observerctl sandbox list` contract

### 10.1 Human view

The compact list should include one row per canonical definition.

Recommended columns:

- `Definition`
- `Purpose`
- `Class`
- `Writes`
- `Status`

Where:

- `Definition` = canonical id only
- `Purpose` = short bounded summary
- `Class` = e.g. `legacy-sim`, `metadata-probe`, `runtime-probe`
- `Writes` = primary output bucket such as `report_tmp/...` or `temp-only`
- `Status` = `stable`, `experimental`, `legacy`, or similarly bounded governed label

### 10.2 JSON view

`--json` should return:

- `template_class`
- `template_variant`
- `definitions[]`

Each definition row should include:

- `id`
- `title`
- `summary`
- `status`
- `category`
- `writes_to`

This preserves machine readability without bloating human output.

## 11) Planned `observerctl sandbox show <definition>` contract

### 11.1 Required sections

A detailed definition page should include:

1. **Identity**
   - canonical id
   - title
   - status/stability
   - category

2. **Purpose**
   - concise operator-facing explanation
   - what the definition proves or checks

3. **Selected definition**
   - canonical id
   - exact command spelling expected on the CLI surface

4. **Execution contract**
   - command that will be run internally
   - required/non-required environment expectations
   - whether it writes under `report_tmp/` or temp-only

5. **Outputs and evidence**
   - primary run index path
   - primary markdown/json review paths
   - whether the run is append-only indexed

6. **Guardrails**
   - names-only output rule
   - no secret printing
   - script-first execution reminder

### 11.2 Selector echo rule

The detail page may echo the selected canonical definition id, but it should not introduce secondary naming layers or resolution notes.

## 12) Planned `observerctl sandbox run <definition>` contract

### 12.1 Execution behavior

The run command should:

1. accept one canonical definition id;
2. fail closed on unknown definitions;
3. execute the mapped runner function;
4. emit a names-only execution summary;
5. point to produced report artifacts;
6. preserve existing append-only run-index behavior where already implemented.

### 12.2 Human output fields

The human frame should prioritize:

- decision/result (`pass`, `review`, `failed`, etc. as real data allows),
- canonical definition id,
- run id,
- primary report paths,
- next review command.

### 12.3 JSON output

The JSON payload should include:

- `template_class`
- `template_variant`
- `definition_id`
- `run_id`
- `result`
- `artifacts`

## 13) Planned `observerctl sandbox runs list` and `observerctl sandbox runs show` contracts

### 13.1 `sandbox runs list`

Compact inventory of retained run bundles.

Recommended fields:

- `Run ID`
- `Definition`
- `Timestamp`
- `Result`
- `Report`

### 13.2 `sandbox runs show <run_id>`

Detailed single-run page with:

- run id,
- definition id,
- execution timestamp,
- result,
- produced artifacts,
- objective/coverage matrix when present,
- remaining gaps if the run recorded them,
- interpretation text if already produced by the run itself.

This surface should read existing retained artifacts; it must not fabricate success semantics beyond what the run recorded.

## 14) Environment and path expectations

### 14.1 Environment posture

This surface is a **sandboxed validation** surface, not a production runtime control plane.

Therefore:

- it should continue to prefer script execution over complex terminal injection,
- it should keep evidence names-only,
- it should not print environment-variable values,
- it should preserve project-relative path reporting where possible.

### 14.2 Output locations

Current sandbox probes already lean on:

- `report_tmp/...`

That is consistent with this lane and should remain the primary retained review bucket for sandbox-run artifacts unless a future approved migration changes it.

## 15) One-push execution micro-plan

### 15.1 Historical one-push objective

This side lane was scoped to finish in one implementation push so the sandbox family would stop drifting and the main lane could return to the then-open **Frame 4 wrapup** immediately afterward.

The deliverable for this push is:

- a locked command family under `observerctl sandbox *`,
- exact canonical definition names with no secondary naming layer,
- implemented list/show/run/runs-list/runs-show surfaces,
- focused tests and docs updated in the same pass,
- a clean handoff back to the then-open Frame 4 wrapup lane.

### 15.2 Micro-frame A — surface lock before mutation

**Goal:** freeze the public nouns and commands before broader edits.

**Must lock:**

- command family = `observerctl sandbox *`
- canonical definitions = `feedback-loop`, `metadata-contract`, `baseline-monitor-runtime`
- exact-name-only selection
- no secondary naming table
- no secondary runner-only naming language in docs/help/output

**Exit evidence:**

- plan updated,
- local proof entrypoint updated to the same canonical names.

### 15.3 Micro-frame B — parser and command skeleton

**Goal:** land the command skeleton in `observerctl` without bloating unrelated lanes.

**Work items:**

1. add the `sandbox` family to `observerctl`
2. add subcommands:
   - `list`
   - `show <definition>`
   - `run <definition>`
   - `runs list`
   - `runs show <run_id>`
3. wire each subcommand to a dedicated helper surface rather than stuffing the logic inline

**Exit evidence:**

- help text shows the full sandbox family,
- each subcommand resolves to a callable path,
- unknown/missing arguments fail cleanly.

### 15.4 Micro-frame C — definition registry and catalog surface

**Goal:** create one authoritative definition catalog used by list/show/run.

**Work items:**

1. define one registry surface for the three canonical definitions
2. record for each definition:
   - id
   - title
   - summary
   - category
   - writes-to target
   - status
3. implement `observerctl sandbox list`
4. keep the list view compact and scan-first

**Exit evidence:**

- `list` returns exactly one row per canonical definition,
- no extra naming layer appears in human or JSON output.

### 15.5 Micro-frame D — definition detail and run surfaces

**Goal:** make one definition inspectable and runnable from the target CLI family.

**Work items:**

1. implement `observerctl sandbox show <definition>`
2. implement `observerctl sandbox run <definition>`
3. route runs into the existing retained evidence layout
4. keep run output names-only and action-oriented

**Detail page must answer:**

- what this definition proves
- what it writes
- where evidence lands
- what the next review command is

**Exit evidence:**

- `show metadata-contract` is readable and complete,
- `run metadata-contract` and `run baseline-monitor-runtime` produce reviewable outputs,
- failure on unknown definition is exact and closed.

### 15.6 Micro-frame E — retained run review surfaces

**Goal:** make already-written sandbox runs inspectable without re-running them.

**Work items:**

1. implement `observerctl sandbox runs list`
2. implement `observerctl sandbox runs show <run_id>`
3. read retained run bundles directly from recorded artifacts
4. avoid fabricating status beyond what the run recorded

**Exit evidence:**

- recent runs are discoverable,
- one run can be inspected from retained artifacts alone.

### 15.7 Micro-frame F — docs, tests, and closeout

**Goal:** close the lane completely in the same push.

**Work items:**

1. update focused tests for the new `observerctl sandbox` family
2. update the simulation/local-proof docs so they mirror the canonical definition names only
3. update this plan with the final implemented shape if it differs in any small non-drifting way
4. run focused validation for the touched surfaces

**Exit evidence:**

- focused tests pass,
- edited docs match implemented commands,
- no leftover temporary naming from this side lane remains in the touched files.

## 16) Return gate to the main lane

This side job is considered done when all of the following are true:

1. `observerctl sandbox list/show/run/runs list/runs show` exist and work for the canonical definitions;
2. the local proof surface uses the same canonical names only;
3. focused tests and docs are green/aligned;
4. there is no unresolved naming drift in the touched sandbox surfaces.

Once those conditions were met, the very next lane was:

- **return to the Frame 4 wrapup**

### 16.1 2026-03-23 completion note

This side lane has now landed its intended command family and cleared its return gate.

Fresh return-to-main-lane evidence:

- `observerctl sandbox list/show/run/runs list/runs show` implemented
- focused sandbox CLI validation passed
- fresh Frame 4 metadata probe run:
      - `report_tmp/frame4_metadata_contract_probe/runs/frame4-metadata-contract-20260323T074830Z/frame4_metadata_probe.md`
      - `report_tmp/frame4_metadata_contract_probe/runs/frame4-metadata-contract-20260323T074830Z/frame4_metadata_probe.json`

Observed Frame 4 reality at return time:

- sample-row metadata contract is green
- retained index/readback metadata is now green as well

So the return target that motivated this side lane has now been satisfied; Frame 4 is closed and the next active lane is beyond the metadata-contract seam.

As of the latest baseline-monitoring reconciliation, the active lane has advanced further: Frame 5 is also closed, and the current next bite is Frame 6 restart-safe monitor continuity under Job 0022.

## 17) Locked design decisions from this pass

- The public sandbox/test-definition inventory surface belongs under `observerctl sandbox *`.
- Canonical definition selection is exact-name-only: `feedback-loop`, `metadata-contract`, `baseline-monitor-runtime`.
- This lane uses one canonical naming set only.
- Compact plural surfaces stay scan-first; detail belongs on single-target pages.
- Human outputs must use classed template intent similar to adjacent CodeSentinel command-family conventions.
