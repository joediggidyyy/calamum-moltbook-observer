# ObserverCTL DS CLI and Wizard Plan

**Document ID**: `OBSERVERCTL_DS_CLI_AND_WIZARD_PLAN_20260325`  
**Status**: Working plan  
**Owner**: ORACL-Prime  
**Project**: Calamum Moltbook Observer  
**Last updated**: 2026-03-25

## Purpose

This plan captures the active implementation-planning lane for wiring the observer data-science operations into `observerctl`.

It preserves the working decisions already reached so the CLI design can advance on-disk rather than relying on chat state.

## Scope of the planned extension

The current `observerctl` surface already organizes observer functionality into clean peer namespaces:

- `sandbox`
- `ops`
- `baseline`
- `librarian`
- `watchdog`
- `health`
- `policy`

The data-science lane should be added as a new peer namespace rather than being mixed into runtime/security families.

**Proposed namespace**:

- `observerctl ds *`

This keeps runtime operations separate from analysis/model operations while preserving the existing parser shape.

## Minimal command surface

The preferred automation path remains a few simple commands that wrap the existing analysis entrypoints.

### Primary commands

| Command | Purpose | Current underlying surface |
|---|---|---|
| `observerctl ds build` | Build a dataset from one or more telemetry JSONL inputs. | `analysis.dataset_builder` |
| `observerctl ds train` | Train a supervised or unsupervised model from a dataset manifest. | `analysis.train_model` |
| `observerctl ds evaluate` | Evaluate a heuristic or trained model and emit run artifacts. | `analysis.evaluation_harness` |
| `observerctl ds score` | Score a dataset with an unsupervised model and emit anomaly scores. | `analysis.score_unsupervised` |
| `observerctl ds run` | Run an opinionated end-to-end flow for demo or pipeline execution. | thin `observerctl` orchestration layer |

### Run submodes

| Command | Purpose |
|---|---|
| `observerctl ds run demo` | Execute the current end-to-end observer demo flow, wrapping `src/analysis/run_demo.py`, then summarize the resulting artifacts. |
| `observerctl ds run pipeline` | Execute build -> train -> evaluate, with optional score -> threshold phases when unsupervised mode is selected. |

### Meaning of the demo lane

In this plan, the **existing demonstration lane** means the current observer-scoped end-to-end demo path already present in the repository:

- `src/analysis/run_demo.py`

That script already exercises the practical demonstration sequence:

1. generate synthetic data,
2. build a dataset,
3. train supervised and unsupervised models,
4. evaluate a trained model,
5. emit artifacts for inspection.

So `observerctl ds run demo` should not invent a second demo implementation. It should wrap and normalize the existing demonstration path behind the `observerctl ds` surface.

## Interactive advanced-user path

The preferred name for the interactive lane is:

- `observerctl ds wizard`

This name is explicit, user-legible, and clearer than `menu` for first-contact operators.

## Wizard design goals

The wizard should serve advanced users without replacing the automation surface.

### Functional goals

1. Show the full parameter state at all times.
2. Let operators edit one parameter at a time from a numbered menu.
3. Preserve already-entered values when switching to guided prompting.
4. Allow a guided prompt cycle for missing or review-worthy values.
5. Display the exact equivalent non-interactive command before execution.
6. Enforce careful blocking and validation before a run is allowed.
7. Render professionally in plain terminal output without requiring rich UI dependencies.

## Intention-preservation notes

The small interaction details in this lane are part of the intended product behavior, not incidental polish.

They should be preserved as design requirements rather than treated as optional UI cleanup.

### Current intention to preserve

- `observerctl ds wizard` is the preferred advanced-user entrypoint name.
- the wizard should feel compact, deliberate, and professional in a plain terminal.
- low character count is an explicit UX goal.
- disciplined vertical footprint is an explicit UX goal.
- structure should communicate intent before labels or help text do.
- headings should be short, but not so compressed that new users cannot infer their meaning.
- users should be allowed to rely on intuition instead of reading long instructions.
- already-entered values must carry forward across edit and prompt flows.
- prompt mode should reuse prior values by default.
- destructive or secondary actions should appear only when context makes them relevant.
- one-off helper actions should not be permanently visible if reselection behavior already makes the function obvious.
- terminal-native discoverability should exist for terse labels that may not be obvious on first view.
- `?` with no parameter should reveal help for the current scope only.
- from the main menu, `?` should reveal the full long-form menu list in a temporary help view.
- from a focused section, `?` should reveal help for that section only.
- `? <item>` should reveal item-specific detail in a temporary peek view.
- execution should remain blocked until validation succeeds.
- the wizard should remain visually readable even in cramped terminal conditions.
- the menu flow should support bidirectional navigation between a main menu and deeper sections.

