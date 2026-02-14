from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Ensure the Calamum observer `src/` directory is importable when tests run from repo root.
_SRC_DIR = Path(__file__).resolve().parents[1]
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))


def test_watchdog_scheduler_due_and_catchup(tmp_path: Path, monkeypatch) -> None:
    # Arrange a minimal Calamum runtime tree.
    project_root = tmp_path
    (project_root / "PROJECT_MANIFEST.json").write_text("{}\n", encoding="utf-8")
    log_dir = project_root / "logs"
    health_dir = log_dir / "health"
    ctrl_dir = log_dir / "control" / "calamum"
    health_dir.mkdir(parents=True, exist_ok=True)
    ctrl_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("CALAMUM_REPO_ROOT", str(project_root))
    monkeypatch.setenv("CALAMUM_LOG_DIR", str(log_dir))
    monkeypatch.setenv("CALAMUM_CONTROL_DIR", str(ctrl_dir))

    # Keep the catch-up threshold small for the test.
    monkeypatch.setenv("CALAMUM_SCHEDULE_STARTUP_CATCHUP_THRESHOLD_SEC", "10")

    from calamum_watchdog import WatchdogSupervisor

    wd = WatchdogSupervisor(interval_sec=0.1)

    # Use tz-aware local time.
    now_local = datetime.now().astimezone()
    today = now_local.date().isoformat()
    yesterday = (now_local.date() - timedelta(days=1)).isoformat()

    # If already ran today, not due.
    assert wd._is_due_daily(last_run_local_date=today, now_local=now_local, hh=9, mm=0) is False

    # If before scheduled time, not due.
    before = now_local.replace(hour=8, minute=59, second=0, microsecond=0)
    assert wd._is_due_daily(last_run_local_date=yesterday, now_local=before, hh=9, mm=0) is False

    # At/after scheduled time and not run today, due.
    at_time = now_local.replace(hour=9, minute=0, second=0, microsecond=0)
    assert wd._is_due_daily(last_run_local_date=yesterday, now_local=at_time, hh=9, mm=0) is True

    # Startup catch-up requires downtime >= threshold and not run today.
    assert wd._is_due_startup_catchup(last_run_local_date=today, now_local=before, downtime_sec=999.0) is False
    assert wd._is_due_startup_catchup(last_run_local_date=yesterday, now_local=before, downtime_sec=1.0) is False
    assert wd._is_due_startup_catchup(last_run_local_date=yesterday, now_local=before, downtime_sec=11.0) is True


def test_watchdog_scheduler_state_file_created(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path
    (project_root / "PROJECT_MANIFEST.json").write_text("{}\n", encoding="utf-8")
    log_dir = project_root / "logs"
    health_dir = log_dir / "health"
    ctrl_dir = log_dir / "control" / "calamum"
    health_dir.mkdir(parents=True, exist_ok=True)
    ctrl_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("CALAMUM_REPO_ROOT", str(project_root))
    monkeypatch.setenv("CALAMUM_LOG_DIR", str(log_dir))
    monkeypatch.setenv("CALAMUM_CONTROL_DIR", str(ctrl_dir))

    from calamum_watchdog import WatchdogSupervisor

    wd = WatchdogSupervisor(interval_sec=0.1)

    # The method expects a UTC datetime.
    _ = wd._update_last_seen_and_get_downtime_sec(now_utc=datetime.now(timezone.utc))

    assert wd._schedule_state_path.exists()
    text = wd._schedule_state_path.read_text(encoding="utf-8", errors="ignore")
    assert "last_seen_utc" in text
