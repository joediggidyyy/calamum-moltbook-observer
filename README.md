# Project: Calamum Moltbook Observer

**Document ID**: `CALAMUM_PUBLIC_README_20260324`  
**Status**: Public project overview  
**Owner**: ORACL-Prime  
**Project**: Calamum Moltbook Observer  
**Last updated**: 2026-04-09

---

<p align="center">
  <img src="assets/branding/calamum_logo_color.png" alt="Calamum Logo" width="400">
  <br>
  <em>Ethical Security</em>
</p>

## Purpose

**Calamum Moltbook Observer** is a security research toolkit for measuring hostile-agent activity on the Moltbook platform using privacy-preserving telemetry, guarded runtime controls, and local analysis workflows.

The project is built around one non-negotiable rule: **no raw Moltbook content is written to disk**. Instead, telemetry is reduced to names-only, schema-bound signals before persistence so the system can support reproducible research without normalizing unsafe retention practices.

Security engineering is not a decorative sidebar here. Containment, minimization, posture enforcement, and fail-closed behavior are part of the operating contract.

## Start here

This README is the public front door for the project. Use it to understand what the observer is, what it retains, and which public document to read next.

| If you want to understand... | Read next |
|---|---|
| the overall documentation map | [Docs Index](docs/INDEX.md) |
| the public report catalog and current packet family | [Report Collections](docs/reports/INDEX.md) |
| the security policy and disclosure boundary | [Security Policy](SECURITY.md) |
| the telemetry and packet contract | [Data Methodology](DATA_METHODOLOGY.md) |
| how to contribute safely | [Contributing Guide](CONTRIBUTING.md) |
| the manual catalog | [Manual Index](docs/manuals/INDEX.md) |
| the runtime operating path | [Runtime Index](docs/manuals/runtime/INDEX.md) |
| the data-science command and report lane | [Data Science Index](docs/manuals/data-science/INDEX.md) |
| the security architecture in more depth | [Calamum Security Model](docs/manuals/reference/SECURITY_MODEL.md) |
| the mode/transition command contract | [Calamum Runtime Transitions](docs/manuals/reference/RUNTIME_TRANSITIONS.md) |

## At a glance

- **Research focus**: hostile-agent measurement, telemetry, and downstream analysis
- **Data posture**: names-only persistence; no raw-content storage by default
- **Operational model**: explicit posture control, watchdog oversight, and local evidence retention
- **Analysis model**: local ML workflows on obfuscated telemetry only
- **Report model**: alias-first human-facing packet families under `docs/reports/collections/<collection-alias>/processing/{build,eval,score,train}/`
- **Public repo scope**: code, docs, deployment surfaces, branding, and curated public artifacts
- **Canonical current runtime family**: `logs/data/calamum/observer_derived/<source>/<mode>/...`

## Current release boundary

The current tracked release boundary is **Stage-4 / canary-ready**.

| Included now | Governed separately |
|---|---|
| sim/canary observer runtime and evidence surfaces | real-source live activation |
| Ghost Console dashboard | active magnet / honeypot deployment |
| watchdog and librarian control surfaces | unsandboxed keysmith live minting |
| names-only telemetry model | |
| local DS/report toolchain | |
| guarded keysmith status and dry-run lanes | |

## Verified current runtime model

The current public architecture centers on three primary components and two telemetry families.

- **Observer Agent**  
  A lightweight producer that emits obfuscated, signed names-only records under the observer-derived runtime tree.

- **Librarian Daemon**  
  A background process responsible for compression, integrity checks, and retention lifecycle management over active telemetry artifacts.

- **Blind ML Pipeline**  
  The local analysis stack under `src/analysis/`, which consumes obfuscated telemetry to train supervised and unsupervised models without exposing raw message semantics.

Telemetry families:

- **Direct telemetry artifacts** provide names-only local telemetry outputs.
- **Observer-derived artifacts** provide the canonical runtime and evidence surfaces for current observer-agent and `observerctl` behavior.

## Security posture

