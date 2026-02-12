"""Telemetry collection for the Calamum Ops dashboard.

Goal: keep the Ghost Console UI stable while driving key indicators from real signals.

Sources (best-effort, no secrets):
- CPU/MEM: psutil
- Records/Density: newest JSONL in repo-root logs/data/calamum
- OBS: observer heartbeat file OR recent activity on JSONL
- WD: watchdog heartbeat file (touched by the watchdog supervisor process)

All paths may be overridden with environment variables.
"""

from __future__ import annotations

import os
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional, Tuple

import psutil


# Optional: if available, validate watchdog heartbeat signatures.
# This prevents a freshness-only false-green when the agent will isolate due to untrusted watchdog heartbeats.
try:
    import obfuscator_lib  # type: ignore
except ImportError:  # pragma: no cover
    obfuscator_lib = None

try:
    from calamum_config import get_calamum_data_dir, get_calamum_health_dir
except ImportError:
    from ..calamum_config import get_calamum_data_dir, get_calamum_health_dir


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


def _verify_signed_record_best_effort(path: Path) -> Tuple[Optional[bool], str]:
    """Return (signature_valid_or_None_if_unavailable, detail_string).

    - If verifier isn't available, return (None, 'unavailable').
    - If JSON is malformed or verification fails, return (False, <reason>).
    - If verification succeeds, return (True, 'ok').
    """
    if not obfuscator_lib:
        return None, 'unavailable'
    if not path.exists():
        return False, 'missing'
    try:
        raw = path.read_text(encoding='utf-8', errors='replace')
        data: Any = json.loads(raw or '{}')
        if not isinstance(data, dict):
            return False, 'not-a-dict'
        # If unsigned/tampered, verify_record should return False.
        ok = bool(obfuscator_lib.Obfuscator.verify_record(data))
        if ok:
            return True, 'ok'
        return False, 'invalid'
    except Exception:
        return False, 'error'


def _safe_touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Write an empty file if it doesn't exist; update mtime if it does.
    path.touch(exist_ok=True)


def _newest_jsonl(data_dir: Path) -> Optional[Path]:
    if not data_dir.exists():
        return None
    try:
        candidates = []
        for p in data_dir.glob('*.jsonl'):
            try:
                if p.is_file():
                    candidates.append(p)
            except OSError:
                continue

        if not candidates:
            return None

        def safe_mtime(p: Path) -> float:
            try:
                return p.stat().st_mtime
            except OSError:
                return 0.0

        return max(candidates, key=safe_mtime)
    except Exception:
        return None


class _SafeStat:
    """Windows-friendly stat wrapper that retries on locking errors."""
    def __init__(self) -> None:
        self._last_good_size: int = 0
        self._last_good_mtime: float = 0.0

    def get_size_and_mtime(self, path: Path) -> Tuple[int, float]:
        # Retry loop for Windows file locking
        for _ in range(3):
            try:
                if not path.exists():
                    # If file genuinely disappears, we might want to reset,
                    # but for stability, returning last known is safer until it reappears.
                    return self._last_good_size, self._last_good_mtime
                st = path.stat()
                self._last_good_size = st.st_size
                self._last_good_mtime = st.st_mtime
                return st.st_size, st.st_mtime
            except OSError:
                time.sleep(0.02)
        # Fallback to last known good state
        return self._last_good_size, self._last_good_mtime


