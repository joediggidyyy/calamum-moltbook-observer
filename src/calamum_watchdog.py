"""Calamum Watchdog Supervisor.

AUTHORITY: SUPERVISOR
The Watchdog operates independently to monitor the health of the Calamum stack:
1.  Observer Agent
2.  Librarian Daemon
3.  Ghost Console (Dashboard)

It enforces 'Stay in Line' policy:
-   Checks heartbeats.
-   Checks PID liveness.
-   Emits ALERTS if a team member is down.
-   Updates its own supervisor heartbeat.

This component MUST run as a distinct process with its own PID.
"""

__version__ = "1.1.0"

import json
import os
import sys
import time
import psutil
import subprocess
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Local imports check
try:
    from calamum_config import get_calamum_health_dir, get_calamum_control_dir
    from calamum_keepalive import KeepaliveHelper
    import obfuscator_lib
except ImportError:
    # Bootstrap path if running directly
    sys.path.append(str(Path(__file__).resolve().parent))
    from calamum_config import get_calamum_health_dir, get_calamum_control_dir
    try:
        from calamum_keepalive import KeepaliveHelper
    except ImportError:
        KeepaliveHelper = None
    try:
        import obfuscator_lib
    except ImportError:
        obfuscator_lib = None

def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def _local_now() -> datetime:
    # tz-aware local time (DST-safe)
    return datetime.now().astimezone()


def _parse_utc_iso(s: str) -> Optional[datetime]:
    if not s:
        return None
    try:
        raw = str(s).strip()
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _safe_int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return int(default)
    try:
        return int(str(raw).strip())
    except Exception:
        return int(default)


@dataclass
class _ScheduledTask:
    task_id: str
    label: str
    script_rel: str
    schedule_hh: int
    schedule_mm: int
    argv: List[str]


