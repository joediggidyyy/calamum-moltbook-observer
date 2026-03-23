# Calamum Simulation Workspace

This directory contains tools and artifacts for validating the Calamum architecture (Observer + Librarian feedback loops).

## Contents

- `run_simulation.py`: Canonical simulation/sandbox entrypoint. It can run the feedback-loop simulation and the current sandbox validation definitions from one dispatcher.
- `calamum_observer_daemon.py`: Simulation-only daemon surface retained for controlled simulation use.

## Usage

```powershell
python projects\calamum-moltbook-observer\src\simulation\run_simulation.py
```

List available definitions:

```powershell
python projects\calamum-moltbook-observer\src\simulation\run_simulation.py --list-definitions
```

Run the metadata-contract sandbox probe through the canonical entrypoint:

```powershell
python projects\calamum-moltbook-observer\src\simulation\run_simulation.py metadata-contract
```

Run the baseline-monitor runtime probe through the canonical entrypoint:

```powershell
python projects\calamum-moltbook-observer\src\simulation\run_simulation.py baseline-monitor-runtime
```

## Methodology

The default feedback-loop simulation:
1. Creates a temp directory structure (`data/`, `control/`, `health/`).
2. Seeds a strict rotation policy (2KB limit).
3. Spawns an Agent thread that generates synthetic Moltbook data.
4. Spawns a Librarian thread that scans for files and processes them.
5. Monitors `rotation_policy.json` for updates.
6. Succeeds when the Librarian detects actual data density and raises the rotation limit significantly (proving the feedback loop).

The sandbox definitions reuse the same entrypoint but pivot into isolated `observerctl` probes that write evidence under `report_tmp/` without requiring complex terminal injection.

Planned structured sandbox CLI surface and output-frame rules are recorded in:

- `projects/calamum-moltbook-observer/docs/plans/SIMULATION_SANDBOX_CLI_SURFACE_PLAN_20260323.md`
