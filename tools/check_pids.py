"""Check Calamum stack PIDs referenced by pidfiles.

Read-only helper to confirm whether processes are running.

Run from repo root:
  .venv-core\\Scripts\\python.exe projects\\calamum-moltbook-observer\\tools\\check_pids.py
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

import psutil


REPO_ROOT = Path(__file__).resolve().parents[3]
PROJECT_ROOT = REPO_ROOT / "projects" / "calamum-moltbook-observer"


def _read_pid(path: Path) -> Optional[int]:
    try:
        raw = path.read_text(encoding="utf-8", errors="replace").splitlines()[0].strip()
        if raw.isdigit():
            return int(raw)
    except Exception:
        return None
    return None


def _fmt_mb(n: int) -> str:
    try:
        return f"{n / (1024 * 1024):.1f}MB"
    except Exception:
        return "?MB"


def main() -> int:
    pidfiles: Dict[str, Path] = {
        "agent": PROJECT_ROOT / "calamum_agent.pid",
        "librarian": PROJECT_ROOT / "calamum_librarian.pid",
        "watchdog": PROJECT_ROOT / "calamum_watchdog.pid",
        "dashboard": PROJECT_ROOT / "ghost_console.pid",
    }

    for name, pf in pidfiles.items():
        if not pf.exists():
            print(f"{name}: pidfile MISSING ({pf})")
            continue
        pid = _read_pid(pf)
        if not pid:
            print(f"{name}: pidfile unreadable ({pf})")
            continue

        if not psutil.pid_exists(pid):
            print(f"{name}: PID {pid} NOT RUNNING")
            continue

        try:
            p = psutil.Process(pid)
            # Use oneshot to reduce Windows API round-trips.
            with p.oneshot():
                proc_name = p.name()
                mem = p.memory_info().rss
                status = p.status()
            # Avoid cmdline() here; it can be slow or flaky on some Windows setups.
            print(
                f"{name}: PID {pid} RUNNING | name={proc_name} | status={status} | rss={_fmt_mb(mem)}"
            )
        except Exception as e:
            print(f"{name}: PID {pid} RUNNING (details unavailable: {e})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
