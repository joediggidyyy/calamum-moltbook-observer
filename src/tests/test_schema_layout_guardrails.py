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
    local_reports_dir = root / "local_untracked" / "reports" / "operations"
    legacy_ops_reports_dir = root / "docs" / "reports" / "operations"
    legacy_queststack_reports_dir = root / "docs" / "reports" / "queststack"

    bad_in_jobs = sorted(
        p.name for p in jobs_dir.glob("**/*") if p.is_file() and p.name.startswith("JOB_REPORT_")
    )
    assert not bad_in_jobs, f"Job report files found in jobs/: {bad_in_jobs}"

    assert not legacy_ops_reports_dir.exists(), "Legacy docs/reports/operations/ must not exist after report-root realignment"
    assert not legacy_queststack_reports_dir.exists(), "Legacy docs/reports/queststack/ must not exist after report-root realignment"

    bad_in_reports = sorted(
        p.name for p in local_reports_dir.glob("**/*") if p.is_file() and p.name.startswith("CALAMUM_JOB_")
    )
    assert not bad_in_reports, f"Job definition files found in local_untracked/reports/operations/: {bad_in_reports}"


def test_manifest_authoritative_root_alignment() -> None:
    root = _project_root()
    manifest = json.loads((root / "PROJECT_MANIFEST.json").read_text(encoding="utf-8"))

    public_surface = manifest["public_surface"]
    content_roots = set(public_surface["content_roots"].keys())
    public_reports = set(manifest["public_reports"])

    assert "src/" in content_roots, "src/ must remain a public content root"
    assert "docs/manuals/" in content_roots, "docs/manuals/ must remain a public content root"
    assert "docs/reports/" in content_roots, "docs/reports/ must remain a public content root"
    assert "template_library/" in content_roots, "template_library/ must remain a public content root"
    assert "tools/" in content_roots, "tools/ must remain a public content root"
    assert "local_untracked/" not in content_roots, "local_untracked/ must not appear as a public content root"

    assert "docs/reports/aggregates/LATEST_COLLECTIONS.md" in public_reports, "Latest collections aggregate must remain declared as a public report"
    assert "docs/reports/aggregates/WORKFLOW_ROLLUP.md" in public_reports, "Workflow rollup must remain declared as a public report"
    assert "docs/reports/aggregates/THRESHOLD_SUMMARY.md" in public_reports, "Threshold summary must remain declared as a public report"
    assert "docs/reports/reference/GENERATED_REPORT_SURFACES.md" in public_reports, "Generated-report reference must use the reference lane"
    assert "docs/reports/validations/INDEX.md" in public_reports, "Validation index must use the validations lane"

    assert "docs/reports/PUBLIC_RUN_LEDGER.md" not in public_reports, "Legacy root-level public run ledger path must not remain in the manifest"
    assert "docs/reports/AGGREGATE_REPORT.md" not in public_reports, "Legacy root-level aggregate report path must not remain in the manifest"
    assert "docs/reports/GENERATED_REPORT_SURFACES.md" not in public_reports, "Legacy root-level generated-report reference must not remain in the manifest"
    assert "docs/reports/AGGREGATE_REPORT_SCHEMA.md" not in public_reports, "Archived aggregate schema must not remain in the manifest"
    assert "docs/reports/ds/INDEX.md" not in public_reports, "Legacy DS publication index must not remain in the manifest"
