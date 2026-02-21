from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def _load_audit_module():
    project_root = Path(__file__).resolve().parents[2]
    tool_path = project_root / "tools" / "audit_implementation_drift.py"
    spec = importlib.util.spec_from_file_location("calamum_audit_implementation_drift", tool_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[str(spec.name)] = mod
    spec.loader.exec_module(mod)
    return mod


def test_project_manifest_layout_detects_missing_tracked_root(monkeypatch, tmp_path: Path) -> None:
    mod = _load_audit_module()

    repo_root = tmp_path / "repo"
    project_root = repo_root / "projects" / "calamum-moltbook-observer"
    project_root.mkdir(parents=True, exist_ok=True)

    manifest = {
        "project": {"id": "calamum-moltbook-observer"},
        "layout": {
            "tracked_roots": ["tools/", "src/"],
            "ignored_roots": ["local_untracked/", "logs/", "src/logs/", "src/.agent_session/"],
        },
        "version": "1.0",
    }
    (project_root / "PROJECT_MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")

    # Simulate tracked top-level dirs discovered from git tree.
    monkeypatch.setattr(
        mod,
        "_git_ls_tree_dirs",
        lambda _repo_root, _treeish: ["tools", "src", "docs"],
    )

    result = mod._check_project_manifest_layout(repo_root, project_root)

    assert result["manifest_exists"] is True
    assert result["manifest_readable"] is True
    assert "docs" in result["missing_from_manifest_tracked_roots"]
    assert any("missing from layout.tracked_roots" in v for v in result["violations"])


def test_project_manifest_layout_passes_when_aligned(monkeypatch, tmp_path: Path) -> None:
    mod = _load_audit_module()

    repo_root = tmp_path / "repo"
    project_root = repo_root / "projects" / "calamum-moltbook-observer"
    project_root.mkdir(parents=True, exist_ok=True)

    manifest = {
        "project": {"id": "calamum-moltbook-observer"},
        "layout": {
            "tracked_roots": ["tools/", "src/", "docs/"],
            "ignored_roots": ["local_untracked/", "logs/", "src/logs/", "src/.agent_session/"],
        },
        "version": "1.0",
    }
    (project_root / "PROJECT_MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")

    monkeypatch.setattr(
        mod,
        "_git_ls_tree_dirs",
        lambda _repo_root, _treeish: ["tools", "src", "docs"],
    )

    result = mod._check_project_manifest_layout(repo_root, project_root)

    assert result["manifest_exists"] is True
    assert result["manifest_readable"] is True
    assert result["violations"] == []


def test_changed_files_unit_test_coverage_flags_missing(monkeypatch, tmp_path: Path) -> None:
    mod = _load_audit_module()

    repo_root = tmp_path / "repo"
    project_root = repo_root / "projects" / "calamum-moltbook-observer"
    tools_dir = project_root / "tools"
    tools_dir.mkdir(parents=True, exist_ok=True)
    (tools_dir / "new_tool.py").write_text("print('x')\n", encoding="utf-8")

    monkeypatch.setattr(
        mod,
        "_git_changed_files",
        lambda _repo_root: ["projects/calamum-moltbook-observer/tools/new_tool.py"],
    )

    result = mod._check_changed_files_unit_test_coverage(repo_root, project_root)
    assert result["missing_unit_tests_count"] == 1
    row = result["missing_unit_tests"][0]
    assert row["module"].endswith("tools/new_tool.py")


def test_changed_files_unit_test_coverage_passes_with_test(monkeypatch, tmp_path: Path) -> None:
    mod = _load_audit_module()

    repo_root = tmp_path / "repo"
    project_root = repo_root / "projects" / "calamum-moltbook-observer"
    tools_dir = project_root / "tools"
    tests_dir = project_root / "src" / "tests"
    tools_dir.mkdir(parents=True, exist_ok=True)
    tests_dir.mkdir(parents=True, exist_ok=True)

    (tools_dir / "new_tool.py").write_text("print('x')\n", encoding="utf-8")
    (tests_dir / "test_new_tool.py").write_text("def test_smoke():\n    assert True\n", encoding="utf-8")

    monkeypatch.setattr(
        mod,
        "_git_changed_files",
        lambda _repo_root: ["projects/calamum-moltbook-observer/tools/new_tool.py"],
    )

    result = mod._check_changed_files_unit_test_coverage(repo_root, project_root)
    assert result["missing_unit_tests_count"] == 0
    assert result["missing_unit_tests"] == []