class _JsonlAppendCounter:
    """Robust line counter for an append-only JSONL file.

    Design goals (Ghost Console):
    - Prefer UI stability over exactness under contention.
    - Avoid stateful offset tracking (fragile with rotation/locking on Windows).
    - Use tail sampling to estimate counts for large files.
    - Enforce monotonic totals so transient read/stat failures don't blank charts.
    """

    def __init__(self) -> None:
        self.path: Optional[Path] = None
        self.total_lines: int = 0
        self._stat_tracker = _SafeStat()
        self._historical_count: int = 0
        self._last_manifest_check: float = 0.0

    def set_path(self, path: Optional[Path]) -> None:
        if self.path != path:
            self.path = path
            # Reset tracker for new file
            self._stat_tracker = _SafeStat()

    def _sync_manifest(self) -> int:
        # Check manifest periodically (e.g. every 5s) or if count seems low
        now = time.time()
        if now - self._last_manifest_check < 5.0 and self._historical_count > 0:
            return self._historical_count
            
        self._last_manifest_check = now
        count = 0
        try:
             # Look for manifest relative to data dir
             # We assume self.path is in data_dir, or we find data_dir via config if we had access.
             # Best effort: look in archive/ relative to the data dir parent.
             # Assuming structure: logs/data/calamum/ -> ../archive -> logs/data/calamum/archive
             # Wait, Librarian puts archive in data_dir/archive.
             if self.path:
                 base = self.path.parent
                 manifest_path = base / 'archive' / 'manifest.json'
                 if manifest_path.exists():
                     data = json.loads(manifest_path.read_text(encoding='utf-8'))
                     for _, meta in data.items():
                         count += meta.get('records', 0)
        except Exception:
            pass
        
        self._historical_count = count
        return count

    def _count_jsonl_records(self, data: bytes) -> int:
        """Count JSONL records in a byte buffer.

        Records are newline-delimited. If the buffer does not end with a newline
        but has content, treat the trailing partial line as a record.
        """
        try:
            nl = int(data.count(b'\n'))
            if data and not data.endswith(b'\n'):
                nl += 1
            return int(max(0, nl))
        except Exception:
            return 0

    def _read_tail(self, path: Path, n_bytes: int) -> Optional[bytes]:
        """Read last N bytes from file (best-effort; retries on Windows locks)."""
        if n_bytes <= 0:
            return b''
        for _ in range(3):
            try:
                with path.open('rb') as f:
                    try:
                        f.seek(-n_bytes, os.SEEK_END)
                    except OSError:
                        # Small file or non-seekable: fall back to beginning.
                        try:
                            f.seek(0)
                        except Exception:
                            pass
                    return f.read(n_bytes)
            except OSError:
                time.sleep(0.02)
            except Exception:
                return None
        return None

    def poll(self, max_read_bytes: int = 2_000_000) -> Tuple[int, int]:
        """Return (new_lines, total_lines).
        
        Robust Implementation:
        - Active File: SafeStat byte estimation (survives locking).
        - Historical: Retrieved from archive/manifest.json.
        """
        historical = self._sync_manifest()

        active_lines = 0
        if self.path:
            size, _ = self._stat_tracker.get_size_and_mtime(self.path)

            # Clamp budget: keep it bounded and predictable.
            try:
                budget = int(max(16_384, min(10_000_000, int(max_read_bytes))))
            except Exception:
                budget = 2_000_000

            if size > 0:
                sample_bytes = int(min(size, budget))
                tail = self._read_tail(self.path, sample_bytes)

                # If we can't read (locked), hold last known totals to avoid blanking.
                if tail is None:
                    new_total = self.total_lines
                    return 0, int(new_total)

                tail_lines = self._count_jsonl_records(tail)

                if size <= budget:
                    # Exact count for small files (tail == whole file).
                    active_lines = int(tail_lines)
                else:
                    # Estimate lines using average bytes-per-record from tail sample.
                    # This is a tailing strategy (no offsets) and stays stable under locking.
                    if tail_lines <= 0:
                        active_lines = 0
                    else:
                        avg_bpr = float(sample_bytes) / float(tail_lines)
                        # Guard against degenerate averages.
                        avg_bpr = float(max(32.0, min(4096.0, avg_bpr)))
                        active_lines = int(max(0, round(float(size) / avg_bpr)))

        new_total = int(historical + active_lines)
        
        # Enforce Monotonicity (prevent negative deltas from locking glitches)
        if new_total < self.total_lines:
            new_total = self.total_lines
            
        delta = new_total - self.total_lines
        self.total_lines = new_total
        
        return delta, self.total_lines



