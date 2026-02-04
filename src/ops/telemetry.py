"""Telemetry collection for the Calamum Ops dashboard.

Goal: keep the Ghost Console UI stable while driving key indicators from real signals.

Sources (best-effort, no secrets):
- CPU/MEM: psutil
- Records/Density: newest JSONL in repo-root logs/data/calamum
- OBS: observer heartbeat file OR recent activity on JSONL
- WD: watchdog heartbeat file (touched by dashboard reset control by default)

All paths may be overridden with environment variables.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import psutil


def _find_repo_root(start: Path) -> Path:
    """Walk upward until a directory containing a `logs/` folder is found."""
    cur = start
    while True:
        if (cur / 'logs').exists():
            return cur
        if cur.parent == cur:
            # Fallback: use start parent; callers should handle missing logs.
            return start
        cur = cur.parent


def _now_ts() -> float:
    return time.time()


def _is_fresh(path: Path, max_age_sec: float, now_ts: Optional[float] = None) -> bool:
    if not path.exists():
        return False
    now = now_ts if now_ts is not None else _now_ts()
    try:
        age = now - path.stat().st_mtime
    except OSError:
        return False
    return age <= max_age_sec


def _safe_touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Write an empty file if it doesn't exist; update mtime if it does.
    path.touch(exist_ok=True)


def _newest_jsonl(data_dir: Path) -> Optional[Path]:
    if not data_dir.exists():
        return None
    candidates = [p for p in data_dir.glob('*.jsonl') if p.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


class _JsonlAppendCounter:
    """Efficient-ish line counter for an append-only JSONL file.

    Keeps a file offset and total line count. If the file shrinks/rotates,
    it resets and recounts from scratch.
    """

    def __init__(self) -> None:
        self.path: Optional[Path] = None
        self.offset: int = 0
        self.total_lines: int = 0
        self.last_size: int = 0

    def set_path(self, path: Optional[Path]) -> None:
        if path is None:
            self.path = None
            self.offset = 0
            self.total_lines = 0
            self.last_size = 0
            return
        if self.path != path:
            self.path = path
            self.offset = 0
            self.total_lines = 0
            self.last_size = 0

    def poll(self, max_read_bytes: int = 2_000_000) -> Tuple[int, int]:
        """Return (new_lines, total_lines).

        NOTE: we cap how many bytes we read per poll to avoid long blocking reads
        which can stall the event loop and destabilize the UI.
        """
        if self.path is None or not self.path.exists():
            return 0, self.total_lines

        try:
            size = self.path.stat().st_size
        except OSError:
            return 0, self.total_lines

        # Rotated or truncated
        if size < self.last_size or size < self.offset:
            self.offset = 0
            self.total_lines = 0

        new_lines = 0
        try:
            with self.path.open('rb') as f:
                f.seek(self.offset)
                remaining = max(0, max_read_bytes)
                # Stream reads in chunks to keep memory bounded.
                while remaining > 0:
                    read_size = min(256 * 1024, remaining)
                    chunk = f.read(read_size)
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    new_lines += chunk.count(b'\n')

                if new_lines:
                    self.total_lines += new_lines

                # Always advance offset by how much we actually read.
                self.offset = f.tell()
        except OSError:
            return 0, self.total_lines

        self.last_size = size
        return new_lines, self.total_lines


@dataclass
class TelemetryConfig:
    # Heartbeats
    watchdog_heartbeat_path: Path
    observer_heartbeat_path: Path
    freshness_sec: float

    # Data source
    data_dir: Path

    # Density aggregation
    density_slice_sec: float

    # Performance knobs
    active_jsonl_rescan_sec: float
    jsonl_max_read_bytes_per_poll: int


def load_config(module_file: Path) -> TelemetryConfig:
    repo_root = _find_repo_root(module_file.resolve())

    freshness_sec = float(os.getenv('CALAMUM_FRESHNESS_SEC', '15'))

    wd_hb = Path(os.getenv(
        'CALAMUM_WATCHDOG_HEARTBEAT_PATH',
        str(repo_root / 'logs' / 'health' / 'calamum_ops_watchdog.heartbeat'),
    ))
    obs_hb = Path(os.getenv(
        'CALAMUM_OBSERVER_HEARTBEAT_PATH',
        str(repo_root / 'logs' / 'health' / 'calamum_observer.heartbeat'),
    ))

    data_dir = Path(os.getenv(
        'CALAMUM_DATA_DIR',
        str(repo_root / 'logs' / 'data' / 'calamum'),
    ))

    density_slice_sec = float(os.getenv('CALAMUM_DENSITY_SLICE_SEC', '15'))

    active_jsonl_rescan_sec = float(os.getenv('CALAMUM_ACTIVE_JSONL_RESCAN_SEC', '3.0'))
    try:
        jsonl_max_read_bytes_per_poll = int(os.getenv('CALAMUM_JSONL_MAX_READ_BYTES', '2000000'))
    except Exception:
        jsonl_max_read_bytes_per_poll = 2_000_000

    return TelemetryConfig(
        watchdog_heartbeat_path=wd_hb,
        observer_heartbeat_path=obs_hb,
        freshness_sec=freshness_sec,
        data_dir=data_dir,
        density_slice_sec=density_slice_sec,
        active_jsonl_rescan_sec=active_jsonl_rescan_sec,
        jsonl_max_read_bytes_per_poll=jsonl_max_read_bytes_per_poll,
    )


class TelemetryProvider:
    def __init__(self, config: TelemetryConfig) -> None:
        self.config = config
        self._counter = _JsonlAppendCounter()
        self._density_window: List[int] = [0] * 12
        self._slice_started_ts: float = _now_ts()
        self._slice_count: int = 0
        self._active_jsonl_cache: Optional[Path] = None
        self._active_jsonl_last_scan_ts: float = 0.0

    def reset_watchdog(self) -> None:
        """Touch the watchdog heartbeat marker (used by dashboard reset control)."""
        _safe_touch(self.config.watchdog_heartbeat_path)

    def _pick_active_jsonl(self) -> Optional[Path]:
        now = _now_ts()
        # Avoid glob+stat on every tick; it can get expensive with many JSONL files.
        interval = float(max(0.25, self.config.active_jsonl_rescan_sec))
        if self._active_jsonl_cache is not None and (now - self._active_jsonl_last_scan_ts) < interval:
            return self._active_jsonl_cache

        self._active_jsonl_last_scan_ts = now
        self._active_jsonl_cache = _newest_jsonl(self.config.data_dir)
        return self._active_jsonl_cache

    def update(self) -> dict:
        """Collect a telemetry snapshot.

        Returns a dict with keys:
          cpu, mem, new_records, total_records, density_bins,
          watchdog_active, observer_active, active_jsonl_path
        """
        now = _now_ts()

        # CPU/MEM
        try:
            cpu = float(psutil.cpu_percent(interval=None))
        except Exception:
            cpu = 0.0
        try:
            mem = float(psutil.virtual_memory().percent)
        except Exception:
            mem = 0.0

        # Data file (JSONL) for records/density + fallback observer liveness
        active_jsonl = self._pick_active_jsonl()
        self._counter.set_path(active_jsonl)
        new_lines, total_lines = self._counter.poll(max_read_bytes=self.config.jsonl_max_read_bytes_per_poll)

        # Density window: aggregate new lines into coarse time slices so the
        # histogram is less twitchy and better represents “volume over time”.
        self._slice_count += int(new_lines)
        slice_sec = float(max(0.25, self.config.density_slice_sec))
        elapsed = now - self._slice_started_ts
        if elapsed >= slice_sec:
            self._density_window = (self._density_window[1:] + [int(self._slice_count)])[-12:]
            self._slice_started_ts = now
            self._slice_count = 0

        # Density bins (0-100 normalized per rolling max)
        denom = max(self._density_window) if max(self._density_window) > 0 else 1
        density_bins = [int(min(100, round((x / denom) * 100))) for x in self._density_window]

        # Heartbeat freshness
        watchdog_active = _is_fresh(self.config.watchdog_heartbeat_path, self.config.freshness_sec, now_ts=now)

        observer_active = _is_fresh(self.config.observer_heartbeat_path, self.config.freshness_sec, now_ts=now)
        if not observer_active and active_jsonl is not None:
            observer_active = _is_fresh(active_jsonl, self.config.freshness_sec, now_ts=now)

        return {
            'cpu': cpu,
            'mem': mem,
            'new_records': int(new_lines),
            'total_records': int(total_lines),
            'density_bins': density_bins,
            'density_raw_window': list(self._density_window),
            'density_slice_sec': float(self.config.density_slice_sec),
            'watchdog_active': bool(watchdog_active),
            'observer_active': bool(observer_active),
            'active_jsonl_path': str(active_jsonl) if active_jsonl is not None else None,
        }
