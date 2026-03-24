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

Run the Frame 4 negative-path regression probe:

```powershell
python projects\calamum-moltbook-observer\src\simulation\run_simulation.py metadata-contract-regression
```

Run the baseline-monitor runtime probe through the canonical entrypoint:

```powershell
python projects\calamum-moltbook-observer\src\simulation\run_simulation.py baseline-monitor-runtime
```

Run the Frame 5 validation-cycle lineage probe:

```powershell
python projects\calamum-moltbook-observer\src\simulation\run_simulation.py validation-cycle-lineage
```

Run the Frame 6 restart continuity probe:

```powershell
python projects\calamum-moltbook-observer\src\simulation\run_simulation.py baseline-monitor-restart-continuity
```

Run the Frame 6 malformed-state recovery probe:

```powershell
python projects\calamum-moltbook-observer\src\simulation\run_simulation.py baseline-monitor-state-recovery
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

Current retained probe lanes include:

- `metadata-contract` for Frame 4 metadata parity
- `metadata-contract-regression` for Frame 4 negative-path regression detection
- `baseline-monitor-runtime` for broad runtime/readiness continuity
- `validation-cycle-lineage` for Frame 5 append-only validation-cycle lineage
- `baseline-monitor-restart-continuity` for Frame 6 restart-safe continuity anchor preservation
- `baseline-monitor-state-recovery` for Frame 6 malformed persisted-state degradation and repair

Planned structured sandbox CLI surface and output-frame rules are recorded in:

- `projects/calamum-moltbook-observer/docs/plans/SIMULATION_SANDBOX_CLI_SURFACE_PLAN_20260323.md`
