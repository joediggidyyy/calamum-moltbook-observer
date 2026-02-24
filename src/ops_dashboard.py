"""Ghost Console Ops Dashboard.

NOTE: NiceGUI is an optional dependency.

The repository test suite expects this module to be importable in minimal
environments that do not have `nicegui` installed. When NiceGUI is missing we
install a small no-op shim so imports succeed; the dashboard cannot be run in
that state.
"""

try:
    from nicegui import ui, app  # type: ignore
    _NICEGUI_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover
    _NICEGUI_AVAILABLE = False

    class _NullNiceGUI:
        """No-op NiceGUI stand-in.

        This is intentionally permissive to allow module import in test/CI.
        Calling any UI APIs will effectively do nothing.
        """

        def __getattr__(self, name: str):
            def _noop(*args, **kwargs):
                # Decorator-style APIs (e.g., @ui.page('/')).
                if name in {"page", "refreshable"}:
                    # Used as @ui.page without params
                    if len(args) == 1 and callable(args[0]) and not kwargs:
                        return args[0]

                    def _decorator(fn):
                        return fn

                    return _decorator

                # Context-manager or builder-style APIs.
                return self

            return _noop

        def __call__(self, *args, **kwargs):
            return self

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    ui = _NullNiceGUI()  # type: ignore
    app = _NullNiceGUI()  # type: ignore
from datetime import datetime, timezone
import base64
import os
import random
import asyncio
import time
import sys
import atexit
import signal
import traceback
import subprocess
from pathlib import Path
from typing import Dict, Optional, List, Tuple
import json
import psutil  # Required for uptime and system resource queries
from ops.controller import controller # Import the controller
from ops.telemetry import TelemetryProvider, load_config
from calamum_config import get_calamum_control_dir, get_calamum_log_dir

# --- CONFIGURATION & THEME ---
THEME_BG = 'bg-zinc-900'
THEME_FG = 'text-gray-300'
THEME_ACCENT = 'border-gray-600'
THEME_FONT = 'font-mono'
# Visible build stamp to confirm the UI is served by the latest backend instance.
# (Helps diagnose cases where a hidden old process keeps running and the launcher can't bind the port.)

BUILD_STAMP = datetime.now(timezone.utc).strftime('%Y-%m-%d')

# Unique per-backend-process id. Used to correlate client reloads with server restarts.
SERVER_BOOT_ID = f"{int(time.time() * 1000)}-{random.randint(1000, 9999)}"

def _backend_runtime_log(event: str, data: Optional[dict] = None) -> None:
    """Append a small runtime record for correlating restarts/crashes.

    This log is append-only and survives launcher stdout/stderr overwrites.
    """
    record = {
        'ts': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        'event': str(event),
        'pid': os.getpid(),
        'server_boot_id': SERVER_BOOT_ID,
        'data': data or {},
    }

    # Best-effort only: we never want the UI to fail due to logging.
    try:
        out_path = get_calamum_log_dir() / 'ghost_console_backend.runtime.jsonl'
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open('a', encoding='utf-8') as f:
            f.write(json.dumps(record, sort_keys=True) + '\n')
        return
    except Exception as e:
        try:
            # Backend is launched hidden with stdout/stderr redirected to logs.
            # If this fails, we want a breadcrumb in those redirected logs.
            print(f"[GhostConsole] backend_runtime_log failed: {e!r}")
        except Exception:
            pass

    return # Removed fallback to repo root to enforce isolation logic


_LIFECYCLE_HOOKS_INSTALLED = False


def _install_backend_lifecycle_hooks() -> None:
    """Install best-effort hooks to log backend exits and unhandled exceptions."""
    global _LIFECYCLE_HOOKS_INSTALLED
    if _LIFECYCLE_HOOKS_INSTALLED:
        return
    _LIFECYCLE_HOOKS_INSTALLED = True

    try:
        atexit.register(lambda: _backend_runtime_log('process_exit', {'build': BUILD_STAMP}))
    except Exception:
        pass

    try:
        _prev_hook = sys.excepthook

        def _hook(exctype, value, tb):
            try:
                _backend_runtime_log(
                    'unhandled_exception',
                    {
                        'build': BUILD_STAMP,
                        'type': getattr(exctype, '__name__', str(exctype)),
                        'value': repr(value),
                        'traceback': ''.join(traceback.format_exception(exctype, value, tb)),
                    },
                )
            except Exception:
                pass
            return _prev_hook(exctype, value, tb)

        sys.excepthook = _hook
    except Exception:
        pass

    # SIGTERM is the most relevant for "killed" processes (Stop-Process, service stop, etc.).
    try:
        def _sigterm_handler(signum, frame):
            try:
                _backend_runtime_log('signal', {'build': BUILD_STAMP, 'signal': int(signum)})
            except Exception:
                pass
            raise SystemExit(0)

        signal.signal(signal.SIGTERM, _sigterm_handler)
    except Exception:
        pass


# Install hooks early so they apply even if NiceGUI/Uvicorn spawns worker processes.
_install_backend_lifecycle_hooks()

# --- MODE SPEC (CANARY now, others stubbed for posterity) ---
# Canonical UI modes (design sketch):
# - CANARY (Current): Test flight, limited sampling.
# - HONEYPOT: High-interaction mode for attracting adverse actors.
# - PASSIVE_LISTENER: Silent recording of traffic without active probing.
# - REPLAY_SIMULATION: Re-running captured traffic for regression testing.
# - CHAOS_MODE: Intentionally introducing faults to test Sentinel resilience.
#
# Optional override for local ops/dev:
#   set CALAMUM_OPS_MODE to one of the canonical modes above.
CANONICAL_MODES: Dict[str, str] = {
    'CANARY': 'Test flight, limited sampling.',
    'HONEYPOT': 'High-interaction mode for attracting adverse actors.',
    'PASSIVE_LISTENER': 'Silent recording of traffic without active probing.',
    'REPLAY_SIMULATION': 'Re-running captured traffic for regression testing.',
    'CHAOS_MODE': 'Intentionally introducing faults to test Sentinel resilience.',
}

OPS_RUNTIME_MODES = {'watch', 'canary', 'live', 'honeypot'}
OPS_RUNTIME_SOURCES = {'sim', 'real'}


def normalize_mode(raw: Optional[str]) -> str:
    """Normalize a user-provided mode into a canonical dashboard mode.

    Any unknown value falls back to CANARY.
    """
    if not raw:
        return 'CANARY'

    candidate = raw.strip().upper().replace('-', '_').replace(' ', '_')
    aliases = {
        'PASSIVE': 'PASSIVE_LISTENER',
        'LISTENER': 'PASSIVE_LISTENER',
        'REPLAY': 'REPLAY_SIMULATION',
        'CHAOS': 'CHAOS_MODE',
    }
    candidate = aliases.get(candidate, candidate)
    return candidate if candidate in CANONICAL_MODES else 'CANARY'


def normalize_ops_runtime_mode(raw: Optional[str]) -> str:
    mode = str(raw or '').strip().lower().replace('_', '-').replace(' ', '-')
    aliases = {
        'active-gated': 'live',
        'activegated': 'live',
        'sampler': 'watch',
    }
    mode = aliases.get(mode, mode)
    if mode in OPS_RUNTIME_MODES:
        return mode
    return 'canary'


def normalize_ops_runtime_source(raw: Optional[str]) -> str:
    source = str(raw or '').strip().lower()
    if source in ('live', 'real'):
        return 'real'
    if source == 'sim':
        return 'sim'
    return 'sim'


def display_runtime_mode(raw: Optional[str]) -> str:
    mode = normalize_ops_runtime_mode(raw)
    if mode in OPS_RUNTIME_MODES:
        return mode.upper()
    return normalize_mode(raw)


def _observerctl_state_path() -> Path:
    return get_calamum_control_dir() / 'observerctl_state.json'


def _load_observerctl_ssot_state() -> Dict[str, str]:
    default = {
        'source': normalize_ops_runtime_source(os.getenv('CALAMUM_MOLTBOOK_SOURCE', 'sim')),
        'mode': normalize_ops_runtime_mode(os.getenv('CALAMUM_OPS_MODE', 'canary')),
    }
    path = _observerctl_state_path()
    try:
        if path.exists():
            payload = json.loads(path.read_text(encoding='utf-8'))
            if isinstance(payload, dict):
                default['source'] = normalize_ops_runtime_source(payload.get('source'))
                default['mode'] = normalize_ops_runtime_mode(payload.get('mode'))
    except Exception:
        pass
    return default


def _observerctl_script_path() -> Path:
    return Path(__file__).resolve().parent / 'observerctl.py'


def _request_observerctl_mode_switch(source: str, mode: str) -> Dict[str, object]:
    source_norm = normalize_ops_runtime_source(source)
    mode_norm = normalize_ops_runtime_mode(mode)
    script = _observerctl_script_path()
    if not script.exists():
        return {
            'decision': 'no-go',
            'reason_codes': ['critical_check_failed:observerctl_script_missing'],
            'message': 'observerctl script missing',
            'source': source_norm,
            'mode': mode_norm,
        }

    cmd = [
        sys.executable,
        str(script),
        'ops',
        'mode',
        'switch',
        '--source',
        source_norm,
        '--to',
        mode_norm,
        '--event',
        'gui-control',
        '--json',
    ]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(Path(__file__).resolve().parent.parent),
        )
    except Exception:
        return {
            'decision': 'no-go',
            'reason_codes': ['critical_check_failed:observerctl_mode_switch_exec_error'],
            'message': 'observerctl mode switch execution failed',
            'source': source_norm,
            'mode': mode_norm,
        }

    output = (proc.stdout or '').strip()
    packet: Dict[str, object] = {}
    if output:
        try:
            parsed = json.loads(output)
            if isinstance(parsed, dict):
                packet = parsed
        except Exception:
            packet = {}

    if not packet:
        packet = {
            'decision': 'no-go' if proc.returncode != 0 else 'go',
            'reason_codes': ['critical_check_failed:observerctl_mode_switch_unparseable_output'] if proc.returncode != 0 else [],
            'message': (proc.stderr or proc.stdout or '').strip() or 'observerctl mode switch returned no packet',
            'source': source_norm,
            'mode': mode_norm,
        }

    return packet


MODE_TOOLTIP = (
    'Future Mode Capabilities:\n'
    + '\n'.join([
        f"- {name}: {desc}" for name, desc in CANONICAL_MODES.items()
    ])
)

# --- MOCK DATA STATE ---
class SystemState:
    def __init__(self):
        self.cpu_history = [10, 20, 15, 30, 25, 40, 35, 20, 15, 10] * 5
        self.mem_history = [50, 52, 51, 53, 55, 54, 52, 51, 50, 49] * 5
        self.integrity_score = 100
        self.availability_score = 100
        self.capacity_score = 100
        self.freshness_score = 100
        self.records_collected = 0
        self.records_main_display = 0
        self.is_running = True
        ssot = _load_observerctl_ssot_state()
        self.mode = normalize_ops_runtime_mode(ssot.get('mode'))
        self.source = normalize_ops_runtime_source(ssot.get('source'))
        self.timestamp = datetime.now()
        self.log_seq: int = 0
        self.log_items: List[Tuple[int, str]] = []  # (seq, line)
        # Density is maintained as a fixed global-time window (base resolution) and
        # rebinned client-side by the Control Deck bin-width (seconds) setting.
        # Backend base default: 60 seconds @ 1s slices.
        self.density_bins = [0] * 60
        self.density_raw_window = [0] * 60
        self.density_slice_sec = 1.0
        self.watchdog_active = True
        self.watchdog_last_reset = datetime.now()
        self.librarian_active = False  # NEW
        self._last_obs_active: Optional[bool] = None
        self._last_wd_active: Optional[bool] = None
        self._last_lib_active: Optional[bool] = None  # NEW
        self._last_archive_count: int = 0  # NEW
        self._wd_sig_ok: Optional[bool] = None
        self._wd_sig_detail: Optional[str] = None
        self._obs_heartbeat_stale: Optional[bool] = None
        self._lib_heartbeat_stale: Optional[bool] = None
        # UI push throttles (monotonic seconds)
        self._last_density_push_at: float = 0.0
        self._last_charts_push_at: float = 0.0
        self._last_status_push_at: float = 0.0
        self._last_server_tick_push_at: float = 0.0
        self._update_loop_busy: bool = False
        # Diagnostics (client->server JSONL)
        self.js_diag_seq: int = 0
        self.js_diag_last_ts_utc: Optional[str] = None


def add_log(msg: str) -> None:
    """Append a log line to the in-memory system log buffer.

    NOTE: UI rendering is client-side via polling to avoid websocket churn.
    """
    # Keep the timestamp short but include seconds so motion is visible.
    ts = datetime.now().strftime('%H:%M:%S')
    line = f"{ts} {msg}"
    state.log_seq += 1
    state.log_items.append((state.log_seq, line))
    # keep bounded
    if len(state.log_items) > 400:
        state.log_items = state.log_items[-400:]


state = SystemState()

# Telemetry provider (best-effort: will fall back to simulation if it can't read sources)
telemetry = TelemetryProvider(load_config(Path(__file__)))

# Density base window (dashboard-local): fixed global time window at 1-second resolution.
# The browser rebins this base window into [1,2,5,10,20] second bins.
_DENSITY_BASE_SLICE_SEC: float = 1.0
_DENSITY_WINDOW_SEC: int = 60
try:
    telemetry.set_density_bins(int(_DENSITY_WINDOW_SEC))
    telemetry.set_density_slice_sec(float(_DENSITY_BASE_SLICE_SEC))
except Exception:
    # best-effort; never break the UI due to telemetry config
    pass

# Branding assets (optional)
_PROJECT_ROOT = Path(__file__).resolve().parents[1]  # .../projects/calamum-moltbook-observer
_BRAND_DIR = _PROJECT_ROOT / 'assets' / 'branding'


def _repo_root_for_logs() -> Path:
    """Best-effort workspace root detection for writing logs.

    Preference order:
      1) CODESENTINEL_REPO_ROOT env var (if set)
      2) walk upward until we find `codesentinel.json` (repo root marker)
      3) walk upward until we find `.git/` (git root marker)
      4) fallback to inferred repo root (two levels above project root)
    """
    env_root = os.getenv('CODESENTINEL_REPO_ROOT')
    if env_root:
        try:
            p = Path(env_root).resolve()
            if p.exists():
                return p
        except Exception:
            pass

    cur = Path(__file__).resolve()
    for parent in [cur] + list(cur.parents):
        if (parent / 'codesentinel.json').exists():
            return parent
    for parent in [cur] + list(cur.parents):
        if (parent / '.git').exists():
            return parent

    return _PROJECT_ROOT.parents[1]


@app.post('/_ghost_console/js_error')
async def ghost_console_js_error(payload: dict) -> dict:
    """Capture client-side JS errors to a local JSONL file.

    This helps diagnose cases where the UI appears to "blank" due to a fatal
    ECharts/Vue error that won't surface in server-side Python logs.
    """
    # src/ops_dashboard.py -> src
    out_path = get_calamum_log_dir() / 'ghost_console_js_errors.jsonl'
    err: Optional[str] = None
    try:
        src_dir = Path(__file__).resolve().parent
        
        out_path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            'ts': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
            'payload': payload,
        }
        with out_path.open('a', encoding='utf-8') as f:
            f.write(json.dumps(record, sort_keys=True) + '\n')
            # Ensure the record is visible on disk immediately (helps when tailing from external tools).
            try:
                f.flush()
                os.fsync(f.fileno())
            except Exception:
                pass
        
        # in-memory counters (shown in snapshot)
        try:
            state.js_diag_seq += 1
            state.js_diag_last_ts_utc = record['ts']
        except Exception:
            pass
            
    except Exception as e:
        # best-effort; never break the UI due to logging failures
        err = repr(e)
        try:
            print(f"[GhostConsole] js_error capture failed: {err} -> {out_path}")
        except Exception:
            pass
    return {'ok': True, 'path': str(out_path), 'error': err}


def _tail_text_file(path: Path, max_lines: int = 50, max_bytes: int = 200_000) -> list[str]:
    """Read the last N lines of a text file without loading the entire file."""
    max_lines = max(1, min(500, int(max_lines)))
    max_bytes = max(4_096, min(2_000_000, int(max_bytes)))
    if not path.exists():
        return []
    try:
        with path.open('rb') as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            start = max(0, size - max_bytes)
            f.seek(start)
            data = f.read()
        # Decode best-effort; replace errors.
        text = data.decode('utf-8', errors='replace')
        lines = [ln for ln in text.splitlines() if ln.strip()]
        return lines[-max_lines:]
    except Exception:
        return []


@app.get('/_ghost_console/js_error_tail')
async def ghost_console_js_error_tail(lines: int = 60) -> dict:
    """Return the last few raw JSONL lines from the client diagnostics log."""
    out_path = get_calamum_log_dir() / 'ghost_console_js_errors.jsonl'
    raw = _tail_text_file(out_path, max_lines=lines)
    return {
        'path': str(out_path),
        'exists': out_path.exists(),
        'size': (out_path.stat().st_size if out_path.exists() else 0),
        'lines': raw,
        'js_diag_seq': state.js_diag_seq,
        'js_diag_last_ts_utc': state.js_diag_last_ts_utc,
    }


@app.get('/_ghost_console/diag_paths')
async def ghost_console_diag_paths() -> dict:
    log_dir = get_calamum_log_dir()
    return {
        'active_log_dir': str(log_dir),
        'logs_dir_exists': log_dir.exists(),
        'js_error_path': str(log_dir / 'ghost_console_js_errors.jsonl'),
    }


@app.get('/_ghost_console/runtime_log_test')
async def ghost_console_runtime_log_test() -> dict:
    """Force-write a backend runtime log record and report file existence.

    This is a debugging endpoint to validate that `ghost_console_backend.runtime.jsonl`
    is writable/visible from this backend instance.
    """
    _backend_runtime_log('runtime_log_test', {'build': BUILD_STAMP})
    repo_root = _repo_root_for_logs()
    out_path = repo_root / 'logs' / 'ghost_console_backend.runtime.jsonl'
    exists = out_path.exists()
    size = 0
    try:
        if exists:
            size = out_path.stat().st_size
    except Exception:
        pass
    return {
        'repo_root': str(repo_root),
        'path': str(out_path),
        'exists': exists,
        'size': size,
        'server_boot_id': SERVER_BOOT_ID,
        'pid': os.getpid(),
    }