@dataclass
class TelemetryConfig:
    # Heartbeats
    watchdog_heartbeat_path: Path
    observer_heartbeat_path: Path
    librarian_heartbeat_path: Path
    freshness_sec: float

    # Data source
    data_dir: Path

    # Density aggregation
    density_slice_sec: float

    # Density histogram shape
    density_bins: int

    # Performance knobs
    active_jsonl_rescan_sec: float
    jsonl_max_read_bytes_per_poll: int


def load_config(module_file: Path) -> TelemetryConfig:
    # Use consolidated config
    health_dir = get_calamum_health_dir()
    
    freshness_sec = float(os.getenv('CALAMUM_FRESHNESS_SEC', '15'))

    wd_hb = Path(os.getenv(
        'CALAMUM_WATCHDOG_HEARTBEAT_PATH',
        str(health_dir / 'calamum_ops_watchdog.heartbeat'),
    ))
    obs_hb = Path(os.getenv(
        'CALAMUM_OBSERVER_HEARTBEAT_PATH',
        str(health_dir / 'calamum_observer.heartbeat'),
    ))
    lib_hb = Path(os.getenv(
        'CALAMUM_LIBRARIAN_HEARTBEAT_PATH',
        str(health_dir / 'calamum_librarian.heartbeat'),
    ))

    data_dir = get_calamum_data_dir()

    # Default to a visibly "streaming" cadence; can be overridden via env var.
    density_slice_sec = float(os.getenv('CALAMUM_DENSITY_SLICE_SEC', '2'))

    try:
        density_bins = int(os.getenv('CALAMUM_DENSITY_BINS', '12'))
    except Exception:
        density_bins = 12
    density_bins = int(max(3, min(60, density_bins)))

    active_jsonl_rescan_sec = float(os.getenv('CALAMUM_ACTIVE_JSONL_RESCAN_SEC', '3.0'))
    try:
        jsonl_max_read_bytes_per_poll = int(os.getenv('CALAMUM_JSONL_MAX_READ_BYTES', '2000000'))
    except Exception:
        jsonl_max_read_bytes_per_poll = 2_000_000

    return TelemetryConfig(
        watchdog_heartbeat_path=wd_hb,
        observer_heartbeat_path=obs_hb,
        librarian_heartbeat_path=lib_hb,
        freshness_sec=freshness_sec,
        data_dir=data_dir,
        density_slice_sec=density_slice_sec,
        density_bins=density_bins,
        active_jsonl_rescan_sec=active_jsonl_rescan_sec,
        jsonl_max_read_bytes_per_poll=jsonl_max_read_bytes_per_poll,
    )