### Specific micro-interactions to preserve

- reselecting an empty field means `enter value`.
- reselecting a populated field should not open a large submenu.
- reselecting a populated field should offer the smallest relevant choice set, such as `keep / clear / new`.
- `clear` should only appear when a value already exists.
- prompt-cycle behavior should use the same value-reuse logic as direct editing.
- prompt-cycle modes should stay split into `missing`, `recommended`, and `all`.
- the layout should avoid spending characters on actions that users will naturally infer.
- the layout should avoid repeating explanations that are already communicated by grouping, ordering, or current state.
- terse headings should have an on-demand explanation path rather than permanently expanded labels.
- scope help and item-specific help should share the same `?` mental model.
- section navigation should always allow returning to the main menu without losing current state.
- section navigation should allow moving from one section to another without restarting the wizard.

## Recommended wizard interaction model

The wizard should use a two-region console layout rendered as simple, deterministic terminal text.

### Region A: current configuration panel

This panel stays at the top of each interaction cycle and shows:

- workflow type
- selected profile
- input path(s)
- dataset manifest path
- output directory
- model type
- seed
- split ratios
- max FPR
- labels present / absent
- threshold settings
- execution mode
- command preview status
- validation state per field

Each field should display one of:

- `set`
- `default`
- `missing`
- `invalid`
- `derived`

### Region B: action menu

The action menu should expose numbered choices such as:

1. set workflow
2. edit inputs
3. edit outputs
4. edit model settings
5. edit evaluation settings
6. load from existing manifest or artifact
7. review generated command
8. run prompt cycle
9. validate current configuration
10. execute
11. reset all
12. exit

There should be no dedicated `reset one field` action.

Instead, if the operator reselects a field that already has a value, the next prompt should offer a compact branch such as:

- keep
- clear
- new

That is more intuitive, costs fewer screen characters overall, and matches what a user is likely to try first without being instructed.

### Left-side vertical menu option

It is possible to use a left-side vertical action menu in a terminal and it does not appear inherently problematic.

In fact, for cramped selection menus, it may improve legibility if implemented carefully.

### Recommendation on left-side menu usage

Use a left-column vertical menu **only if** the rendering remains plain, stable, and width-aware.

The strongest layout candidate is a two-column view:

- left column: short action list or section selector,
- right column: current parameter panel, checks, and command preview.

This can improve scanning because the eye can anchor to a narrow action rail while the main content stays grouped on the right.

### Benefits of a left-side vertical menu

- clearer scanning in cramped terminals,
- improved line-by-line readability,
- more stable action placement across redraws,
- less visual crowding in the main parameter panel,
- easier separation between `where I am` and `what I can do`.

It also creates a natural home for a terminal-compatible `peek` interaction if the action rail contains terse labels.

### Risks of a left-side vertical menu

- true side-by-side layout can break down in narrow terminal widths,
- long action labels can steal too much horizontal room,
- if both columns are dense, the screen can feel busier rather than clearer,
- redraw alignment becomes more fragile if line wrapping is not controlled.

### Best-fit recommendation

Treat the left-side menu as a **responsive layout option**, not a fixed requirement.

Recommended behavior:

- use two columns when terminal width is comfortably available,
- fall back to a stacked single-column layout when width is constrained,
- keep left-column labels very short,
- reserve most horizontal space for the right-hand parameter panel.

This gives the legibility benefits of a vertical action rail without making the UI brittle.

### Suggested left-column content

If a left-side rail is used, keep it extremely short. It should act more like navigation than explanation.

Suggested entries:

- flow
- in
- out
- model
- eval
- cmd
- check
- run
- exit

If drafts are enabled later:

- save
- load

Avoid longer labels in the left column unless there is clear evidence they improve comprehension enough to justify the width cost.

If any short label risks ambiguity, it should not be permanently expanded. Instead, it should support a compact `peek` behavior.

Examples:

- `model` -> model family, train settings, seed, artifacts
- `eval` -> labels, max FPR, threshold/report settings
- `cmd` -> equivalent command preview and export path
- `check` -> validation state and blockers

### Suggested responsive rule

For professional behavior in plain terminals:

- wide terminal -> two-column layout,
- medium terminal -> stacked layout with compact headings,
- narrow terminal -> single active section view with breadcrumb-style context.

That last fallback is important. In a truly cramped terminal, showing one focused section at a time may be more readable than any full-screen multi-section layout.

### Opinion on practicality

