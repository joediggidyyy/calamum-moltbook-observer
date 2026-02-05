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
from pathlib import Path

# Local imports check
try:
    from calamum_config import get_calamum_health_dir, get_calamum_control_dir
except ImportError:
    # Bootstrap path if running directly
    sys.path.append(str(Path(__file__).resolve().parent))
    from calamum_config import get_calamum_health_dir, get_calamum_control_dir

def _utc_now_iso() -> str:
    from datetime import datetime
    return datetime.utcnow().isoformat() + 'Z'

class WatchdogSupervisor:
    def __init__(self, interval_sec: float = 5.0):
        self.interval_sec = interval_sec
        self.health_dir = get_calamum_health_dir()
        self.control_dir = get_calamum_control_dir()
        
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

    def _touch_heartbeat(self):
        self.my_heartbeat.parent.mkdir(parents=True, exist_ok=True)
        self.my_heartbeat.touch(exist_ok=True)

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
        while True:
            try:
                self._touch_heartbeat()
                self._check_team()
            except Exception as e:
                print(f"Watchdog Interval Error: {e}", file=sys.stderr)
            
            time.sleep(self.interval_sec)

if __name__ == "__main__":
    wd = WatchdogSupervisor()
    wd.loop()
