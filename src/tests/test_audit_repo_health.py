from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def _load_audit_module():
    project_root = Path(__file__).resolve().parents[2]
    tool_path = project_root / "tools" / "audit_repo_health.py"
    spec = importlib.util.spec_from_file_location("calamum_audit_repo_health", tool_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[str(spec.name)] = mod
    spec.loader.exec_module(mod)
    return mod


def test_extract_status_from_queststack_json_prefers_top_level_status() -> None:
    mod = _load_audit_module()

    payload = {
        "status": "on-hold",
        "current_focus_frame": "FRAME-2",
        "frames": [
            {"frame_id": "FRAME-1", "status": "completed"},
            {"frame_id": "FRAME-2", "status": "open"},
        ],
    }

    assert mod._extract_status_from_queststack_json(json.dumps(payload)) == "blocked"


def test_check_job_status_sync_reads_json_queststack_status(tmp_path: Path) -> None:
    mod = _load_audit_module()

    repo_root = tmp_path / "repo"
    project_root = repo_root / "projects" / "calamum-moltbook-observer"
    queststack_path = project_root / "queststacks" / "QS-DEMO.json"
    tasks_path = repo_root / "operations" / "tasks.json"
    dashboard_path = repo_root / "docs" / "dashboards" / "room" / "JOBS_DASHBOARD.md"

    queststack_path.parent.mkdir(parents=True, exist_ok=True)
    tasks_path.parent.mkdir(parents=True, exist_ok=True)
    dashboard_path.parent.mkdir(parents=True, exist_ok=True)

    tasks_path.write_text(
        json.dumps(
            [
                {
                    "id": "calamum-demo-json-queststack",
                    "path": "projects/calamum-moltbook-observer/queststacks/QS-DEMO.json",
                    "status": "open",
                }
            ]
        ),
        encoding="utf-8",
    )
    dashboard_path.write_text("", encoding="utf-8")
    queststack_path.write_text(
        json.dumps(
            {
                "status": "open",
                "current_focus_frame": "FRAME-1",
                "frames": [{"frame_id": "FRAME-1", "status": "open"}],
            }
        ),
        encoding="utf-8",
    )

    result = mod._check_job_status_sync(repo_root, project_root)

    assert result["checked_task_count"] == 1
    assert result["violations"] == []