Yes, a left-side vertical menu is feasible and potentially useful.

My main caution is that the **goal is legibility, not literal left-sideness**.

If a left rail improves readability at the current width, use it.
If it starts to crush the content panel, drop back to a stacked or section-focused view.

So my recommendation is:

- support a left-side vertical menu when width allows,
- make it compact,
- keep it responsive,
- never let it force wrapping in the main content panel.

## Terminal-compatible `peek` behavior

Since a GUI hover panel is not available in a plain terminal, the equivalent behavior should be a temporary, dismissible help reveal built around `?`.

### Decided `peek` model

The help model should support two closely related behaviors:

1. `?` with no parameter
  - shows help for the current scope,
  - opens as a temporary help view,
  - dismisses with `Esc` when the operator is ready.

  Scope rules:

  - from the main menu, `?` shows the full long-form menu list,
  - from a focused section, `?` shows only that section's long-form help.

2. `?` with a parameter, section name, or current selection
  - shows an item-specific detail peek,
  - explains the selected terse heading,
  - briefly summarizes what is edited or reviewed there,
  - may include one or two high-value current state details,
  - dismisses without changing state.

This preserves one mental model:

- `?` means `show me more`

with scope determined by current context or supplied target.

### Recommended trigger behavior

- `?` alone -> current-scope help
- `? <item>` -> item-specific peek
- `Enter` -> open normally
- `Esc` -> dismiss help / peek or move back

If direct single-key handling is not used in the first implementation, the same behavior can be exposed through typed commands with the same semantics.

### What main-menu help should show

The main-menu help view should be brief, not a second manual.

It should show:

- short item name,
- long-form name,
- a few descriptive words,
- no deep prose,
- no state mutation.

Example:

```text
flow   workflow and run type
in     inputs and sources
out    outputs and artifact paths
model  model family and training
eval   labels, fpr, threshold, reports
cmd    command preview and export
check  validation and blockers
run    execute current config
exit   leave wizard
```

This gives the user the full list in readable long form without permanently increasing default screen noise.

### What section-scope help should show

The section-scope help view should stay even shorter than the main-menu help view.

It should show:

- the section name in long form,
- the fields or concerns covered there,
- any short action hints needed in that section,
- no unrelated menu items.

### What item-specific peek should show

The item-specific peek should stay short and structured.

For a section heading or left-rail item, it should show:

- plain-language meaning,
- what can be edited there,
- whether the section is complete / blocked / derived,
- any especially relevant current values.

Example for `eval`:

```text
eval
labels, max fpr, threshold, reports
state: ready
max fpr: 0.01
labels: present
```

That is enough to remove ambiguity without permanently expanding the menu.

### Best placement for help and peek

The default help/peek placement should be an inline lower panel.

Reasons:

- keeps the main layout intact,
- avoids stealing width from the content panel,
- behaves well in cramped terminals,
- is easy to dismiss,
- is the safest plain-terminal default.

A right-side transient pane may still be used as a responsive enhancement in wide terminals, but it should not be the primary or required behavior.

### Why this combined model is better

This preserves the low-character design goal while still making short labels learnable.

Benefits:

- keeps the default screen compact,
- supports new-user orientation,
- avoids permanent width consumption,
- teaches the terse vocabulary over time,
- uses one consistent help key,
- separates main-menu orientation from local detail,
- keeps focused sections simpler by showing only scope-relevant help.

## Main menu and bidirectional navigation

The wizard should adopt a main-menu-plus-sections model with bidirectional navigation.

### Recommended navigation shape

- main menu
  - flow
  - in
  - out
  - model
  - eval
  - cmd
  - check
  - run
  - exit
- section view
  - focused fields for that section
  - local edit actions
  - back to main
  - next section
  - previous section

This is preferable to a flat single-screen action list because it improves legibility and reduces crowding.

### Bidirectional navigation requirements

- users must be able to enter a section and return to the main menu at any time,
- users must be able to move from one section directly to adjacent sections,
- current state must persist across all movement,
- no navigation action should silently discard entered values,
- breadcrumbs or a short location line should show the current position.

Example:

- `ds wizard > model`
- `ds wizard > eval`
- `ds wizard > check`

### Why this is a strong fit

This approach combines several good suggestions already accepted in this lane:

- the `model` / `eval` split,
- left-side or compact vertical section selection,
- responsive layouts for cramped terminals,
- low character count through terse headings,
- on-demand discoverability through scope-based `?` help and item peek rather than persistent explanation.

It also mirrors how users naturally think:

- choose an area,
- edit what matters there,
- move sideways or back,
- validate,
- run.

