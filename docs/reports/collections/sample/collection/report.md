# 20260404.collection.md

## Collection identity

| Field | Value |
| --- | --- |
| Collection alias | `sample` |
| Source scope | `real:canary` |
| Collection window | `2026-04-04 09:00 UTC -> 2026-04-04 11:00 UTC` |
| Reader posture | curated, public-safe, names-only |
| Role in the report spine | first document; explains the collection before any processing run is interpreted |

## What a collection is in the observer environment

In Calamum, a collection is not just a pile of records waiting for a model. It is a governed handoff assembled from retained observer evidence. Before any build, train, eval, or score document is worth reading, the collection has to show that the runtime actually emitted telemetry, that the watchdog posture was coherent, that the baseline lane produced a usable comparison window, that the librarian can account for retained artifacts, and that stricter-lane security linkage is present when required.

That is why the collection document exists first. It explains what was gathered, which authority surfaces say the gathering was real, and why the retained packet is suitable for downstream processing.

## What this sample collection says

The `sample` collection represents a bounded `real:canary` observer window whose retained telemetry was stable enough to support later analysis. The collection story is deliberately small, but it is not imaginary. It is built from the same classes of evidence that the shipped CLI already emits:

- resource telemetry segments written to the archive and indexed for reuse
- baseline analysis packets that decide whether comparison work is actually ready
- watchdog control-state receipts used by gate evaluation
- librarian census and retention surfaces that account for what was kept
- health and transition packets that preserve the run linkage, including `security_report_ref`

In other words, the collection is the point where raw observation becomes accountable analysis input.

## Authority surfaces used for this collection

| Surface | Canonical artifact or command | Why it matters to the collection |
| --- | --- | --- |
| Resource telemetry retention | `logs/data/calamum/observer_derived/real/canary/resource/index.jsonl` plus archived `resource_real_canary_*` segments under `logs/data/calamum/archive/` | proves that the observer actually retained collection-window telemetry and that the window can be replayed or audited later |
| Resource baseline analysis | `observerctl baseline analyze --source real --mode canary --json` and its emitted evidence packet under `logs/data/calamum/observer_derived/real/canary/evidence/` | decides whether the retained window is comparison-ready rather than merely present |
| Integrity baseline | `observerctl baseline status --json` / `observerctl baseline check --json` against `logs/control/calamum/observerctl_fs_baseline.json` | shows whether the workspace-side file baseline is intact while the collection is being interpreted |
| Watchdog posture receipt | `logs/control/calamum/watchdog_posture_state.json` and the posture-apply receipt emitted into lane evidence | proves that the lane posture and cadence settings matched the requested runtime mode |
| Watchdog resource state | `logs/control/calamum/watchdog_resource_state.json` plus `observerctl watchdog check --json` | summarizes the latest CPU, RAM, spike score, and freshness readings used by gate logic |
| Evidence packet ledger | `logs/data/calamum/observer_derived/real/canary/evidence/index.jsonl` | links collection-time commands to their retained packet paths and run linkage |
| Librarian census | `observerctl librarian stats --json` and `observerctl librarian stores --json` | explains what the lane retained, what was archived, and whether store integrity stayed coherent |
| Runtime health rollup | `observerctl health full --json` | collates baseline, librarian, watchdog, and policy readiness into one public-safe snapshot |
| Security linkage | `run_id`, `posture_trigger_id`, `posture_trigger`, and `security_report_ref` carried by gate/evidence packets; KEYSMITH status via `observerctl ops keysmith` | anchors stricter-lane collection work to its names-only security receipt instead of treating the run as free-floating |

## How to read the collection evidence

The collection should be read from runtime outward.

Start with the retained telemetry and its indexes. Those surfaces establish that a real collection window exists. Then read the baseline-analysis packet, because that is the first place the system declares whether the retained window is actually suitable for later comparison work. After that, check the watchdog posture and resource-state surfaces to confirm the lane was gathered under the expected runtime posture. Finally, use librarian and health surfaces to verify that the collection is accounted for and still readable from the operator side.

That order matters. The collection is not defined by the later model outputs; it is defined by the reliability of the retained observer evidence that those later outputs depend on.

## Collection interpretation

This sample collection is fit for downstream processing because the evidence classes point in the same direction.

The retained resource stream says the window exists. The baseline-analysis surface says the window is usable. The watchdog surfaces say the collection happened under a coherent lane posture. The librarian surfaces say the retained artifacts can be counted and located. The health and transition packets preserve the run linkage required to explain where this collection belongs in the larger observer execution story.

That is the educational point of the collection report: before a model is trained or a threshold is discussed, the observer environment has already produced enough provenance to explain why this collection deserves to be processed at all.

## Limits

- This is a sample collection document, not a production readiness claim.
- The collection report is interpretive; canonical machine-readable authority remains in the retained JSON packets, indexes, manifests, and control-state files.
- A single collection can feed more than one processing run, so this document should summarize the retained evidence once and then track downstream processing separately.

## Processing run ledger

| Date | Time (UTC) | Source:Mode | Collection window | Relevant note |
| --- | --- | --- | --- | --- |
| [2026-04-04](../processing/build/20260404.build.md) | `09:00` | `real:canary` | `2026-04-04 09:00 UTC -> 2026-04-04 11:00 UTC` | first processing run for this sample collection; baseline-analysis, watchdog, librarian, and security-linkage surfaces were present for handoff |
