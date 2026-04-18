# Documentation Index

Version: `1.0.1`
Updated: 2026-04-18

This index routes readers through the tracked documentation surfaces for Calamum Moltbook Observer.

## Delivery boundary

| Documentation surface                                                                                                                                                                                                                                                                                                                                            | Current ship state                                                       | Role                                                                                                                    |
| ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------- |
| [`INDEX.md`](INDEX.md) + [`manuals/`](manuals/)                                                                                                                                                                                                                                                                                                                  | tracked in the repo and shipped with the installable application package | packaged documentation library for runtime operators and readers                                                        |
| report framework baseline under [`reports/INDEX.md`](reports/INDEX.md), [`reports/aggregates/`](reports/aggregates/), [`reports/reference/GENERATED_REPORT_SURFACES.md`](reports/reference/GENERATED_REPORT_SURFACES.md), [`reports/validations/INDEX.md`](reports/validations/INDEX.md), and the structural [`reports/collections/`](reports/collections/) lane | tracked in the repo and shipped with the installable application package | reader-facing report routing, aggregate, reference, validation-index, and zero-state collection-lane framework surfaces |
| populated packet leaves under [`reports/collections/<collection-alias>/...`](reports/collections/) and emitted validation report files                                                                                                                                                                                                                           | tracked in the repo as publication-derived surfaces                      | dated collection, workflow, figure-backed, and validation packet outputs rebuilt from canonical local artifacts         |
| [`Spring2026/INDEX.md`](Spring2026/INDEX.md) and the adjacent writeups under [`Spring2026/`](Spring2026/)                                                                                                                                                                                                                                                        | tracked in the repo, not part of the shipped application package         | public Spring 2026 course writeups and reader-facing project background materials                                       |
| other adjacent `docs/` subtrees                                                                                                                                                                                                                                                                                                                                  | evaluated individually                                                   | no blanket ship claim until that subtree is intentionally classified                                                    |

## Start here

| Reader goal                                        | Start here                                                       | Then                                                                                             | Then                                                                                               |
| -------------------------------------------------- | ---------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------- |
| project overview                                   | [`../README.md`](../README.md)                                   | [`../SECURITY.md`](../SECURITY.md)                                                               | [`../DATA_METHODOLOGY.md`](../DATA_METHODOLOGY.md)                                                 |
| public report packets and latest collection routes | [`reports/INDEX.md`](reports/INDEX.md)                           | [`reports/aggregates/WORKFLOW_ROLLUP.md`](reports/aggregates/WORKFLOW_ROLLUP.md)                 | [`reports/reference/GENERATED_REPORT_SURFACES.md`](reports/reference/GENERATED_REPORT_SURFACES.md) |
| runtime and operations                             | [`manuals/runtime/INDEX.md`](manuals/runtime/INDEX.md)           | [`manuals/runtime/RUNTIME_WORKFLOWS.md`](manuals/runtime/RUNTIME_WORKFLOWS.md)                   | [`manuals/runtime/RUNTIME_OPERATIONS.md`](manuals/runtime/RUNTIME_OPERATIONS.md)                   |
| security and transition rules                      | [`manuals/reference/INDEX.md`](manuals/reference/INDEX.md)       | [`manuals/reference/SECURITY_MODEL.md`](manuals/reference/SECURITY_MODEL.md)                     | [`manuals/reference/RUNTIME_TRANSITIONS.md`](manuals/reference/RUNTIME_TRANSITIONS.md)             |
| data science and reporting                         | [`manuals/data-science/INDEX.md`](manuals/data-science/INDEX.md) | [`manuals/data-science/DS_OPERATIONS.md`](manuals/data-science/DS_OPERATIONS.md)                 | [`reports/INDEX.md`](reports/INDEX.md)                                                             |
| Spring 2026 course writeups                        | [`Spring2026/INDEX.md`](Spring2026/INDEX.md)                     | [`Spring2026/DATA780_FinalProject_JoeWaller.pdf`](Spring2026/DATA780_FinalProject_JoeWaller.pdf) | [`Spring2026/DATA740_FinalProject_JoeWaller.pdf`](Spring2026/DATA740_FinalProject_JoeWaller.pdf)   |

## Root project documents

| Document                                           | Role                                                     |
| -------------------------------------------------- | -------------------------------------------------------- |
| [`../README.md`](../README.md)                     | public project overview and primary entry surface        |
| [`../CONTRIBUTING.md`](../CONTRIBUTING.md)         | public contribution workflow and validation expectations |
| [`../SECURITY.md`](../SECURITY.md)                 | public security doctrine and evidence-boundary policy    |
| [`../DATA_METHODOLOGY.md`](../DATA_METHODOLOGY.md) | public telemetry and packet-contract surface             |

## Manual sections

| Section                                                          | Role                                                     |
| ---------------------------------------------------------------- | -------------------------------------------------------- |
| [`manuals/runtime/INDEX.md`](manuals/runtime/INDEX.md)           | operating path and command-level runtime reference       |
| [`manuals/data-science/INDEX.md`](manuals/data-science/INDEX.md) | DS commands, wizard use, and reporting linkage           |
| [`manuals/reference/INDEX.md`](manuals/reference/INDEX.md)       | security architecture and the formal transition contract |

## Project writeups

| Section                                                                                          | Role                                                                                                 |
| ------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------- |
| [`Spring2026/INDEX.md`](Spring2026/INDEX.md)                                                     | index for the Spring 2026 DATA 740 and DATA 780 public writeups                                      |
| [`Spring2026/DATA740_FinalProject_JoeWaller.pdf`](Spring2026/DATA740_FinalProject_JoeWaller.pdf) | project writeup for DATA 740: Governance, Bias, & Ethics in Data Science and Artificial Intelligence |
| [`Spring2026/DATA780_FinalProject_JoeWaller.pdf`](Spring2026/DATA780_FinalProject_JoeWaller.pdf) | project writeup for DATA 780: Machine Learning                                                       |

## Reports

Use [`reports/INDEX.md`](reports/INDEX.md) for the curated tracked report framework and packet catalog.
The shipped baseline covers report routing, aggregates, reference guidance, validation entry, and the structural `collections/` lane. Populated packet families are organized by collection alias and then by dated `build`, `train`, `evaluate`, and `score` leaves.

## Quick routes

- Want the project overview? Start at [`../README.md`](../README.md)
- Want the current public packet family? Use [`reports/INDEX.md`](reports/INDEX.md)
- Want the manual hub? Use [`manuals/INDEX.md`](manuals/INDEX.md)
- Want runtime guidance? Use [`manuals/runtime/INDEX.md`](manuals/runtime/INDEX.md)
- Want the DS lane? Use [`manuals/data-science/INDEX.md`](manuals/data-science/INDEX.md) and [`reports/INDEX.md`](reports/INDEX.md)
- Want the Spring 2026 course writeups? Use [`Spring2026/INDEX.md`](Spring2026/INDEX.md)
- Want contribution guidance? Use [`../CONTRIBUTING.md`](../CONTRIBUTING.md)