## Prompt-cycle behavior

The last menu choice requested in the live planning lane is a prompt-driven path that cycles through needed values.

### Proposed behavior

- `run prompt cycle` should walk the operator through required fields in a stable order.
- already-entered values must be shown and retained by default.
- the operator should be able to:
  - keep current value,
  - replace current value,
  - clear current value,
  - accept a derived default.
- prompt cycling should skip fields that are already valid unless the operator explicitly chooses `review all fields`.

When prompt mode encounters a field that already has a value, it should use the same compact reuse pattern as direct field editing:

- accept current value immediately,
- allow `clear`, or
- allow `new` input.

This keeps the interaction model consistent across both direct-edit and prompt-cycle paths.

### Recommended prompt-cycle modes

To improve usability, the prompt lane should expose three options instead of a single monolithic prompt action:

1. `prompt missing` — only asks for missing or invalid values.
2. `prompt recommended` — asks for fields that are commonly tuned for the chosen workflow.
3. `prompt all` — full interview from top to bottom.

This keeps the user's desired prompt concept intact while reducing unnecessary re-entry.

## Assessment of the requested console/panel model

The requested model is sound and should be professional if implemented as a disciplined state machine rather than a loose chain of `input()` calls.

### Strengths of the requested model

- immediate clarity: operators can see all parameters before execution
- discoverability: advanced users do not need to memorize flags
- continuity: manually entered values can carry into prompt mode
- safety: blocked execution can be explained before launch
- professionalism: a structured layout feels deliberate rather than improvised

### Primary risks

- a large menu can become visually noisy if every parameter is editable from one flat list
- repeated full-screen redraws can feel jumpy in plain terminals
- a single generic `prompt` option can become ambiguous unless it is scoped to missing, recommended, or all fields
- too much inline prose can make the wizard feel slower than direct commands
- excessive labels and helper text can consume horizontal and vertical budget without adding meaning if structure already communicates intent

## Recommendations to improve usability and professionalism

### 1. Use workflow presets first

The first wizard decision should be workflow selection:

- build dataset
- train model
- evaluate model
- score dataset
- run demo
- run pipeline

That lets the parameter panel populate only the relevant fields instead of showing every possible knob up front.

Once workflow is chosen, the user should move through section-based navigation rather than a single monolithic menu. This will improve readability and make terse section labels more workable.

### 2. Separate required fields from advanced fields

The panel should group fields into:

- required
- optional
- derived
- advanced

This gives the operator a cleaner first read and reduces cognitive load.

### 3. Keep a persistent command preview block

At the bottom of each redraw, show:

- `equivalent command`
- `execution readiness`
- `blocking issues`

This makes the wizard teach the CLI while remaining operationally useful.

### 4. Treat execution as a blocked state transition

`execute` should remain disabled until validation passes.

Suggested states:

- `draft`
- `needs-input`
- `invalid`
- `ready`
- `running`
- `complete`
- `failed`

This will make the flow more reliable and easier to test.

### 5. Support artifact import and carry-forward

To reduce retyping, the wizard should allow loading values from:

- dataset manifest
- training manifest
- existing model path
- previous run ledger

This is a more efficient professional behavior than forcing every value to be entered manually.

### 6. Use spacing and whitespace as the main visual system

Follow existing CodeSentinel-style terminal discipline:

- one compact title line
- one blank line before each major section
- fixed ordering of sections
- aligned labels for parameter rows
- short validation messages
- no decorative clutter
- ASCII-safe output by default

Character count should be treated as a first-class design constraint.

That means the wizard should prefer:

- short section titles,
- short action labels,
- status tokens instead of sentences,
- structural grouping instead of explanatory prose,
- context-sensitive choices instead of permanently advertised features.

If the structure already implies the available action, do not spend extra characters naming it.

This principle also applies to layout mode. If a left rail already makes the action structure obvious, the main panel should not repeat the same navigation meaning in long-form prose.

If terse headings are used, the scope-based `?` help model should carry the burden of first-time discoverability so the steady-state layout can stay compact.

### 7. Prefer deterministic redraws over terminal tricks

A professional wizard does not require a heavy TUI dependency.

A simple redraw pattern is likely sufficient:

1. title
2. current workflow summary
3. parameter table
4. validation block
5. command preview block
6. numbered actions
7. prompt line

This is more portable and easier to keep aligned with `observerctl`'s current plain-output style.

Vertical space should be managed just as carefully as character count. The goal is not maximal whitespace; it is disciplined whitespace.

Recommended rule:

