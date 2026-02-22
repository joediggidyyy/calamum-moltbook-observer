from __future__ import annotations

import json
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_simulation_code_locality_under_src() -> None:
    root = _project_root()
    assert not (root / "simulation").exists(), "Top-level simulation/ must not exist after migration"

    src_sim = root / "src" / "simulation"
    assert src_sim.exists(), "src/simulation/ must exist"

    required = {
        "run_simulation.py",
        "calamum_observer_daemon.py",
        "README.md",
    }
    actual = {p.name for p in src_sim.iterdir() if p.is_file()}
    missing = sorted(required - actual)
    assert not missing, f"Missing expected simulation files under src/simulation: {missing}"


def test_jobs_and_operations_report_naming_boundaries() -> None:
    root = _project_root()

    jobs_dir = root / "jobs"
    reports_dir = root / "docs" / "reports" / "operations"

    bad_in_jobs = sorted(
        p.name for p in jobs_dir.glob("**/*") if p.is_file() and p.name.startswith("JOB_REPORT_")
    )
    assert not bad_in_jobs, f"Job report files found in jobs/: {bad_in_jobs}"

    bad_in_reports = sorted(
        p.name for p in reports_dir.glob("**/*") if p.is_file() and p.name.startswith("CALAMUM_JOB_")
    )
    assert not bad_in_reports, f"Job definition files found in docs/reports/operations/: {bad_in_reports}"


def test_manifest_authoritative_root_alignment() -> None:
    root = _project_root()
    manifest = json.loads((root / "PROJECT_MANIFEST.json").read_text(encoding="utf-8"))

    tracked = set(manifest["layout"]["tracked_roots"])
    ignored = set(manifest["layout"]["ignored_roots"])

    assert "simulation/" not in tracked, "Legacy top-level simulation/ must not remain in tracked roots"
    assert "src/" in tracked, "src/ must remain a tracked root"
    assert "logs/" in ignored, "logs/ must remain ignored"
    assert "local_untracked/" in ignored, "local_untracked/ must remain ignored"