class TelemetryProvider:
    def __init__(self, config: TelemetryConfig) -> None:
        self.config = config
        self._counter = _JsonlAppendCounter()
        # Oldest -> newest density slice counts.
        self._density_window: List[int] = [0] * int(max(3, min(60, self.config.density_bins)))
        self._slice_started_ts: float = _now_ts()
        self._slice_count: int = 0
        self._active_jsonl_cache: Optional[Path] = None
        self._active_jsonl_last_scan_ts: float = 0.0
        self._active_path_high_water_mtime: float = 0.0

    def _clamp_density_slice_sec(self, value: float) -> float:
        try:
            v = float(value)
        except Exception:
            v = float(self.config.density_slice_sec)
        if not (v > 0):
            v = float(self.config.density_slice_sec)
        # Hard clamps: avoid degenerate cadence and avoid overly large windows.
        return float(max(0.25, min(60.0, v)))

    def _clamp_density_bins(self, value: int) -> int:
        try:
            n = int(value)
        except Exception:
            n = int(self.config.density_bins)
        return int(max(3, min(60, n)))

    def _ensure_density_window_size(self, n_bins: int) -> None:
        """Resize internal density window to match requested bin count.

        Keeps the most-recent values stable (window is oldest->newest).
        """
        n = self._clamp_density_bins(n_bins)
        cur = list(self._density_window)
        if len(cur) == n:
            return
        if len(cur) > n:
            self._density_window = cur[-n:]
            return
        # len(cur) < n
        pad = [0] * (n - len(cur))
        self._density_window = pad + cur

    def set_density_slice_sec(self, slice_sec: float) -> float:
        """Adjust density slice width at runtime (best-effort, non-persistent)."""
        ss = self._clamp_density_slice_sec(slice_sec)
        self.config.density_slice_sec = float(ss)
        # Reset slice accumulator so the change takes effect immediately.
        self._slice_started_ts = _now_ts()
        self._slice_count = 0
        return float(ss)

    def set_density_bins(self, bins: int) -> int:
        """Adjust density histogram bin count at runtime (best-effort, non-persistent)."""
        n = self._clamp_density_bins(bins)
        self.config.density_bins = int(n)
        self._ensure_density_window_size(n)
        # Reset slice accumulator to avoid mixing incompatible windows.
        self._slice_started_ts = _now_ts()
        self._slice_count = 0
        return int(n)

    def get_density_config(self) -> dict:
        return {
            'density_slice_sec': float(self.config.density_slice_sec),
            'density_bins': int(self._clamp_density_bins(self.config.density_bins)),
        }

    def reset_watchdog(self) -> None:
        """Deprecated no-op.

        Watchdog liveness is proved by the watchdog supervisor process touching
        its own heartbeat. The UI should not fabricate watchdog freshness.

        This method is retained for backwards compatibility with older UI code
        paths, but intentionally performs no action.
        """
        return None

    def _pick_active_jsonl(self) -> Optional[Path]:
        now = _now_ts()
        # Avoid glob+stat on every tick; it can get expensive with many JSONL files.
        interval = float(max(0.25, self.config.active_jsonl_rescan_sec))
        
        # PROACTIVE FALLBACK: If cache is None, we should try harder.
        if self._active_jsonl_cache is not None and (now - self._active_jsonl_last_scan_ts) < interval:
            return self._active_jsonl_cache

        self._active_jsonl_last_scan_ts = now
        new_pick = _newest_jsonl(self.config.data_dir)

        # MONOTONIC GUARD: Prevent flapping to older files during Windows locking.
        # If the active file is locked, glob/stat may return 0 or miss it, choosing an old file.
        if new_pick is not None and self._active_jsonl_cache is not None:
             if new_pick != self._active_jsonl_cache:
                 try:
                     new_mtime = new_pick.stat().st_mtime
                     # If the new pick is older than the high-water mark of our current file,
                     # assume the current file is ghosting/locked and stick with it.
                     if new_mtime < self._active_path_high_water_mtime:
                         new_pick = self._active_jsonl_cache
                     else:
                         # Valid switch to a newer file; reset high water logic for the new file.
                         self._active_path_high_water_mtime = new_mtime
                 except OSError:
                     # If we can't stat the new pick, it's unsafe to switch.
                     new_pick = self._active_jsonl_cache

        # Persistence override: if scan fails (transient Windows locking on dir),
        # always prefer the cache over returning None/0.
        if new_pick is None:
             if self._active_jsonl_cache is not None:
                 return self._active_jsonl_cache
             
             # DETERMINISTIC FALLBACK:
             # If we have never found a file (start up) and scanning failed,
             # check for the known canonical filename directly.
             canary = self.config.data_dir / 'moltbook_canary_metrics.jsonl'
             # Note: We do NOT check exists() here to avoid lock failure.
             # We just assume it might be valid and let the counter try to stat it.
             return canary

        self._active_jsonl_cache = new_pick
        
        # Update high-water mark if possible
        if self._active_jsonl_cache:
             try:
                 ts = self._active_jsonl_cache.stat().st_mtime
                 if ts > self._active_path_high_water_mtime:
                     self._active_path_high_water_mtime = ts
             except OSError:
                 pass
                 
        return self._active_jsonl_cache
    
    def _get_freshness_age(self, path: Path, now_ts: float) -> Tuple[bool, float, str]:
        """Returns (is_fresh, age_sec, pretty_age)."""
        if not path.exists():
            return False, 9999.9, "Missing"
        try:
            mtime = path.stat().st_mtime
            age = max(0.0, now_ts - mtime)
            is_fresh = age <= self.config.freshness_sec
            return is_fresh, age, f"{age:.1f}s"
        except OSError:
            # File locked or vanished
            return False, 9999.9, "Locked"

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
        
        historical = self._counter._historical_count
        session_recs = max(0, total_lines - historical)

        # Ensure window size matches config (config may change at runtime).
        self._ensure_density_window_size(int(self.config.density_bins))

        # Density window: aggregate new lines into coarse time slices so the
        # histogram is less twitchy and better represents “volume over time”.
        self._slice_count += int(new_lines)
        slice_sec = self._clamp_density_slice_sec(self.config.density_slice_sec)
        elapsed = now - self._slice_started_ts
        if elapsed >= slice_sec:
            self._density_window = (self._density_window[1:] + [int(self._slice_count)])[-len(self._density_window):]
            self._slice_started_ts = now
            self._slice_count = 0

        # Density bins (0-100 normalized per rolling max)
        denom = max(self._density_window) if max(self._density_window) > 0 else 1
        density_bins = [int(min(100, round((x / denom) * 100))) for x in self._density_window]

        # Heartbeat freshness
        wd_fresh, wd_age, wd_age_str = self._get_freshness_age(self.config.watchdog_heartbeat_path, now)
        obs_fresh, obs_age, obs_age_str = self._get_freshness_age(self.config.observer_heartbeat_path, now)
        lib_fresh, lib_age, lib_age_str = self._get_freshness_age(self.config.librarian_heartbeat_path, now)

        # Heartbeat trust (signature validity)
        wd_sig_ok, wd_sig_detail = _verify_signed_record_best_effort(self.config.watchdog_heartbeat_path)
        # If signature verification is available, require it.
        wd_trusted = bool(wd_fresh and (wd_sig_ok is True)) if wd_sig_ok is not None else bool(wd_fresh)
        
        # Fallback for Observer if file lock prevents reading its heartbeat but data is flowing
        if not obs_fresh and active_jsonl is not None:
             # If we choose active_jsonl as proxy, check its freshness
             aj_fresh, aj_age, aj_age_str = self._get_freshness_age(active_jsonl, now)
             if aj_fresh:
                 obs_fresh = True
                 obs_age = aj_age
                 obs_age_str = aj_age_str

        return {
            'cpu': cpu,
            'mem': mem,
            'new_records': int(new_lines),
            'total_records': int(total_lines),
            'records_session': int(session_recs),
            'records_archive': int(historical),
            'density_bins': density_bins,
            'density_raw_window': list(self._density_window),
            'density_slice_sec': float(self.config.density_slice_sec),
            'watchdog_active': bool(wd_trusted),
            'watchdog_stats': {
                'age': wd_age,
                'age_str': wd_age_str,
                'path': str(self.config.watchdog_heartbeat_path.name),
                'signature_check_available': bool(obfuscator_lib),
                'signature_valid': wd_sig_ok,
                'signature_detail': wd_sig_detail,
            },
            'observer_active': bool(obs_fresh),
            'observer_stats': {'age': obs_age, 'age_str': obs_age_str, 'path': str(self.config.observer_heartbeat_path.name)},
            'librarian_active': bool(lib_fresh),
            'librarian_stats': {'age': lib_age, 'age_str': lib_age_str, 'path': str(self.config.librarian_heartbeat_path.name)},
            'active_jsonl_path': str(active_jsonl) if active_jsonl is not None else None,
        }
