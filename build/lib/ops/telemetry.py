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
from datetime import datetime, timezone
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
    from calamum_config import get_calamum_data_dir, get_calamum_health_dir, get_calamum_control_dir
except ImportError:
    from ..calamum_config import get_calamum_data_dir, get_calamum_health_dir, get_calamum_control_dir


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
        preferred = []
        fallback = []
        for p in data_dir.rglob('*.jsonl'):
            try:
                if 'archive' in p.parts:
                    continue
                if p.is_file():
                    # Canonical ingest stream for dashboard record counters.
                    if p.name == 'moltbook_metrics.jsonl':
                        preferred.append(p)
                    else:
                        fallback.append(p)
            except OSError:
                continue

        candidates = preferred if preferred else fallback
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


def _is_sim_likely_path(path: Optional[Path]) -> bool:
    """Best-effort sim classifier based on path/name tokens."""
    if path is None:
        return False
    lowered_parts = [str(part).strip().lower() for part in path.parts]
    lowered_name = str(path.name).strip().lower()
    if 'observer_derived' in lowered_parts:
        try:
            idx = lowered_parts.index('observer_derived')
            if idx + 1 < len(lowered_parts):
                return lowered_parts[idx + 1] == 'sim'
        except Exception:
            pass
    return ('legacy_sim' in lowered_name) or ('simulation' in lowered_name)


def _archive_manifest_totals(data_dir: Path) -> Tuple[int, int, int]:
    """Return (archive_total, archive_non_sim, archive_sim_estimate)."""
    manifest_path = data_dir / 'archive' / 'manifest.json'
    if not manifest_path.exists():
        return 0, 0, 0

    try:
        payload = json.loads(manifest_path.read_text(encoding='utf-8'))
    except Exception:
        return 0, 0, 0

    if not isinstance(payload, dict):
        return 0, 0, 0

    total = 0
    sim_est = 0
    for key, meta in payload.items():
        if not isinstance(meta, dict):
            continue
        records = int(meta.get('records', 0) or 0)
        total += records

        key_l = str(key or '').strip().lower()
        artifact_l = str(meta.get('artifact_path', '') or '').strip().lower()
        imported = meta.get('imported_from', {}) if isinstance(meta.get('imported_from', {}), dict) else {}
        src_art_l = str(imported.get('src_artifact', '') or '').strip().lower()
        src_tag_l = str(imported.get('source_tag', '') or '').strip().lower()
        blob = ' '.join([key_l, artifact_l, src_art_l, src_tag_l])

        if ('simulation' in blob) or ('legacy_sim' in blob) or ('/sim/' in blob) or ('\\sim\\' in blob):
            sim_est += records

    non_sim = max(0, total - sim_est)
    return int(total), int(non_sim), int(sim_est)


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

    def __init__(self, data_dir: Optional[Path] = None) -> None:
        self.path: Optional[Path] = None
        self.total_lines: int = 0
        self._stat_tracker = _SafeStat()
        self._historical_count: int = 0
        self._last_manifest_check: float = 0.0
        self._data_dir: Optional[Path] = data_dir

    def set_path(self, path: Optional[Path]) -> None:
        if self.path != path:
            self.path = path
            # Reset tracker for new file
            self._stat_tracker = _SafeStat()
            # Reset running total baseline when switching streams.
            # Without this, monotonic clamping can pin totals from an old lane
            # and suppress new-record deltas on the newly active lane.
            self.total_lines = 0

    def _sync_manifest(self) -> int:
        # Check manifest periodically (e.g. every 5s) or if count seems low
        now = time.time()
        if now - self._last_manifest_check < 5.0 and self._historical_count > 0:
            return self._historical_count
            
        self._last_manifest_check = now
        count = 0
        try:
             manifest_path: Optional[Path] = None
             if self._data_dir:
                 manifest_path = self._data_dir / 'archive' / 'manifest.json'
             elif self.path:
                 # Backward-compatible fallback if data_dir is unavailable.
                 manifest_path = self.path.parent / 'archive' / 'manifest.json'

             if manifest_path and manifest_path.exists():
                 data = json.loads(manifest_path.read_text(encoding='utf-8'))
                 if isinstance(data, dict):
                     for _, meta in data.items():
                         if isinstance(meta, dict):
                             count += int(meta.get('records', 0) or 0)
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
    watchdog_freshness_sec: float
    observer_freshness_sec: float
    librarian_freshness_sec: float

    # Data source
    data_dir: Path

    # Density aggregation
    density_slice_sec: float

    # Density histogram shape
    density_bins: int

    # Performance knobs
    active_jsonl_rescan_sec: float
    jsonl_max_read_bytes_per_poll: int
    resource_pin_max_age_sec: float