def _compute_snapshot() -> dict:
    """Compute the latest dashboard snapshot.

    This intentionally does NOT push UI diffs over websockets. The browser polls
    this endpoint and updates the DOM locally.
    """
    try:
        snap = telemetry.update()
    except Exception as e:
        # Log critical telemetry failure so it's visible in the UI console
        add_log(f"[ERR] Telemetry failed: {str(e)}")
        snap = {}

    # CPU/MEM -> histories (bounded)
    try:
        cpu = int(max(0, min(100, float(snap.get('cpu', 0.0)))))
    except Exception:
        cpu = 0
    try:
        mem = int(max(0, min(100, float(snap.get('mem', 0.0)))))
    except Exception:
        mem = 0

    state.cpu_history.append(cpu)
    state.cpu_history = state.cpu_history[-50:]
    state.mem_history.append(mem)
    state.mem_history = state.mem_history[-50:]

    # Records + density
    total = int(snap.get('total_records', state.records_collected) or 0)
    total_display = int(snap.get('records_total_display', total) or 0)
    new = int(snap.get('new_records', 0) or 0)
    route_stream_mismatch = bool(snap.get('route_stream_mismatch', False))
    active_stream_source = normalize_ops_runtime_source(snap.get('active_stream_source')) if snap.get('active_stream_source') else None
    active_stream_mode = normalize_ops_runtime_mode(snap.get('active_stream_mode')) if snap.get('active_stream_mode') else None

    ssot_state = _load_observerctl_ssot_state()
    state.mode = normalize_ops_runtime_mode(ssot_state.get('mode'))
    state.source = normalize_ops_runtime_source(ssot_state.get('source'))

    main_display_records = int(total_display)
    if state.source == 'sim':
        main_display_records = int(snap.get('records_session', snap.get('records_session_display', 0)) or 0)
    elif bool(route_stream_mismatch):
        # During route/stream drift, prefer live total so the operator-facing
        # counter still reflects ingest motion rather than archive-only totals.
        main_display_records = int(total)

    # UI runtime counter should reflect live ingest (including sim mode) so
    # operators can see movement when the stream is healthy.
    state.records_collected = total
    state.records_main_display = int(main_display_records)

    session_raw = int(snap.get('records_session', snap.get('records_session_display', 0)) or 0)
    archive_raw = int(snap.get('records_archive', snap.get('records_archive_display', 0)) or 0)
    session_display = int(snap.get('records_session_display', session_raw) or 0)
    archive_display = int(snap.get('records_archive_display', archive_raw) or 0)

    bins = snap.get('density_bins')
    if isinstance(bins, list):
        state.density_bins = [int(max(0, min(100, x))) for x in bins]

    raw = snap.get('density_raw_window')
    if isinstance(raw, list):
        state.density_raw_window = [int(max(0, x)) for x in raw]
    try:
        state.density_slice_sec = float(snap.get('density_slice_sec', state.density_slice_sec))
    except Exception:
        pass

    # WD/OBS/LIB
    state.watchdog_active = bool(snap.get('watchdog_active', False))
    state.is_running = bool(snap.get('observer_active', False))
    state.librarian_active = bool(snap.get('librarian_active', False))

    # Derive scores
    availability = 100 if state.is_running else 0
    
    # Freshness depends on both Watchdog and Librarian now
    freshness = 100 if state.watchdog_active else 0
    if state.librarian_active:
        freshness = int((freshness + 100) / 2)
    elif freshness > 0:
        # Penalize if Librarian is down but Watchdog is up
        freshness = int(freshness / 2)

    capacity = int(max(0, min(100, 100 - max(cpu, mem))))
    
    # Real Integrity Calculation:
    # Based on whether we have a valid data source file that is growing or stable.
    # If no active jsonl path is found, integrity is 0 (System Blind).
    src = snap.get('active_jsonl_path')
    if src and total > 0:
         # We have a file and it has data.
         state.integrity_score = 100
    elif src:
         # We have a file but it's empty (startup?)
         state.integrity_score = 50
    else:
         # No file found.
         state.integrity_score = 0
         
    integrity = state.integrity_score

    # Status
    if not state.is_running:
        status = {'text': 'CRITICAL', 'color': 'red'}
    elif cpu >= 80:
        status = {'text': 'DEGRADED', 'color': 'orange'}
    else:
        status = {'text': 'NOMINAL', 'color': 'green'}

    # System log intentionally excludes ingest periodic/stall chatter.

    if state._last_obs_active is None: state._last_obs_active = state.is_running
    if state._last_wd_active is None: state._last_wd_active = state.watchdog_active
    if state._last_lib_active is None: state._last_lib_active = state.librarian_active

    if state.is_running != state._last_obs_active:
        add_log(f"[SYS] Observer state -> {'ACTIVE' if state.is_running else 'DOWN'}")
        state._last_obs_active = state.is_running
    if state.watchdog_active != state._last_wd_active:
        add_log(f"[SYS] Watchdog state -> {'ACTIVE' if state.watchdog_active else 'STALE'}")
        state._last_wd_active = state.watchdog_active
    if state.librarian_active != state._last_lib_active:
        add_log(f"[SYS] Librarian state -> {'ACTIVE' if state.librarian_active else 'DOWN'}")
        state._last_lib_active = state.librarian_active

    wd_stats = snap.get('watchdog_stats', {}) if isinstance(snap.get('watchdog_stats', {}), dict) else {}
    if bool(wd_stats.get('signature_check_available', False)):
        sig_ok = bool(wd_stats.get('signature_valid', False))
        sig_detail = str(wd_stats.get('signature_detail', 'unknown'))
        if state._wd_sig_ok is None:
            state._wd_sig_ok = sig_ok
            state._wd_sig_detail = sig_detail
        elif sig_ok != state._wd_sig_ok:
            if sig_ok:
                add_log('[SYS] Watchdog signature verification restored')
            else:
                add_log(f"[WARN] Watchdog signature verification failed ({sig_detail})")
            state._wd_sig_ok = sig_ok
            state._wd_sig_detail = sig_detail

    obs_stats = snap.get('observer_stats', {}) if isinstance(snap.get('observer_stats', {}), dict) else {}
    lib_stats = snap.get('librarian_stats', {}) if isinstance(snap.get('librarian_stats', {}), dict) else {}

    obs_age = obs_stats.get('age')
    lib_age = lib_stats.get('age')
    try:
        obs_stale = float(obs_age) > 15.0
    except Exception:
        obs_stale = None
    try:
        lib_stale = float(lib_age) > 30.0
    except Exception:
        lib_stale = None

    if obs_stale is not None:
        if state._obs_heartbeat_stale is None:
            state._obs_heartbeat_stale = bool(obs_stale)
        elif bool(obs_stale) != bool(state._obs_heartbeat_stale):
            if obs_stale:
                add_log(f"[WARN] Observer heartbeat stale ({obs_stats.get('age_str', str(obs_age))})")
            else:
                add_log('[SYS] Observer heartbeat recovered')
            state._obs_heartbeat_stale = bool(obs_stale)

    if lib_stale is not None:
        if state._lib_heartbeat_stale is None:
            state._lib_heartbeat_stale = bool(lib_stale)
        elif bool(lib_stale) != bool(state._lib_heartbeat_stale):
            if lib_stale:
                add_log(f"[WARN] Librarian heartbeat stale ({lib_stats.get('age_str', str(lib_age))})")
            else:
                add_log('[SYS] Librarian heartbeat recovered')
            state._lib_heartbeat_stale = bool(lib_stale)

    # Archive Logic (Librarian activity)
    current_archived = int(snap.get('records_archive', 0))
    if current_archived > state._last_archive_count and state._last_archive_count > 0:
        delta_arch = current_archived - state._last_archive_count
        add_log(f"[LIB] Archived +{delta_arch} records (Total: {current_archived})")
    state._last_archive_count = current_archived

    return {
        'ts': datetime.now().isoformat(),
        'server_boot_id': SERVER_BOOT_ID,
        'server_now_ms': int(time.time() * 1000),
        'js_diag': {
            'seq': state.js_diag_seq,
            'last_ts_utc': state.js_diag_last_ts_utc,
        },
        'mode': display_runtime_mode(state.mode),
        'source': state.source,
        'route_stream_mismatch': bool(route_stream_mismatch),
        'active_stream_source': active_stream_source,
        'active_stream_mode': active_stream_mode,
        'cpu': cpu,
        'mem': mem,
        'cpu_history': state.cpu_history,
        'mem_history': state.mem_history,
        'total_records': total,
        'records_total_display': total_display,
        'display_main_records': int(main_display_records),
        'new_records': new,
        'density_bins': state.density_bins,
        'density_raw_window': state.density_raw_window,
        'density_slice_sec': state.density_slice_sec,
        'watchdog_active': state.watchdog_active,
        'watchdog_last_reset': state.watchdog_last_reset.isoformat(),
        'observer_active': state.is_running,
        'librarian_active': state.librarian_active,
        'scores': {
            'availability': availability,
            'integrity': integrity,
            'capacity': capacity,
            'freshness': freshness,
        },
        'stats': {
            'wd': snap.get('watchdog_stats', {}),
            'obs': snap.get('observer_stats', {}),
            'lib': snap.get('librarian_stats', {}),
        },
        'records_breakdown': {
            'session': int(session_display),
            'archive': int(archive_display),
            'session_raw': int(session_raw),
            'archive_raw': int(archive_raw),
        },
        'records_breakdown_display': {
            'session': int(session_display),
            'archive': int(archive_display),
            'main': int(main_display_records),
        },
        'uptime_s': time.time() - psutil.boot_time(),
        'status': status,
        'log_last_seq': state.log_seq,
    }


@app.get('/_ghost_console/snapshot')
async def ghost_console_snapshot() -> dict:
    return _compute_snapshot()


@app.get('/_ghost_console/log_tail')
async def ghost_console_log_tail(after: int = 0, limit: int = 80) -> dict:
    try:
        after_i = int(after)
    except Exception:
        after_i = 0
    try:
        limit_i = max(1, min(200, int(limit)))
    except Exception:
        limit_i = 80

    items = [(seq, line) for (seq, line) in state.log_items if seq > after_i]
    if len(items) > limit_i:
        items = items[-limit_i:]

    return {
        'last_seq': state.log_seq,
        'lines': [{'seq': seq, 'line': line} for (seq, line) in items],
    }


def _resolve_brand_path(env_name: str, default_rel_name: str) -> Optional[Path]:
    """Resolve a branding file path.

    Priority:
      1) env var (absolute or relative to project root)
      2) default under assets/branding
    """
    raw = os.getenv(env_name)
    if raw:
        p = Path(raw)
        if not p.is_absolute():
            p = (_PROJECT_ROOT / p).resolve()
        return p if p.exists() else None

    candidate = _BRAND_DIR / default_rel_name
    return candidate if candidate.exists() else None


def _data_uri_for_image(path: Optional[Path]) -> Optional[str]:
    if path is None:
        return None
    try:
        data = path.read_bytes()
    except OSError:
        return None

    ext = path.suffix.lower().lstrip('.')
    mime = {
        'png': 'image/png',
        'jpg': 'image/jpeg',
        'jpeg': 'image/jpeg',
        'webp': 'image/webp',
        'svg': 'image/svg+xml',
    }.get(ext, 'application/octet-stream')
    b64 = base64.b64encode(data).decode('ascii')
    return f'data:{mime};base64,{b64}'


_BRAND_THUMB_SRC = _data_uri_for_image(_resolve_brand_path('CALAMUM_BRAND_THUMB_PATH', 'calamum_thumbnail.png'))
_BRAND_PANEL_SRC = _data_uri_for_image(_resolve_brand_path('CALAMUM_BRAND_PANEL_PATH', 'calamum_logo_color.png'))

# --- COMPONENTS ---

def create_header(toggle_drawer_fn):
    with ui.row().props('id="cids-header-row"').classes('w-full justify-between items-center border-b border-gray-700 pb-2 mb-2 h-16'):
        with ui.row().classes('items-center gap-4'):
            if _BRAND_THUMB_SRC:
                ui.image(_BRAND_THUMB_SRC).classes('w-10 h-10').props('fit=contain')
            else:
                ui.icon('hub', size='md').classes('text-gray-400')
            with ui.column().classes('gap-0'):
                ui.label('CALAMUM OPS').classes(f'text-xl {THEME_FONT} font-bold tracking-wider text-white')
                ui.label(f"MODE: [ {display_runtime_mode(state.mode)} ] SRC: [ {str(state.source).upper()} ]")\
                    .props('id="cids-mode"')\
                    .classes('text-xs text-gray-500 uppercase')\
                    .tooltip(MODE_TOOLTIP)
                ui.label(f"ROUTE: {str(state.source).upper()}:{display_runtime_mode(state.mode)}")\
                    .props('id="cids-route-indicator"')\
                    .classes('text-[10px] text-gray-600 uppercase')
        
        with ui.row().classes('gap-6 items-center'):
            # Watchdog indicator
            watchdog_badge = ui.badge('WD: ACTIVE', color='green-10')\
                .props('id="cids-wd-badge"')\
                .classes('font-bold text-[10px]')
            # TODO(pivot-gates): enrich on-hover status to include age + signature validity/trust + reason.
            # Until then, ensure the *server snapshot* drives trusted WD status (no freshness-only false-green).
            watchdog_badge.tooltip('Watchdog: monitors the observer loop heartbeat. Reset in Control Deck.')

            # Observer indicator
            observer_badge = ui.badge('OBS: ACTIVE', color='green-10')\
                .props('id="cids-obs-badge"')\
                .classes('font-bold text-[10px]')
            observer_badge.tooltip('Observer: process status for the active node.')

            # Librarian indicator
            librarian_badge = ui.badge('LIB: ACTIVE', color='green-10')\
                .props('id="cids-lib-badge"')\
                .classes('font-bold text-[10px]')
            librarian_badge.tooltip('Librarian: archival process status (Auto-Rotate/Compaction).')

            # Records Counter
            with ui.row().classes('items-center gap-2'):
                ui.label('RECORDS:').classes('text-xs text-gray-500 font-bold')
                ui.label(f"{int(state.records_main_display):,}")\
                    .props('id="cids-records"')\
                    .classes('text-xl font-bold text-white')
                    # Tooltip logic handled by client-side JS updating the 'title' attribute
                    # to match the requested format: [ sess: <m> \n arch: <n> ]

            ui.separator().props('vertical').classes('h-8 border-gray-700')

            # Clock + build stamp
            with ui.column().classes('gap-0 items-end'):
                ui.label(datetime.now().strftime('%H:%M:%S'))\
                    .props('id="cids-clock"')\
                    .classes('text-gray-400 font-mono')
                ui.label(f'BUILD {BUILD_STAMP}').classes('text-[10px] text-gray-600 font-mono leading-none')
            # NOTE: clock is updated client-side (poll loop) to avoid websocket churn.

            ui.button(icon='menu', on_click=toggle_drawer_fn).props('flat round color=white')

            # NOTE: WD/OBS badges are updated client-side via polling to avoid websocket churn.

def create_integrity_diamond_chart() -> ui.echart:
    """Radar chart using ECharts for stable sizing (no toolbars/modebar)."""
    option = {
        'backgroundColor': 'transparent',
        'tooltip': {'show': True, 'trigger': 'item'},
        'radar': {
            'shape': 'polygon',
            'radius': '72%',
            'splitNumber': 4,
            'indicator': [
                {'name': 'AVAILABILITY', 'max': 100},
                {'name': 'INTEGRITY', 'max': 100},
                {'name': 'CAPACITY', 'max': 100},
                {'name': 'FRESHNESS', 'max': 100},
            ],
            'axisName': {'color': '#d4d4d8', 'fontFamily': 'monospace', 'fontSize': 12},
            'splitLine': {'lineStyle': {'color': ['#3f3f46']}},
            'splitArea': {'areaStyle': {'color': ['rgba(0,0,0,0)']}},
            'axisLine': {'lineStyle': {'color': '#52525b'}},
        },
        'series': [
            {
                'type': 'radar',
                'name': 'SYSTEM',
                'symbol': 'none',
                'lineStyle': {'color': '#ffffff', 'width': 2},
                'areaStyle': {'color': 'rgba(255,255,255,0.08)'},
                'data': [
                    {'value': [state.availability_score, state.integrity_score, state.capacity_score, state.freshness_score]},
                ],
            }
        ],
    }
    return ui.echart(option).classes('w-full h-full')


def create_biorhythm_chart() -> ui.echart:
    """Line chart using ECharts for stable sizing."""
    x = list(range(len(state.cpu_history)))
    option = {
        'backgroundColor': 'transparent',
        'animation': False,
        'tooltip': {
            'show': True,
            'trigger': 'axis',
            'axisPointer': {'type': 'line'},
        },
        'grid': {'left': 8, 'right': 8, 'top': 16, 'bottom': 8, 'containLabel': False},
        'xAxis': {
            'type': 'category',
            'data': x,
            'boundaryGap': False,
            'axisLabel': {'show': False},
            'axisTick': {'show': False},
            'axisLine': {'show': False},
            'splitLine': {'show': False},
        },
        'yAxis': {
            'type': 'value',
            'min': 0,
            'max': 100,
            'axisLabel': {'show': False},
            'axisTick': {'show': False},
            'axisLine': {'show': False},
            'splitLine': {'show': True, 'lineStyle': {'color': '#27272a'}},
        },
        'series': [
            {'name': 'CPU', 'type': 'line', 'data': state.cpu_history, 'showSymbol': False, 'lineStyle': {'color': '#ffffff', 'width': 2}},
            {'name': 'MEM', 'type': 'line', 'data': state.mem_history, 'showSymbol': False, 'lineStyle': {'color': '#a1a1aa', 'width': 2, 'type': 'dotted'}},
        ],
    }
    return ui.echart(option).classes('w-full h-full')


def create_density_histogram_chart() -> ui.echart:
    """Histogram-like bars representing collection volume without showing raw content."""
    x = list(range(len(state.density_bins)))
    option = {
        'backgroundColor': 'transparent',
        'animation': False,
        'tooltip': {
            'show': True,
            'trigger': 'item',
            # Use xAxis category labels to show raw stats without changing series data shape.
            'formatter': '{b}',
        },
        'grid': {'left': 8, 'right': 8, 'top': 10, 'bottom': 8, 'containLabel': False},
        'xAxis': {
            'type': 'category',
            # Hidden axis labels; we use categories for tooltip stats.
            'data': [f"{int(state.density_raw_window[i])} rec / {int(state.density_slice_sec)}s" for i in range(len(x))],
            'axisLabel': {'show': False},
            'axisTick': {'show': False},
            'axisLine': {'show': False},
        },
        'yAxis': {
            'type': 'value',
            'min': 0,
            'max': 100,
            'axisLabel': {'show': False},
            'axisTick': {'show': False},
            'axisLine': {'show': False},
            'splitLine': {'show': False},
        },
        'series': [
            {
                'type': 'bar',
                'data': [int(v) for v in state.density_bins],
                'barWidth': '70%',
                'itemStyle': {
                    'color': '#d4d4d8',
                    'opacity': 0.65,
                    'borderColor': '#ffffff',
                    'borderWidth': 0,
                },
            }
        ],
    }
    return ui.echart(option).classes('w-full h-full')


def _update_density_dom(bins: List[int], raw: List[int], slice_sec: float) -> None:
    """Update the DOM-based density histogram.

    This is intentionally client-side to avoid destabilizing the page by pushing
    complex chart diffs at 2Hz.
    """
    try:
        # Keep this snippet ES5-ish (no template literals, no nullish coalescing).
        ui.run_javascript(f'''
            (function() {{
                var bins = {json.dumps([int(x) for x in bins])};
                var raw = {json.dumps([int(x) for x in raw])};
                var sliceSec = {json.dumps(float(slice_sec))};
                for (var i = 0; i < bins.length; i++) {{
                    var el = document.getElementById('cids-density-bar-' + i);
                    if (!el) continue;
                    var bi = (bins[i] !== undefined && bins[i] !== null) ? bins[i] : 0;
                    var ri = (raw[i] !== undefined && raw[i] !== null) ? raw[i] : 0;
                    var h = Math.max(0, Math.min(100, Number(bi)));
                    el.style.height = (Math.max(2, h)) + '%';
                    el.setAttribute('title', String(Number(ri)) + ' rec / ' + String(Math.round(sliceSec)) + 's');
                }}
            }})();
        ''')
    except Exception:
        # best-effort; never crash the update loop
        pass

# --- MAIN LAYOUT ---