- keep separation between sections,
- compress within sections,
- avoid repeating headings or hints that the current layout already makes obvious.

If a two-column layout is used, preserve these same rules inside each column:

- short labels,
- stable alignment,
- minimal wrapping,
- no decorative filler.

The same rule applies to help and peek rendering: it should be short, deterministic, and dismissible without changing the underlying state.

### 8. Add a field-level edit path and a guided interview path

The best combination is not menu *or* prompt. It is both:

- direct edit for users who know what they want
- prompt cycle for guided completion

That matches the desired behavior while staying efficient.

Field-level editing should lean on user intuition before explicit labeling. If a populated field is selected again, the wizard should assume the user intends to modify it and respond with the smallest viable choice set rather than a verbose explanatory sub-menu.

At the section level, the same principle applies: if a terse section name is potentially unclear, support scope help and item peek instead of permanently replacing it with a long heading.

### 9. Add `save draft` and `load draft`

If the wizard is expected to support serious advanced use, draft persistence would significantly improve usability.

Suggested commands surfaced through the wizard:

- save current draft
- load saved draft
- export command

This supports interrupted work without requiring the user to restart from scratch.

### 10. Keep `--json` out of the wizard surface

The wizard should remain human-oriented.

Machine-readable outputs should still come from the non-interactive commands. The wizard can display the equivalent command that the operator may run later with `--json` if needed.

## Suggested wizard menu skeleton

```text
observerctl ds wizard

workflow: run pipeline
profile: supervised
state: needs-input

required
  1. input jsonl path           missing
  2. output directory           set        demo_output/pipeline
  3. model type                 set        supervised
  4. seed                       default    42

optional
  5. split train                default    0.70
  6. split val                  default    0.15
  7. split test                 default    0.15
  8. max fpr                    default    0.01

artifacts
  9. dataset manifest           derived    <pending>
 10. model path                 derived    <pending>

validation
  - input jsonl path is required
  - output directory is valid

command preview
  observerctl ds run pipeline --input ... --out-dir ... --model-type supervised --seed 42

actions
  11. prompt missing
  12. prompt recommended
  13. prompt all
  14. review command
  15. validate
  16. execute
  17. save draft
  18. load draft
  19. exit
```

This skeleton should be treated as structural rather than literal. The final implementation should continue trimming labels and menu text wherever intuition and layout already communicate the intent.

In particular:

- avoid redundant words like `field`, `setting`, or `option` when the list context already makes that clear,
- prefer short verbs,
- avoid showing destructive or secondary actions until they are contextually relevant,
- only show `clear` when a value already exists.

If a left-side vertical menu is used, the same compression rule becomes even more important because the left rail consumes width that would otherwise belong to the content panel.

## Proposed execution frame-set

Implement the `observerctl ds` lane as a sequence of narrow frames. Each frame should land one coherent capability slice, then stop for validation before the next one.

### Frame 1 — land the DS command spine

**Goal**:

- add the `observerctl ds` namespace and the command-family skeleton without yet building the full wizard

**Tracked edit targets**:

- `src/observerctl.py`
- `src/tests/test_observerctl.py`
- `docs/manuals/OBSERVERCTL_DS_CLI_AND_WIZARD_PROPOSAL_20260325.md`

**Required work**:

- add `observerctl ds` as a top-level peer namespace
- add parser scaffolding for:
  - `build`
  - `train`
  - `evaluate`
  - `score`
  - `run`
  - `wizard`
- keep outputs aligned with existing `observerctl` JSON/human conventions
- make `ds` discoverable in CLI help

**Do not do in this frame**:

- no end-to-end wizard loop yet
- no draft persistence yet
- no heavy terminal layout logic yet

**Exit criteria**:

- `observerctl -h` exposes the `ds` namespace
- `observerctl ds -h` exposes the planned command family
- the CLI shape is stable enough for later frames to fill in implementation detail

#### Frame 1 micro-plan — create the DS CLI spine without behavior sprawl

##### Micro-frame 1A — add top-level parser namespace

**Goal**:

- add `ds` as a first-class top-level namespace beside the existing runtime families

**Tracked edit targets**:

- `src/observerctl.py`

**Required work**:

- add the `ds` parser namespace
- keep naming aligned with the established `observerctl` command-family pattern
- ensure help output remains compact and predictable

**Exit evidence**:

- `observerctl ds -h` resolves through the parser without errors

##### Micro-frame 1B — add subcommand skeletons

**Goal**:

- define the stable DS command surface before wiring full behavior

**Required work**:

- add parser entries for `build`, `train`, `evaluate`, `score`, `run`, and `wizard`
- add `run demo` and `run pipeline` submodes
- reserve flag names consistent with the current analysis entrypoints