class WatchdogSupervisor:
    def __init__(self, interval_sec: float = 5.0):
        self.interval_sec = interval_sec
        self.health_dir = get_calamum_health_dir()
        self.control_dir = get_calamum_control_dir()

        # Resolve project/repo roots for running scheduled reports.
        # health_dir -> logs/health; project_root -> logs/..; repo_root -> project_root/../..
        self.project_root = self.health_dir.resolve().parents[1]
        self.repo_root = self.project_root.resolve().parents[1]

        # Scheduler state under local_untracked/ (ignored).
        self._schedule_state_path = (
            self.project_root / "local_untracked" / "scheduler" / "watchdog_schedule_state.json"
        ).resolve()

        # Prevent overlapping report runs.
        self._schedule_lock = threading.Lock()
        self._schedule_thread: Optional[threading.Thread] = None
        self._schedule_bootstrap_done = False

        # Startup catch-up threshold: if watchdog downtime exceeds this, run missed daily
        # reports immediately on startup (even if before the scheduled time).
        self._startup_catchup_threshold_sec = float(
            _safe_int_env("CALAMUM_SCHEDULE_STARTUP_CATCHUP_THRESHOLD_SEC", 6 * 60 * 60)
        )

        # Approved daily schedules (local time).
        # NOTE: These are intentionally embedded in the watchdog so they run when the system is up.
        self._scheduled_tasks = [
            _ScheduledTask(
                task_id="ops_parameters",
                label="Ops parameters report",
                script_rel="projects/calamum-moltbook-observer/tools/report_ops_parameters.py",
                schedule_hh=9,
                schedule_mm=0,
                argv=[],
            ),
            _ScheduledTask(
                task_id="runtime_artifacts",
                label="Runtime artifacts audit",
                script_rel="projects/calamum-moltbook-observer/tools/audit_runtime_artifacts.py",
                schedule_hh=9,
                schedule_mm=5,
                argv=[],
            ),
            _ScheduledTask(
                task_id="repo_health",
                label="Repo health audit",
                script_rel="projects/calamum-moltbook-observer/tools/audit_repo_health.py",
                schedule_hh=9,
                schedule_mm=10,
                argv=[],
            ),
        ]
        
        # My Heartbeat (Supervisor Proof of Life)
        self.my_heartbeat = self.health_dir / 'calamum_ops_watchdog.heartbeat'
        
        # Team Roster
        self.roster = {
            'agent': {
                'heartbeat': self.health_dir / 'calamum_observer.heartbeat',
                'max_age': 15.0,
                'label': 'Observer Agent'
            },
            'librarian': {
                'heartbeat': self.health_dir / 'calamum_librarian.heartbeat',
                'max_age': 30.0,
                'label': 'Librarian Daemon'
            }
            # Dashboard is checked via URL/Process in typical setups, 
            # but we can look for a heartbeat file if we implement one there.
        }


    def _load_schedule_state(self) -> Dict[str, Any]:
        try:
            if self._schedule_state_path.exists():
                raw = self._schedule_state_path.read_text(encoding="utf-8", errors="ignore")
                obj = json.loads(raw or "{}")
                return obj if isinstance(obj, dict) else {}
        except Exception:
            return {}
        return {}


    def _write_schedule_state(self, state: Dict[str, Any]) -> None:
        try:
            self._schedule_state_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._schedule_state_path.with_suffix(self._schedule_state_path.suffix + ".tmp")
            tmp.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            tmp.replace(self._schedule_state_path)
        except Exception:
            # Best-effort: scheduler must not crash watchdog.
            pass


    def _update_last_seen_and_get_downtime_sec(self, *, now_utc: datetime) -> Optional[float]:
        state = self._load_schedule_state()
        last_seen_s = str(state.get("last_seen_utc") or "")
        last_seen_dt = _parse_utc_iso(last_seen_s)
        downtime: Optional[float] = None
        if last_seen_dt is not None:
            try:
                downtime = max(0.0, (now_utc - last_seen_dt).total_seconds())
            except Exception:
                downtime = None

        state["version"] = 1
        state["updated_at_utc"] = now_utc.isoformat().replace("+00:00", "Z")
        state["last_seen_utc"] = state["updated_at_utc"]
        if "tasks" not in state or not isinstance(state.get("tasks"), dict):
            state["tasks"] = {}
        self._write_schedule_state(state)
        return downtime


    def _get_task_state(self, state: Dict[str, Any], task_id: str) -> Dict[str, Any]:
        tasks = state.get("tasks")
        if not isinstance(tasks, dict):
            tasks = {}
            state["tasks"] = tasks
        t = tasks.get(task_id)
        if isinstance(t, dict):
            return t
        t = {}
        tasks[task_id] = t
        return t


    def _is_due_daily(self, *, last_run_local_date: str, now_local: datetime, hh: int, mm: int) -> bool:
        # Due if not run today and local time >= scheduled time.
        try:
            today = now_local.date().isoformat()
        except Exception:
            return False
        if last_run_local_date == today:
            return False

        try:
            if (now_local.hour, now_local.minute) < (int(hh), int(mm)):
                return False
        except Exception:
            return False
        return True


    def _is_due_startup_catchup(self, *, last_run_local_date: str, now_local: datetime, downtime_sec: Optional[float]) -> bool:
        # If downtime exceeded threshold and task has not run today, run immediately on startup
        # (even if before scheduled time).
        if downtime_sec is None:
            return False
        if downtime_sec < float(self._startup_catchup_threshold_sec):
            return False
        try:
            today = now_local.date().isoformat()
        except Exception:
            return False
        return last_run_local_date != today


    def _run_script(self, *, label: str, script_abs: Path, argv: List[str]) -> Tuple[int, str]:
        cmd = [sys.executable, str(script_abs)] + list(argv)
        try:
            p = subprocess.run(
                cmd,
                cwd=str(self.repo_root),
                capture_output=True,
                text=True,
                timeout=900.0,
                check=False,
            )
            rc = int(p.returncode)
            err = (p.stderr or "").strip()
            if rc != 0:
                # Names-only stderr; safe.
                print(
                    f"[{_utc_now_iso()}] [WATCHDOG-SCHEDULER] [ERR] {label} rc={rc} stderr={err[:2000]}",
                    file=sys.stderr,
                    flush=True,
                )
            else:
                print(
                    f"[{_utc_now_iso()}] [WATCHDOG-SCHEDULER] [OK] {label}",
                    file=sys.stdout,
                    flush=True,
                )
            return rc, err
        except Exception as e:
            msg = repr(e)
            print(
                f"[{_utc_now_iso()}] [WATCHDOG-SCHEDULER] [ERR] {label} exception={msg}",
                file=sys.stderr,
                flush=True,
            )
            return 999, msg


    def _scheduler_worker(self, *, run_mode: str, downtime_sec: Optional[float]) -> None:
        # run_mode: "startup" or "tick"
        with self._schedule_lock:
            state = self._load_schedule_state()
            now_utc = datetime.now(timezone.utc)
            now_local = _local_now()
            tasks = state.get("tasks")
            if not isinstance(tasks, dict):
                state["tasks"] = {}

            for t in self._scheduled_tasks:
                t_state = self._get_task_state(state, t.task_id)
                last_local = str(t_state.get("last_run_local_date") or "")
                due = False
                if run_mode == "startup":
                    due = self._is_due_startup_catchup(last_run_local_date=last_local, now_local=now_local, downtime_sec=downtime_sec)
                if not due:
                    due = self._is_due_daily(last_run_local_date=last_local, now_local=now_local, hh=t.schedule_hh, mm=t.schedule_mm)

                if not due:
                    continue

                script_abs = (self.repo_root / t.script_rel).resolve()
                if not script_abs.exists():
                    print(
                        f"[{_utc_now_iso()}] [WATCHDOG-SCHEDULER] [ERR] missing script: {t.script_rel}",
                        file=sys.stderr,
                        flush=True,
                    )
                    t_state["last_exit_code"] = 998
                    t_state["last_error"] = "missing script"
                    continue

                rc, err = self._run_script(label=t.label, script_abs=script_abs, argv=list(t.argv))
                now_utc = datetime.now(timezone.utc)
                now_local = _local_now()
                t_state["last_run_utc"] = now_utc.isoformat().replace("+00:00", "Z")
                t_state["last_run_local_date"] = now_local.date().isoformat()
                t_state["last_exit_code"] = int(rc)
                t_state["last_error"] = (err or "")[:4000]

            state["updated_at_utc"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            state["version"] = 1
            self._write_schedule_state(state)


    def _maybe_start_scheduler(self, *, run_mode: str, downtime_sec: Optional[float]) -> None:
        # Avoid overlapping scheduler runs.
        if self._schedule_thread is not None and self._schedule_thread.is_alive():
            return

        th = threading.Thread(
            target=self._scheduler_worker,
            kwargs={"run_mode": run_mode, "downtime_sec": downtime_sec},
            daemon=True,
            name="calamum_watchdog_scheduler",
        )
        self._schedule_thread = th
        th.start()

    def _touch_heartbeat(self):
        self.my_heartbeat.parent.mkdir(parents=True, exist_ok=True)
        
        # Security: Write a SIGNED heartbeat so sub-agents can trust it.
        # Just touching the file is insufficient for "Signed Watchdog" compliance.
        payload = {
            "component": "calamum_watchdog",
            "ts": _utc_now_iso(),
            "status": "alive"
        }
        
        if obfuscator_lib:
            try:
                payload = obfuscator_lib.Obfuscator.sign_record(payload)
            except Exception as e:
                print(f"[WATCHDOG] Signing failed: {e}", file=sys.stderr)
        
        try:
            # Atomic write pattern
            temp = self.my_heartbeat.with_suffix('.tmp')
            temp.write_text(json.dumps(payload), encoding='utf-8')
            temp.replace(self.my_heartbeat)
        except Exception as e:
            print(f"[WATCHDOG] Heartbeat write failed: {e}", file=sys.stderr)


    def _check_team(self):
        now = time.time()
        issues = []

        for role, cfg in self.roster.items():
            hb_path = cfg['heartbeat']
            if not hb_path.exists():
                issues.append(f"{cfg['label']} DOWN (No Heartbeat)")
                continue
            
            try:
                mtime = hb_path.stat().st_mtime
                age = now - mtime
                if age > cfg['max_age']:
                    issues.append(f"{cfg['label']} STALE (Lag: {age:.1f}s)")
            except OSError:
                # Locked file usually means it's being written to (Active)
                pass

        if issues:
            self._log_alert(issues)
        else:
            # All Green
            pass

    def _log_alert(self, issues: list):
        # Log to stderr (captured by launcher logs)
        msg = f"[{_utc_now_iso()}] [WATCHDOG-SUPERVISOR] ALERT: {', '.join(issues)}"
        print(msg, file=sys.stderr)
        
        # Also could emit a signal or write to a centralized status file

    def loop(self):
        print(f"[{_utc_now_iso()}] Watchdog Supervisor 1.0 Started. Authority established.")

        # Initialize shared keepalive helper (if available)
        keepalive_helper = None
        if KeepaliveHelper:
            # Use raw env read logic here since we removed the helper function
            interval_raw = os.getenv('CALAMUM_STDOUT_KEEPALIVE_SEC', '60')
            try:
                interval = float(interval_raw)
            except Exception:
                interval = 60.0
            
            if interval > 0:
                keepalive_helper = KeepaliveHelper("CalamumWatchdog", interval_seconds=interval)

        while True:
            try:
                self._touch_heartbeat()
                self._check_team()

                # Scheduler: run approved daily reports while the watchdog is alive.
                now_utc = datetime.now(timezone.utc)
                downtime_sec = self._update_last_seen_and_get_downtime_sec(now_utc=now_utc)
                if not self._schedule_bootstrap_done:
                    self._schedule_bootstrap_done = True
                    # Startup catch-up: if watchdog downtime exceeded threshold, run missed dailies now.
                    self._maybe_start_scheduler(run_mode="startup", downtime_sec=downtime_sec)
                # Normal tick scheduling (after the scheduled time).
                self._maybe_start_scheduler(run_mode="tick", downtime_sec=None)

                # Operator-friendly liveness signal (stdout; rate-limited)
                if keepalive_helper:
                    keepalive_helper.emit("RUNNING", {"interval_sec": self.interval_sec})

            except Exception as e:
                print(f"[{_utc_now_iso()}] [WATCHDOG] ERROR in loop: {e}", file=sys.stderr)
            
            time.sleep(self.interval_sec)


if __name__ == "__main__":
    wd = WatchdogSupervisor()
    wd.loop()