def load_config(module_file: Path) -> TelemetryConfig:
    # Use consolidated config
    health_dir = get_calamum_health_dir()

    # Legacy global freshness override (applies to all components when provided).
    # Component-specific env vars take precedence when set.
    raw_global_freshness = os.getenv('CALAMUM_FRESHNESS_SEC')
    global_freshness: Optional[float]
    if raw_global_freshness is not None:
        try:
            global_freshness = float(raw_global_freshness)
        except Exception:
            global_freshness = 15.0
    else:
        global_freshness = None

    def _freshness(name: str, default_value: float) -> float:
        raw = os.getenv(name)
        if raw is not None:
            try:
                val = float(raw)
                return float(max(0.5, val))
            except Exception:
                pass
        if global_freshness is not None:
            return float(max(0.5, global_freshness))
        return float(default_value)

    # Defaults aligned to runtime policy/checks:
    # - watchdog: 45s
    # - observer: 15s
    # - librarian: 30s
    wd_freshness_sec = _freshness('CALAMUM_WATCHDOG_FRESHNESS_SEC', 45.0)
    obs_freshness_sec = _freshness('CALAMUM_OBSERVER_FRESHNESS_SEC', 15.0)
    lib_freshness_sec = _freshness('CALAMUM_LIBRARIAN_FRESHNESS_SEC', 30.0)
    # Back-compat field retained for downstream code that still expects one value.
    freshness_sec = float(global_freshness) if global_freshness is not None else float(obs_freshness_sec)

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
    try:
        resource_pin_max_age_sec = float(os.getenv('CALAMUM_RESOURCE_PIN_MAX_AGE_SEC', '600'))
    except Exception:
        resource_pin_max_age_sec = 600.0

    return TelemetryConfig(
        watchdog_heartbeat_path=wd_hb,
        observer_heartbeat_path=obs_hb,
        librarian_heartbeat_path=lib_hb,
        freshness_sec=freshness_sec,
        watchdog_freshness_sec=wd_freshness_sec,
        observer_freshness_sec=obs_freshness_sec,
        librarian_freshness_sec=lib_freshness_sec,
        data_dir=data_dir,
        density_slice_sec=density_slice_sec,
        density_bins=density_bins,
        active_jsonl_rescan_sec=active_jsonl_rescan_sec,
        jsonl_max_read_bytes_per_poll=jsonl_max_read_bytes_per_poll,
        resource_pin_max_age_sec=float(max(0.0, resource_pin_max_age_sec)),
    )


