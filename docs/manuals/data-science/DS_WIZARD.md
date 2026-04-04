# Calamum DS Wizard

Updated: 2026-04-03

This document explains how to use the guided data-science wizard for `observerctl ds`.

## What the wizard is

The wizard is the interactive front end for the same DS operations documented in [`DS_OPERATIONS.md`](DS_OPERATIONS.md).

Use it when you want guided configuration, seeded state from existing artifacts, draft save/load, command preview, and optional execute handoff without manually assembling every CLI flag.

## Dataset authority: Librarian-first

Raw filesystem paths are not accepted for dataset inputs in `train`, `evaluate`, or `score` workflows -- in the wizard or at the CLI. All datasets must be registered in the approved Librarian catalog before use.

### Onboarding a dataset

Register a built dataset manifest once:

```
observerctl librarian dataset register local_untracked/analysis/datasets/<your-run>/dataset_manifest.json
```

This assigns a stable `entry_id` selector. The selector can be passed by index, `entry_id`, `run_id`, or display name anywhere a dataset token is accepted.

To confirm the catalog:

```
observerctl librarian datasets
```

### Dataset inputs by workflow

| Workflow | `in` page dataset surface | Notes |
| --- | --- | --- |
| `train` | approved dataset picker (Librarian) | selector resolved via `librarian dataset release` |
| `evaluate` | approved dataset picker (Librarian) | features/labels/manifest hydrated from approved entry |
| `score` | approved dataset picker (Librarian) | selector resolved via `librarian dataset release` |
| `build` | raw `--input` telemetry paths (CLI-seeded) | pre-Librarian; raw JSONL telemetry is the input |
| `run-pipeline` | raw `--input` telemetry paths (CLI-seeded) | pre-Librarian; same as `build` |
| `run-demo` | self-contained; no external dataset input required | generates its own synthetic data |

The wizard `in` section for `train`/`evaluate`/`score` opens an approved dataset picker that resolves the entry through the Librarian before hydrating wizard fields. The `source` and `mode` advanced-route fields do not appear in the default `in` menu for `build` and `run-pipeline`.

### CLI dataset selectors

The `ds train --dataset` and `ds score --dataset` flags accept the same approved selector tokens as the wizard:

```
# by index (1-based position in the catalog)
observerctl ds train --dataset 1 --model-type supervised

# by entry_id
observerctl ds score --dataset demo_20260331t221410 --model local_untracked/analysis/runs/demo/.../models
```

Raw paths passed to `--dataset` will be rejected with a registration instruction.

## Wizard workflows

The current shipped workflow presets are:

| Workflow | Use it for |
| --- | --- |
| `build` | dataset creation from approved telemetry inputs |
| `train` | model training from an existing dataset manifest |
| `evaluate` | metric and threshold evaluation using prepared features and optional labels |
| `score` | scoring a dataset with an unsupervised model |
| `run-demo` | the packaged demo route |
| `run-pipeline` | the default build/train/evaluate sequence |

## Wizard sections

The wizard uses these sections to walk through a run:

| Section | Purpose |
| --- | --- |
| `flow` | choose the workflow preset |
| `in` | bind inputs, source/mode context, and dataset-facing artifacts |
| `model` | choose model family, seeds, split values, and model artifacts |
| `eval` | set evaluation guards such as `--max-fpr` |
| `report` | choose output destinations |
| `cmd` | preview the assembled command |
| `check` | review validation issues before execution |
| `run` | execute the handoff |
| `exit` | leave the wizard |

Not every workflow uses every section. The wizard trims the path to the sections that apply to the selected workflow.

## How to launch it

Launch the wizard directly:

- `observerctl ds wizard`

You can also seed it on launch with any of the supported helper switches below.

## Hydration and seeding options

| Switch | What it seeds from |
| --- | --- |
| `--hydrate-dataset <selector>` | an approved dataset selector (index, run_id, display name, or entry_id) |
| `--hydrate-train <path>` | `train_manifest.json` |
| `--hydrate-model <path>` | a saved model artifact path |
| `--hydrate-baseline-analysis <path>` | a baseline analysis packet |
| `--hydrate-run <path>` | an existing evaluation `run.json` ledger |
| `--hydrate-latest-context` | the latest SSOT source/mode context and latest saved baseline-analysis packet when available |

These options are especially useful when you want the wizard to open with a partially completed run context instead of starting from zero.

## Draft save and load

| Switch | What it does |
| --- | --- |
| `--load-draft <slot-or-path>` | load a canonical draft slot token or a saved draft JSON file |
| `--save-draft [slot-or-path]` | save the seeded or current wizard state to the next canonical slot or an explicit draft path |

If you want to work iteratively, save a draft after the input and model sections are correct, then return later for validation and execute handoff.

## Preloading field values

Use repeatable `--set key=value` items to preload individual fields before the interactive flow starts.

This is useful for values such as:

- source and mode context
- seeds
- split values
- output paths
- run identifiers

## Execute handoff

Add `--execute` if you want the wizard to attempt the execute handoff after seeding state.

Recommended flow:

1. choose the workflow in `flow`
2. fill the required inputs and model context
3. review the assembled command in `cmd`
4. review validation issues in `check`
5. execute only when the wizard shows a clean handoff path

## Reporting and artifacts

The wizard writes into the same DS reporting structure as the direct CLI.

| Surface | Role |
| --- | --- |
| local run artifacts under the chosen output root | detailed execution residue and ledgers |
| `docs/reports/collections/<collection-alias>/collection/report.md` | tracked collection packet keyed by the canonical alias shown in the wizard |
| `docs/reports/collections/<collection-alias>/processing/<stage>/YYYYMMDDTHHMMSSffffffZ.<stage>.md` | tracked stage report for each published calculation run under that collection alias |
| `docs/reports/aggregates/*.md` | tracked rollups |
| `docs/reports/INDEX.md` | reader-facing report-collections hub |

The collection folder is keyed by the canonical alias used in the wizard dataset selector, not by the calculation run id. Historical stage identity comes from the canonical UTC timestamp token in the filename; the tracked publication lane does not use same-day numeric suffixes for reader-facing stage documents.

If you only need the publication view, go to [`../../reports/INDEX.md`](../../reports/INDEX.md). If you need the direct non-wizard command forms, go to [`DS_OPERATIONS.md`](DS_OPERATIONS.md).

## Practical tips

| Tip | Why it helps |
| --- | --- |
| start with `--hydrate-latest-context` when working from a current runtime lane | it saves you from re-entering source/mode context |
| use `saved baselines` before evaluation-heavy runs | the wizard can cite the right baseline packet more cleanly when you already know the selector |
| review the `cmd` and `check` sections before execute | this catches missing context before the run is launched |
| save drafts for longer workflows | it keeps iterative configuration work reproducible |

## Related documents

- [`DS_OPERATIONS.md`](DS_OPERATIONS.md)
- [`../../reports/INDEX.md`](../../reports/INDEX.md)
- [`../../../src/analysis/README.md`](../../../src/analysis/README.md)
- [`../runtime/RUNTIME_WORKFLOWS.md`](../runtime/RUNTIME_WORKFLOWS.md)
- [`../INDEX.md`](../INDEX.md)