The observer treats the upstream platform and its content stream as hostile by default. That assumption drives the rest of the design:

- **Data minimization first**: persist structured telemetry, not raw content
- **Fail-closed control flow**: deny or stop on invalid posture, stale state, or missing prerequisites
- **Layered containment**: runtime, watchdog, and persistence boundaries are intentionally separate
- **Local evidence discipline**: high-detail operational residue remains operator-local
- **Credential hygiene**: secrets are environment-injected and presence-checked; values never belong in tracked workflows

For the root policy surface, read [Security Policy](SECURITY.md). For the deeper posture and enforcement architecture, read [Calamum Security Model](docs/manuals/reference/SECURITY_MODEL.md).

## Public repository scope

This repository presents the **public observer surface** only:

- source code
- deployment assets
- branding
- public manuals
- curated public reports and reader-facing packet collections
- reusable project templates

Runtime logs and operator-local governance surfaces remain outside the tracked public presentation.

## Current public report spine

Tracked public reports are rebuilt from the canonical local DS run spine into human-facing packet families under `docs/reports/`.
The public entry surface for that lane is [Report Collections](docs/reports/INDEX.md).

| If you need to... | Open |
|---|---|
| get the fastest route into the current collection packet | [docs/reports/INDEX.md](docs/reports/INDEX.md) |
| compare the latest build / train / evaluate / score packets | [docs/reports/aggregates/WORKFLOW_ROLLUP.md](docs/reports/aggregates/WORKFLOW_ROLLUP.md) |
| understand the tracked packet filesystem contract | [docs/reports/reference/GENERATED_REPORT_SURFACES.md](docs/reports/reference/GENERATED_REPORT_SURFACES.md) |
| review the current dated packet leaves | `docs/reports/collections/<collection-alias>/processing/{build,eval,score,train}/` |

The public report tree is intentionally reader-first. Machine-readable authority stays in the local analysis indexes and is referenced from these public packet surfaces rather than duplicated there.

## Project layout

```text
projects/calamum-moltbook-observer/
 assets/              # Branding and static assets
 deployment/          # Deployment/support surfaces kept public
 docs/                # Public documentation (`manuals/` + `reports/`)
 src/                 # Source code
    analysis/         # Local ML and analysis workflows
    deployment/       # Dockerfiles and hardening profiles
    ops/              # Ops, telemetry, and control surfaces
    tests/            # Validation suites
    calamum_sampler.py
    calamum_observer_agent.py
    obfuscator_lib.py
 template_library/    # Project-local tracked templates
 tools/               # Audits, reporting tools, and support scripts
 launch_ghost_console.ps1
```

## Research workstreams

| Workstream | Current status | Public meaning |
|---|---|---|
| **Observe & Sample** | **COMPLETE** | Read-only sampling of the public feed with obfuscation safety validated. |
| **Container Hardening** | **COMPLETE** | Deployment of the read-only “Glass Box” runtime environment. |
| **Passive Canary** | **COMPLETE** | Silent account deployment for measuring inbound background activity. |
| **Active Magnet (Honeypot)** | *PLANNED* | Soft-target deployment path for higher-risk hostile-agent measurement. |
| **Blind ML Analysis** | **ACTIVE** | Local supervised and unsupervised analysis on obfuscated telemetry. |

## Reference map

### Public documents

| Surface | Purpose |
|---|---|
| this `README.md` | Project overview |
| [Docs Index](docs/INDEX.md) | Documentation hub |
| [Report Collections](docs/reports/INDEX.md) | Public report catalog and current packet-family routing |
| [Manual Index](docs/manuals/INDEX.md) | Manual catalog |
| [Runtime Index](docs/manuals/runtime/INDEX.md) | Runtime operating path and command reference |
| [Data Science Index](docs/manuals/data-science/INDEX.md) | DS commands, wizard use, and reporting linkage |
| [Reference Index](docs/manuals/reference/INDEX.md) | Security architecture and transition contract |
| [Contributing Guide](CONTRIBUTING.md) | Public contribution and validation guidance |
| [Security Policy](SECURITY.md) | Security policy |
| [Data Methodology](DATA_METHODOLOGY.md) | Methodology contract |
| [Calamum Security Model](docs/manuals/reference/SECURITY_MODEL.md) | Security architecture |
| [Calamum Runtime Transitions](docs/manuals/reference/RUNTIME_TRANSITIONS.md) | Runtime transition contract |
| [Container Constraints](src/deployment/HARDENING_PROFILE.md) | Container hardening profile |

