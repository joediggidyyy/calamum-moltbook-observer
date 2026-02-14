from __future__ import annotations

import sys
from pathlib import Path

# Ensure the Calamum observer `src/` directory is importable when tests run from repo root.
_SRC_DIR = Path(__file__).resolve().parents[1]
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))


def test_env_repo_root_outside_project_is_ignored(tmp_path: Path, monkeypatch) -> None:
    """If CALAMUM_REPO_ROOT points somewhere that is *not* the Calamum project root,
    we should ignore it and keep paths project-local.
    """

    project_root = Path(__file__).resolve().parents[2]

    # Point at an arbitrary directory with no PROJECT_MANIFEST.json marker.
    monkeypatch.setenv("CALAMUM_REPO_ROOT", str(tmp_path))
    monkeypatch.delenv("CALAMUM_LOG_DIR", raising=False)
    monkeypatch.delenv("CALAMUM_ALLOW_NONLOCAL_PATHS", raising=False)

    from calamum_config import get_calamum_log_dir

    assert get_calamum_log_dir().resolve() == (project_root / "logs").resolve()


def test_env_log_dir_outside_project_is_rejected_by_default(tmp_path: Path, monkeypatch) -> None:
    project_root = Path(__file__).resolve().parents[2]

    external_logs = tmp_path / "external_logs"
    external_logs.mkdir(parents=True, exist_ok=True)

    monkeypatch.delenv("CALAMUM_REPO_ROOT", raising=False)
    monkeypatch.setenv("CALAMUM_LOG_DIR", str(external_logs))
    monkeypatch.delenv("CALAMUM_ALLOW_NONLOCAL_PATHS", raising=False)

    from calamum_config import get_calamum_log_dir

    assert get_calamum_log_dir().resolve() == (project_root / "logs").resolve()


def test_env_log_dir_outside_project_allowed_with_flag(tmp_path: Path, monkeypatch) -> None:
    external_logs = tmp_path / "external_logs"
    external_logs.mkdir(parents=True, exist_ok=True)

    monkeypatch.delenv("CALAMUM_REPO_ROOT", raising=False)
    monkeypatch.setenv("CALAMUM_LOG_DIR", str(external_logs))
    monkeypatch.setenv("CALAMUM_ALLOW_NONLOCAL_PATHS", "1")

    from calamum_config import get_calamum_log_dir

    assert get_calamum_log_dir().resolve() == external_logs.resolve()