@ui.page('/')
def main_page():
    # Update Theme Colors - Set primary to Dark Gray to fix button contrast default
    ui.colors(primary='#27272a', secondary='#1f2937', accent='#e5e7eb', dark='#18181b')

    # Seed a minimal, system-timestamped boot narrative (no fake times)
    if not state.log_items:
        add_log(f"[INF] Sentinel initialized loop [build:{BUILD_STAMP}]")
        _backend_runtime_log('server_start', {'build': BUILD_STAMP})
    
    # Global Style injection
    ui.add_head_html('''
        <style>
            :root {
                --cids-min-w: 1100px;
                --cids-min-h: 720px;
                /* Filled at runtime from header measurement; used to keep overlays from blocking header controls. */
                --cids-header-bottom: 72px;
                /* Filled at runtime so the Control Deck can align to the centered/scaled surface. */
                --cids-deck-top: 0px;
                --cids-deck-bottom: 0px;
                --cids-deck-right: 0px;
                --cids-deck-width: 300px;
            }
            html, body {
                width: 100%;
                height: 100%;
                margin: 0;
                padding: 0;
                background-color: #18181b;
                color: #e5e7eb;
                overflow: hidden; /* NO SCROLLBARS */
            }

            /*
             * Prevent right-drift:
             * Quasar (and some overlay behaviors) can add body padding-right to
             * compensate for scrollbars ("prevent-scroll"). That moves our
             * center-aligned fixed stage over time and looks like a blanking UI.
             */
            body { padding-right: 0 !important; }
            body.q-body--prevent-scroll { padding-right: 0 !important; }
            body.q-body--prevent-scroll .q-layout,
            body.q-body--prevent-scroll #q-app {
                padding-right: 0 !important;
            }

            /* If any ancestor gets transformed, position:fixed becomes relative to it. */
            #q-app,
            .q-layout,
            .nicegui-content {
                transform: none !important;
            }
            .nicegui-content {
                padding: 0 !important;
                height: 100vh;
                display: flex;
                flex-direction: column;
            }

            #cids-scale-stage {
                position: fixed;
                inset: 0;
                overflow: hidden;
                display: flex;
                align-items: center;
                justify-content: center;
                background: #18181b;
            }

            /* Fixed-size surface (preferred): always render at the designed resolution */
            #cids-scale-root {
                transform-origin: top left;
                width: var(--cids-min-w);
                height: var(--cids-min-h);
                box-sizing: border-box;
                will-change: transform;
                transform: none;
            }

            /*
             * Guardrail: keep the root as a vertical flex stack.
             * We have captured cases where the root behaves like flex-direction: row,
             * which places the header and main grid side-by-side and pushes the grid
             * to x ~= root_content_width + gap ("pulled right" symptom).
             */
            #cids-scale-root {
                display: flex !important;
                flex-direction: column !important;
                justify-content: flex-start !important;
                align-items: stretch !important;
                flex-wrap: nowrap !important;
            }

            /* Control Deck overlay (custom; avoids Quasar drawer layout transforms) */
            #cids-control-deck-backdrop {
                /* Stage-level overlay so it stays pinned when the main surface is centered */
                position: fixed;
                left: 0;
                right: 0;
                bottom: 0;
                /* Do not block or dim the header row; start below it (set at runtime on the stage). */
                top: var(--cids-header-bottom, 72px);
                background: rgba(0, 0, 0, 0.55);
                opacity: 0;
                pointer-events: none;
                transition: opacity 140ms ease;
                z-index: 50;
            }
            #cids-control-deck-backdrop.open {
                opacity: 1;
                pointer-events: auto;
            }
            #cids-control-deck {
                /* Stage-level panel aligned to the centered surface (vars set at runtime). */
                position: fixed;
                top: var(--cids-deck-top, 0px);
                right: var(--cids-deck-right, 0px);
                bottom: var(--cids-deck-bottom, 0px);
                width: var(--cids-deck-width, 300px);
                /*
                 * When the surface is centered, right != 0 (it equals the stage gutter).
                 * A plain translateX(100%) would slide the deck into that gutter and it will
                 * still be visible when "closed" on wide screens.
                 *
                 * Add the gutter to the slide distance so the closed deck is fully off-viewport.
                 */
                transform: translateX(calc(100% + var(--cids-deck-right, 0px)));
                transition: transform 160ms ease;
                z-index: 60;
                pointer-events: none;
                overflow: hidden;
            }
            #cids-control-deck.open {
                transform: translateX(0);
                pointer-events: auto;
            }

            /* Control Deck: bin-width spinbox (local, persistent) */
            .cids-spinbox {
                display: flex;
                align-items: center;
                gap: 10px;
                user-select: none;
            }
            .cids-spinbox-core {
                display: flex;
                align-items: center;
                justify-content: center;
                background: rgba(255, 255, 255, 0.06);
                border: 1px solid rgba(255, 255, 255, 0.16);
                width: 86px;
                height: 58px;
                box-sizing: border-box;
            }
            .cids-spinbox-arrows {
                display: flex;
                flex-direction: column;
                align-items: stretch;
                justify-content: center;
                height: 58px;
                width: 28px;
                box-sizing: border-box;
            }
            .cids-spinbox-btn {
                display: flex;
                align-items: center;
                justify-content: center;
                height: 29px;
                background: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.12);
                color: #e5e7eb;
                font-family: monospace;
                cursor: pointer;
                padding: 0;
            }
            .cids-spinbox-btn:active {
                background: rgba(255, 255, 255, 0.09);
            }
            .cids-spinbox-value {
                font-family: monospace;
                font-weight: 800;
                font-size: 18px;
                color: #ffffff;
                letter-spacing: 0.04em;
                width: 70px;
                text-align: center;
            }
            .cids-spinbox-value.off {
                color: #a1a1aa;
            }
            .cids-spinbox-suffix {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                height: 22px;
                padding: 0 8px;
                border: 1px solid rgba(255, 255, 255, 0.12);
                background: rgba(255, 255, 255, 0.03);
                color: #d4d4d8;
                font-size: 12px;
                letter-spacing: 0.06em;
                text-transform: lowercase;
            }

            /* Optional: crisper text when scaled */
            #cids-scale-root * { -webkit-font-smoothing: antialiased; }

            /* Hide scrollbars while still allowing programmatic scroll */
            .no-scrollbar {
                scrollbar-width: none; /* Firefox */
                -ms-overflow-style: none; /* IE/Edge legacy */
            }
            .no-scrollbar::-webkit-scrollbar { display: none; }

            /* System Log: subtle flash on new lines to make deltas obvious */
            @keyframes cidsFlash {
                0% { background: rgba(255,255,255,0.10); }
                100% { background: rgba(255,255,255,0.00); }
            }
            .cids-log-flash {
                animation: cidsFlash 0.35s ease-out 1;
                padding: 1px 0;
            }
            /* Zebra striping for logs (applied via JS)
             * IMPORTANT: This is character-level striping (text/opacity), not row background fills.
             */
            .cids-log-zebra-even { opacity: 0.92; }
            .cids-log-zebra-odd { opacity: 0.80; }

            /*
             * Prevent long unbroken log lines (paths, hashes) from influencing flex min-content sizing.
             * Without this, some browsers can compute large min-widths which appear as a “snap right”.
             */
            #cids-log-scroll {
                min-width: 0;
                overflow-wrap: anywhere;
                word-break: break-word;
                white-space: pre-wrap;
                overflow-x: hidden;
                max-width: 100%;
            }

            /* Main grid: ensure flex items are allowed to shrink; prevent horizontal overflow cascade */
            #cids-main-grid {
                min-width: 0;
                overflow: hidden;
                /* NiceGUI/Quasar rows default to flex-wrap: wrap; that can cause borderline-width
                 * layouts to wrap or distribute unevenly (looks like a "skew"). Clamp it. */
                display: flex !important;
                flex-direction: row !important;
                flex-wrap: nowrap !important;
                justify-content: flex-start !important;
                align-items: stretch !important;
            }
            #cids-main-grid > * {
                min-width: 0;
            }

            /*
             * Clamp the grid to the root.
             * We have captured cases where the grid subtree jumps to x ~= 100% of the viewport
             * (root stays at x=0), which pulls the entire UI “out of view”.
             * Force the grid back into normal flow.
             */
            #cids-main-grid {
                position: relative !important;
                left: 0 !important;
                right: auto !important;
                margin-left: 0 !important;
                transform: none !important;
            }
            #cids-right-col {
                position: relative !important;
                left: 0 !important;
                right: auto !important;
                margin-left: 0 !important;
                transform: none !important;
            }

            /*
             * Integrity radar containment clamp:
             * We have observed cases where the radar chart's paint surface (canvas)
             * is translated roughly by one column width, visually "mounting" the
             * left chart on the right wall while DOM ancestry remains correct.
             *
             * These rules are intentionally narrow and only target the integrity
             * chart subtree.
             */
            #cids-integrity-wrap {
                position: relative !important;
                overflow: hidden !important;
                isolation: isolate;
                contain: layout paint size;
            }
            #cids-integrity-radar-chart {
                position: relative !important;
                left: 0 !important;
                top: 0 !important;
                right: auto !important;
                bottom: auto !important;
                margin: 0 !important;
                transform: none !important;
                max-width: 100% !important;
                max-height: 100% !important;
                overflow: hidden !important;
            }
            #cids-integrity-radar-chart > div {
                left: 0 !important;
                top: 0 !important;
                right: auto !important;
                bottom: auto !important;
                margin: 0 !important;
                transform: none !important;
                max-width: 100% !important;
                max-height: 100% !important;
            }
            #cids-integrity-radar-chart canvas {
                left: 0 !important;
                top: 0 !important;
                transform: none !important;
                max-width: 100% !important;
                max-height: 100% !important;
            }
        </style>
    ''')

    # Control Deck toggler (pure client-side DOM toggle; no Quasar layout involvement)
    ui.add_head_html('''
        <script>
            (function() {
                function byId(id) { try { return document.getElementById(id); } catch (e) { return null; } }

                // Keep overlays and fixed-size stage usable across window sizes.
                // - Measure header bottom so the backdrop doesn't block/dim it.
                // - If the viewport is smaller than the designed surface, apply a scale-down.
                function clamp(n, lo, hi) {
                    n = Number(n);
                    if (!isFinite(n)) return lo;
                    return Math.max(Number(lo), Math.min(Number(hi), n));
                }

                function updateLayoutVars() {
                    try {
                        var stage = byId('cids-scale-stage');
                        var root = byId('cids-scale-root');
                        if (!stage || !root || !root.getBoundingClientRect) return;

                        function setVar(name, value) {
                            try {
                                if (stage && stage.style && stage.style.setProperty) {
                                    stage.style.setProperty(String(name), String(value));
                                }
                            } catch (eSVar) { }
                            // Also write to :root as a fallback in case the overlay is reparented by the framework.
                            try {
                                var de = document && document.documentElement ? document.documentElement : null;
                                if (de && de.style && de.style.setProperty) {
                                    de.style.setProperty(String(name), String(value));
                                }
                            } catch (eRVar) { }
                        }

                        // Scale-to-fit (only scale down; keep scale=1 when there's enough room)
                        var s = 1;
                        try {
                            var vw = Number(window.innerWidth || 0);
                            var vh = Number(window.innerHeight || 0);
                            // Use numeric values to avoid parsing CSS vars.
                            var designW = 1100;
                            var designH = 720;
                            if (vw > 0 && vh > 0) {
                                var sW = vw / designW;
                                var sH = vh / designH;
                                s = Math.min(1, sW, sH);
                                // Never scale up; also avoid going too tiny.
                                s = clamp(s, 0.55, 1);

                                // Only update when meaningfully different to reduce layout churn.
                                var prev = null;
                                try { prev = root.style.zoom ? Number(root.style.zoom) : null; } catch (eP) { prev = null; }
                                if (!prev || !isFinite(prev) || Math.abs(prev - s) > 0.002) {
                                    try { root.style.zoom = String(s); } catch (eZ) {
                                        try { root.style.setProperty('zoom', String(s)); } catch (eZ2) { }
                                    }
                                }
                            }
                        } catch (eS) {
                            s = 1;
                        }

                        function computeOverlayVars() {
                            try {
                                // After zoom updates, compute stage/root geometry and set overlay vars.
                                var sr = null;
                                var rr = null;
                                try { sr = stage.getBoundingClientRect ? stage.getBoundingClientRect() : null; } catch (eSR) { sr = null; }
                                try { rr = root.getBoundingClientRect ? root.getBoundingClientRect() : null; } catch (eRR) { rr = null; }
                                if (!sr || !rr) return;

                                // Header measurement (for backdrop top offset)
                                try {
                                    var header = byId('cids-header-row');
                                    if (header && header.getBoundingClientRect) {
                                        var hr = header.getBoundingClientRect();
                                        // Backdrop is stage-level. Compute the header bottom relative to the stage.
                                        var topPx = Math.max(0, (Number(hr.bottom) - Number(sr.top)));
                                        // Round to 0.5px to avoid churn.
                                        topPx = Math.round(topPx * 2) / 2;
                                        setVar('--cids-header-bottom', String(topPx) + 'px');
                                    }
                                } catch (eH) {
                                    // swallow
                                }

                                // Control Deck alignment: keep it flush with the centered/scaled surface.
                                try {
                                    var deckTop = Math.max(0, Number(rr.top) - Number(sr.top));
                                    var deckBottom = Math.max(0, Number(sr.bottom) - Number(rr.bottom));
                                    var deckRight = Math.max(0, Number(sr.right) - Number(rr.right));
                                    // Scale the deck width with the surface so it looks consistent across zoom levels.
                                    var deckW = Math.round(300 * clamp(s, 0.55, 1) * 2) / 2;

                                    // Round to 0.5px to avoid churn.
                                    deckTop = Math.round(deckTop * 2) / 2;
                                    deckBottom = Math.round(deckBottom * 2) / 2;
                                    deckRight = Math.round(deckRight * 2) / 2;

                                    setVar('--cids-deck-top', String(deckTop) + 'px');
                                    setVar('--cids-deck-bottom', String(deckBottom) + 'px');
                                    setVar('--cids-deck-right', String(deckRight) + 'px');
                                    setVar('--cids-deck-width', String(deckW) + 'px');
                                } catch (eDeck) {
                                    // swallow
                                }
                            } catch (eCO) {
                                // swallow
                            }
                        }

                        // Compute immediately, then again after the browser applies zoom/layout.
                        computeOverlayVars();
                        try { setTimeout(computeOverlayVars, 0); } catch (eT0) { }
                        try { setTimeout(computeOverlayVars, 60); } catch (eT1) { }
                        try {
                            if (window.requestAnimationFrame) {
                                window.requestAnimationFrame(function() {
                                    try { computeOverlayVars(); } catch (eRAF) { }
                                });
                            }
                        } catch (eRAF0) { }
                    } catch (eAll) {
                        // swallow
                    }
                }

                // Expose for debugging / other injected scripts.
                try { window.__cids_update_layout_vars = updateLayoutVars; } catch (eEx) { }

                // Apply on load + resize (debounced)
                var tHandle = null;
                function schedule() {
                    try {
                        if (tHandle) { clearTimeout(tHandle); tHandle = null; }
                        tHandle = setTimeout(function() { updateLayoutVars(); }, 80);
                    } catch (eT) {
                        // swallow
                    }
                }
                try {
                    window.addEventListener('resize', schedule);
                } catch (eR) {
                    // swallow
                }
                // Multiple passes catch first-paint and late font/layout changes.
                try { setTimeout(updateLayoutVars, 30); } catch (e0) { }
                try { setTimeout(updateLayoutVars, 250); } catch (e1) { }
                try { setTimeout(updateLayoutVars, 1200); } catch (e2) { }

                window.__cids_set_deck = function(open) {
                    try {
                        var deck = byId('cids-control-deck');
                        var bd = byId('cids-control-deck-backdrop');
                        if (!deck || !bd) return;
                        var isOpen = !!open;
                        try { window.__cids_control_deck_open = isOpen; } catch (eFlag) { }
                        if (isOpen) {
                            deck.classList.add('open');
                            bd.classList.add('open');
                        } else {
                            deck.classList.remove('open');
                            bd.classList.remove('open');
                        }

                        // Re-evaluate layout vars (header height/zoom) after transitions.
                        try { updateLayoutVars(); } catch (eUL) { }
                    } catch (e2) {
                        // swallow
                    }
                };
                window.__cids_toggle_deck = function() {
                    try {
                        var deck = byId('cids-control-deck');
                        if (!deck) return;
                        var open = !deck.classList.contains('open');
                        window.__cids_set_deck(open);
                    } catch (e3) {
                        // swallow
                    }
                };
            })();
        </script>
    ''')

    # Capture client-side JS errors and ship them back to the server as JSON.
    # IMPORTANT: keep this snippet ES5-ish and ASCII-only; if this hook fails to parse,
    # we lose the only breadcrumb when the UI blanks.
    ui.add_head_html('''
        <script>
            (function() {
                if (window.__cids_js_err_bound) return;
                window.__cids_js_err_bound = true;

                // A per-tab id to distinguish reloads vs brand new app windows.
                // sessionStorage persists across reloads within the same tab.
                var sessionId = null;
                try {
                    sessionId = sessionStorage.getItem('__cids_session_id');
                    if (!sessionId) {
                        sessionId = String(Date.now()) + '-' + Math.random().toString(16).slice(2);
                        sessionStorage.setItem('__cids_session_id', sessionId);
                    }
                } catch (eSID) {
                    sessionId = null;
                }

                // Rate-limit uploads to avoid feedback loops.
                var windowStart = Date.now();
                var sentInWindow = 0;
                function allowSend() {
                    var now = Date.now();
                    if ((now - windowStart) > 5000) {
                        windowStart = now;
                        sentInWindow = 0;
                    }
                    if (sentInWindow >= 12) return false;
                    sentInWindow += 1;
                    return true;
                }

                function safeString(x) {
                    try {
                        if (x === null || x === undefined) return String(x);
                        if (typeof x === 'string') return x;
                        if (typeof x === 'object') {
                            try { return JSON.stringify(x); } catch (e) { return String(x); }
                        }
                        return String(x);
                    } catch (e2) {
                        return '[unstringifiable]';
                    }
                }

                function truncate(s, maxLen) {
                    s = String(s || '');
                    return s.length > maxLen ? (s.slice(0, maxLen) + '...') : s;
                }

                function safeRect(el) {
                    try {
                        if (!el || !el.getBoundingClientRect) return null;
                        var r = el.getBoundingClientRect();
                        function rr(x) { return Math.round(Number(x || 0) * 100) / 100; }
                        return {
                            left: rr(r.left),
                            top: rr(r.top),
                            width: rr(r.width),
                            height: rr(r.height),
                            right: rr(r.right),
                            bottom: rr(r.bottom)
                        };
                    } catch (e) {
                        return null;
                    }
                }

                function styleProbe(el) {
                    try {
                        if (!el || !window.getComputedStyle) return null;
                        var cs = window.getComputedStyle(el);
                        return {
                            position: cs.position,
                            display: cs.display,
                            left: cs.left,
                            right: cs.right,
                            top: cs.top,
                            bottom: cs.bottom,
                            width: cs.width,
                            height: cs.height,
                            minWidth: cs.minWidth,
                            minHeight: cs.minHeight,
                            maxWidth: cs.maxWidth,
                            maxHeight: cs.maxHeight,
                            marginLeft: cs.marginLeft,
                            marginRight: cs.marginRight,
                            marginTop: cs.marginTop,
                            marginBottom: cs.marginBottom,
                            transform: cs.transform,
                            overflowX: cs.overflowX,
                            overflowY: cs.overflowY
                        };
                    } catch (e) {
                        return null;
                    }
                }

                function countSel(sel) {
                    try {
                        if (!document || !document.querySelectorAll) return null;
                        return Number(document.querySelectorAll(String(sel)).length);
                    } catch (e) {
                        return null;
                    }
                }

                function elStyleProbe(el) {
                    try {
                        if (!el || !window.getComputedStyle) return null;
                        var cs = window.getComputedStyle(el);
                        return {
                            position: cs.position,
                            display: cs.display,
                            left: cs.left,
                            right: cs.right,
                            top: cs.top,
                            bottom: cs.bottom,
                            width: cs.width,
                            maxWidth: cs.maxWidth,
                            minWidth: cs.minWidth,
                            transform: cs.transform,
                            overflowX: cs.overflowX,
                            overflowY: cs.overflowY,
                            whiteSpace: cs.whiteSpace
                        };
                    } catch (e) {
                        return null;
                    }
                }

                function ancestorProbe(el, depth) {
                    try {
                        var out = [];
                        var cur = el;
                        var n = Number(depth || 0);
                        if (!isFinite(n) || n < 1) n = 1;
                        if (n > 8) n = 8;
                        for (var i = 0; i < n; i++) {
                            if (!cur) break;
                            out.push({
                                tag: cur.tagName ? String(cur.tagName) : null,
                                id: cur.id ? String(cur.id) : null,
                                cls: cur.className ? truncate(String(cur.className), 180) : null,
                                rect: safeRect(cur)
                            });
                            try { cur = cur.parentElement; } catch (eP) { cur = null; }
                        }
                        return out;
                    } catch (e) {
                        return null;
                    }
                }

                function computedStyleSnapshot() {
                    try {
                        var bodyCS = null;
                        try { bodyCS = window.getComputedStyle(document.body); } catch (e0) { bodyCS = null; }
                        var qApp = null;
                        try { qApp = document.getElementById('q-app'); } catch (e1) { qApp = null; }
                        var nice = null;
                        try { nice = document.querySelector('.nicegui-content'); } catch (e2) { nice = null; }
                        var root = null;
                        var grid = null;
                        var rc = null;
                        var deck = null;
                        var bd = null;
                        try { root = document.getElementById('cids-scale-root'); } catch (eR0) { root = null; }
                        try { grid = document.getElementById('cids-main-grid'); } catch (eG0) { grid = null; }
                        try { rc = document.getElementById('cids-right-col'); } catch (eC0) { rc = null; }
                        try { deck = document.getElementById('cids-control-deck'); } catch (eD0) { deck = null; }
                        try { bd = document.getElementById('cids-control-deck-backdrop'); } catch (eB0) { bd = null; }
                        var qAppCS = null;
                        var niceCS = null;
                        var rootCS = null;
                        var gridCS = null;
                        var rcCS = null;
                        var deckCS = null;
                        var bdCS = null;
                        try { if (qApp) qAppCS = window.getComputedStyle(qApp); } catch (e3) { qAppCS = null; }
                        try { if (nice) niceCS = window.getComputedStyle(nice); } catch (e4) { niceCS = null; }
                        try { if (root) rootCS = window.getComputedStyle(root); } catch (e5) { rootCS = null; }
                        try { if (grid) gridCS = window.getComputedStyle(grid); } catch (e6) { gridCS = null; }
                        try { if (rc) rcCS = window.getComputedStyle(rc); } catch (e7) { rcCS = null; }
                        try { if (deck) deckCS = window.getComputedStyle(deck); } catch (e8) { deckCS = null; }
                        try { if (bd) bdCS = window.getComputedStyle(bd); } catch (e9) { bdCS = null; }
                        return {
                            viewport: { w: window.innerWidth, h: window.innerHeight, dpr: (window.devicePixelRatio || null) },
                            body: bodyCS ? {
                                paddingRight: bodyCS.paddingRight,
                                overflowX: bodyCS.overflowX,
                                overflowY: bodyCS.overflowY,
                                transform: bodyCS.transform
                            } : null,
                            q_app: qAppCS ? { transform: qAppCS.transform } : null,
                            nicegui_content: niceCS ? { transform: niceCS.transform } : null,
                            scale_root: rootCS ? {
                                display: rootCS.display,
                                zoom: (rootCS.zoom !== undefined) ? rootCS.zoom : null,
                                flexDirection: rootCS.flexDirection,
                                justifyContent: rootCS.justifyContent,
                                alignItems: rootCS.alignItems,
                                flexWrap: rootCS.flexWrap,
                                gap: rootCS.gap,
                                width: rootCS.width,
                                height: rootCS.height,
                                minWidth: rootCS.minWidth,
                                maxWidth: rootCS.maxWidth,
                                position: rootCS.position,
                                transform: rootCS.transform
                            } : null,
                            main_grid: gridCS ? {
                                display: gridCS.display,
                                flexDirection: gridCS.flexDirection,
                                justifyContent: gridCS.justifyContent,
                                alignItems: gridCS.alignItems,
                                flexWrap: gridCS.flexWrap,
                                position: gridCS.position,
                                left: gridCS.left,
                                right: gridCS.right,
                                marginLeft: gridCS.marginLeft,
                                transform: gridCS.transform,
                                width: gridCS.width
                            } : null,
                            right_col: rcCS ? {
                                display: rcCS.display,
                                flexDirection: rcCS.flexDirection,
                                position: rcCS.position,
                                left: rcCS.left,
                                right: rcCS.right,
                                marginLeft: rcCS.marginLeft,
                                transform: rcCS.transform,
                                width: rcCS.width
                            } : null,
                            control_deck: (deckCS || bdCS) ? {
                                deck: deckCS ? {
                                    display: deckCS.display,
                                    position: deckCS.position,
                                    right: deckCS.right,
                                    width: deckCS.width,
                                    height: deckCS.height,
                                    transform: deckCS.transform,
                                    pointerEvents: deckCS.pointerEvents,
                                    zIndex: deckCS.zIndex
                                } : null,
                                backdrop: bdCS ? {
                                    display: bdCS.display,
                                    position: bdCS.position,
                                    opacity: bdCS.opacity,
                                    pointerEvents: bdCS.pointerEvents,
                                    zIndex: bdCS.zIndex
                                } : null
                            } : null
                        };
                    } catch (e) {
                        return null;
                    }
                }

                function post(kind, data) {
                    try {
                        if (!allowSend()) return Promise.resolve();
                        // IMPORTANT: always catch fetch rejections; otherwise a transient backend stall
                        // will generate unhandledrejection events and can spiral into reload/blank behavior.
                        return fetch('/_ghost_console/js_error', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({ kind: kind, data: data, href: location.href, ua: navigator.userAgent, t: Date.now() })
                        }).catch(function() { /* swallow */ });
                    } catch (e) {
                        return Promise.resolve();
                    }
                }

                // Make available to other head-injected scripts.
                try { window.__cids_post_diag = post; } catch (ePost) { }

                // Confirm the hook is active.
                // Include navigation context so we can distinguish reloads vs fresh launches.
                (function() {
                    try {
                        var navType = null;
                        var navMeta = null;
                        try {
                            if (performance && performance.getEntriesByType) {
                                var nav = performance.getEntriesByType('navigation');
                                if (nav && nav.length && nav[0]) {
                                    if (nav[0].type) navType = String(nav[0].type);
                                    navMeta = {
                                        redirectCount: (nav[0].redirectCount !== undefined) ? Number(nav[0].redirectCount) : null,
                                        transferSize: (nav[0].transferSize !== undefined) ? Number(nav[0].transferSize) : null,
                                        nextHopProtocol: (nav[0].nextHopProtocol !== undefined) ? String(nav[0].nextHopProtocol) : null,
                                        duration: (nav[0].duration !== undefined) ? Number(nav[0].duration) : null
                                    };
                                }
                            }
                        } catch (e0) { navType = null; }
                        post('client_boot', {
                            build: %s,
                            nav_type: navType,
                            nav_meta: navMeta,
                            session_id: sessionId,
                            referrer: (document && document.referrer) ? String(document.referrer) : null,
                            hash: (location && location.hash !== undefined) ? String(location.hash) : null,
                            history_len: (history && history.length !== undefined) ? Number(history.length) : null,
                            visibility: (document && document.visibilityState) ? String(document.visibilityState) : null,
                            ready_state: (document && document.readyState) ? String(document.readyState) : null
                        });
                    } catch (e1) {
                        post('client_boot', { build: %s });
                    }
                })();

                // Capture lifecycle events that indicate a real navigation/unload.
                try {
                    window.addEventListener('beforeunload', function() {
                        post('beforeunload', { session_id: sessionId });
                    });
                    window.addEventListener('pagehide', function(ev) {
                        post('pagehide', { persisted: !!(ev && ev.persisted), session_id: sessionId });
                    });
                    window.addEventListener('pageshow', function(ev) {
                        post('pageshow', { persisted: !!(ev && ev.persisted), session_id: sessionId });
                    });
                    document.addEventListener('visibilitychange', function() {
                        post('visibilitychange', { state: (document && document.visibilityState) ? String(document.visibilityState) : null, session_id: sessionId });
                    });
                } catch (eLife) {
                    // swallow
                }

                // Heartbeat from client -> server so we can distinguish:
                //   (a) UI blanked but JS still running (CSS/layout/overlay)
                //   (b) JS/event loop stalled/crashed (no more heartbeats)
                setInterval(function() {
                    try {
                        var now = Date.now();
                        // Keep the diagnostics stream small so the tail endpoint (bounded by bytes)
                        // retains rare events like chart_mount / chart_lookup / echarts_module.
                        // Full layout probes are only sent periodically or when forced.
                        var includeProbe = false;
                        try {
                            var lastFull = Number(window.__cids_alive_full_ts || 0);
                            var forceFull = !!window.__cids_force_alive_full;
                            includeProbe = forceFull || !isFinite(lastFull) || (now - lastFull) > 30000;
                            if (includeProbe) {
                                window.__cids_alive_full_ts = now;
                                window.__cids_force_alive_full = false;
                            }
                        } catch (eProbeCtl) {
                            includeProbe = false;
                        }
                        var serverTick = window.__cids_server_tick;
                        var serverTickAge = (serverTick && typeof serverTick === 'number') ? (now - serverTick) : null;
                        var x = Math.floor(window.innerWidth * 0.5);
                        var y = Math.floor(window.innerHeight * 0.62);
                        var top = null;
                        try {
                            var el = document.elementFromPoint(x, y);
                            if (el) {
                                top = {
                                    tag: el.tagName ? String(el.tagName) : null,
                                    id: el.id ? String(el.id) : null,
                                    cls: el.className ? truncate(String(el.className), 220) : null
                                };
                            }
                        } catch (e0) {
                            top = null;
                        }
                        var rootEl = document.getElementById('cids-scale-root');
                        var stageEl = null;
                        try { stageEl = document.getElementById('cids-scale-stage'); } catch (eStage) { stageEl = null; }
                        var rootStyle = null;
                        try {
                            if (rootEl && window.getComputedStyle) {
                                var cs = window.getComputedStyle(rootEl);
                                rootStyle = {
                                    position: cs.position,
                                    display: cs.display,
                                    flexDirection: cs.flexDirection,
                                    visibility: cs.visibility,
                                    opacity: cs.opacity,
                                    pointerEvents: cs.pointerEvents,
                                    zoom: (cs.zoom !== undefined) ? cs.zoom : null,
                                    cssVars: {
                                        header_bottom: (function() {
                                            try {
                                                var v = stageEl && stageEl.style ? stageEl.style.getPropertyValue('--cids-header-bottom') : '';
                                                return v ? String(v).trim() : null;
                                            } catch (eV) {
                                                return null;
                                            }
                                        })(),
                                        deck_top: (function() {
                                            try {
                                                var v = stageEl && stageEl.style ? stageEl.style.getPropertyValue('--cids-deck-top') : '';
                                                return v ? String(v).trim() : null;
                                            } catch (eV2) {
                                                return null;
                                            }
                                        })(),
                                        deck_bottom: (function() {
                                            try {
                                                var v = stageEl && stageEl.style ? stageEl.style.getPropertyValue('--cids-deck-bottom') : '';
                                                return v ? String(v).trim() : null;
                                            } catch (eV3) {
                                                return null;
                                            }
                                        })(),
                                        deck_right: (function() {
                                            try {
                                                var v = stageEl && stageEl.style ? stageEl.style.getPropertyValue('--cids-deck-right') : '';
                                                return v ? String(v).trim() : null;
                                            } catch (eV4) {
                                                return null;
                                            }
                                        })(),
                                        deck_width: (function() {
                                            try {
                                                var v = stageEl && stageEl.style ? stageEl.style.getPropertyValue('--cids-deck-width') : '';
                                                return v ? String(v).trim() : null;
                                            } catch (eV5) {
                                                return null;
                                            }
                                        })()
                                    }
                                };
                            }
                        } catch (e1) {
                            rootStyle = null;
                        }

                        var alivePayload = {
                            build: %s,
                            server_tick_age_ms: serverTickAge,
                            top_at_point: top,
                            root_style: rootStyle
                        };

                        if (includeProbe) {
                            var gridEl = null;
                            var rightColEl = null;
                            try { gridEl = document.getElementById('cids-main-grid'); } catch (eG) { gridEl = null; }
                            try { rightColEl = document.getElementById('cids-right-col'); } catch (eR) { rightColEl = null; }

                            var logEl = null;
                            var denEl = null;
                            try { logEl = document.getElementById('cids-log-scroll'); } catch (eL) { logEl = null; }
                            try { denEl = document.getElementById('cids-density-chart'); } catch (eD) { denEl = null; }

                            var logOP = null;
                            var denOP = null;
                            try { logOP = logEl ? logEl.offsetParent : null; } catch (eLOP) { logOP = null; }
                            try { denOP = denEl ? denEl.offsetParent : null; } catch (eDOP) { denOP = null; }

                            var docMetrics = null;
                            try {
                                var de = document.documentElement;
                                docMetrics = {
                                    scrollX: (window && window.scrollX !== undefined) ? Number(window.scrollX) : null,
                                    scrollY: (window && window.scrollY !== undefined) ? Number(window.scrollY) : null,
                                    clientW: de ? Number(de.clientWidth) : null,
                                    clientH: de ? Number(de.clientHeight) : null,
                                    scrollW: de ? Number(de.scrollWidth) : null,
                                    scrollH: de ? Number(de.scrollHeight) : null
                                };
                            } catch (eDM) {
                                docMetrics = null;
                            }

                            // Control Deck anchoring probe (is it still positioned correctly, and are its children in-frame?)
                            var deckProbe = null;
                            try {
                                var deck = document.getElementById('cids-control-deck');
                                var bd = document.getElementById('cids-control-deck-backdrop');
                                var body = document.getElementById('cids-deck-body');
                                var statusBadge = document.getElementById('cids-status-badge');

                                var op = null;
                                try { op = deck ? deck.offsetParent : null; } catch (eOP) { op = null; }

                                var bodyOP = null;
                                try { bodyOP = body ? body.offsetParent : null; } catch (eBOP) { bodyOP = null; }

                                var statusOP = null;
                                try { statusOP = statusBadge ? statusBadge.offsetParent : null; } catch (eSOP) { statusOP = null; }

                                deckProbe = {
                                    deck_rect: safeRect(deck),
                                    backdrop_rect: safeRect(bd),
                                    offset_parent: op ? {
                                        tag: op.tagName ? String(op.tagName) : null,
                                        id: op.id ? String(op.id) : null,
                                        cls: op.className ? truncate(String(op.className), 220) : null,
                                        rect: safeRect(op)
                                    } : null,
                                    body_rect: safeRect(body),
                                    body_style: elStyleProbe(body),
                                    body_offset_parent: bodyOP ? {
                                        tag: bodyOP.tagName ? String(bodyOP.tagName) : null,
                                        id: bodyOP.id ? String(bodyOP.id) : null,
                                        cls: bodyOP.className ? truncate(String(bodyOP.className), 220) : null,
                                        rect: safeRect(bodyOP)
                                    } : null,
                                    status_badge_rect: safeRect(statusBadge),
                                    status_badge_style: elStyleProbe(statusBadge),
                                    status_badge_offset_parent: statusOP ? {
                                        tag: statusOP.tagName ? String(statusOP.tagName) : null,
                                        id: statusOP.id ? String(statusOP.id) : null,
                                        cls: statusOP.className ? truncate(String(statusOP.className), 220) : null,
                                        rect: safeRect(statusOP)
                                    } : null,
                                    status_badge_ancestors: ancestorProbe(statusBadge, 6)
                                };
                            } catch (eDP) {
                                deckProbe = null;
                            }

                            alivePayload.layout_probe = {
                                stage_rect: safeRect(document.getElementById('cids-scale-stage')),
                                root_rect: safeRect(document.getElementById('cids-scale-root')),
                                main_grid_rect: safeRect(gridEl),
                                right_col_rect: safeRect(rightColEl),
                                density_rect: safeRect(denEl),
                                log_scroll_rect: safeRect(logEl),
                                density_offset_parent: denOP ? {
                                    tag: denOP.tagName ? String(denOP.tagName) : null,
                                    id: denOP.id ? String(denOP.id) : null,
                                    cls: denOP.className ? truncate(String(denOP.className), 180) : null,
                                    rect: safeRect(denOP)
                                } : null,
                                log_scroll_offset_parent: logOP ? {
                                    tag: logOP.tagName ? String(logOP.tagName) : null,
                                    id: logOP.id ? String(logOP.id) : null,
                                    cls: logOP.className ? truncate(String(logOP.className), 180) : null,
                                    rect: safeRect(logOP)
                                } : null,
                                density_style: elStyleProbe(denEl),
                                log_scroll_style: elStyleProbe(logEl),
                                density_ancestors: ancestorProbe(denEl, 6),
                                log_scroll_ancestors: ancestorProbe(logEl, 6),
                                id_counts: {
                                    cids_scale_root: countSel('#cids-scale-root'),
                                    cids_main_grid: countSel('#cids-main-grid'),
                                    cids_right_col: countSel('#cids-right-col'),
                                    cids_density_chart: countSel('#cids-density-chart'),
                                    cids_log_scroll: countSel('#cids-log-scroll')
                                },
                                doc_metrics: docMetrics,
                                root_classes: (rootEl && rootEl.className) ? truncate(String(rootEl.className), 240) : null,
                                control_deck_open: (function() {
                                    try {
                                        var dk = document.getElementById('cids-control-deck');
                                        if (!dk || !dk.classList) return false;
                                        return !!dk.classList.contains('open');
                                    } catch (e) {
                                        return false;
                                    }
                                })(),
                                control_deck: deckProbe,
                                styles: computedStyleSnapshot()
                            };
                        }

                        post('client_alive', alivePayload);
                    } catch (e2) {
                        // swallow
                        post('client_alive', { build: %s });
                    }
                }, 2000);

                // Anti-drift enforcement:
                // Quasar can add body padding-right for scroll-lock and/or transforms on ancestors.
                // Either can shift the entire centered stage and look like the UI "pulled right".
                var lastEnforcedKey = null;
                setInterval(function() {
                    try {
                        var fixes = [];
                        var before = computedStyleSnapshot();
                        if (!before || !before.body) return;

                        var pr = String(before.body.paddingRight || '').trim();
                        var prNum = parseFloat(pr.replace('px', ''));
                        if (isFinite(prNum) && prNum > 0.5) {
                            try { document.body.style.paddingRight = '0px'; } catch (ePR) { }
                            fixes.push({ what: 'body_paddingRight', from: pr, to: '0px' });
                        }

                        try {
                            var qApp = document.getElementById('q-app');
                            if (qApp && window.getComputedStyle) {
                                var t = window.getComputedStyle(qApp).transform;
                                if (t && t !== 'none') {
                                    qApp.style.transform = 'none';
                                    fixes.push({ what: '#q-app_transform', from: String(t), to: 'none' });
                                }
                            }
                        } catch (eT1) { }

                        try {
                            var nice = document.querySelector('.nicegui-content');
                            if (nice && window.getComputedStyle) {
                                var t2 = window.getComputedStyle(nice).transform;
                                if (t2 && t2 !== 'none') {
                                    nice.style.transform = 'none';
                                    fixes.push({ what: '.nicegui-content_transform', from: String(t2), to: 'none' });
                                }
                            }
                        } catch (eT2) { }

                        // Root flex-direction guardrail:
                        // Bad state observed: #cids-scale-root behaves like flex-direction: row and
                        // pushes #cids-main-grid to the right by ~root_content_width + gap.
                        try {
                            var root = document.getElementById('cids-scale-root');
                            if (root && window.getComputedStyle) {
                                var rcs = window.getComputedStyle(root);
                                var fd = rcs && rcs.flexDirection ? String(rcs.flexDirection) : null;
                                if (fd && fd !== 'column') {
                                    try { root.style.setProperty('display', 'flex', 'important'); } catch (eRD) { try { root.style.display = 'flex'; } catch (_) {} }
                                    try { root.style.setProperty('flex-direction', 'column', 'important'); } catch (eRF) { try { root.style.flexDirection = 'column'; } catch (_) {} }
                                    try { root.style.setProperty('flex-wrap', 'nowrap', 'important'); } catch (eRW) { try { root.style.flexWrap = 'nowrap'; } catch (_) {} }
                                    try { root.style.setProperty('justify-content', 'flex-start', 'important'); } catch (eRJ) { }
                                    try { root.style.setProperty('align-items', 'stretch', 'important'); } catch (eRA) { }
                                    fixes.push({ what: '#cids-scale-root_flexDirection', from: fd, to: 'column' });
                                }
                            }
                        } catch (eRF2) { }

                        // Grid re-center enforcement:
                        // Observed bad state: root rect stays at left=0, but the main grid rect jumps to ~x=viewport width.
                        try {
                            var rootEl = document.getElementById('cids-scale-root');
                            var gridEl = document.getElementById('cids-main-grid');
                            if (rootEl && gridEl && rootEl.getBoundingClientRect && gridEl.getBoundingClientRect) {
                                var rr = rootEl.getBoundingClientRect();
                                var gr = gridEl.getBoundingClientRect();
                                // Only act on a clear displacement (avoid noise during first paint).
                                var dx = Number(gr.left) - Number(rr.left);
                                if (isFinite(dx) && dx > 320) {
                                    var beforeRect = {
                                        left: gr.left, right: gr.right, top: gr.top, bottom: gr.bottom, width: gr.width, height: gr.height,
                                    };
                                    var beforeStyle = null;
                                    try {
                                        var csG = window.getComputedStyle(gridEl);
                                        beforeStyle = {
                                            position: csG.position,
                                            left: csG.left,
                                            right: csG.right,
                                            marginLeft: csG.marginLeft,
                                            transform: csG.transform,
                                        };
                                    } catch (eCSG) {}

                                    // Force back into normal flow.
                                    // Use !important to override any framework-applied !important rules.
                                    try { gridEl.style.setProperty('position', 'relative', 'important'); } catch (eP) { try { gridEl.style.position = 'relative'; } catch (_) {} }
                                    try { gridEl.style.setProperty('left', '0px', 'important'); } catch (eL) { try { gridEl.style.left = '0px'; } catch (_) {} }
                                    try { gridEl.style.setProperty('right', 'auto', 'important'); } catch (eR) { try { gridEl.style.right = 'auto'; } catch (_) {} }
                                    try { gridEl.style.setProperty('margin-left', '0px', 'important'); } catch (eM) { try { gridEl.style.marginLeft = '0px'; } catch (_) {} }
                                    try { gridEl.style.setProperty('transform', 'none', 'important'); } catch (eX) { try { gridEl.style.transform = 'none'; } catch (_) {} }

                                    // Also clamp the right column, as it is inside the grid and tends to shift with it.
                                    try {
                                        var rc = document.getElementById('cids-right-col');
                                        if (rc && rc.style && rc.style.setProperty) {
                                            rc.style.setProperty('position', 'relative', 'important');
                                            rc.style.setProperty('left', '0px', 'important');
                                            rc.style.setProperty('right', 'auto', 'important');
                                            rc.style.setProperty('margin-left', '0px', 'important');
                                            rc.style.setProperty('transform', 'none', 'important');
                                        }
                                    } catch (eRC) {}

                                    // Measure again after applying.
                                    var afterRect = null;
                                    try {
                                        var gr2 = gridEl.getBoundingClientRect();
                                        afterRect = {
                                            left: gr2.left, right: gr2.right, top: gr2.top, bottom: gr2.bottom, width: gr2.width, height: gr2.height,
                                        };
                                    } catch (eGR2) {}

                                    fixes.push({
                                        what: '#cids-main-grid_recenter',
                                        from_dx: dx,
                                        before_rect: beforeRect,
                                        after_rect: afterRect,
                                        before_style: beforeStyle,
                                    });
                                }
                            }
                        } catch (eG) { }

                        if (fixes.length) {
                            // If charts are mounted, ask them to recompute geometry after enforcement.
                            // This is especially important when the framework briefly applies transforms
                            // or padding adjustments that can confuse ECharts' internal canvas placement.
                            try {
                                if (window.__cids_resize_charts) {
                                    setTimeout(function() {
                                        try { window.__cids_resize_charts(); } catch (eRZ) { }
                                    }, 60);
                                }
                            } catch (eRZ0) {
                                // swallow
                            }

                            var after = computedStyleSnapshot();
                            var stageRect = safeRect(document.getElementById('cids-scale-stage'));
                            var key = JSON.stringify({ fixes: fixes, stage: stageRect, after: after });
                            if (key !== lastEnforcedKey) {
                                lastEnforcedKey = key;
                                post('layout_enforced', {
                                    fixes: fixes,
                                    stage_rect: stageRect,
                                    before: before,
                                    after: after
                                });
                            }
                        }
                    } catch (eAll) {
                        // swallow
                    }
                }, 1500);

                setTimeout(function() {
                    post('client_boot_delayed', { build: %s, session_id: sessionId });
                }, 6000);

                // Detect the "blank grid" symptom even when no JS error is thrown.
                // We sample a couple of key elements and only report on state transitions.
                var lastBlank = null; // null=unknown, false=ok, true=blank
                function isBlankNow() {
                    try {
                        var root = document.getElementById('cids-scale-root');
                        if (!root) return true;
                        // Header exists even during blanking; pick a card in the main grid.
                        var cards = root.querySelectorAll('.q-card');
                        if (!cards || cards.length < 2) return true;
                        // The first card is radar; if it collapses to ~0 height, treat as blank.
                        var r = cards[0].getBoundingClientRect();
                        return !(r && r.height && r.height > 40);
                    } catch (e) {
                        return true;
                    }
                }

                function reportBlankState(force) {
                    var blank = isBlankNow();
                    if (!force && lastBlank === blank) return;
                    lastBlank = blank;
                    try {
                        var rootEl = document.getElementById('cids-scale-root');
                        var top = null;
                        try {
                            var x = Math.floor(window.innerWidth * 0.5);
                            var y = Math.floor(window.innerHeight * 0.62);
                            var el = document.elementFromPoint(x, y);
                            if (el) {
                                top = {
                                    tag: el.tagName ? String(el.tagName) : null,
                                    id: el.id ? String(el.id) : null,
                                    cls: el.className ? truncate(String(el.className), 220) : null
                                };
                            }
                        } catch (e0) {
                            top = null;
                        }

                        var rootStyle = null;
                        try {
                            if (rootEl && window.getComputedStyle) {
                                var cs = window.getComputedStyle(rootEl);
                                rootStyle = {
                                    display: cs.display,
                                    visibility: cs.visibility,
                                    opacity: cs.opacity,
                                    pointerEvents: cs.pointerEvents
                                };
                            }
                        } catch (e1) {
                            rootStyle = null;
                        }

                        var info = {
                            blank: blank,
                            root: rootEl ? {
                                childCount: rootEl.childNodes ? rootEl.childNodes.length : null,
                                htmlLen: (rootEl.innerHTML ? rootEl.innerHTML.length : null)
                            } : null,
                            cards: null,
                            top_at_point: top,
                            root_style: rootStyle
                        };
                        if (rootEl) {
                            var cs = rootEl.querySelectorAll('.q-card');
                            info.cards = [];
                            for (var i = 0; i < cs.length && i < 4; i++) {
                                var b = cs[i].getBoundingClientRect();
                                info.cards.push({ w: Math.round(b.width || 0), h: Math.round(b.height || 0) });
                            }
                        }
                        post('layout_state', info);
                    } catch (e2) {
                        // swallow
                    }
                }

                // First sample after the UI should be mounted.
                setTimeout(function() { reportBlankState(true); }, 1500);
                // Then watch for transitions.
                setInterval(function() { reportBlankState(false); }, 750);

                // Detect if the root gets unmounted or heavily mutated.
                try {
                    var target = document.getElementById('cids-scale-root');
                    if (target && window.MutationObserver) {
                        var mo = new MutationObserver(function(muts) {
                            try {
                                // Only report when we already look blank to avoid noise.
                                if (isBlankNow()) {
                                    post('mutation_when_blank', { count: muts ? muts.length : null });
                                }
                            } catch (e3) {
                                // swallow
                            }
                        });
                        mo.observe(target, { childList: true, subtree: true });
                    }
                } catch (e4) {
                    // swallow
                }

                window.addEventListener('error', function(ev) {
                    post('error', {
                        message: ev && ev.message ? String(ev.message) : null,
                        filename: ev && ev.filename ? String(ev.filename) : null,
                        lineno: ev && ev.lineno ? Number(ev.lineno) : null,
                        colno: ev && ev.colno ? Number(ev.colno) : null,
                        stack: ev && ev.error && ev.error.stack ? String(ev.error.stack) : null
                    });
                });

                window.addEventListener('unhandledrejection', function(ev) {
                    var r = ev ? ev.reason : null;
                    post('unhandledrejection', {
                        message: r && r.message ? String(r.message) : safeString(r),
                        stack: r && r.stack ? String(r.stack) : null
                    });
                });

                // Framework/runtime errors often surface via console.error (not window.onerror).
                try {
                    var origErr = console.error;
                    console.error = function() {
                        try {
                            var args = Array.prototype.slice.call(arguments, 0, 6);
                            var mapped = [];
                            for (var i = 0; i < args.length; i++) {
                                mapped.push(truncate(safeString(args[i]), 800));
                            }
                            // Quasar/NiceGUI sometimes emits noisy anchor messages during early boot.
                            // Keep them out of the error stream so we can focus on fatal events.
                            var head = mapped && mapped.length ? String(mapped[0] || '') : '';
                            if (head.indexOf('Anchor: target') === 0) {
                                post('console_warn', { args: mapped, filtered: 'anchor_target_not_found' });
                            } else {
                                post('console_error', { args: mapped });
                            }
                        } catch (e) {
                            // swallow
                        }
                        return origErr && origErr.apply ? origErr.apply(console, arguments) : undefined;
                    };

                    var origWarn = console.warn;
                    console.warn = function() {
                        try {
                            var argsW = Array.prototype.slice.call(arguments, 0, 6);
                            var mappedW = [];
                            for (var j = 0; j < argsW.length; j++) {
                                mappedW.push(truncate(safeString(argsW[j]), 800));
                            }
                            post('console_warn', { args: mappedW });
                        } catch (e2) {
                            // swallow
                        }
                        return origWarn && origWarn.apply ? origWarn.apply(console, arguments) : undefined;
                    };
                } catch (e3) {
                    // swallow
                }
            })();
        </script>
    ''' % (
        json.dumps(BUILD_STAMP),
        json.dumps(BUILD_STAMP),
        json.dumps(BUILD_STAMP),
        json.dumps(BUILD_STAMP),
        json.dumps(BUILD_STAMP),
    ))

    # Client-side polling loop (avoids websocket diff churn which was correlated with UI blanking)
    poll_ms = int(os.getenv('CALAMUM_CLIENT_POLL_MS', '1500'))
    log_poll_ms = int(os.getenv('CALAMUM_CLIENT_LOG_POLL_MS', '1000'))
    ui.add_head_html((
        '''
        <script>
            (function() {
                if (window.__cids_poll_bound) return;
                window.__cids_poll_bound = true;

                var POLL_MS = __CIDS_POLL_MS__;
                var LOG_POLL_MS = __CIDS_LOG_POLL_MS__;
                var logAfter = 0;
                var snapBusy = false;
                var logBusy = false;

                function byId(id) {
                    try { return document.getElementById(id); } catch (e) { return null; }
                }

                function pad2(n) {
                    n = Number(n || 0);
                    return (n < 10 ? '0' : '') + String(n);
                }

                function fmtInt(n) {
                    try {
                        n = Number(n || 0);
                        if (!isFinite(n)) n = 0;
                        var s = String(Math.floor(n));
                        var out = '';
                        while (s.length > 3) {
                            out = ',' + s.slice(-3) + out;
                            s = s.slice(0, -3);
                        }
                        return s + out;
                    } catch (e) {
                        return String(n);
                    }
                }

                function setText(id, text) {
                    var el = byId(id);
                    if (!el) return;
                    el.textContent = String(text);
                }

                function setBadge(id, text, colorName) {
                    var el = byId(id);
                    if (!el) return;
                    el.textContent = String(text);
                    var bg = '#065f46';
                    if (colorName === 'red') bg = '#7f1d1d';
                    else if (colorName === 'orange') bg = '#9a3412';
                    else if (colorName === 'blue') bg = '#1e3a8a';
                    else if (colorName === 'green') bg = '#065f46';
                    try {
                        // Quasar badge classes may override plain inline styles; force with !important.
                        if (el.style && el.style.setProperty) {
                            el.style.setProperty('background-color', bg, 'important');
                            el.style.setProperty('color', '#ffffff', 'important');
                        } else {
                            el.style.backgroundColor = bg;
                            el.style.color = '#ffffff';
                        }
                    } catch (e) {
                        // swallow
                    }
                }

                function safeRect(el) {
                    try {
                        if (!el || !el.getBoundingClientRect) return null;
                        var r = el.getBoundingClientRect();
                        function rr(x) { return Math.round(Number(x || 0) * 100) / 100; }
                        return {
                            left: rr(r.left),
                            top: rr(r.top),
                            width: rr(r.width),
                            height: rr(r.height),
                            right: rr(r.right),
                            bottom: rr(r.bottom)
                        };
                    } catch (e) {
                        return null;
                    }
                }

                function ancestorChain(el, depth) {
                    try {
                        var out = [];
                        var cur = el;
                        var n = Number(depth || 0);
                        if (!isFinite(n) || n < 1) n = 1;
                        if (n > 8) n = 8;
                        for (var i = 0; i < n; i++) {
                            if (!cur) break;
                            out.push({
                                tag: cur.tagName ? String(cur.tagName) : null,
                                id: cur.id ? String(cur.id) : null,
                                cls: cur.className ? String(cur.className).slice(0, 180) : null,
                                rect: safeRect(cur)
                            });
                            try { cur = cur.parentElement; } catch (eP) { cur = null; }
                        }
                        return out;
                    } catch (e) {
                        return null;
                    }
                }

                function postDiag(kind, data) {
                    try {
                        if (window.__cids_post_diag) {
                            window.__cids_post_diag(String(kind), data || {});
                        }
                    } catch (e) {
                        // swallow
                    }
                }

                function postDiagThrottled(kind, key, data, minMs) {
                    try {
                        var now = Date.now();
                        var ms = Number(minMs || 0);
                        if (!isFinite(ms) || ms < 0) ms = 0;
                        if (!window.__cids_diag_throttle) window.__cids_diag_throttle = {};
                        var last = Number(window.__cids_diag_throttle[String(key || kind)] || 0);
                        if (isFinite(last) && ms && (now - last) < ms) return;
                        window.__cids_diag_throttle[String(key || kind)] = now;
                        postDiag(kind, data || {});
                    } catch (e) {
                        // swallow
                    }
                }

                // ECharts wiring (stable under polling; no websocket diffs)
                function getEChart(id) {
                    try {
                        var el = byId(id);
                        if (!el) return null;

                        // NiceGUI does not expose `window.echarts`. However, the bundled module
                        // `nicegui-echart` *does* export `echarts`. Load it once and cache it on
                        // `window` so our polling loop can call `getInstanceByDom` reliably.
                        function ensureEChartsModule() {
                            try {
                                if (window.__cids_echarts_ref && typeof window.__cids_echarts_ref.getInstanceByDom === 'function') return;
                                if (window.__cids_echarts_loading) return;
                                window.__cids_echarts_loading = true;

                                function looksLikeECharts(obj) {
                                    try {
                                        return !!(obj && typeof obj.getInstanceByDom === 'function' && typeof obj.init === 'function');
                                    } catch (e) {
                                        return false;
                                    }
                                }

                                function tryFindEChartsRef() {
                                    try {
                                        // Fast-path common globals
                                        try { if (looksLikeECharts(window.echarts)) return { via: 'window.echarts', ref: window.echarts }; } catch (e0) { }
                                        try { if (looksLikeECharts(window._echarts)) return { via: 'window._echarts', ref: window._echarts }; } catch (e1) { }
                                        try { if (looksLikeECharts(window.__echarts)) return { via: 'window.__echarts', ref: window.__echarts }; } catch (e2) { }

                                        // Scan for any window prop that looks like an ECharts export.
                                        // Keep this bounded; we only do it occasionally.
                                        var names = [];
                                        try { names = Object.getOwnPropertyNames(window); } catch (eN) { names = []; }

                                        // First pass: names containing 'echarts'
                                        for (var i = 0; i < names.length && i < 1200; i++) {
                                            var nm = String(names[i] || '');
                                            if (!nm) continue;
                                            var low = nm.toLowerCase();
                                            if (low.indexOf('echarts') < 0) continue;
                                            var v = null;
                                            try { v = window[nm]; } catch (eV) { v = null; }
                                            if (looksLikeECharts(v)) return { via: 'window.' + nm, ref: v };
                                        }

                                        // Second pass: small bounded scan for objects with getInstanceByDom/init.
                                        // (Some builds expose it under a short, non-obvious global.)
                                        for (var j = 0; j < names.length && j < 260; j++) {
                                            var nm2 = String(names[j] || '');
                                            if (!nm2) continue;
                                            var v2 = null;
                                            try { v2 = window[nm2]; } catch (eV2) { v2 = null; }
                                            if (looksLikeECharts(v2)) return { via: 'window.' + nm2, ref: v2 };
                                        }
                                        return null;
                                    } catch (eAll) {
                                        return null;
                                    }
                                }

                                // Fallback: window-scan (throttled) before attempting module import.
                                try {
                                    var now = Date.now();
                                    var lastScan = Number(window.__cids_echarts_scan_ts || 0);
                                    if (!isFinite(lastScan)) lastScan = 0;
                                    if (!lastScan || (now - lastScan) > 20000) {
                                        window.__cids_echarts_scan_ts = now;
                                        var found = tryFindEChartsRef();
                                        if (found && looksLikeECharts(found.ref)) {
                                            window.__cids_echarts_ref = found.ref;
                                            window.__cids_echarts_loading = false;
                                            try {
                                                postDiag('echarts_ref_found', { via: String(found.via || ''), ok: true });
                                            } catch (eDiag0) {
                                                // swallow
                                            }
                                            return;
                                        }
                                    }
                                } catch (eScan) {
                                    // swallow
                                }

                                // Prove we attempted module wiring (throttled to avoid spam).
                                try {
                                    if (!window.__cids_echarts_attempt_ts) window.__cids_echarts_attempt_ts = 0;
                                    if (!window.__cids_echarts_attempt_ts || (Date.now() - Number(window.__cids_echarts_attempt_ts || 0)) > 15000) {
                                        window.__cids_echarts_attempt_ts = Date.now();
                                        postDiag('echarts_module_attempt', {});
                                    }
                                } catch (eAttempt) {
                                    // swallow
                                }

                                // Safety: clear loading if module resolution hangs.
                                try {
                                    setTimeout(function() {
                                        try {
                                            if (window.__cids_echarts_loading) {
                                                window.__cids_echarts_loading = false;
                                                postDiag('echarts_module_timeout', {});
                                            }
                                        } catch (eTO) {
                                            // swallow
                                        }
                                    }, 4000);
                                } catch (eTO2) {
                                    // swallow
                                }

                                // Dynamic import is supported in modern Edge; keep it promise-based (no await).
                                import('nicegui-echart').then(function(mod) {
                                    try {
                                        window.__cids_echarts_ref = (mod && mod.echarts) ? mod.echarts : null;
                                    } catch (eSet) {
                                        window.__cids_echarts_ref = null;
                                    }
                                    window.__cids_echarts_loading = false;
                                    try {
                                        postDiag('echarts_module', {
                                            ok: !!(window.__cids_echarts_ref && typeof window.__cids_echarts_ref.getInstanceByDom === 'function'),
                                            has_mod: !!mod,
                                            keys: (mod && Object && Object.keys) ? Object.keys(mod).slice(0, 8) : null
                                        });
                                    } catch (eDiag) {
                                        // swallow
                                    }
                                }).catch(function(err) {
                                    window.__cids_echarts_loading = false;
                                    try {
                                        postDiag('echarts_module_fail', { err: String(err || '') });
                                    } catch (eDiag2) {
                                        // swallow
                                    }
                                });
                            } catch (eAll) {
                                try { window.__cids_echarts_loading = false; } catch (eF) { }
                            }
                        }

                        // Trigger module load early; first call may return null, later calls will succeed.
                        try { ensureEChartsModule(); } catch (eImp) { }

                        function diagLookup(reason, extra) {
                            try {
                                var now = Date.now();
                                if (!window.__cids_chart_lookup_ts) window.__cids_chart_lookup_ts = {};
                                var last = Number(window.__cids_chart_lookup_ts[id] || 0);
                                if (isFinite(last) && (now - last) < 5000) return;
                                window.__cids_chart_lookup_ts[id] = now;

                                var markedCount = null;
                                try {
                                    markedCount = 0;
                                    try {
                                        // ECharts marks the root container with `_echarts_instance_`.
                                        if (el && el.getAttribute && el.getAttribute('_echarts_instance_')) {
                                            markedCount += 1;
                                        }
                                    } catch (eM0) {
                                        // swallow
                                    }
                                    try {
                                        markedCount += (el && el.querySelectorAll) ? el.querySelectorAll('[_echarts_instance_]').length : 0;
                                    } catch (eM1) {
                                        // swallow
                                    }
                                } catch (eMC) {
                                    markedCount = null;
                                }

                                var payload = {
                                    id: String(id || ''),
                                    reason: String(reason || ''),
                                    el_exists: !!el,
                                    el_rect: safeRect(el),
                                    marked_count: markedCount
                                };
                                try {
                                    if (extra) {
                                        for (var k in extra) {
                                            if (!extra.hasOwnProperty(k)) continue;
                                            payload[k] = extra[k];
                                        }
                                    }
                                } catch (eX) {
                                    // swallow
                                }
                                postDiag('chart_lookup', payload);
                            } catch (eD) {
                                // swallow
                            }
                        }

                        // Cache chart instances once found.
                        function isLiveInstanceForElement(inst, domEl) {
                            try {
                                if (!inst || typeof inst.setOption !== 'function') return false;
                                var d = null;
                                try { d = (typeof inst.getDom === 'function') ? inst.getDom() : null; } catch (eGD) { d = null; }
                                if (!d) return false;
                                try {
                                    if (d.isConnected === false) return false;
                                } catch (eConn) {
                                    // swallow
                                }
                                if (!domEl) return true;
                                try {
                                    if (d === domEl) return true;
                                    if (domEl.contains && domEl.contains(d)) return true;
                                    if (d.contains && d.contains(domEl)) return true;
                                } catch (eRel) {
                                    // swallow
                                }
                                return false;
                            } catch (eAll) {
                                return false;
                            }
                        }

                        try {
                            if (!window.__cids_chart_inst_cache) window.__cids_chart_inst_cache = {};
                            var cached = window.__cids_chart_inst_cache[id];
                            if (cached && isLiveInstanceForElement(cached, el)) return cached;
                            if (cached && !isLiveInstanceForElement(cached, el)) {
                                try {
                                    delete window.__cids_chart_inst_cache[id];
                                } catch (eDel) {
                                    window.__cids_chart_inst_cache[id] = null;
                                }
                                try {
                                    diagLookup('cache_stale', {
                                        has_window_echarts: !!(window && (window.echarts || window.__cids_echarts_ref)),
                                        cache_key: String(id || '')
                                    });
                                } catch (eDiagCache) {
                                    // swallow
                                }
                            }
                        } catch (eCache) {
                            // swallow
                        }

                        function looksLikeChart(inst) {
                            try {
                                return !!(inst && typeof inst.setOption === 'function' && typeof inst.resize === 'function');
                            } catch (e) {
                                return false;
                            }
                        }

                        function tryCache(inst) {
                            try {
                                if (!looksLikeChart(inst)) return null;
                                if (!isLiveInstanceForElement(inst, el)) return null;
                                if (!window.__cids_chart_inst_cache) window.__cids_chart_inst_cache = {};
                                window.__cids_chart_inst_cache[id] = inst;
                                return inst;
                            } catch (e) {
                                return null;
                            }
                        }

                        // Vue component locator:
                        // NiceGUI bundles ECharts inside the `nicegui-echart` Vue component module.
                        // The ECharts instance is stored as `this.chart` on the component proxy.
                        // Vue attaches component internals to DOM nodes via non-enumerable properties,
                        // so we must use Object.getOwnPropertyNames/Symbols (not for..in).
                        function findVueComponent(dom) {
                            try {
                                if (!dom) return null;
                                try {
                                    if (dom.__vueParentComponent) return dom.__vueParentComponent;
                                    if (dom.__vue_app__) return dom.__vue_app__._instance; 
                                } catch (e0) {
                                    // swallow
                                }

                                function looksLikeVueComp(x) {
                                    try {
                                        if (!x || (typeof x !== 'object' && typeof x !== 'function')) return false;
                                        // Vue component instance commonly has `proxy`.
                                        if (x.proxy) return true;
                                        // Some builds attach a vnode which then links to component.
                                        if (x.component) return true;
                                        return false;
                                    } catch (e) {
                                        return false;
                                    }
                                }

                                function probeValue(v) {
                                    try {
                                        if (!v) return null;
                                        // Direct component instance
                                        if (looksLikeVueComp(v)) return v;
                                        // VNode-ish wrappers
                                        if (v.component && looksLikeVueComp(v.component)) return v.component;
                                        if (v.ctx && v.ctx._ && looksLikeVueComp(v.ctx._)) return v.ctx._;
                                        return null;
                                    } catch (e) {
                                        return null;
                                    }
                                }

                                var names = [];
                                try { names = Object.getOwnPropertyNames(dom); } catch (eN) { names = []; }
                                for (var i = 0; i < names.length && i < 80; i++) {
                                    var nm = names[i];
                                    // Only probe likely internal keys to avoid touching huge objects.
                                    if (nm && (String(nm).indexOf('vue') >= 0 || String(nm).indexOf('__v') === 0)) {
                                        var v = null;
                                        try { v = dom[nm]; } catch (eV) { v = null; }
                                        var comp = probeValue(v);
                                        if (comp) return comp;
                                    }
                                }

                                var syms = [];
                                try { syms = Object.getOwnPropertySymbols(dom); } catch (eS) { syms = []; }
                                for (var j = 0; j < syms.length && j < 40; j++) {
                                    var sym = syms[j];
                                    var sv = null;
                                    try { sv = dom[sym]; } catch (eSV) { sv = null; }
                                    var comp2 = probeValue(sv);
                                    if (comp2) return comp2;
                                }
                                
                                return null;
                            } catch (eAll) {
                                return null;
                            }
                        }

                        // Strategy A: if the ECharts library is globally exposed, use it.
                        var ec = null;
                        try {
                            ec = (window && window.echarts && typeof window.echarts.getInstanceByDom === 'function') ? window.echarts : null;
                            if (!ec && window && window.__cids_echarts_ref && typeof window.__cids_echarts_ref.getInstanceByDom === 'function') {
                                ec = window.__cids_echarts_ref;
                            }
                            if (!ec) {
                                // If we don't have the module yet, trigger a reload attempt.
                                try { ensureEChartsModule(); } catch (eEns) { }
                            }
                        } catch (eEc) {
                            ec = null;
                        }

                        function tryGetByDom(dom) {
                            try {
                                if (!ec || !dom) return null;
                                return ec.getInstanceByDom(dom);
                            } catch (eTG) {
                                return null;
                            }
                        }

                        if (ec) {
                            var instA = tryCache(tryGetByDom(el));
                            if (instA) return instA;
                            try {
                                var marked = el.querySelectorAll ? el.querySelectorAll('[_echarts_instance_]') : null;
                                if (marked && marked.length) {
                                    for (var m = 0; m < marked.length && m < 8; m++) {
                                        instA = tryCache(tryGetByDom(marked[m]));
                                        if (instA) return instA;
                                    }
                                }
                            } catch (eMarked) {
                                // swallow
                            }
                            try {
                                var nodesA = el.querySelectorAll ? el.querySelectorAll('*') : null;
                                if (nodesA && nodesA.length) {
                                    for (var nA = 0; nA < nodesA.length && nA < 40; nA++) {
                                        instA = tryCache(tryGetByDom(nodesA[nA]));
                                        if (instA) return instA;
                                    }
                                }
                            } catch (eScan) {
                                // swallow
                            }
                        }

                        // Strategy B: locate instance via Vue component internals.
                        function tryFromVue(dom) {
                            try {
                                if (!dom) return null;
                                var comp = findVueComponent(dom);
                                if (!comp) return null;

                                var cands = [];
                                try { if (comp.exposed) cands.push(comp.exposed); } catch (e1) { }
                                try { if (comp.ctx) cands.push(comp.ctx); } catch (e2) { }
                                try { if (comp.setupState) cands.push(comp.setupState); } catch (e3) { }
                                try { if (comp.proxy) cands.push(comp.proxy); } catch (e4) { }

                                for (var i = 0; i < cands.length; i++) {
                                    var c = cands[i];
                                    if (!c) continue;
                                    var names = ['chart', 'echart', 'instance', 'inst', 'myChart', 'ec', 'ecInstance'];
                                    for (var j = 0; j < names.length; j++) {
                                        var nm = names[j];
                                        var v = null;
                                        try { v = c[nm]; } catch (eV) { v = null; }
                                        if (looksLikeChart(v)) return v;
                                    }
                                }
                                return null;
                            } catch (e) {
                                return null;
                            }
                        }

                        var inst = null;
                        inst = tryCache(tryFromVue(el));
                        if (inst) return inst;

                        try {
                            var marked0 = el.querySelector ? el.querySelector('[_echarts_instance_]') : null;
                            inst = tryCache(tryFromVue(marked0));
                            if (inst) return inst;
                        } catch (eM0) {
                            // swallow
                        }

                        try {
                            var nodes = el.querySelectorAll ? el.querySelectorAll('*') : null;
                            if (nodes && nodes.length) {
                                for (var n = 0; n < nodes.length && n < 40; n++) {
                                    inst = tryCache(tryFromVue(nodes[n]));
                                    if (inst) return inst;
                                }
                            }
                        } catch (eN) {
                            // swallow
                        }

                        try {
                            var cur = el;
                            for (var up = 0; up < 8; up++) {
                                if (!cur) break;
                                inst = tryCache(tryFromVue(cur));
                                if (inst) return inst;
                                cur = cur.parentElement || null;
                            }
                        } catch (eUp) {
                            // swallow
                        }

                        // Strategy C: scan DOM node properties for an ECharts-like instance.
                        // NiceGUI can bundle ECharts without exposing `window.echarts`.
                        function tryFromDomProps(dom) {
                            try {
                                if (!dom) return null;
                                var names = [
                                    '__echarts__', '__echarts', '_echarts', 'echarts',
                                    '__chart', '_chart', 'chart',
                                    '__ec', '_ec', 'ec',
                                    '__instance', 'instance', 'inst',
                                    'myChart', 'ecInstance'
                                ];
                                for (var i = 0; i < names.length; i++) {
                                    var nm = names[i];
                                    var v = null;
                                    try { v = dom[nm]; } catch (eV) { v = null; }
                                    if (looksLikeChart(v)) return v;
                                }

                                // Non-enumerable internal props (best-effort):
                                // scan a small subset of own properties looking for chart-like values.
                                try {
                                    var props = Object.getOwnPropertyNames(dom);
                                    for (var p = 0; p < props.length && p < 60; p++) {
                                        var pn = props[p];
                                        if (!pn) continue;
                                        // reduce noise: only inspect keys that look relevant
                                        var ps = String(pn);
                                        if (ps.indexOf('chart') < 0 && ps.indexOf('echarts') < 0 && ps.indexOf('ec') !== 0) continue;
                                        var pv = null;
                                        try { pv = dom[pn]; } catch (ePV) { pv = null; }
                                        if (looksLikeChart(pv)) return pv;
                                    }
                                } catch (eOwn) {
                                    // swallow
                                }
                                return null;
                            } catch (e) {
                                return null;
                            }
                        }

                        inst = tryCache(tryFromDomProps(el));
                        if (inst) return inst;

                        try {
                            var nodesP = el.querySelectorAll ? el.querySelectorAll('*') : null;
                            if (nodesP && nodesP.length) {
                                for (var p = 0; p < nodesP.length && p < 60; p++) {
                                    inst = tryCache(tryFromDomProps(nodesP[p]));
                                    if (inst) return inst;
                                }
                            }
                        } catch (eScanP) {
                            // swallow
                        }

                        diagLookup('no_instance', {
                            has_window_echarts: !!ec,
                            vue_parent: !!(el && el.__vueParentComponent),
                            vue_component_found: !!findVueComponent(el)
                        });
                        return null;
                    } catch (e) {
                        return null;
                    }
                }

                function setRadarEChart(a, i, c, f) {
                    try {
                        var inst = ensureChartInstance('cids-integrity-radar-chart');
                        if (!inst) return;
                        try { inst.resize && inst.resize(); } catch (eR) { }
                        try {
                            inst.setOption({
                                backgroundColor: 'transparent',
                                tooltip: { show: true, trigger: 'item' },
                                radar: {
                                    shape: 'polygon',
                                    radius: '72%',
                                    splitNumber: 4,
                                    indicator: [
                                        { name: 'AVAILABILITY', max: 100 },
                                        { name: 'INTEGRITY', max: 100 },
                                        { name: 'CAPACITY', max: 100 },
                                        { name: 'FRESHNESS', max: 100 }
                                    ],
                                    axisName: { color: '#d4d4d8', fontFamily: 'monospace', fontSize: 12 },
                                    splitLine: { lineStyle: { color: ['#3f3f46'] } },
                                    splitArea: { areaStyle: { color: ['rgba(0,0,0,0)'] } },
                                    axisLine: { lineStyle: { color: '#52525b' } }
                                },
                                series: [{
                                    type: 'radar',
                                    symbol: 'none',
                                    lineStyle: { color: '#ffffff', width: 2 },
                                    areaStyle: { color: 'rgba(255,255,255,0.08)' },
                                    data: [{ value: [Number(a||0), Number(i||0), Number(c||0), Number(f||0)] }]
                                }]
                            }, { notMerge: false, lazyUpdate: true });
                            postDiagThrottled('chart_set_ok', 'chart_ok_radar', { id: 'cids-integrity-radar-chart' }, 30000);
                        } catch (eSet) {
                            postDiagThrottled('chart_set_fail', 'chart_fail_radar', { id: 'cids-integrity-radar-chart', err: String(eSet || '') }, 5000);
                        }
                    } catch (e) {
                        // swallow
                    }
                }

                function setBiorhythmEChart(cpuHist, memHist) {
                    try {
                        var inst = ensureChartInstance('cids-resource-chart');
                        if (!inst) return;
                        try { inst.resize && inst.resize(); } catch (eR) { }
                        var n = (cpuHist && cpuHist.length) ? cpuHist.length : 0;
                        var x = [];
                        for (var k = 0; k < n; k++) x.push(k);
                        try {
                            inst.setOption({
                                backgroundColor: 'transparent',
                                animation: false,
                                tooltip: { show: true, trigger: 'axis', axisPointer: { type: 'line' } },
                                grid: { left: 8, right: 8, top: 16, bottom: 8, containLabel: false },
                                xAxis: {
                                    type: 'category',
                                    data: x,
                                    boundaryGap: false,
                                    axisLabel: { show: false },
                                    axisTick: { show: false },
                                    axisLine: { show: false },
                                    splitLine: { show: false }
                                },
                                yAxis: {
                                    type: 'value',
                                    min: 0,
                                    max: 100,
                                    axisLabel: { show: false },
                                    axisTick: { show: false },
                                    axisLine: { show: false },
                                    splitLine: { show: true, lineStyle: { color: '#27272a' } }
                                },
                                series: [
                                    { name: 'CPU', type: 'line', data: cpuHist || [], showSymbol: false, lineStyle: { color: '#ffffff', width: 2 } },
                                    { name: 'MEM', type: 'line', data: memHist || [], showSymbol: false, lineStyle: { color: '#a1a1aa', width: 2, type: 'dotted' } }
                                ]
                            }, { notMerge: false, lazyUpdate: true });
                            postDiagThrottled('chart_set_ok', 'chart_ok_resource', { id: 'cids-resource-chart', n: n }, 30000);
                        } catch (eSet) {
                            postDiagThrottled('chart_set_fail', 'chart_fail_resource', { id: 'cids-resource-chart', err: String(eSet || '') }, 5000);
                        }
                    } catch (e) {
                        // swallow
                    }
                }

                function mean3(arr) {
                    try {
                        if (!arr || !arr.length) return [0,0,0];
                        var n = arr.length;
                        var g = Math.floor(n / 3);
                        if (g < 1) g = 1;
                        var out = [0,0,0];
                        var cnt = [0,0,0];
                        for (var i = 0; i < n; i++) {
                            var gi = Math.min(2, Math.floor(i / g));
                            var v = Number(arr[i] || 0);
                            if (!isFinite(v)) v = 0;
                            out[gi] += v;
                            cnt[gi] += 1;
                        }
                        for (var j = 0; j < 3; j++) {
                            out[j] = cnt[j] ? (out[j] / cnt[j]) : 0;
                        }
                        return out;
                    } catch (e) {
                        return [0,0,0];
                    }
                }

                function sum3(arr) {
                    try {
                        if (!arr || !arr.length) return [0,0,0];
                        var n = arr.length;
                        var g = Math.floor(n / 3);
                        if (g < 1) g = 1;
                        var out = [0,0,0];
                        for (var i = 0; i < n; i++) {
                            var gi = Math.min(2, Math.floor(i / g));
                            var v = Number(arr[i] || 0);
                            if (!isFinite(v)) v = 0;
                            out[gi] += v;
                        }
                        return out;
                    } catch (e) {
                        return [0,0,0];
                    }
                }

                function setDensityEChart(bins, raw, sliceSec) {
                    try {
                        var inst = ensureChartInstance('cids-density-chart');
                        if (!inst) return;
                        try { inst.resize && inst.resize(); } catch (eR) { }
                        var ss = Number(sliceSec || 2);
                        if (!isFinite(ss) || ss <= 0) ss = 2;

                        // Density is inherently spiky; update this chart at ~slice cadence so it reads cleanly.
                        try {
                            var now = Date.now();
                            if (!window.__cids_density_last_set) window.__cids_density_last_set = 0;
                            var minMs = Math.max(1200, Math.round(ss * 1000));
                            if ((now - Number(window.__cids_density_last_set || 0)) < minMs) return;
                            window.__cids_density_last_set = now;
                        } catch (eT) {
                            // swallow
                        }

                        var b = (bins && bins.length) ? bins : [];
                        var r = (raw && raw.length) ? raw : [];
                        var n = b.length;
                        if (r.length && r.length < n) n = r.length;
                        if (!n || n < 1) n = b.length || r.length || 0;

                        var cats = [];
                        var data = [];
                        for (var k = 0; k < n; k++) {
                            var bi = Number(b[k] || 0);
                            var ri = Number(r[k] || 0);
                            if (!isFinite(bi)) bi = 0;
                            if (!isFinite(ri)) ri = 0;
                            bi = Math.max(0, Math.min(100, bi));
                            cats.push(String(Math.round(ri)) + ' rec / ' + String(Math.round(ss)) + 's');
                            data.push(Math.round(bi));
                        }

                        try {
                            inst.setOption({
                                backgroundColor: 'transparent',
                                xAxis: { type: 'category', data: cats, axisLabel: { show: false }, axisTick: { show: false }, axisLine: { show: false } },
                                yAxis: { type: 'value', min: 0, max: 100, axisLabel: { show: false }, axisTick: { show: false }, axisLine: { show: false }, splitLine: { show: false } },
                                series: [{
                                    type: 'bar',
                                    data: data,
                                    barWidth: '70%',
                                    barMinHeight: 2,
                                    itemStyle: { color: '#d4d4d8', opacity: 0.75, borderColor: '#ffffff', borderWidth: 0 }
                                }]
                            }, { notMerge: false, lazyUpdate: true });
                            postDiagThrottled('chart_set_ok', 'chart_ok_density', { id: 'cids-density-chart', n: n }, 30000);
                        } catch (eSet) {
                            postDiagThrottled('chart_set_fail', 'chart_fail_density', { id: 'cids-density-chart', err: String(eSet || '') }, 5000);
                        }
                    } catch (e) {
                        // swallow
                    }
                }

                // --- Density bin-width (sec) control (local, persistent; OFF is chart-only) ---
                var __CIDS_DENSITY_BIN_WIDTH_KEY = '__cids_density_bin_width_sec';
                var __CIDS_DENSITY_BIN_WIDTH_CHOICES = [1, 2, 5, 10, 20, 'off'];
                var __CIDS_DENSITY_BIN_WIDTH_DEFAULT = 10;

                function normalizeBinWidthSetting(v) {
                    try {
                        if (v === null || v === undefined) return __CIDS_DENSITY_BIN_WIDTH_DEFAULT;
                        if (typeof v === 'number') {
                            if (!isFinite(v)) return __CIDS_DENSITY_BIN_WIDTH_DEFAULT;
                            v = Math.round(v);
                            for (var i = 0; i < __CIDS_DENSITY_BIN_WIDTH_CHOICES.length; i++) {
                                if (__CIDS_DENSITY_BIN_WIDTH_CHOICES[i] === v) return v;
                            }
                            return __CIDS_DENSITY_BIN_WIDTH_DEFAULT;
                        }
                        var s = String(v).trim().toLowerCase();
                        if (s === 'off' || s === '0' || s === 'false') return 'off';
                        var n = parseInt(s, 10);
                        if (!isFinite(n)) return __CIDS_DENSITY_BIN_WIDTH_DEFAULT;
                        for (var j = 0; j < __CIDS_DENSITY_BIN_WIDTH_CHOICES.length; j++) {
                            if (__CIDS_DENSITY_BIN_WIDTH_CHOICES[j] === n) return n;
                        }
                        return __CIDS_DENSITY_BIN_WIDTH_DEFAULT;
                    } catch (e) {
                        return __CIDS_DENSITY_BIN_WIDTH_DEFAULT;
                    }
                }

                function readBinWidthSetting() {
                    try {
                        var raw = null;
                        try { raw = localStorage.getItem(__CIDS_DENSITY_BIN_WIDTH_KEY); } catch (eLS) { raw = null; }
                        return normalizeBinWidthSetting(raw);
                    } catch (e) {
                        return __CIDS_DENSITY_BIN_WIDTH_DEFAULT;
                    }
                }

                function writeBinWidthSetting(v) {
                    try {
                        var nv = normalizeBinWidthSetting(v);
                        try { localStorage.setItem(__CIDS_DENSITY_BIN_WIDTH_KEY, String(nv)); } catch (eLS) { }
                        try { window.__cids_density_bin_width = nv; } catch (eW) { }
                        return nv;
                    } catch (e) {
                        return __CIDS_DENSITY_BIN_WIDTH_DEFAULT;
                    }
                }

                function renderBinWidthSetting(v) {
                    try {
                        var nv = normalizeBinWidthSetting(v);
                        var elVal = byId('cids-binwidth-value');
                        var elSuf = byId('cids-binwidth-suffix');
                        if (elVal) {
                            if (String(nv) === 'off') {
                                elVal.textContent = 'OFF';
                                try { elVal.classList.add('off'); } catch (eC0) { }
                                if (elSuf) elSuf.style.opacity = '0.35';
                            } else {
                                elVal.textContent = String(nv);
                                try { elVal.classList.remove('off'); } catch (eC1) { }
                                if (elSuf) elSuf.style.opacity = '1';
                            }
                        }
                        try { window.__cids_density_bin_width = nv; } catch (eW) { }
                    } catch (e) {
                        // swallow
                    }
                }

                function stepBinWidthSetting(dir) {
                    try {
                        var cur = readBinWidthSetting();
                        var idx = 0;
                        for (var i = 0; i < __CIDS_DENSITY_BIN_WIDTH_CHOICES.length; i++) {
                            if (__CIDS_DENSITY_BIN_WIDTH_CHOICES[i] === cur) { idx = i; break; }
                        }
                        var next = idx + (dir >= 0 ? 1 : -1);
                        if (next < 0) next = __CIDS_DENSITY_BIN_WIDTH_CHOICES.length - 1;
                        if (next >= __CIDS_DENSITY_BIN_WIDTH_CHOICES.length) next = 0;
                        var nv = __CIDS_DENSITY_BIN_WIDTH_CHOICES[next];
                        nv = writeBinWidthSetting(nv);
                        renderBinWidthSetting(nv);
                    } catch (e) {
                        // swallow
                    }
                }

                function bindBinWidthControl() {
                    try {
                        if (window.__cids_binwidth_bound) return;
                        window.__cids_binwidth_bound = true;
                        var up = byId('cids-binwidth-up');
                        var dn = byId('cids-binwidth-down');
                        if (up) up.addEventListener('click', function() { stepBinWidthSetting(+1); });
                        if (dn) dn.addEventListener('click', function() { stepBinWidthSetting(-1); });

                        // Initialize from storage.
                        var v = readBinWidthSetting();
                        writeBinWidthSetting(v);
                        renderBinWidthSetting(v);
                    } catch (e) {
                        // swallow
                    }
                }

                function aggregateDensityFromBase(rawBase, binWidthSec) {
                    try {
                        var w = Number(binWidthSec || 0);
                        if (!isFinite(w) || w <= 0) w = __CIDS_DENSITY_BIN_WIDTH_DEFAULT;
                        w = Math.round(w);

                        var base = (rawBase && rawBase.length) ? rawBase : [];
                        var m = base.length;
                        if (!m) return { raw: [], bins: [] };

                        // Make window divisible by width by trimming the oldest remainder.
                        var rem = m % w;
                        var start = rem > 0 ? rem : 0;
                        var usable = m - start;
                        if (usable <= 0) return { raw: [], bins: [] };
                        var nBins = Math.floor(usable / w);
                        if (nBins < 1) return { raw: [], bins: [] };

                        var outRaw = [];
                        for (var i = 0; i < nBins; i++) {
                            var sum = 0;
                            for (var j = 0; j < w; j++) {
                                var idx = start + (i * w) + j;
                                var v = Number(base[idx] || 0);
                                if (!isFinite(v)) v = 0;
                                sum += v;
                            }
                            outRaw.push(Math.round(sum));
                        }

                        var denom = 1;
                        for (var k = 0; k < outRaw.length; k++) {
                            if (outRaw[k] > denom) denom = outRaw[k];
                        }
                        if (denom < 1) denom = 1;
                        var outBins = [];
                        for (var t = 0; t < outRaw.length; t++) {
                            outBins.push(Math.max(0, Math.min(100, Math.round((outRaw[t] / denom) * 100))));
                        }
                        return { raw: outRaw, bins: outBins };
                    } catch (e) {
                        return { raw: [], bins: [] };
                    }
                }

                function resizeChartsKicker() {
                    try {
                        var ids = ['cids-integrity-radar-chart', 'cids-resource-chart', 'cids-density-chart'];
                        for (var i = 0; i < ids.length; i++) {
                            var inst = ensureChartInstance(ids[i]);
                            if (!inst) continue;
                            try { inst.resize && inst.resize(); } catch (eR) { }
                        }
                    } catch (e) {
                        // swallow
                    }
                }

                function ensureChartInstance(id) {
                    try {
                        var inst = getEChart(id);
                        if (inst) return inst;
                        var el = byId(id);
                        if (!el) return null;

                        // Fallback re-init path for stale browser state where the ECharts
                        // instance reference is lost but the DOM node still exists.
                        var ec = null;
                        try {
                            ec = (window && window.echarts) ? window.echarts : null;
                            if (!ec && window && window.__cids_echarts_ref) {
                                ec = window.__cids_echarts_ref;
                            }
                        } catch (eEc) {
                            ec = null;
                        }
                        if (!ec || typeof ec.init !== 'function') return null;

                        try {
                            var existing = (typeof ec.getInstanceByDom === 'function') ? ec.getInstanceByDom(el) : null;
                            if (existing) return existing;
                        } catch (eG) {
                            // swallow
                        }

                        // Dispose any orphan instance bound to this dom (best effort).
                        try {
                            if (typeof ec.dispose === 'function') ec.dispose(el);
                        } catch (eD) {
                            // swallow
                        }

                        var created = null;
                        try {
                            created = ec.init(el, null, { renderer: 'canvas' });
                        } catch (eI) {
                            created = null;
                        }
                        if (created) {
                            postDiagThrottled('chart_reinit_ok', 'chart_reinit_' + String(id), { id: String(id) }, 10000);
                            return created;
                        }
                        return null;
                    } catch (e) {
                        return null;
                    }
                }

                // Expose for other head-injected scripts (layout enforcement / scaling) to call.
                try { window.__cids_resize_charts = resizeChartsKicker; } catch (eExpose) { }

                function appendLogLine(line) {
                    try {
                        var el = byId('cids-log-scroll');
                        if (!el) return;
                        var node = document.createElement('div');
                        
                        // Zebra striping (infer from previous sibling to maintain alternated look)
                        var isOdd = true;
                        if (el.firstChild && el.firstChild.classList) {
                            if (el.firstChild.classList.contains('cids-log-zebra-odd')) isOdd = false;
                        }
                        
                        node.className = 'w-full cids-log-flash ' + (isOdd ? 'cids-log-zebra-odd' : 'cids-log-zebra-even');
                        if (String(line).indexOf('[ALERT]') >= 0) node.className += ' text-red-300';
                        else if (String(line).indexOf('[WARN]') >= 0 || String(line).indexOf('[WRN]') >= 0) node.className += ' text-orange-200';
                        else if (String(line).indexOf('Ingested +') >= 0 || String(line).indexOf('[INGEST]') >= 0) node.className += ' text-emerald-200';
                        else node.className += ' text-gray-400';
                        node.textContent = String(line);
                        if (el.firstChild) el.insertBefore(node, el.firstChild);
                        else el.appendChild(node);
                        while (el.childNodes && el.childNodes.length > 220) {
                            el.removeChild(el.lastChild);
                        }
                        if (el.dataset && el.dataset.follow === '1') {
                            el.scrollTop = 0;
                        }
                    } catch (e) {
                        // swallow
                    }
                }

                function bindLogFollow() {
                    try {
                        var el = byId('cids-log-scroll');
                        if (!el) return;
                        if (el.__cids_follow_bound) return;
                        el.__cids_follow_bound = true;

                        // Follow means "stick to the top" since we prepend new lines.
                        try {
                            if (!el.dataset) el.dataset = {};
                            if (!el.dataset.follow) el.dataset.follow = '1';
                        } catch (eD) {
                            // swallow
                        }

                        el.addEventListener('scroll', function() {
                            try {
                                var st = Number(el.scrollTop || 0);
                                var follow = (isFinite(st) && st <= 4) ? '1' : '0';
                                if (el.dataset) el.dataset.follow = follow;
                            } catch (eS) {
                                // swallow
                            }
                        });
                    } catch (e) {
                        // swallow
                    }
                }

                function reportChartMount(tag) {
                    try {
                        var key = String(tag || 't');
                        if (!window.__cids_chart_mount_seen) window.__cids_chart_mount_seen = {};
                        if (window.__cids_chart_mount_seen[key]) return;
                        window.__cids_chart_mount_seen[key] = 1;

                        var ids = ['cids-integrity-radar-chart', 'cids-resource-chart', 'cids-density-chart'];
                        var out = [];
                        for (var i = 0; i < ids.length; i++) {
                            var id = ids[i];
                            var el = byId(id);
                            var inst = null;
                            try { inst = getEChart(id); } catch (eI) { inst = null; }
                            out.push({
                                id: id,
                                el: !!el,
                                rect: safeRect(el),
                                has_instance: !!(inst && typeof inst.setOption === 'function'),
                                has_resize: !!(inst && typeof inst.resize === 'function'),
                                vue_parent: !!(el && el.__vueParentComponent)
                            });
                        }
                        postDiag('chart_mount', {
                            tag: key,
                            has_window_echarts: !!(window && window.echarts),
                            charts: out
                        });
                    } catch (e) {
                        // swallow
                    }
                }

                async function pollSnapshot() {
                    if (snapBusy) return;
                    snapBusy = true;
                    try {
                        var res = await fetch('/_ghost_console/snapshot', { cache: 'no-store' });
                        if (!res || !res.ok) return;
                        var snap = await res.json();
                        if (!snap) return;

                        // Mark server responsiveness for the heartbeat probe.
                        try { window.__cids_server_tick = Date.now(); } catch (eTick) { }

                        // Detect backend restarts (server boot id changes) and log them.
                        try {
                            var nextBoot = snap.server_boot_id ? String(snap.server_boot_id) : null;
                            if (!window.__cids_server_boot_id) {
                                window.__cids_server_boot_id = nextBoot;
                            } else if (nextBoot && String(window.__cids_server_boot_id) !== nextBoot) {
                                if (window.__cids_post_diag) {
                                    window.__cids_post_diag('server_boot_changed', {
                                        prev: String(window.__cids_server_boot_id),
                                        next: nextBoot
                                    });
                                }
                                window.__cids_server_boot_id = nextBoot;
                            }
                        } catch (eSB) {
                            // swallow
                        }

                        setText('cids-records', fmtInt(snap.display_main_records || snap.records_total_display || snap.total_records || 0));
                        
                        // Detail pill (Removed from DOM, but logic might remain in old cached JS? No.)
                        // Tooltip update
                        try {
                            var rb = snap.records_breakdown_display || snap.records_breakdown || {};
                            var sRec = rb.session || 0;
                            var aRec = rb.archive || 0;
                            var elRecs = byId('cids-records');
                            if (elRecs) {
                                // Use fmtInt safely
                                var sStr = (typeof fmtInt === 'function') ? fmtInt(sRec) : String(sRec);
                                var aStr = (typeof fmtInt === 'function') ? fmtInt(aRec) : String(aRec);
                                elRecs.title = 'sess: ' + sStr + ' \\narch: ' + aStr;
                            }
                        } catch (eTip) {
                            // swallow
                        }

                        setText('cids-mode', 'MODE: [ ' + String(snap.mode || 'CANARY') + ' ] SRC: [ ' + String((snap.source || 'sim')).toUpperCase() + ' ]');
                        setText('cids-route-indicator', 'ROUTE: ' + String((snap.source || 'sim')).toUpperCase() + ':' + String(snap.mode || 'CANARY'));

                        // badges
                        var wd = !!snap.watchdog_active;
                        var obs = !!snap.observer_active;
                        var lib = !!snap.librarian_active;
                        setBadge('cids-wd-badge', wd ? 'WD: ACTIVE' : 'WD: STALE', wd ? 'green' : 'orange');
                        setBadge('cids-obs-badge', obs ? 'OBS: ACTIVE' : 'OBS: DOWN', obs ? 'green' : 'red');
                        setBadge('cids-lib-badge', lib ? 'LIB: ACTIVE' : 'LIB: DOWN', lib ? 'green' : 'gray');
                        if (snap.status && snap.status.text) {
                            setBadge('cids-status-badge', String(snap.status.text), String(snap.status.color || 'green'));
                        }
                        setBadge('cids-wd-state', wd ? 'ACTIVE' : 'STALE', wd ? 'green' : 'orange');

                        // watchdog reset time
                        try {
                            var d = snap.watchdog_last_reset ? new Date(String(snap.watchdog_last_reset)) : null;
                            if (d && isFinite(d.getTime())) {
                                setText('cids-wd-lastreset', 'Last reset: ' + pad2(d.getHours()) + ':' + pad2(d.getMinutes()) + ':' + pad2(d.getSeconds()));
                            }
                        } catch (e0) {
                            // swallow
                        }

                        // scores (drive the radar)
                        var s = snap.scores || {};
                        var a = Number(s.availability || 0);
                        var i = Number(s.integrity || 0);
                        var c = Number(s.capacity || 0);
                        var f = Number(s.freshness || 0);
                        setRadarEChart(a, i, c, f);

                        // charts
                        setBiorhythmEChart(snap.cpu_history || [], snap.mem_history || []);
                        try {
                            // Local-only chart control:
                            // - OFF freezes the density chart only (backend sampling continues)
                            // - Otherwise we rebin the backend 1s base window into the selected bin width.
                            if (!window.__cids_binwidth_bound) {
                                bindBinWidthControl();
                            }
                            var bw = (window.__cids_density_bin_width !== undefined && window.__cids_density_bin_width !== null)
                                ? window.__cids_density_bin_width
                                : readBinWidthSetting();

                            if (String(bw) !== 'off') {
                                var bws = Number(bw || __CIDS_DENSITY_BIN_WIDTH_DEFAULT);
                                var agg = aggregateDensityFromBase(snap.density_raw_window || [], bws);
                                setDensityEChart(agg.bins || [], agg.raw || [], bws);
                            }
                        } catch (eDen) {
                            // swallow
                        }
                    } catch (e) {
                        // swallow
                    } finally {
                        snapBusy = false;
                    }
                }

                async function pollLog() {
                    if (logBusy) return;
                    logBusy = true;
                    try {
                        bindLogFollow();
                        var res = await fetch('/_ghost_console/log_tail?after=' + String(logAfter) + '&limit=120', { cache: 'no-store' });
                        if (!res || !res.ok) return;
                        var payload = await res.json();
                        if (!payload) return;
                        var lines = payload.lines || [];
                        for (var i = 0; i < lines.length; i++) {
                            var item = lines[i] || null;
                            if (!item) continue;
                            var seq = Number(item.seq || 0);
                            if (seq > logAfter) logAfter = seq;
                            (function() {
                                try {
                                    var line = item.line || '';
                                    var el = byId('cids-log-scroll');
                                    if (!el) { appendLogLine(line); return; }
                                    var node = document.createElement('div');
                                    node.className = 'w-full cids-log-flash ' + ((seq % 2) ? 'cids-log-zebra-odd' : 'cids-log-zebra-even');
                                    if (line.indexOf('[ALERT]') >= 0) node.className += ' text-red-300';
                                    else if (line.indexOf('[WARN]') >= 0 || line.indexOf('[WRN]') >= 0) node.className += ' text-orange-200';
                                    else if (line.indexOf('Ingested +') >= 0 || line.indexOf('[INGEST]') >= 0) node.className += ' text-emerald-200';
                                    else node.className += ' text-gray-400';
                                    node.textContent = String(line);
                                    if (el.firstChild) el.insertBefore(node, el.firstChild);
                                    else el.appendChild(node);
                                    while (el.childNodes && el.childNodes.length > 220) {
                                        el.removeChild(el.lastChild);
                                    }
                                    if (el.dataset.follow === '1') {
                                        el.scrollTop = 0;
                                    }
                                } catch (eX) {
                                    appendLogLine(item.line || '');
                                }
                            })();
                        }
                    } catch (e) {
                        // swallow
                    } finally {
                        logBusy = false;
                    }
                }

                function tickClock() {
                    try {
                        var d = new Date();
                        setText('cids-clock', pad2(d.getHours()) + ':' + pad2(d.getMinutes()) + ':' + pad2(d.getSeconds()));
                    } catch (e) {
                        // swallow
                    }
                }

                // Start
                if (POLL_MS < 250) POLL_MS = 250;
                if (LOG_POLL_MS < 250) LOG_POLL_MS = 250;
                postDiagThrottled('poll_started', 'poll_started', { poll_ms: POLL_MS, log_poll_ms: LOG_POLL_MS }, 60000);
                tickClock();
                bindBinWidthControl();
                bindLogFollow();
                pollSnapshot();
                pollLog();
                // After initial mount/layout settles, kick chart resizes and record placement.
                setTimeout(function() { resizeChartsKicker(); reportChartMount('t+650'); }, 650);
                setTimeout(function() { resizeChartsKicker(); reportChartMount('t+1400'); }, 1400);
                // Visibility/focus recovery for blank-chart edge cases after tab sleep,
                // browser cache restore, or embedded-browser wake-up.
                try {
                    var __cidsRecoverCharts = function(tag) {
                        try {
                            resizeChartsKicker();
                            reportChartMount(String(tag || 'recover'));
                            // Force one immediate snapshot pull to repopulate series data.
                            pollSnapshot();
                        } catch (eRec) {
                            // swallow
                        }
                    };
                    window.addEventListener('resize', function() {
                        try { __cidsRecoverCharts('resize'); } catch (eRz) { }
                    });
                    window.addEventListener('focus', function() {
                        try { __cidsRecoverCharts('focus'); } catch (eFc) { }
                        setTimeout(function() { try { __cidsRecoverCharts('focus+350ms'); } catch (eFc2) { } }, 350);
                    });
                    document.addEventListener('visibilitychange', function() {
                        try {
                            if (!document.hidden) {
                                __cidsRecoverCharts('visible');
                                setTimeout(function() { try { __cidsRecoverCharts('visible+500ms'); } catch (eV2) { } }, 500);
                            }
                        } catch (eVs) {
                            // swallow
                        }
                    });
                } catch (eBindRec) {
                    // swallow
                }
                setInterval(tickClock, 1000);
                setInterval(pollSnapshot, POLL_MS);
                setInterval(pollLog, LOG_POLL_MS);
            })();
        </script>
        '''
    ).replace('__CIDS_POLL_MS__', str(poll_ms)).replace('__CIDS_LOG_POLL_MS__', str(log_poll_ms)))
    
    # Control Deck overlay (does not resize/push content)
    def toggle_control_deck() -> None:
        try:
            ui.run_javascript('window.__cids_toggle_deck && window.__cids_toggle_deck();')
        except Exception:
            pass

    def close_control_deck() -> None:
        try:
            ui.run_javascript('window.__cids_set_deck && window.__cids_set_deck(false);')
        except Exception:
            pass

    # --- CONTROL HANDLER ---
    def handle_control(action):
        msg = 'UNKNOWN ACTION'
        color = 'grey'

        if action == 'KILL':
            _success, msg = controller.kill_signal()
            color = 'red'
            add_log(f"[ALERT] {msg}")
        elif action == 'ISOLATE':
            _success, msg = controller.isolate_node()
            color = 'orange'
            add_log(f"[WARN] {msg}")
        elif action == 'REFRESH':
            _success, msg = controller.force_refresh()
            color = 'green'
            add_log(f"[SYS] {msg}")
        elif action == 'WD_RESET':
            _success, msg = controller.reset_watchdog()
            color = 'blue'
            state.watchdog_last_reset = datetime.now()
            add_log(f"[SYS] {msg}")
        else:
            add_log(f"[ERR] Unknown control action: {action}")

        # Keep notifications subtle (log is the primary narrative).
        ui.notify(msg, color=color, position='bottom-right', timeout=1.5)

    def handle_runtime_route_change(source_value: str, mode_value: str) -> None:
        source_norm = normalize_ops_runtime_source(source_value)
        mode_norm = normalize_ops_runtime_mode(mode_value)
        packet = _request_observerctl_mode_switch(source=source_norm, mode=mode_norm)
        decision = str(packet.get('decision', 'no-go')).strip().lower()
        reasons = packet.get('reason_codes', []) if isinstance(packet.get('reason_codes', []), list) else []

        if decision == 'go':
            state.source = source_norm
            state.mode = mode_norm
            msg = 'Runtime route set -> {0}:{1}'.format(source_norm, mode_norm)
            add_log('[SYS] {0}'.format(msg))
            ui.notify(msg, color='green', position='bottom-right', timeout=2.0)
            return

        reason_text = ', '.join([str(x) for x in reasons]) if reasons else str(packet.get('message', 'unknown gate failure'))
        msg = 'Route change blocked -> {0}:{1} ({2})'.format(source_norm, mode_norm, reason_text)
        add_log('[WARN] {0}'.format(msg))
        ui.notify(msg, color='orange', position='bottom-right', timeout=2.5)

    # Main Content Container (Scale Stage -> Scale Root)
    with ui.element('div').props('id="cids-scale-stage"'):
        # Backdrop (click to close) - stage-level so it doesn't inherit surface centering
        ui.element('div')\
            .props('id="cids-control-deck-backdrop" onclick="window.__cids_set_deck && window.__cids_set_deck(false);"')

        # Control deck panel (right side) - stage-level so it stays pinned in maximized mode
        with ui.element('div').props('id="cids-control-deck"').classes('bg-zinc-900 border-l border-gray-700 p-3 flex flex-col'):
            with ui.row().classes('w-full items-center justify-between border-b border-gray-700 pb-2 mb-3 shrink-0'):
                ui.label('CONTROL DECK').classes('text-xl font-bold text-white')
                ui.button(icon='close', on_click=close_control_deck).props('flat round color=white')

            # Deck body should flex to fill remaining height (avoid brittle h-full in nested flex layouts).
            # Allow internal scroll if needed; hide scrollbars to keep the appliance look.
            with ui.column().props('id="cids-deck-body"').classes('w-full flex-1 min-h-0 gap-3 overflow-y-auto no-scrollbar'):
                # Buttons (Grayscale Style) - Explicit Colors via Props
                def btn_props():
                    return 'push color=grey-9 text-color=white'

                # Status Indicator
                with ui.row().classes('w-full items-center justify-between'):
                    ui.label('STATUS')
                    status_badge = ui.badge('NOMINAL', color='green-10').props('id="cids-status-badge"').classes('font-bold')

                ui.separator().classes('bg-gray-700')

                with ui.row().classes('w-full justify-between items-center'):
                    with ui.row().classes('items-center gap-2'):
                        ui.label('RUNTIME ROUTE').classes('text-sm text-gray-400')
                        ui.icon('help_outline', size='xs').classes('text-gray-600')\
                            .tooltip('Authoritative route control (gated). Uses observerctl mode switch (single action): validates, gates, syncs runtime, and records evidence.')

                route_source = ui.select(
                    options={'sim': 'SIM', 'real': 'REAL'},
                    value=normalize_ops_runtime_source(state.source),
                    label='SOURCE',
                ).props('dense outlined color=grey-8').classes('w-full')

                route_mode = ui.select(
                    options={'watch': 'WATCH', 'canary': 'CANARY', 'live': 'LIVE', 'honeypot': 'HONEYPOT'},
                    value=normalize_ops_runtime_mode(state.mode),
                    label='MODE',
                ).props('dense outlined color=grey-8').classes('w-full')

                ui.button(
                    'APPLY ROUTE (GATED)',
                    on_click=lambda: handle_runtime_route_change(str(route_source.value), str(route_mode.value)),
                ).props('push color=grey-9 text-color=white').classes('w-full border border-gray-700')

                ui.separator().classes('bg-gray-700')

                # Density histogram bin width control (local, persistent; OFF is chart-only)
                with ui.row().classes('w-full justify-between items-center'):
                    with ui.row().classes('items-center gap-2'):
                        ui.label('BIN WIDTH').classes('text-sm text-gray-400')
                        ui.icon('help_outline', size='xs').classes('text-gray-600')\
                            .tooltip('Density Histogram bin width (seconds). Local to this UI (persisted in browser). OFF freezes the chart only; backend sampling continues.')
                    # NiceGUI Html now requires an explicit `sanitize=` kw-only arg.
                    # This markup is static/owned by the backend, so we disable sanitization
                    # to preserve intended structure and styling.
                    ui.html('''
                        <div class="cids-spinbox" title="Bin width (sec). Local persistent. OFF freezes chart only.">
                            <div class="cids-spinbox-arrows">
                                <button id="cids-binwidth-up" class="cids-spinbox-btn" type="button" aria-label="Increase bin width">&#9650;</button>
                                <button id="cids-binwidth-down" class="cids-spinbox-btn" type="button" aria-label="Decrease bin width">&#9660;</button>
                            </div>
                            <div class="cids-spinbox-core">
                                <div id="cids-binwidth-value" class="cids-spinbox-value">10</div>
                            </div>
                            <div id="cids-binwidth-suffix" class="cids-spinbox-suffix">sec</div>
                        </div>
                    ''', sanitize=False)

                # Watchdog controls
                with ui.row().classes('w-full justify-between items-center'):
                    with ui.row().classes('items-center gap-2'):
                        ui.label('WATCHDOG').classes('text-sm text-gray-400')
                        ui.icon('help_outline', size='xs').classes('text-gray-600')\
                            .tooltip('Watchdog: expects periodic supervisor heartbeats. Reset stages an intent signal; it does not fabricate liveness.')
                    wd_state = ui.badge('ACTIVE', color='green-10').props('id="cids-wd-state"').classes('font-bold text-[10px]')

                ui.button('WATCHDOG RESET', on_click=lambda: handle_control('WD_RESET')).props(btn_props()).classes('w-full border border-gray-700')
                ui.label(f"Last reset: {state.watchdog_last_reset.strftime('%H:%M:%S')}")\
                    .props('id="cids-wd-lastreset"')\
                    .classes('text-xs text-gray-500 -mt-2')

                # NOTE: WD status + last reset are updated client-side via polling.

                ui.button('FORCE REFRESH', on_click=lambda: handle_control('REFRESH')).props(btn_props()).classes('w-full border border-gray-700')
                ui.button('ISOLATE NODE', on_click=lambda: handle_control('ISOLATE')).props('push color=grey-10 text-color=orange').classes('w-full border border-orange-900')
                ui.label('ISOLATE NODE blocks external ingress to the observer (ops channel remains).').classes('text-xs text-gray-500 -mt-2')

                ui.separator().classes('bg-gray-700')

                # Footer (pushed to bottom): kill switch + branding
                with ui.column().classes('w-full mt-auto gap-3'):
                    ui.button('KILL SWITCH', on_click=lambda: handle_control('KILL'))\
                        .props('push color=red-10 text-color=white')\
                        .classes('w-full py-4 font-bold tracking-widest border border-red-900')
                    if _BRAND_PANEL_SRC:
                        ui.image(_BRAND_PANEL_SRC).classes('w-full max-h-[210px] opacity-80').props('fit=contain')

        # Main surface (centered/scaled)
        with ui.element('div').props('id="cids-scale-root"').classes('relative p-6 bg-zinc-900 text-gray-300 font-mono gap-4 flex flex-col'):
            create_header(toggle_control_deck)
        
            # Primary Grid (Takes remaining height)
            with ui.row().props('id="cids-main-grid"').classes('w-full flex-grow min-h-0 min-w-0 gap-4 overflow-hidden'):

                # SYSTEM INTEGRITY (Left, 50%)
                with ui.card().classes('relative overflow-hidden flex-1 min-w-0 h-full min-h-0 bg-zinc-900 border border-gray-700 rounded-none p-0 flex flex-col'):
                    with ui.row().classes('w-full border-b border-gray-800 p-2 justify-between items-center bg-zinc-950'):
                        ui.label('SYSTEM INTEGRITY').classes('text-xs font-bold text-gray-500')
                        with ui.row().classes('items-center gap-2'):
                            ui.icon('help_outline', size='xs').classes('text-gray-600')\
                                .tooltip('System Integrity: radar chart derived from live snapshot scores (polling).')
                            ui.icon('shield', size='xs').classes('text-gray-600')

                    # Radar chart (ECharts) - matches the original layout.
                    with ui.element('div').props('id="cids-integrity-wrap"').classes('relative w-full flex-grow min-h-0 overflow-hidden p-3'):
                        create_integrity_diamond_chart().props('id="cids-integrity-radar-chart"')

                # RIGHT COLUMN (Bio-Rhythm + Density + System Log)
                # Use flex-based row splitting instead of percentage heights; percent heights can be
                # unstable during first layout and can look like panels “appear” after a snap/reflow.
                with ui.column().props('id="cids-right-col"').classes('flex-1 min-w-0 h-full min-h-0 gap-4 flex flex-col'):

                    # BIORHYTHM (Top Third)
                    with ui.card().classes('w-full flex-1 min-h-0 bg-zinc-900 border border-gray-700 rounded-none p-0 flex flex-col'):
                        with ui.row().classes('w-full border-b border-gray-800 p-2 justify-between items-center bg-zinc-950'):
                            ui.label('RESOURCE METRICS').classes('text-xs font-bold text-gray-500')
                            with ui.row().classes('items-center gap-2'):
                                ui.icon('help_outline', size='xs').classes('text-gray-600')\
                                    .tooltip('Resource Metrics: CPU% + MEM% history (ECharts). Updated via client-side polling.')
                                ui.icon('query_stats', size='xs').classes('text-gray-600')
                        with ui.element('div').classes('w-full flex-grow min-h-0 overflow-hidden p-3'):
                            create_biorhythm_chart().props('id="cids-resource-chart"')

                    # DENSITY HISTOGRAM (Middle Third)
                    with ui.card().classes('w-full flex-1 min-h-0 bg-zinc-900 border border-gray-700 rounded-none p-0 flex flex-col'):
                        with ui.row().classes('w-full border-b border-gray-800 p-2 justify-between items-center bg-zinc-950'):
                            ui.label('DENSITY HISTOGRAM').classes('text-xs font-bold text-gray-500')
                            with ui.row().classes('items-center gap-2'):
                                ui.icon('help_outline', size='xs').classes('text-gray-600')\
                                    .tooltip('Density Histogram: relative collection volume over the last 60 seconds (base 1s sampling), rebinned locally by the Control Deck bin width (sec). Hover a bar for raw counts.')
                                ui.icon('bar_chart', size='xs').classes('text-gray-600')
                        with ui.element('div').classes('w-full flex-grow min-h-0 overflow-hidden p-3'):
                            create_density_histogram_chart().props('id="cids-density-chart"')

                    # SYSTEM LOG (Bottom Third)
                    with ui.card().classes('w-full flex-1 min-h-0 bg-zinc-900 border border-gray-700 rounded-none p-0 flex flex-col'):
                        with ui.row().classes('w-full border-b border-gray-800 p-2 justify-between items-center bg-zinc-950'):
                            ui.label('SYSTEM LOG').classes('text-xs font-bold text-gray-500')
                            ui.icon('terminal', size='xs').classes('text-gray-600')

                        # Scrollable feed (scrollbar hidden). Auto-follows when at bottom.
                        # NOTE: use a plain flex div instead of `ui.column()` here.
                        # We've observed the NiceGUI column wrapper sometimes laying out offscreen (pulled-right symptom)
                        # while its parent card remains in-place.
                        with ui.element('div').classes('w-full flex-1 min-h-0 p-2 bg-black font-mono text-xs gap-1 flex flex-col'):
                            log_scroll = ui.element('div').props('id="cids-log-scroll"')\
                                .classes('w-full flex-1 min-h-0 overflow-y-auto no-scrollbar')
                            # Prompt line intentionally removed (was a visual artifact under the feed).

    # --- UPDATE LOOP ---
    # Intentionally removed.
    #
    # The GUI used to blank under server-driven websocket UI diffs (timers calling
    # .update(), ui.run_javascript(), dynamic element churn). The dashboard now
    # updates via client-side polling of JSON endpoints:
    #   - /_ghost_console/snapshot
    #   - /_ghost_console/log_tail

# --- EXECUTION CONFIG ---
# We use native=False to avoid pythonnet/pywebview dependency issues on Python 3.14
# The launcher script handles the "App Mode" window creation.
if __name__ in {"__main__", "__mp_main__"}:
    _install_backend_lifecycle_hooks()
    _backend_runtime_log('process_start', {'build': BUILD_STAMP})
    # Allow the launcher/tests to pick a port without editing source.
    # Default remains 8899 to preserve operator expectations.
    try:
        _port = int(os.getenv('CALAMUM_DASHBOARD_PORT', '8899'))
    except Exception:
        _port = 8899

    _host = os.getenv('CALAMUM_DASHBOARD_HOST')  # optional; if unset, NiceGUI default applies

    _run_kwargs = dict(
        native=False,
        port=_port,  # Changed port to avoid zombie process conflicts
        title='CALAMUM OPS V2',
        dark=True,
        show=False,
        reload=False,
    )
    if _host:
        _run_kwargs['host'] = str(_host)

    ui.run(**_run_kwargs)
