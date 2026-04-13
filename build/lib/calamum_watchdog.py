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

__version__ = "1.0.1"

import atexit
import hashlib
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

        # Single-instance guard (prevents duplicate watchdogs and confusing telemetry).
        self._instance_lock_path: Optional[Path] = None
        self._instance_lock_acquired: bool = False
        self._instance_mutex_handle: Any = None
        self._last_converge_check_ts: float = 0.0

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

        # Alert-churn guardrails: emit immediately on state transition, then
        # throttle repeated identical ALERT lines to avoid log-volume-induced lag.
        self._last_issue_signature: str = ""
        self._last_alert_emit_ts: float = 0.0
        self._alert_repeat_sec: float = float(_safe_int_env("CALAMUM_WATCHDOG_ALERT_REPEAT_SEC", 60))


    def _pid_looks_like_watchdog(self, pid: int) -> Optional[bool]:
        """Best-effort check: does a PID appear to be a calamum_watchdog process?

        Returns:
            True/False if determinable, None if unknown (e.g., access denied).
        """
        try:
            p = psutil.Process(int(pid))
            if not p.is_running():
                return False
            try:
                cmd = " ".join(p.cmdline() or [])
            except Exception:
                cmd = ""
            if "calamum_watchdog.py" in cmd.replace("\\", "/"):
                return True
            # If we cannot match command line, fall back to process name heuristics.
            try:
                nm = (p.name() or "").lower()
            except Exception:
                nm = ""
            if nm in {"python.exe", "python"}:
                return None
            return None
        except psutil.NoSuchProcess:
            return False
        except psutil.AccessDenied:
            return None
        except Exception:
            return None


    def _release_instance_lock_best_effort(self) -> None:
        if not self._instance_lock_acquired:
            return
        p = self._instance_lock_path
        if not p:
            return


    def _release_instance_mutex_best_effort(self) -> None:
        h = self._instance_mutex_handle
        if not h:
            return
        try:
            import ctypes  # local import; only meaningful on Windows

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            try:
                kernel32.ReleaseMutex(h)
            except Exception:
                pass
            kernel32.CloseHandle(h)
        except Exception:
            return
        finally:
            self._instance_mutex_handle = None
        try:
            # Only delete if we still own it (PID match).
            raw = p.read_text(encoding="utf-8", errors="ignore")
            obj = json.loads(raw or "{}") if raw else {}
            pid_in_file = int(obj.get("pid") or 0) if isinstance(obj, dict) else 0
            if pid_in_file == os.getpid():
                p.unlink(missing_ok=True)  # type: ignore[call-arg]
        except Exception:
            # Never crash on cleanup.
            return


    def _ensure_single_instance(self) -> bool:
        """Acquire a single-instance lock; return False if another instance is active."""
        if (os.getenv("CALAMUM_WATCHDOG_ALLOW_MULTI") or "").strip() == "1":
            return True

        # Prefer a robust OS primitive on Windows to avoid startup race conditions.
        if os.name == "nt":
            try:
                import ctypes
                from ctypes import wintypes

                # Mutex name is stable per project root to avoid collisions.
                root_tag = hashlib.sha256(str(self.project_root).lower().encode("utf-8")).hexdigest()[:12]
                mutex_name = f"Local\\CalamumWatchdogSingleInstance_{root_tag}"

                kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
                CreateMutexW = kernel32.CreateMutexW
                CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
                CreateMutexW.restype = wintypes.HANDLE

                ERROR_ALREADY_EXISTS = 183
                ctypes.set_last_error(0)
                # Take initial ownership if newly created.
                h = CreateMutexW(None, True, mutex_name)
                last = int(ctypes.get_last_error())
                if h:
                    # One-time, names-only diagnostic (helps explain duplicate watchdog instances).
                    try:
                        print(
                            f"[{_utc_now_iso()}] [WATCHDOG] mutex_acquire pid={os.getpid()} last_error={last}",
                            file=sys.stderr,
                            flush=True,
                        )
                    except Exception:
                        pass
                    if last == int(ERROR_ALREADY_EXISTS):
                        print(
                            f"[{_utc_now_iso()}] [WATCHDOG] Another watchdog instance holds mutex. Exiting.",
                            file=sys.stderr,
                            flush=True,
                        )
                        try:
                            kernel32.CloseHandle(h)
                        except Exception:
                            pass
                        return False

                    self._instance_mutex_handle = h
                    atexit.register(self._release_instance_mutex_best_effort)
                    return True
            except Exception as e:
                # Fall back to lock file approach.
                print(
                    f"[{_utc_now_iso()}] [WATCHDOG] Mutex guard unavailable: {e}",
                    file=sys.stderr,
                    flush=True,
                )
                pass

        lock_path = (self.project_root / "local_untracked" / "locks" / "calamum_watchdog.lock").resolve()
        try:
            lock_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            # If we cannot create the lock dir, proceed rather than fail closed.
            return True

        def _try_create() -> bool:
            try:
                fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    rec = {
                        "pid": int(os.getpid()),
                        "started_at_utc": _utc_now_iso(),
                        "component": "calamum_watchdog",
                        "host": (os.getenv("COMPUTERNAME") or ""),
                    }
                    f.write(json.dumps(rec, sort_keys=True) + "\n")
                self._instance_lock_path = lock_path
                self._instance_lock_acquired = True
                atexit.register(self._release_instance_lock_best_effort)
                return True
            except FileExistsError:
                return False
            except Exception as e:
                # If locking fails for unexpected reasons, fail closed to avoid duplicate
                # watchdog instances producing conflicting telemetry.
                print(
                    f"[{_utc_now_iso()}] [WATCHDOG] Lock acquisition error: {e}",
                    file=sys.stderr,
                    flush=True,
                )
                return False

        if _try_create():
            return True

        # Lock file exists; determine whether it is stale.
        existing_pid = 0
        started_at_utc = ""
        try:
            raw = lock_path.read_text(encoding="utf-8", errors="ignore")
            obj = json.loads(raw or "{}") if raw else {}
            if isinstance(obj, dict):
                existing_pid = int(obj.get("pid") or 0)
                started_at_utc = str(obj.get("started_at_utc") or "")
        except Exception:
            existing_pid = 0

        # Guard against startup races: if the lock is very new, treat it as held
        # even if we cannot validate the PID yet.
        try:
            started_dt = _parse_utc_iso(started_at_utc)
            if started_dt is not None:
                age_s = (datetime.now(timezone.utc) - started_dt).total_seconds()
                if age_s >= 0.0 and age_s < 30.0:
                    print(
                        f"[{_utc_now_iso()}] [WATCHDOG] Lock is recent (age_s={age_s:.1f}); another instance is starting. Exiting.",
                        file=sys.stderr,
                        flush=True,
                    )
                    return False
        except Exception:
            pass

        if existing_pid > 0:
            looks = self._pid_looks_like_watchdog(existing_pid)
            if looks is True or looks is None:
                # Another instance appears to be running (or we cannot safely disprove it).
                print(
                    f"[{_utc_now_iso()}] [WATCHDOG] Another watchdog instance is active (pid={existing_pid}). Exiting.",
                    file=sys.stderr,
                    flush=True,
                )
                return False

        # Stale lock: remove and retry once.
        try:
            lock_path.unlink(missing_ok=True)  # type: ignore[call-arg]
        except Exception:
            pass
        if _try_create():
            return True

        print(
            f"[{_utc_now_iso()}] [WATCHDOG] Unable to acquire single-instance lock. Exiting.",
            file=sys.stderr,
            flush=True,
        )
        return False


    def _converge_duplicate_instances_best_effort(self) -> bool:
        """Best-effort convergence to a single watchdog instance.

        Observed failure mode (Windows): a watchdog process can spawn a second
        watchdog process (parent->child) with the same command line.

        Policy: prefer to keep the *child* (higher PID) when parent-child is detected.
        For non-parent/child duplicates, keep the highest PID (most recent).

        Returns:
            True if this process should continue running.
            False if this process should exit to avoid duplicates.
        """
        try:
            my_pid = int(os.getpid())
            my_ppid = int(os.getppid())

            # Fast path: if I have a direct child watchdog process, I am the parent stub.
            # Exit so only the child remains.
            try:
                me = psutil.Process(my_pid)
                for c in me.children(recursive=False):
                    try:
                        cmd = " ".join(c.cmdline() or [])
                    except Exception:
                        cmd = ""
                    if "calamum_watchdog.py" in cmd.replace("\\", "/"):
                        print(
                            f"[{_utc_now_iso()}] [WATCHDOG] Detected direct watchdog child pid={c.pid}; parent pid={my_pid} exiting to converge.",
                            file=sys.stderr,
                            flush=True,
                        )
                        return False
            except Exception:
                pass

            # Collect watchdog-like PIDs.
            watchdog_pids: List[int] = []
            watchdog_ppids: Dict[int, int] = {}

            for p in psutil.process_iter(attrs=["pid", "ppid", "cmdline"]):
                try:
                    pid = int(p.info.get("pid") or 0)
                    if pid <= 0:
                        continue
                    cmd = p.info.get("cmdline") or []
                    cmd_str = " ".join([str(x) for x in cmd if x])
                    if "calamum_watchdog.py" not in cmd_str.replace("\\", "/"):
                        continue
                    watchdog_pids.append(pid)
                    watchdog_ppids[pid] = int(p.info.get("ppid") or 0)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
                except Exception:
                    continue

            watchdog_pids = sorted(set(watchdog_pids))
            if len(watchdog_pids) <= 1:
                return True

            # If I spawned another watchdog instance, I should exit.
            for pid in watchdog_pids:
                if pid == my_pid:
                    continue
                if int(watchdog_ppids.get(pid) or 0) == my_pid:
                    print(
                        f"[{_utc_now_iso()}] [WATCHDOG] Detected watchdog child pid={pid}; parent pid={my_pid} exiting to converge.",
                        file=sys.stderr,
                        flush=True,
                    )
                    return False

            # If my parent is also a watchdog, prefer to keep running as the child.
            if my_ppid in watchdog_pids:
                return True

            # Otherwise (siblings), keep the newest-ish instance (highest PID).
            keep_pid = max(watchdog_pids)
            if my_pid != keep_pid:
                print(
                    f"[{_utc_now_iso()}] [WATCHDOG] Duplicate watchdogs detected pids={watchdog_pids}; keeping pid={keep_pid}. Exiting pid={my_pid}.",
                    file=sys.stderr,
                    flush=True,
                )
                return False

            return True
        except Exception:
            # Never crash on convergence logic.
            return True


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
        
        # Compliance: watchdog heartbeat MUST be signed.
        # If signing is unavailable or fails, do not overwrite the heartbeat with
        # an unsigned payload (stale is safer than untrusted fresh).
        if not obfuscator_lib:
            print("[WATCHDOG] Signing unavailable: obfuscator_lib not importable", file=sys.stderr)
            return

        try:
            payload = obfuscator_lib.Obfuscator.sign_record(payload)
        except Exception as e:
            print(f"[WATCHDOG] Signing failed: {e}", file=sys.stderr)
            return
        
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

        signature = " | ".join(sorted([str(x) for x in issues])) if issues else ""
        # Transition to healthy: emit once to close the alert narrative.
        if not issues and self._last_issue_signature:
            print(f"[{_utc_now_iso()}] [WATCHDOG-SUPERVISOR] RECOVERY: all monitored teammates healthy", file=sys.stderr)
            self._last_issue_signature = ""
            self._last_alert_emit_ts = now
            return

        if issues:
            is_transition = signature != self._last_issue_signature
            is_repeat_due = (now - float(self._last_alert_emit_ts)) >= max(5.0, float(self._alert_repeat_sec))
            if is_transition or is_repeat_due:
                self._log_alert(issues)
                self._last_issue_signature = signature
                self._last_alert_emit_ts = now

    def _log_alert(self, issues: list):
        # Log to stderr (captured by launcher logs)
        msg = f"[{_utc_now_iso()}] [WATCHDOG-SUPERVISOR] ALERT: {', '.join(issues)}"
        print(msg, file=sys.stderr)
        
        # Also could emit a signal or write to a centralized status file

    def loop(self):
        if not self._ensure_single_instance():
            return
        if not self._converge_duplicate_instances_best_effort():
            return
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
                # Periodic convergence guard: if a duplicate watchdog appears after startup,
                # the parent instance will exit and the child will remain.
                now_s = time.time()
                if (now_s - float(self._last_converge_check_ts)) >= 10.0:
                    self._last_converge_check_ts = now_s
                    if not self._converge_duplicate_instances_best_effort():
                        return

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