### Source surfaces

| Surface | Path |
|---|---|
| Observer runtime CLI | `src/observerctl.py` |
| Watchdog runtime (`sentinel.py`) | `src/sentinel.py` |
| Observer agent | `src/calamum_observer_agent.py` |
| Analysis workflows | `src/analysis/` |

### Runtime evidence (retained locally)

| Evidence family | Canonical path |
|---|---|
| Direct telemetry artifacts | `logs/data/calamum/moltbook_samples_obfuscated.jsonl` and `logs/data/calamum/moltbook_canary_metrics.jsonl` |
| Canonical observer-runtime stream | `logs/data/calamum/observer_derived/<sim|real>/<watch|canary|live|honeypot>/moltbook_metrics.jsonl` |
| Baseline/resource evidence family | `logs/data/calamum/observer_derived/<sim|real>/<mode>/{resource,evidence}/` |

These evidence streams are retained locally and sit outside the tracked public repo surface.

## Contract summary

The current public contract can be summarized as follows:

- direct telemetry outputs and observer-derived outputs both exist,
- the active runtime and readiness surfaces live under `observer_derived/`,
- gate/evidence outputs are expected to be names-only and carry run-linkage fields,
- the packet-level details live in `DATA_METHODOLOGY.md`, not in this overview page.

## Visual surfaces

### Operational radar

<img src="assets/branding/calamum_obs_radar.png" alt="Observer Radar" width="600">

### CLI dashboard reference

<img src="assets/branding/syslog_scroll.png" alt="CLI Dashboard" width="600">

## Runtime operations

### Observer runtime CLI (`observerctl`)

Observer runtime operations are exposed through `src/observerctl.py` and remain standalone from CodeSentinel runtime process surfaces.

Install the native CLI entrypoint once per environment:

- `python -m pip install -e .`

Add the supported extras only when you need those lanes:

- `python -m pip install -e ".[ds]"` for the DS / report / visualization lane
- `python -m pip install -e ".[dashboard]"` for Ghost Console / NiceGUI surfaces

After installation, use the observer-native command surface directly:

- **Preflight status packet**  
  `observerctl ops preflight --source sim --json`
- **Gate decision packet**  
  `observerctl ops gate-check --source sim --json`
- **Publication-grade evidence packet**  
  `observerctl ops evidence pack --source sim --json`
- **Atomic transition workflow**  
  `observerctl ops mode transition --to canary --source sim --event transition-canary --output logs/data/calamum/observer_derived/sim/canary/evidence/transition_canary.json --json`

`ops gate-check` is fail-closed and returns non-zero when required inputs are missing or invalid.

### Data science and report packet lane

The observer-native DS surface now covers dataset build, train, evaluate, score, and end-to-end demo or pipeline execution.

- **Build a dataset packet**  
  `observerctl ds build --dataset <selector> --json`
- **Train from an approved dataset**  
  `observerctl ds train --dataset <selector> --model-type supervised --json`
- **Evaluate a model or heuristic**  
  `observerctl ds evaluate --features-csv <features.csv> --dataset-manifest <dataset_manifest.json> --json`
- **Score an approved dataset with an unsupervised model**  
  `observerctl ds score --dataset <selector> --model <train_manifest.json> --json`
- **Run the packaged demo flow**  
  `observerctl ds run demo --json`

Approved local DS artifacts can be explicitly published into the tracked public report lane under `docs/reports/`, where collection packets and stage packets follow the current alias-first report family.

For the lower-level transition/evidence contract, see:

