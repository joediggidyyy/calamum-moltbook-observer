# Calamum DS Operations

Updated: 2026-04-03

This document is the main operating reference for the `observerctl ds` command family.

## Install surface

Use the core install for the observer runtime itself:

- `python -m pip install -e .`

Add the DS extra before using `observerctl ds *` for the supported ApexLab-backed training, evaluation, scoring, and report-visualization path:

- `python -m pip install -e ".[ds]"`

If you also want the Ghost Console UI, add the dashboard extra separately:

- `python -m pip install -e ".[dashboard]"`

## What the DS surface does

The DS lane turns names-only runtime telemetry into reproducible local analysis runs.

| Stage | Result |
| --- | --- |
| build | dataset artifacts are created from approved telemetry inputs |
| train | a supervised or unsupervised model artifact is produced from a dataset manifest |
| evaluate | heuristics or trained artifacts are measured against feature and label data |
| score | an unsupervised model produces a scores CSV |
| run | opinionated end-to-end workflows execute the common happy paths |
| saved | existing train, run, baseline, and draft selectors are listed for reuse |
| wizard | the interactive guided interface builds and optionally executes the same DS commands |

## Inputs and outputs

| Surface | Default role |
| --- | --- |
| telemetry inputs | names-only runtime JSONL under the observer-derived lane or approved local telemetry files |
| local analysis home | `src/analysis/` |
| default ignored output root | `local_untracked/analysis/` |
| tracked report publication hub | `docs/reports/INDEX.md` |

The project-local analysis home also documents the current supported analysis stack in [`src/analysis/README.md`](../../../src/analysis/README.md).

## Direct command map

| Command | What it does | Key inputs |
| --- | --- | --- |
| `observerctl ds build` | build a dataset from observer telemetry inputs | repeatable `--input`, optional `--out-dir`, split settings, seed |
| `observerctl ds train` | train a model from `dataset manifest.json` | `--dataset`, optional `--out-dir`, `--model-type`, `--seed` |
| `observerctl ds evaluate` | evaluate a heuristic or trained model | `--features-csv`, optional `--labels-csv`, `--dataset-manifest`, `--model-path`, `--max-fpr`, `--out-dir` |
| `observerctl ds score` | score a dataset with an unsupervised model | `--dataset`, `--model`, optional `--out-file` |
| `observerctl ds run demo` | execute the packaged demo flow | optional `--out-dir`, `--dataset-seed`, `--model-seed`, `--max-fpr` |
| `observerctl ds run pipeline` | execute the default build/train/evaluate pipeline | repeatable `--input`, optional `--out-dir`, split settings, model type, seed, `--max-fpr` |

## Saved selector families

The saved namespace makes it easier to reuse approved artifacts without rebuilding path arguments from scratch.

| Command | Returns |
| --- | --- |
| `observerctl ds saved trained` | saved train/model selectors |
| `observerctl ds saved runs` | saved evaluation run selectors |
| `observerctl ds saved baselines --source <sim|real> --mode <mode>` | baseline-analysis selectors for a specific source/mode scope |
| `observerctl ds saved drafts` | canonical wizard draft slots |

## Recommended operating sequences

### Build → train → evaluate

1. build a dataset with `observerctl ds build`
2. train a model with `observerctl ds train`
3. evaluate the resulting artifact with `observerctl ds evaluate`
4. publish or review tracked report collections through [`../../reports/INDEX.md`](../../reports/INDEX.md)

### Demo lane

Use `observerctl ds run demo` when you want a single-command validation pass through the supported observer DS pipeline.

### Full pipeline lane

Use `observerctl ds run pipeline` when you want the default build/train/evaluate flow in one command and already know the telemetry inputs you want to use.

## Reporting structure

The DS lane uses both local run artifacts and tracked reader-facing summaries.

| Surface | What it is for |
| --- | --- |
| local run ledgers such as `run.json` and `run.md` | detailed per-run execution records kept with the generated analysis output |
| `docs/reports/collections/<collection-alias>/collection/report.md` | tracked collection-level report keyed by the canonical alias shown in the wizard |
| `docs/reports/collections/<collection-alias>/processing/<stage>/YYYYMMDDTHHMMSSffffffZ.<stage>.md` | timestamped stage report for each published calculation run under that collection alias |
| `docs/reports/aggregates/*.md` | tracked rollups such as latest collections, workflow rollup, and threshold summary |
| `docs/reports/INDEX.md` | the entry point for the tracked report collection set |

Historical stage identity comes from the canonical UTC timestamp token in the filename. The tracked publication lane does not use same-day numeric suffixes for reader-facing stage documents.

## When to use the wizard instead

Use the wizard when any of the following are true:

- you want the command assembled interactively
- you want to seed the run from a saved dataset, model, baseline packet, or prior run
- you want draft save/load support while iterating on a DS workflow

The wizard is documented separately in [`DS_WIZARD.md`](DS_WIZARD.md), but it targets the same underlying DS command surface.

## Practical guardrails

| Guardrail | Meaning |
| --- | --- |
| stay names-only | do not route raw message content into the analysis lane |
| keep run artifacts reproducible | preserve manifests, seeds, and ledger outputs |
| respect source/mode context | when a run cites baseline or runtime state, keep the source/mode pairing explicit |
| use tracked reports for public presentation | keep detailed local run residue in ignored storage |

## Related documents

- [`DS_WIZARD.md`](DS_WIZARD.md)
- [`../../../src/analysis/README.md`](../../../src/analysis/README.md)
- [`../../reports/INDEX.md`](../../reports/INDEX.md)
- [`../runtime/RUNTIME_WORKFLOWS.md`](../runtime/RUNTIME_WORKFLOWS.md)
- [`../INDEX.md`](../INDEX.md)