class TelemetryProvider:
    def __init__(self, config: TelemetryConfig) -> None:
        self.config = config
        self._counter = _JsonlAppendCounter(data_dir=self.config.data_dir)
        # Oldest -> newest density slice counts.
        self._density_window: List[int] = [0] * int(max(3, min(60, self.config.density_bins)))
        self._slice_started_ts: float = _now_ts()
        self._slice_count: int = 0
        self._active_jsonl_cache: Optional[Path] = None
        self._active_jsonl_last_scan_ts: float = 0.0
        self._active_path_high_water_mtime: float = 0.0
        # Fallback stream for observerctl baseline resource collection.
        self._resource_last_marker: Tuple[float, str] = (0.0, '')
        self._resource_total_records: int = 0

    def _load_route_state(self) -> Tuple[str, str, bool]:
        """Read and normalize observerctl source/mode SSOT state."""
        source = 'sim'
        mode = 'canary'
        has_state = False
        try:
            st_path = get_calamum_control_dir() / 'observerctl_state.json'
            if st_path.exists():
                payload = json.loads(st_path.read_text(encoding='utf-8'))
                if isinstance(payload, dict):
                    has_state = True
                    source = str(payload.get('source', source) or source).strip().lower()
                    mode = str(payload.get('mode', mode) or mode).strip().lower().replace('_', '-')
        except Exception:
            pass

        if source not in ('sim', 'real'):
            source = 'sim'

        mode_aliases = {
            'active-gated': 'live',
            'activegated': 'live',
            'sampler': 'watch',
        }
        mode = mode_aliases.get(mode, mode)
        if mode not in ('watch', 'canary', 'live', 'honeypot'):
            mode = 'canary'

        return source, mode, has_state

    def _preferred_jsonl_for_route(self) -> Optional[Path]:
        """Return canonical metrics path for the currently selected source/mode route."""
        source, mode, has_state = self._load_route_state()
        if not has_state:
            return None
        metrics_path = self.config.data_dir / 'observer_derived' / source / mode / 'moltbook_metrics.jsonl'

        # If route metrics exists, always pin to SSOT lane.
        if metrics_path.exists():
            return metrics_path

        # During baseline/resource-only windows, keep lane pinning if the route's
        # resource index has recent activity.
        resource_idx = self.config.data_dir / 'observer_derived' / source / mode / 'resource' / 'index.jsonl'
        if resource_idx.exists():
            max_age = float(max(0.0, self.config.resource_pin_max_age_sec))
            if max_age <= 0.0:
                return metrics_path
            try:
                age = max(0.0, _now_ts() - resource_idx.stat().st_mtime)
                if age <= max_age:
                    return metrics_path
            except OSError:
                pass

        # If the selected route has neither metrics nor fresh resource activity,
        # allow fallback stream discovery so counters reflect active ingest.
        return None

    def _parse_stream_route_from_path(self, path: Optional[Path]) -> Tuple[Optional[str], Optional[str]]:
        """Return (source, mode) when path matches observer_derived/<source>/<mode>/..."""
        if path is None:
            return None, None
        try:
            parts = [str(p).strip().lower() for p in path.parts]
            idx = parts.index('observer_derived')
            if idx + 2 < len(parts):
                src = parts[idx + 1]
                mode = parts[idx + 2]
                if src in ('sim', 'real') and mode in ('watch', 'canary', 'live', 'honeypot'):
                    return src, mode
        except Exception:
            pass
        return None, None

    def _read_tail_bytes(self, path: Path, n_bytes: int) -> Optional[bytes]:
        """Read last N bytes from a file (best-effort, Windows-lock tolerant)."""
        if n_bytes <= 0:
            return b''
        for _ in range(3):
            try:
                with path.open('rb') as f:
                    try:
                        f.seek(-n_bytes, os.SEEK_END)
                    except OSError:
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

    def _parse_iso_ts(self, value: Any) -> Optional[float]:
        raw = str(value or '').strip()
        if not raw:
            return None
        try:
            if raw.endswith('Z'):
                raw = raw[:-1] + '+00:00'
            dt = datetime.fromisoformat(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            return float(dt.timestamp())
        except Exception:
            return None

    def _active_resource_index_path(self) -> Optional[Path]:
        """Best-effort active resource index path from observerctl SSOT state."""
        source, mode, _ = self._load_route_state()

        p = self.config.data_dir / 'observer_derived' / source / mode / 'resource' / 'index.jsonl'
        if p.exists():
            return p

        # Fallback to newest index if state path is absent/stale.
        try:
            cands = list((self.config.data_dir / 'observer_derived').glob('*/*/resource/index.jsonl'))
        except Exception:
            cands = []
        # Windows glob with spaces is brittle; use recursive fallback.
        if not cands:
            try:
                cands = [x for x in (self.config.data_dir / 'observer_derived').rglob('index.jsonl') if 'resource' in x.parts]
            except Exception:
                cands = []
        if not cands:
            return None
        try:
            return max(cands, key=lambda x: x.stat().st_mtime)
        except Exception:
            return None

    def _poll_resource_index(self) -> Tuple[int, int]:
        """Return (delta_records, total_records) from resource index stream.

        Uses a monotonic marker (timestamp, segment_path) to avoid double counting.
        """
        idx_path = self._active_resource_index_path()
        if idx_path is None or not idx_path.exists():
            return 0, int(self._resource_total_records)

        raw = self._read_tail_bytes(idx_path, 1_000_000)
        if raw is None:
            return 0, int(self._resource_total_records)

        try:
            text = raw.decode('utf-8', errors='replace')
        except Exception:
            return 0, int(self._resource_total_records)

        marker = self._resource_last_marker
        delta = 0
        newest = marker

        for ln in text.splitlines():
            line = str(ln or '').strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            if not isinstance(row, dict):
                continue
            ts = self._parse_iso_ts(row.get('timestamp_utc'))
            if ts is None:
                continue
            seg_path = str(row.get('segment_path', '') or '')
            key = (float(ts), seg_path)
            if key > marker:
                try:
                    delta += int(row.get('segment_records', 0) or 0)
                except Exception:
                    delta += 0
            if key > newest:
                newest = key

        if newest > marker:
            self._resource_last_marker = newest
        if delta > 0:
            self._resource_total_records = int(max(0, self._resource_total_records + delta))
        return int(max(0, delta)), int(max(0, self._resource_total_records))

    def _fallback_active_candidates(self) -> List[Path]:
        """Return deterministic fallback candidates when recursive scan yields nothing.

        Order matters: prefer common operating paths first.
        """
        base = self.config.data_dir / 'observer_derived'
        candidates: List[Path] = []
        for src in ('sim', 'real'):
            for mode in ('watch', 'canary', 'live', 'honeypot'):
                candidates.append(base / src / mode / 'moltbook_metrics.jsonl')
        return candidates

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

        # SSOT-first selection: if observerctl declares a concrete source/mode route
        # and its canonical metrics stream exists, prefer it over newest-file heuristics.
        preferred = self._preferred_jsonl_for_route()
        if preferred is not None:
            self._active_jsonl_cache = preferred
            try:
                self._active_path_high_water_mtime = preferred.stat().st_mtime
            except OSError:
                self._active_path_high_water_mtime = 0.0
            self._active_jsonl_last_scan_ts = now
            return preferred

        # If cached path disappeared (rotation, cleanup, or stale pointer), clear it
        # so we can recover on the next scan instead of freezing on stale totals.
        if self._active_jsonl_cache is not None:
            try:
                if not self._active_jsonl_cache.exists():
                    self._active_jsonl_cache = None
                    self._active_path_high_water_mtime = 0.0
            except Exception:
                # Keep cache if existence check itself is unavailable.
                pass
        
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
                     if new_mtime < self._active_path_high_water_mtime and self._active_jsonl_cache.exists():
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
             # If recursive scan fails, prefer known canonical paths that actually exist.
             for candidate in self._fallback_active_candidates():
                 try:
                     if candidate.exists():
                         self._active_jsonl_cache = candidate
                         try:
                             self._active_path_high_water_mtime = candidate.stat().st_mtime
                         except OSError:
                             self._active_path_high_water_mtime = 0.0
                         return candidate
                 except Exception:
                     continue

             # Last-resort fallback path for startup before first file is created.
             return self.config.data_dir / 'observer_derived' / 'sim' / 'canary' / 'moltbook_metrics.jsonl'

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
    
    def _get_freshness_age(self, path: Path, now_ts: float, max_age_sec: float) -> Tuple[bool, float, str]:
        """Returns (is_fresh, age_sec, pretty_age)."""
        if not path.exists():
            return False, 9999.9, "Missing"
        try:
            mtime = path.stat().st_mtime
            age = max(0.0, now_ts - mtime)
            is_fresh = age <= float(max_age_sec)
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
        route_source, route_mode, route_has_state = self._load_route_state()

        active_jsonl = self._pick_active_jsonl()
        self._counter.set_path(active_jsonl)
        new_lines, total_lines = self._counter.poll(max_read_bytes=self.config.jsonl_max_read_bytes_per_poll)
        active_stream_source, active_stream_mode = self._parse_stream_route_from_path(active_jsonl)
        route_stream_mismatch = bool(
            route_has_state
            and active_stream_source is not None
            and active_stream_mode is not None
            and (active_stream_source != route_source or active_stream_mode != route_mode)
        )

        # Resource-index fallback for observerctl baseline collection windows.
        resource_new, resource_total = self._poll_resource_index()
        effective_new = int(new_lines)
        effective_total = int(total_lines)
        if effective_new <= 0 and resource_new > 0:
            effective_new = int(resource_new)
            effective_total = int(max(effective_total, resource_total))
        
        historical = self._counter._historical_count
        session_recs = max(0, effective_total - historical)
        active_is_sim = _is_sim_likely_path(active_jsonl)

        archive_total, archive_non_sim, archive_sim_est = _archive_manifest_totals(self.config.data_dir)
        session_non_sim = 0 if active_is_sim else int(session_recs)
        # Display total: canonical archive total + non-sim active session stream.
        total_display = int(archive_total + session_non_sim)

        # Ensure window size matches config (config may change at runtime).
        self._ensure_density_window_size(int(self.config.density_bins))

        # Density window: aggregate new lines into coarse time slices so the
        # histogram is less twitchy and better represents “volume over time”.
        self._slice_count += int(effective_new)
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
        wd_fresh, wd_age, wd_age_str = self._get_freshness_age(
            self.config.watchdog_heartbeat_path,
            now,
            self.config.watchdog_freshness_sec,
        )
        obs_fresh, obs_age, obs_age_str = self._get_freshness_age(
            self.config.observer_heartbeat_path,
            now,
            self.config.observer_freshness_sec,
        )
        lib_fresh, lib_age, lib_age_str = self._get_freshness_age(
            self.config.librarian_heartbeat_path,
            now,
            self.config.librarian_freshness_sec,
        )

        # Heartbeat trust (signature validity)
        wd_sig_ok, wd_sig_detail = _verify_signed_record_best_effort(self.config.watchdog_heartbeat_path)
        # If signature verification is available, require it.
        wd_trusted = bool(wd_fresh and (wd_sig_ok is True)) if wd_sig_ok is not None else bool(wd_fresh)
        
        # Fallback for Observer if file lock prevents reading its heartbeat but data is flowing
        if not obs_fresh and active_jsonl is not None:
             # If we choose active_jsonl as proxy, check its freshness
             aj_fresh, aj_age, aj_age_str = self._get_freshness_age(
                 active_jsonl,
                 now,
                 self.config.observer_freshness_sec,
             )
             if aj_fresh:
                 obs_fresh = True
                 obs_age = aj_age
                 obs_age_str = aj_age_str

        return {
            'cpu': cpu,
            'mem': mem,
            'new_records': int(effective_new),
            'total_records': int(effective_total),
            'records_session': int(session_recs),
            'records_archive': int(historical),
            'records_session_display': int(session_non_sim),
            'records_archive_display': int(archive_total),
            'records_total_display': int(total_display),
            'records_archive_non_sim': int(archive_non_sim),
            'records_archive_sim_estimate': int(archive_sim_est),
            'active_source_is_sim': bool(active_is_sim),
            'resource_new_records': int(resource_new),
            'resource_total_records': int(resource_total),
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
            'route_source': route_source,
            'route_mode': route_mode,
            'active_stream_source': active_stream_source,
            'active_stream_mode': active_stream_mode,
            'route_stream_mismatch': bool(route_stream_mismatch),
        }