- `docs/manuals/reference/RUNTIME_TRANSITIONS.md`
- `docs/manuals/runtime/RUNTIME_OPERATIONS.md`

### Launching on a Windows host

#### A) Ghost Console V2 (Ops Dashboard)

The Ghost Console is a fixed-size NiceGUI + ECharts dashboard designed to present **names-only** telemetry.

- Start UI (recommended): `projects/calamum-moltbook-observer/launch_ghost_console.ps1`
  - starts the backend hidden
  - opens Microsoft Edge in app-mode at **1100×720**

Dashboard source: `src/ops_dashboard.py`

#### B) Observer + Watchdog (direct)

1. Start observer: `./src/deployment/secure_run.ps1`
2. Start watchdog runtime: `python src/sentinel.py`

## Ghost Console data and control model

### Telemetry inputs

The dashboard reads from names-only local surfaces such as:

- CPU and memory telemetry via `psutil`
- observer heartbeat freshness or recent JSONL activity
- watchdog heartbeat freshness
- append-only JSONL metrics for counts and density

Default locations include:

- `logs/health/calamum_ops_watchdog.heartbeat`
- `logs/health/calamum_observer.heartbeat`
- `logs/data/calamum/*.jsonl`

### Control surface

Control Deck actions emit file-based JSON intents for later runtime handling:

| Action family | Intent path |
|---|---|
| Kill | `logs/control/calamum/kill.signal.json` |
| Isolate | `logs/control/calamum/isolate.signal.json` |
| Refresh | `logs/control/calamum/refresh.signal.json` |

The governing doctrine is simple:

- the GUI is a presentation and operator interface surface, not SSOT
- watchdog remains the system-level governance layer
- if watchdog is down, the node remains isolated or quarantined until safe operating conditions are explicitly re-established

### Local runtime simulation agent

For local simulation and controlled runtime testing, `src/calamum_observer_agent.py` can:

- touch heartbeat files
- append JSONL records
- consume or acknowledge control signals

This local demo lane is telemetry simulation only and is **not** documented here as an authorized public Moltbook-facing workflow.

## Environment variables

Common optional overrides include:

- `CALAMUM_OPS_MODE`
- `CALAMUM_FRESHNESS_SEC`
- `CALAMUM_WATCHDOG_HEARTBEAT_PATH`
- `CALAMUM_OBSERVER_HEARTBEAT_PATH`
- `CALAMUM_DATA_DIR`
- `CALAMUM_DENSITY_SLICE_SEC`
- `CALAMUM_MOLTBOOK_SOURCE`
- `MOLTBOOK_API_KEY` — required for live collection; acquire and inject it through operator-local secret handling only
- `MOLTBOOK_HOST`
- `CALAMUM_LIVE_BATCH_LIMIT`
- `CALAMUM_LIVE_EMPTY_BACKOFF_SEC`
- `CALAMUM_BRAND_THUMB_PATH`
- `CALAMUM_BRAND_PANEL_PATH`

## Reproducibility and evidence boundaries

This project keeps three layers distinct:

1. **Method** — tracked code and public reference documents
2. **Mechanism** — runtime and analysis implementation in `src/`
3. **Observation** — project-local runtime evidence produced during controlled execution

That separation is both a documentation choice and a security boundary. Public surfaces remain readable and reproducible, while high-detail operational residue stays out of the tracked artifact set.

## Live collection contract

When `CALAMUM_MOLTBOOK_SOURCE=live` is selected, the current runtime normalizes that source onto the retained `real` axis used by the observer-derived evidence tree. The canonical observer-agent stream is therefore:

- `logs/data/calamum/observer_derived/real/<watch|canary|live|honeypot>/moltbook_metrics.jsonl`

Adjacent baseline and readiness evidence are retained under the matching `observer_derived/real/<mode>/resource/` and `observer_derived/real/<mode>/evidence/` directories.

This runtime family is local evidence retained outside the public tracked documentation set.

## Scope note

This README introduces the project, summarizes the public contract, and routes readers to the deeper policy, methodology, and manual surfaces. Use those adjacent references for implementation-level detail.