**Guardrail**:

- no attempt to finish all execution behavior in the same micro-frame

**Exit evidence**:

- the entire DS command tree is visible through help output

##### Micro-frame 1C — align DS output contract

**Goal**:

- keep the new surface consistent with the current `observerctl` JSON/plain output contract

**Required work**:

- decide how `ds` commands will emit human output vs `--json`
- keep names-only, deterministic output behavior
- avoid inventing a second CLI output style

**Exit evidence**:

- the DS surface inherits the same output discipline as the rest of `observerctl`

##### Micro-frame 1D — add parser-level test coverage

**Goal**:

- prove the new command tree exists and parses cleanly

**Tracked edit targets**:

- `src/tests/test_observerctl.py`

**Required work**:

- add tests covering `observerctl ds` help / parser reachability
- cover the main subcommands and `run` submodes

**Exit evidence**:

- parser tests pass for the DS command spine

##### Frame 1 completion criteria

Frame 1 is complete only when all of the following are true:

- `observerctl ds` exists as a top-level namespace
- the planned DS subcommands are visible and parse cleanly
- help output remains readable and aligned with existing CLI style
- no wizard-specific complexity has leaked into the spine frame

### Frame 2 — wire the non-interactive DS wrappers

**Goal**:

- make the core DS automation commands execute the existing analysis lane through `observerctl`

**Tracked edit targets**:

- `src/observerctl.py`
- `src/analysis/dataset_builder.py`
- `src/analysis/train_model.py`
- `src/analysis/evaluation_harness.py`
- `src/analysis/score_unsupervised.py`
- `src/tests/test_observerctl.py`

**Required work**:

- wire `observerctl ds build`
- wire `observerctl ds train`
- wire `observerctl ds evaluate`
- wire `observerctl ds score`
- normalize argument passing and artifact summaries

**Do not do in this frame**:

- no wizard menu loop
- no prompt-cycle logic
- no draft persistence

**Exit criteria**:

- the non-interactive DS lane works through `observerctl`
- users can run the existing analysis steps without leaving the CLI surface

#### Frame 2 micro-plan — wrap the existing analysis entrypoints cleanly

##### Micro-frame 2A — implement `ds build`

**Goal**:

- expose dataset building through `observerctl`

**Required work**:

- map CLI flags to `analysis.dataset_builder`
- preserve existing manifest output expectations
- emit a compact artifact summary on success

**Exit evidence**:

- `observerctl ds build` creates a dataset successfully

##### Micro-frame 2B — implement `ds train`

**Goal**:

- expose model training through `observerctl`

**Required work**:

- support supervised and unsupervised modes
- preserve `model.pkl` / train-manifest expectations
- keep model-type semantics aligned with the current analysis implementation

**Exit evidence**:

- `observerctl ds train` trains and emits expected artifacts

##### Micro-frame 2C — implement `ds evaluate` and `ds score`

**Goal**:

- expose evaluation and scoring through the CLI with clear artifact handoff

**Required work**:

- wire model-backed and heuristic evaluation paths
- wire unsupervised scoring output
- keep threshold/anomaly semantics aligned with the current ApexLab-backed lane

**Exit evidence**:

- `observerctl ds evaluate` and `observerctl ds score` run successfully and emit expected outputs

##### Micro-frame 2D — add focused wrapper tests

**Goal**:

- validate the wrapper layer before orchestration begins

**Required work**:

- extend CLI tests for the new non-interactive commands
- prefer targeted command behavior tests over broad end-to-end wizard expectations

**Exit evidence**:

- wrapper tests pass and prove the DS commands delegate correctly

##### Frame 2 completion criteria

Frame 2 is complete only when all of the following are true:

- `build`, `train`, `evaluate`, and `score` execute from `observerctl ds`
- artifact handoff is coherent and readable
- tests prove the wrapper layer works without the wizard

### Frame 3 — land `ds run demo` and `ds run pipeline`

**Goal**:

- add the opinionated automation layer for common end-to-end flows

**Tracked edit targets**:

- `src/observerctl.py`
- `src/analysis/run_demo.py`
- `src/tests/test_observerctl.py`

**Required work**:

- implement `observerctl ds run demo` as the normalized wrapper around `src/analysis/run_demo.py`
- implement `observerctl ds run pipeline` as the opinionated orchestration flow
- emit compact summary output plus useful artifact locations

**Do not do in this frame**:

- no interactive wizard yet
- no left-rail or `?` help rendering yet

**Exit criteria**:

- both `run` submodes execute the expected automation flows successfully

#### Frame 3 micro-plan — build the automation lane before the guided lane

##### Micro-frame 3A — normalize the demo wrapper

**Goal**:

- make `ds run demo` the authoritative CLI wrapper around the current demo lane

**Required work**:

- wrap `src/analysis/run_demo.py`
- normalize success output into `observerctl` style
- summarize major produced artifacts

**Exit evidence**:

- `observerctl ds run demo` executes the current demo lane cleanly

##### Micro-frame 3B — implement pipeline orchestration

**Goal**:

- provide a small-command end-to-end lane for common non-demo usage

**Required work**:

- orchestrate build -> train -> evaluate
- support optional score -> threshold behavior for unsupervised paths where appropriate
- keep the command readable and predictable rather than maximally configurable

**Exit evidence**:

- `observerctl ds run pipeline` performs the intended sequence and returns a usable artifact summary

##### Micro-frame 3C — validate orchestration flow

**Goal**:

- prove the automation lane works before adding interactive layers on top

**Required work**:

- add targeted tests for `run demo` and `run pipeline`
- ensure the wrapper does not break the underlying demo path

**Exit evidence**:

- run-mode tests pass for both orchestration commands

##### Frame 3 completion criteria

Frame 3 is complete only when all of the following are true:

- `ds run demo` works as the normalized wrapper around the existing demo lane
- `ds run pipeline` lands as a stable opinionated automation path
- the automation lane is test-backed before wizard work starts

### Frame 4 — land the wizard shell and navigation model

**Goal**:

- create the interactive `ds wizard` shell with stable state management and bidirectional navigation

**Tracked edit targets**:

- `src/observerctl.py`
- `src/tests/test_observerctl.py`
- `docs/manuals/OBSERVERCTL_DS_CLI_AND_WIZARD_PROPOSAL_20260325.md`

**Required work**:

- implement `observerctl ds wizard`
- add wizard state object for parameters and validation
- add main menu plus section views
- add bidirectional navigation:
  - back to main
  - next section
  - previous section

**Do not do in this frame**:

- no draft persistence yet
- no responsive two-column enhancement beyond minimal scaffolding

**Exit criteria**:

- the wizard opens, preserves state, and supports section-based navigation cleanly

#### Frame 4 micro-plan — land the guided shell without over-polishing it

##### Micro-frame 4A — add wizard state model

**Goal**:

- create one authoritative state object for all wizard parameter handling

**Required work**:

- define parameter storage, validation state, and workflow selection state
- ensure state persists across menu movement

**Exit evidence**:

- wizard state survives section navigation without data loss

##### Micro-frame 4B — implement main menu and section navigation

**Goal**:

- land the navigation backbone before layout polish

**Required work**:

- implement main menu sections such as:
  - flow
  - in
  - out
  - model
  - eval
  - cmd
  - check
  - run
  - exit
- support back / next / previous movement
- add short breadcrumb-style location context

**Exit evidence**:

- users can move around the wizard without losing orientation or state

##### Micro-frame 4C — implement field reselection behavior

**Goal**:

- land the intuitive field edit pattern early so later prompt/help work reuses it

**Required work**:

- empty field reselection -> enter value
- populated field reselection -> `keep / clear / new`
- keep this behavior compact and context-sensitive

**Exit evidence**:

- the wizard supports intuitive field editing without a dedicated `reset one field` action

##### Frame 4 completion criteria

Frame 4 is complete only when all of the following are true:

- `observerctl ds wizard` opens and maintains stable state
- main-menu and section navigation work bidirectionally
- field reselection behavior matches the locked plan

### Frame 5 — land scope help, item peek, and compact rendering

**Goal**:

- make the wizard discoverable and readable in cramped terminals without bloating the default view

**Tracked edit targets**:

- `src/observerctl.py`
- `src/tests/test_observerctl.py`

**Required work**:

- implement scope-based `?` help
- implement `? <item>` item-specific peek
- render help/peek as temporary, dismissible inline lower-panel output by default
- keep low-character and low-footprint layout discipline

**Do not do in this frame**:

- no draft persistence yet
- no mandatory wide-terminal side pane behavior

**Exit criteria**:

- the wizard is learnable without permanently expanding terse headings

#### Frame 5 micro-plan — add discoverability without destroying compactness

##### Micro-frame 5A — implement scope-based help

**Goal**:

- make `?` show only the right amount of help for the current context

**Required work**:

- from main menu: `?` shows the long-form menu list
- from focused section: `?` shows only section-scope help
- dismiss with `Esc`

**Exit evidence**:

