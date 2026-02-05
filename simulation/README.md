# Calamum Simulation Workspace

This directory contains tools and artifacts for validating the Calamum architecture (Observer + Librarian feedback loops).

## Contents

-   `run_simulation.py`: End-to-end simulation script that provisions a temporary environment, runs the Agent and Librarian in threads, and asserts that the Adaptive Rotation Policy is functioning.

## Usage

```powershell
python projects\calamum-moltbook-observer\simulation\run_simulation.py
```

## Methodology

The simulation:
1.  Creates a temp directory structure (`data/`, `control/`, `health/`).
2.  Seeds a "strict" rotation policy (2KB limit).
3.  Spawns an **Agent Thread** that generates synthetic Moltbook data.
4.  Spawns a **Librarian Thread** that scans for files and processes them.
5.  Monitors the `rotation_policy.json` for updates.
6.  Succeeds when the Librarian detects the actual data density and raises the rotation limit significantly (proving the feedback loop).
