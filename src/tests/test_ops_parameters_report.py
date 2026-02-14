from __future__ import annotations

import json
import sys
import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Ensure the Calamum observer `src/` directory is importable when tests run from repo root.
_SRC_DIR = Path(__file__).resolve().parents[1]
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))


def test_ops_parameters_report_includes_figures_and_density(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path
    project_root = tmp_path

    # Mark the temp tree as a Calamum project root so calamum_config will trust it.
    (project_root / "PROJECT_MANIFEST.json").write_text("{}\n", encoding="utf-8")

    # Minimal tracked template
    tpl_rel = "tpl.md.template"
    tpl_path = repo_root / tpl_rel
    tpl_path.write_text(
        "# Ops Params\n\n"
        "## Figures of interest\n\n{{ figures_of_interest_block }}\n\n"
        "## Collection density (derived)\n\n{{ collection_density_block }}\n\n"
        "## Future\n\n{{ future_placeholders_block }}\n",
        encoding="utf-8",
    )

    # Create logs/data
    data_dir = project_root / "logs" / "data" / "calamum"
    health_dir = project_root / "logs" / "health"
    data_dir.mkdir(parents=True, exist_ok=True)
    health_dir.mkdir(parents=True, exist_ok=True)

    # Force runtime path resolution (calamum_config) to use the temp tree.
    monkeypatch.setenv("CALAMUM_REPO_ROOT", str(project_root))
    monkeypatch.setenv("CALAMUM_LOG_DIR", str(project_root / "logs"))
    monkeypatch.setenv("CALAMUM_DATA_DIR", str(data_dir))
    monkeypatch.setenv("CALAMUM_CONTROL_DIR", str(project_root / "logs" / "control" / "calamum"))

    # Heartbeats
    (health_dir / "calamum_ops_watchdog.heartbeat").touch()
    (health_dir / "calamum_observer.heartbeat").touch()
    (health_dir / "calamum_librarian.heartbeat").touch()

    # Active telemetry
    canary = data_dir / "moltbook_canary_metrics.jsonl"
    canary.write_text("{\"a\": 1}\n{\"a\": 2}\n", encoding="utf-8")

    # Archive manifest
    archive_dir = data_dir / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    manifest = archive_dir / "manifest.json"
    manifest.write_text(json.dumps({"shard_001": {"records": 10}}) + "\n", encoding="utf-8")

    # Prior provenance snapshot with metrics (to enable density)
    jsonl_rel = "local_untracked/audit_log/ops_parameters_report.jsonl"
    jsonl_path = project_root / jsonl_rel
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)

    prior_ts = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat().replace("+00:00", "Z")
    prior_snapshot = {
        "kind": "snapshot",
        "timestamp_utc": prior_ts,
        "run_id": "prior",
        "auditor": "ORACL-Prime",
        "overall_status": "OK",
        "metrics": {
            "active_records_total": 1,
            "archived_records_total": 10,
            "total_records": 11,
            "active_bytes_total": 0,
            "active_records_by_file": {"moltbook_canary_metrics.jsonl": 1},
        },
    }
    jsonl_path.write_text(json.dumps(prior_snapshot, sort_keys=True) + "\n", encoding="utf-8")

    # Import the real tool module by file path (not from the temp project tree).
    real_project_root = Path(__file__).resolve().parents[2]
    tool_path = real_project_root / "tools" / "report_ops_parameters.py"
    spec = importlib.util.spec_from_file_location("calamum_report_ops_parameters", tool_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[str(spec.name)] = mod
    spec.loader.exec_module(mod)
    report_ops_parameters = getattr(mod, "report_ops_parameters")

    evidence = report_ops_parameters(
        repo_root=repo_root,
        project_root=project_root,
        template_rel=tpl_rel,
        out_dir_rel="local_untracked/reports/ops_parameters",
        jsonl_rel=jsonl_rel,
        max_tail_bytes=1024,
        hb_warn_seconds=300.0,
        hb_err_seconds=900.0,
        scout_max_results=10,
        set_baseline=False,
        dry_run=False,
    )

    derived = evidence.get("derived_metrics")
    assert isinstance(derived, dict)
    assert derived.get("active_records_total") == 2
    assert derived.get("archived_records_total") == 10

    outputs = evidence.get("outputs")
    assert isinstance(outputs, dict)
    report_path_s = outputs.get("report_path")
    assert isinstance(report_path_s, str) and report_path_s

    report_text = Path(report_path_s).read_text(encoding="utf-8")
    assert "| Metric | Value | Notes |" in report_text
    assert "Report-to-report active collection rate" in report_text
    # Ensure the report-to-report row isn't the placeholder.
    assert "Report-to-report active collection rate | (n/a)" not in report_text