- `?` help works consistently at both main-menu and section scope

##### Micro-frame 5B — implement item-specific peek

**Goal**:

- make terse headings explainable on demand without steady-state text growth

**Required work**:

- support `? <item>`
- show short meaning + relevant current state
- keep peek deterministic and dismissible

**Exit evidence**:

- item-specific detail is available without cluttering the main layout

##### Micro-frame 5C — apply compact rendering rules

**Goal**:

- make the wizard readable under width and height pressure

**Required work**:

- preserve short labels
- keep section spacing disciplined
- avoid decorative filler
- prefer inline lower help panels over width-hungry layouts by default

**Exit evidence**:

- the wizard remains readable in a cramped terminal without sacrificing discoverability

##### Frame 5 completion criteria

Frame 5 is complete only when all of the following are true:

- `?` help matches the locked scope rules
- item peek works without changing state
- the rendered layout remains compact, readable, and consistent with existing CLI style

### Frame 6 — land imports, drafts, and closeout validation

**Goal**:

- finish the serious-use wizard capabilities and close the lane with validation

**Tracked edit targets**:

- `src/observerctl.py`
- `src/tests/test_observerctl.py`
- `docs/manuals/OBSERVERCTL_DS_CLI_AND_WIZARD_PROPOSAL_20260325.md`

**Required work**:

- add artifact import helpers:
  - dataset manifest
  - training manifest
  - model path
  - previous run ledger where practical
- add draft save/load support
- run focused validation across parser, wrapper, run, and wizard behavior

**Exit criteria**:

- the wizard supports serious interrupted/operator use
- the CLI lane is test-backed and closure-ready

#### Frame 6 micro-plan — finish the durable-use layer and validate the full lane

##### Micro-frame 6A — add artifact import helpers

**Goal**:

- reduce re-entry and let the wizard hydrate state from existing artifacts

**Required work**:

- support import from dataset/train/model surfaces
- keep imported values visible and editable after load

**Exit evidence**:

- users can hydrate a wizard session from existing artifacts instead of retyping everything

##### Micro-frame 6B — add draft persistence

**Goal**:

- make interrupted advanced-user workflows resumable

**Required work**:

- add `save draft`
- add `load draft`
- keep draft behavior names-only and deterministic

**Exit evidence**:

- a partially configured wizard session can be resumed later without re-entry

##### Micro-frame 6C — final focused validation

**Goal**:

- prove the whole DS CLI lane is coherent and implementation-ready

**Required work**:

- validate parser reachability
- validate wrapper commands
- validate `run demo` / `run pipeline`
- validate wizard navigation and help behavior
- validate draft and import flows if landed

**Exit evidence**:

- focused tests and spot execution confirm the DS lane is coherent end to end

##### Frame 6 completion criteria

Frame 6 is complete only when all of the following are true:

- artifact import and draft behavior work as intended
- the wizard is suitable for real operator use rather than demo-only use
- focused tests and execution checks support the full DS CLI lane

## Recommended frame order

Run the implementation in this order:

1. Frame 1 — DS command spine
2. Frame 2 — non-interactive wrappers
3. Frame 3 — run automation lane
4. Frame 4 — wizard shell and navigation
5. Frame 5 — scope help, item peek, and compact rendering
6. Frame 6 — imports, drafts, and closeout validation

Rationale:

- the parser spine should exist before execution behavior fills it in
- non-interactive wrappers should be proven before orchestration
- orchestration should be proven before the wizard is built on top of it
- navigation and state should exist before discoverability polish
- help/peek behavior should land before durable-use features like drafts
- import/draft support and closeout validation belong at the end of the lane

## Current recommendation

Proceed with the `observerctl ds` namespace and reserve `observerctl ds wizard` as the professional advanced-user path.

The wizard should be implemented as a structured, stateful console flow with:

- a main menu with bidirectional section navigation,
- a persistent parameter panel,
- numbered parameter-edit actions,
- terminal-compatible `?` help support with scope-based long-form help and item-specific peek,
- prompt-cycle modes that preserve previously entered values,
- execution blocking until validation succeeds, and
- a persistent equivalent-command preview.

The implementation should also treat low character count and disciplined vertical footprint as explicit UX goals, using intuitive structure and context-sensitive branching to remove unnecessary on-screen text.

Where terminal width allows, a compact left-side vertical action rail may be used to improve legibility, but the implementation should remain responsive and should fall back gracefully to stacked or section-focused layouts when the terminal is cramped.

This gives first-time users a clear automation surface while giving advanced users a guided cockpit that still respects the repo's current CLI style and output discipline.
