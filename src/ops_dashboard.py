from nicegui import ui, app
from datetime import datetime, timezone
import base64
import os
import random
import asyncio
import time
import atexit
import signal
import sys
import traceback
from pathlib import Path
from typing import Dict, Optional, List, Tuple
import json
from ops.controller import controller # Import the controller
from ops.telemetry import TelemetryProvider, load_config

# --- CONFIGURATION & THEME ---
THEME_BG = 'bg-zinc-900'
THEME_FG = 'text-gray-300'
THEME_ACCENT = 'border-gray-600'
THEME_FONT = 'font-mono'

# Visible build stamp to confirm the UI is served by the latest backend instance.
# (Helps diagnose cases where a hidden old process keeps running and the launcher can't bind the port.)
BUILD_STAMP = '2026-02-04'

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
        repo_root = _repo_root_for_logs()
        out_path = repo_root / 'logs' / 'ghost_console_backend.runtime.jsonl'
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

    # Fallback: try writing relative to the project root inference.
    try:
        out_path = _PROJECT_ROOT.parents[1] / 'logs' / 'ghost_console_backend.runtime.jsonl'
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open('a', encoding='utf-8') as f:
            f.write(json.dumps(record, sort_keys=True) + '\n')
    except Exception:
        return


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
        self.records_collected = 12450
        self.is_running = True
        self.mode = normalize_mode(os.getenv('CALAMUM_OPS_MODE', 'CANARY'))
        self.timestamp = datetime.now()
        self.log_seq: int = 0
        self.log_items: List[Tuple[int, str]] = []  # (seq, line)
        self.density_bins = [0] * 12
        self.density_raw_window = [0] * 12
        self.density_slice_sec = 15.0
        self.watchdog_active = True
        self.watchdog_last_reset = datetime.now()
        self._last_obs_active: Optional[bool] = None
        self._last_wd_active: Optional[bool] = None
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
    ts = datetime.now().strftime('%H:%M')
    line = f"{ts} {msg}"
    state.log_seq += 1
    state.log_items.append((state.log_seq, line))
    # keep bounded
    if len(state.log_items) > 400:
        state.log_items = state.log_items[-400:]

state = SystemState()

# Telemetry provider (best-effort: will fall back to simulation if it can't read sources)
telemetry = TelemetryProvider(load_config(Path(__file__)))

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
    repo_root = _repo_root_for_logs()
    out_path = repo_root / 'logs' / 'ghost_console_js_errors.jsonl'
    err: Optional[str] = None
    try:
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
    repo_root = _repo_root_for_logs()
    out_path = repo_root / 'logs' / 'ghost_console_js_errors.jsonl'
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
    repo_root = _repo_root_for_logs()
    return {
        'repo_root': str(repo_root),
        'logs_dir_exists': (repo_root / 'logs').exists(),
        'js_error_path': str(repo_root / 'logs' / 'ghost_console_js_errors.jsonl'),
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
    except Exception:
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
    new = int(snap.get('new_records', 0) or 0)
    state.records_collected = total

    bins = snap.get('density_bins')
    if isinstance(bins, list) and len(bins) == len(state.density_bins):
        state.density_bins = [int(max(0, min(100, x))) for x in bins]

    raw = snap.get('density_raw_window')
    if isinstance(raw, list) and len(raw) == len(state.density_bins):
        state.density_raw_window = [int(max(0, x)) for x in raw]
    try:
        state.density_slice_sec = float(snap.get('density_slice_sec', state.density_slice_sec))
    except Exception:
        pass

    # WD/OBS
    state.watchdog_active = bool(snap.get('watchdog_active', False))
    state.is_running = bool(snap.get('observer_active', False))

    # Derive scores
    availability = 100 if state.is_running else 0
    freshness = 100 if state.watchdog_active else 0
    capacity = int(max(0, min(100, 100 - max(cpu, mem))))
    integrity = int(max(0, min(100, state.integrity_score)))

    # Status
    if not state.is_running:
        status = {'text': 'CRITICAL', 'color': 'red'}
    elif cpu >= 80:
        status = {'text': 'DEGRADED', 'color': 'orange'}
    else:
        status = {'text': 'NOMINAL', 'color': 'green'}

    # Log narrative
    if new > 0:
        src = snap.get('active_jsonl_path')
        if src:
            add_log(f"Ingested +{new} records ({Path(src).name})")
        else:
            add_log(f"Ingested +{new} records")

    if state._last_obs_active is None:
        state._last_obs_active = state.is_running
    if state._last_wd_active is None:
        state._last_wd_active = state.watchdog_active

    if state.is_running != state._last_obs_active:
        add_log(f"[SYS] Observer state -> {'ACTIVE' if state.is_running else 'DOWN'}")
        state._last_obs_active = state.is_running
    if state.watchdog_active != state._last_wd_active:
        add_log(f"[SYS] Watchdog state -> {'ACTIVE' if state.watchdog_active else 'STALE'}")
        state._last_wd_active = state.watchdog_active

    return {
        'ts': datetime.now().isoformat(),
        'server_boot_id': SERVER_BOOT_ID,
        'server_now_ms': int(time.time() * 1000),
        'js_diag': {
            'seq': state.js_diag_seq,
            'last_ts_utc': state.js_diag_last_ts_utc,
        },
        'mode': normalize_mode(state.mode),
        'cpu': cpu,
        'mem': mem,
        'cpu_history': state.cpu_history,
        'mem_history': state.mem_history,
        'total_records': total,
        'new_records': new,
        'density_bins': state.density_bins,
        'density_raw_window': state.density_raw_window,
        'density_slice_sec': state.density_slice_sec,
        'watchdog_active': state.watchdog_active,
        'watchdog_last_reset': state.watchdog_last_reset.isoformat(),
        'observer_active': state.is_running,
        'scores': {
            'availability': availability,
            'integrity': integrity,
            'capacity': capacity,
            'freshness': freshness,
        },
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
                ui.label(f"MODE: [ {normalize_mode(state.mode)} ]")\
                    .props('id="cids-mode"')\
                    .classes('text-xs text-gray-500 uppercase')\
                    .tooltip(MODE_TOOLTIP)
        
        with ui.row().classes('gap-6 items-center'):
            # Watchdog indicator
            watchdog_badge = ui.badge('WD: ACTIVE', color='green-10')\
                .props('id="cids-wd-badge"')\
                .classes('font-bold text-[10px]')
            watchdog_badge.tooltip('Watchdog: monitors the observer loop heartbeat. Reset in Control Deck.')

            # Observer indicator (low-profile, beside WD)
            observer_badge = ui.badge('OBS: ACTIVE', color='green-10')\
                .props('id="cids-obs-badge"')\
                .classes('font-bold text-[10px]')
            observer_badge.tooltip('Observer: process status for the active node.')

            # Records Counter
            with ui.row().classes('items-center gap-2'):
                ui.label('RECORDS:').classes('text-xs text-gray-500')
                ui.label(f"{int(state.records_collected):,}")\
                    .props('id="cids-records"')\
                    .classes('text-xl font-bold text-white')

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
            'formatter': '{b}<br/>norm: {c}',
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
                    el.setAttribute('title', String(Number(ri)) + ' rec / ' + String(Math.round(sliceSec)) + 's  |  norm: ' + String(Math.round(h)));
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
                transform: translateX(100%);
                transition: transform 160ms ease;
                z-index: 60;
                pointer-events: none;
                overflow: hidden;
            }
            #cids-control-deck.open {
                transform: translateX(0);
                pointer-events: auto;
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

                        var gridEl = null;
                        var rightColEl = null;
                        try { gridEl = document.getElementById('cids-main-grid'); } catch (eG) { gridEl = null; }
                        try { rightColEl = document.getElementById('cids-right-col'); } catch (eR) { rightColEl = null; }

                        var logEl = null;
                        var denEl = null;
                        try { logEl = document.getElementById('cids-log-scroll'); } catch (eL) { logEl = null; }
                        try { denEl = document.getElementById('cids-density-root'); } catch (eD) { denEl = null; }

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

                        // Control Deck anchoring probe (is it still positioned relative to the root?)
                        var deckProbe = null;
                        try {
                            var deck = document.getElementById('cids-control-deck');
                            var bd = document.getElementById('cids-control-deck-backdrop');
                            var op = null;
                            try { op = deck ? deck.offsetParent : null; } catch (eOP) { op = null; }
                            deckProbe = {
                                deck_rect: safeRect(deck),
                                backdrop_rect: safeRect(bd),
                                offset_parent: op ? {
                                    tag: op.tagName ? String(op.tagName) : null,
                                    id: op.id ? String(op.id) : null,
                                    cls: op.className ? truncate(String(op.className), 220) : null,
                                    rect: safeRect(op)
                                } : null
                            };
                        } catch (eDP) {
                            deckProbe = null;
                        }

                        post('client_alive', {
                            build: %s,
                            server_tick_age_ms: serverTickAge,
                            top_at_point: top,
                            root_style: rootStyle,
                            layout_probe: {
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
                                    cids_density_root: countSel('#cids-density-root'),
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
                            }
                        });
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
    ui.add_head_html(f'''
        <script>
            (function() {{
                if (window.__cids_poll_bound) return;
                window.__cids_poll_bound = true;

                var POLL_MS = {poll_ms};
                var LOG_POLL_MS = {log_poll_ms};
                var logAfter = 0;
                var snapBusy = false;
                var logBusy = false;

                function byId(id) {{
                    try {{ return document.getElementById(id); }} catch (e) {{ return null; }}
                }}

                function pad2(n) {{
                    n = Number(n || 0);
                    return (n < 10 ? '0' : '') + String(n);
                }}

                function fmtInt(n) {{
                    try {{
                        n = Number(n || 0);
                        if (!isFinite(n)) n = 0;
                        var s = String(Math.floor(n));
                        var out = '';
                        while (s.length > 3) {{
                            out = ',' + s.slice(-3) + out;
                            s = s.slice(0, -3);
                        }}
                        return s + out;
                    }} catch (e) {{
                        return String(n);
                    }}
                }}

                function setText(id, text) {{
                    var el = byId(id);
                    if (!el) return;
                    el.textContent = String(text);
                }}

                function setBar(id, v) {{
                    var el = byId(id);
                    if (!el) return;
                    var x = Number(v || 0);
                    if (!isFinite(x)) x = 0;
                    x = Math.max(0, Math.min(100, x));
                    el.style.width = String(x) + '%';
                }}

                function setBadge(id, text, colorName) {{
                    var el = byId(id);
                    if (!el) return;
                    el.textContent = String(text);
                    var bg = '#065f46';
                    if (colorName === 'red') bg = '#7f1d1d';
                    else if (colorName === 'orange') bg = '#9a3412';
                    else if (colorName === 'blue') bg = '#1e3a8a';
                    else if (colorName === 'green') bg = '#065f46';
                    el.style.backgroundColor = bg;
                    el.style.color = '#ffffff';
                }}

                function toPoints(arr, w, h) {{
                    try {{
                        if (!arr || !arr.length) return '';
                        var n = arr.length;
                        var pts = [];
                        for (var i = 0; i < n; i++) {{
                            var v = Number(arr[i]);
                            if (!isFinite(v)) v = 0;
                            v = Math.max(0, Math.min(100, v));
                            var x = (n <= 1) ? 0 : (i / (n - 1)) * w;
                            var y = h - (v / 100.0) * h;
                            pts.push(x.toFixed(1) + ',' + y.toFixed(1));
                        }}
                        return pts.join(' ');
                    }} catch (e) {{
                        return '';
                    }}
                }}

                function bindLogFollow() {{
                    var el = byId('cids-log-scroll');
                    if (!el || el.dataset.bound === '1') return;
                    el.dataset.bound = '1';
                    el.dataset.follow = '1';
                    el.scrollTop = 0;
                    var onScroll = function() {{
                        try {{
                            var nearTop = el.scrollTop < 20;
                            el.dataset.follow = nearTop ? '1' : '0';
                        }} catch (e) {{
                            // swallow
                        }}
                    }};
                    el.addEventListener('scroll', onScroll, {{ passive: true }});
                    onScroll();
                }}

                function appendLogLine(line) {{
                    var el = byId('cids-log-scroll');
                    if (!el) return;
                    var node = document.createElement('div');
                    node.className = 'w-full cids-log-flash';
                    if (line.indexOf('[ALERT]') >= 0) node.className += ' text-red-300';
                    else if (line.indexOf('[WARN]') >= 0 || line.indexOf('[WRN]') >= 0) node.className += ' text-orange-200';
                    else if (line.indexOf('Ingested +') >= 0) node.className += ' text-emerald-200';
                    else node.className += ' text-gray-400';
                    node.textContent = String(line);
                    if (el.firstChild) el.insertBefore(node, el.firstChild);
                    else el.appendChild(node);
                    while (el.childNodes && el.childNodes.length > 220) {{
                        el.removeChild(el.lastChild);
                    }}
                    if (el.dataset.follow === '1') {{
                        el.scrollTop = 0;
                    }}
                }}

                async function pollSnapshot() {{
                    if (snapBusy) return;
                    snapBusy = true;
                    try {{
                        var res = await fetch('/_ghost_console/snapshot', {{ cache: 'no-store' }});
                        if (!res || !res.ok) return;
                        var snap = await res.json();
                        if (!snap) return;

                        // Mark server responsiveness for the heartbeat probe.
                        try {{ window.__cids_server_tick = Date.now(); }} catch (eTick) {{ }}

                        // Detect backend restarts (server boot id changes) and log them.
                        try {{
                            var nextBoot = snap.server_boot_id ? String(snap.server_boot_id) : null;
                            if (!window.__cids_server_boot_id) {{
                                window.__cids_server_boot_id = nextBoot;
                            }} else if (nextBoot && String(window.__cids_server_boot_id) !== nextBoot) {{
                                if (window.__cids_post_diag) {{
                                    window.__cids_post_diag('server_boot_changed', {{
                                        prev: String(window.__cids_server_boot_id),
                                        next: nextBoot
                                    }});
                                }}
                                window.__cids_server_boot_id = nextBoot;
                            }}
                        }} catch (eSB) {{
                            // swallow
                        }}

                        setText('cids-records', fmtInt(snap.total_records || 0));
                        setText('cids-mode', 'MODE: [ ' + String(snap.mode || 'CANARY') + ' ]');

                        // badges
                        var wd = !!snap.watchdog_active;
                        var obs = !!snap.observer_active;
                        setBadge('cids-wd-badge', wd ? 'WD: ACTIVE' : 'WD: STALE', wd ? 'green' : 'orange');
                        setBadge('cids-obs-badge', obs ? 'OBS: ACTIVE' : 'OBS: DOWN', obs ? 'green' : 'red');

                        if (snap.status && snap.status.text) {{
                            setBadge('cids-status-badge', String(snap.status.text), String(snap.status.color || 'green'));
                        }}
                        setBadge('cids-wd-state', wd ? 'ACTIVE' : 'STALE', wd ? 'green' : 'orange');

                        // watchdog reset time
                        try {{
                            var d = snap.watchdog_last_reset ? new Date(String(snap.watchdog_last_reset)) : null;
                            if (d && isFinite(d.getTime())) {{
                                setText('cids-wd-lastreset', 'Last reset: ' + pad2(d.getHours()) + ':' + pad2(d.getMinutes()) + ':' + pad2(d.getSeconds()));
                            }}
                        }} catch (e0) {{
                            // swallow
                        }}

                        // scores
                        var s = snap.scores || {{}};
                        var a = Number(s.availability || 0);
                        var i = Number(s.integrity || 0);
                        var c = Number(s.capacity || 0);
                        var f = Number(s.freshness || 0);
                        setText('cids-score-availability', String(Math.round(a)) + '/100');
                        setText('cids-score-integrity', String(Math.round(i)) + '/100');
                        setText('cids-score-capacity', String(Math.round(c)) + '/100');
                        setText('cids-score-freshness', String(Math.round(f)) + '/100');
                        setBar('cids-bar-availability', a);
                        setBar('cids-bar-integrity', i);
                        setBar('cids-bar-capacity', c);
                        setBar('cids-bar-freshness', f);

                        // cpu/mem + sparkline
                        setText('cids-cpu', String(Math.round(Number(snap.cpu || 0))) + '%');
                        setText('cids-mem', String(Math.round(Number(snap.mem || 0))) + '%');
                        var cpuPts = toPoints(snap.cpu_history || [], 100, 24);
                        var memPts = toPoints(snap.mem_history || [], 100, 24);
                        var cpuEl = byId('cids-spark-cpu');
                        var memEl = byId('cids-spark-mem');
                        if (cpuEl) cpuEl.setAttribute('points', cpuPts);
                        if (memEl) memEl.setAttribute('points', memPts);

                        // density
                        try {{
                            var bins = snap.density_bins || [];
                            var raw = snap.density_raw_window || [];
                            var sliceSec = Number(snap.density_slice_sec || 15);
                            for (var k = 0; k < bins.length; k++) {{
                                var el = byId('cids-density-bar-' + String(k));
                                if (!el) continue;
                                var bi = Number(bins[k] || 0);
                                var ri = Number(raw[k] || 0);
                                if (!isFinite(bi)) bi = 0;
                                if (!isFinite(ri)) ri = 0;
                                bi = Math.max(0, Math.min(100, bi));
                                el.style.height = String(Math.max(2, bi)) + '%';
                                el.setAttribute('title', String(Math.round(ri)) + ' rec / ' + String(Math.round(sliceSec)) + 's  |  norm: ' + String(Math.round(bi)));
                            }}
                        }} catch (e2) {{
                            // swallow
                        }}

                        // keep a hint for log poll
                        if (snap.log_last_seq && Number(snap.log_last_seq) > logAfter) {{
                            // no-op; log polling will catch up
                        }}
                    }} catch (e) {{
                        // swallow
                    }} finally {{
                        snapBusy = false;
                    }}
                }}

                async function pollLog() {{
                    if (logBusy) return;
                    logBusy = true;
                    try {{
                        bindLogFollow();
                        var res = await fetch('/_ghost_console/log_tail?after=' + String(logAfter) + '&limit=120', {{ cache: 'no-store' }});
                        if (!res || !res.ok) return;
                        var payload = await res.json();
                        if (!payload) return;
                        var lines = payload.lines || [];
                        for (var i = 0; i < lines.length; i++) {{
                            var item = lines[i] || null;
                            if (!item) continue;
                            var seq = Number(item.seq || 0);
                            if (seq > logAfter) logAfter = seq;
                            appendLogLine(item.line || '');
                        }}
                    }} catch (e) {{
                        // swallow
                    }} finally {{
                        logBusy = false;
                    }}
                }}

                function tickClock() {{
                    try {{
                        var d = new Date();
                        setText('cids-clock', pad2(d.getHours()) + ':' + pad2(d.getMinutes()) + ':' + pad2(d.getSeconds()));
                    }} catch (e) {{
                        // swallow
                    }}
                }}

                // Start
                if (POLL_MS < 250) POLL_MS = 250;
                if (LOG_POLL_MS < 250) LOG_POLL_MS = 250;
                tickClock();
                bindLogFollow();
                pollSnapshot();
                pollLog();
                setInterval(tickClock, 1000);
                setInterval(pollSnapshot, POLL_MS);
                setInterval(pollLog, LOG_POLL_MS);
            }})();
        </script>
    ''')
    
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
            # Touch the local watchdog heartbeat marker so WD reflects the reset immediately.
            try:
                telemetry.reset_watchdog()
            except Exception:
                pass
            state.watchdog_last_reset = datetime.now()
            add_log(f"[SYS] {msg}")
        else:
            add_log(f"[ERR] Unknown control action: {action}")

        # Keep notifications subtle (log is the primary narrative).
        ui.notify(msg, color=color, position='bottom-right', timeout=1.5)

    # Main Content Container (Scale Stage -> Scale Root)
    with ui.element('div').props('id="cids-scale-stage"'):
        # Backdrop (click to close) - stage-level so it doesn't inherit surface centering
        ui.element('div')\
            .props('id="cids-control-deck-backdrop" onclick="window.__cids_set_deck && window.__cids_set_deck(false);"')

        # Control deck panel (right side) - stage-level so it stays pinned in maximized mode
        with ui.element('div').props('id="cids-control-deck"').classes('bg-zinc-900 border-l border-gray-700 p-3 flex flex-col'):
            with ui.row().classes('w-full items-center justify-between border-b border-gray-700 pb-2 mb-3'):
                ui.label('CONTROL DECK').classes('text-xl font-bold text-white')
                ui.button(icon='close', on_click=close_control_deck).props('flat round color=white')

            # Use full-height flex column so the footer can be pinned to the bottom without scrolling.
            with ui.column().classes('w-full h-full min-h-0 gap-3'):
                # Buttons (Grayscale Style) - Explicit Colors via Props
                def btn_props():
                    return 'push color=grey-9 text-color=white'

                # Status Indicator
                with ui.row().classes('w-full items-center justify-between'):
                    ui.label('STATUS')
                    status_badge = ui.badge('NOMINAL', color='green-10').props('id="cids-status-badge"').classes('font-bold')

                ui.separator().classes('bg-gray-700')

                # Watchdog controls
                with ui.row().classes('w-full justify-between items-center'):
                    with ui.row().classes('items-center gap-2'):
                        ui.label('WATCHDOG').classes('text-sm text-gray-400')
                        ui.icon('help_outline', size='xs').classes('text-gray-600')\
                            .tooltip('Watchdog: expects periodic loop heartbeats. Reset nudges the timer (stub).')
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

                with ui.row().classes('w-full justify-between items-center'):
                    with ui.row().classes('items-center gap-2'):
                        ui.label('AUTO-PURGE').classes('text-sm text-gray-400')
                        ui.icon('help_outline', size='xs').classes('text-gray-600')\
                            .tooltip('Auto-Purge: retention cleanup for logs/cached metrics (stub for now).')
                    ui.switch().props('color=white')

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
                with ui.card().classes('flex-1 min-w-0 h-full min-h-0 bg-zinc-900 border border-gray-700 rounded-none p-0 flex flex-col'):
                    with ui.row().classes('w-full border-b border-gray-800 p-2 justify-between items-center bg-zinc-950'):
                        ui.label('SYSTEM INTEGRITY').classes('text-xs font-bold text-gray-500')
                        with ui.row().classes('items-center gap-2'):
                            ui.icon('help_outline', size='xs').classes('text-gray-600')\
                                .tooltip('Scores are updated via client-side polling (no websocket diffs).')
                            ui.icon('shield', size='xs').classes('text-gray-600')

                    # DOM-only score bars (stable; updated by client polling)
                    with ui.column().classes('w-full flex-grow min-h-0 overflow-hidden p-3 gap-3'):
                        def score_row(label: str, val_id: str, bar_id: str) -> None:
                            with ui.column().classes('gap-1'):
                                with ui.row().classes('w-full justify-between items-center text-[11px] text-gray-400'):
                                    ui.label(label)
                                    ui.label('0/100').props(f'id="{val_id}"').classes('text-gray-200')
                                with ui.element('div').classes('w-full h-2 bg-zinc-800 border border-gray-700')\
                                    .style('position: relative; overflow: hidden;'):
                                    ui.element('div')\
                                        .props(f'id="{bar_id}"')\
                                        .classes('h-full bg-zinc-200/70')\
                                        .style('width: 0%;')

                        score_row('AVAILABILITY', 'cids-score-availability', 'cids-bar-availability')
                        score_row('INTEGRITY', 'cids-score-integrity', 'cids-bar-integrity')
                        score_row('CAPACITY', 'cids-score-capacity', 'cids-bar-capacity')
                        score_row('FRESHNESS', 'cids-score-freshness', 'cids-bar-freshness')

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
                                    .tooltip('Resource Metrics: CPU% + MEM% with a tiny sparkline history. Updated via client-side polling.')
                                ui.icon('query_stats', size='xs').classes('text-gray-600')
                        with ui.column().classes('w-full flex-grow min-h-0 overflow-hidden p-3 gap-2'):
                            with ui.row().classes('w-full justify-between items-center'):
                                ui.label('CPU').classes('text-xs text-gray-500')
                                ui.label('0%').props('id="cids-cpu"').classes('text-sm text-white font-bold')
                            with ui.row().classes('w-full justify-between items-center'):
                                ui.label('MEM').classes('text-xs text-gray-500')
                                ui.label('0%').props('id="cids-mem"').classes('text-sm text-white font-bold')

                            # Simple SVG sparkline (client-updated)
                            ui.html('''
                                <svg id="cids-spark" viewBox="0 0 100 24" preserveAspectRatio="none" style="width:100%; height: 56px;">
                                  <polyline id="cids-spark-cpu" fill="none" stroke="#ffffff" stroke-width="1.5" points="" />
                                  <polyline id="cids-spark-mem" fill="none" stroke="#a1a1aa" stroke-width="1.2" stroke-dasharray="3 2" points="" />
                                </svg>
                            ''', sanitize=False)

                    # DENSITY HISTOGRAM (Middle Third)
                    with ui.card().classes('w-full flex-1 min-h-0 bg-zinc-900 border border-gray-700 rounded-none p-0 flex flex-col'):
                        with ui.row().classes('w-full border-b border-gray-800 p-2 justify-between items-center bg-zinc-950'):
                            ui.label('DENSITY HISTOGRAM').classes('text-xs font-bold text-gray-500')
                            with ui.row().classes('items-center gap-2'):
                                ui.icon('help_outline', size='xs').classes('text-gray-600')\
                                    .tooltip('Density Histogram: relative collection volume over the last 12 time slices (normalized 0-100). Time slice width is configurable; hover a bar for raw counts.')
                                ui.icon('bar_chart', size='xs').classes('text-gray-600')
                        with ui.column().classes('w-full flex-grow min-h-0 overflow-hidden'):
                            # DOM-based histogram bars (stable under rapid updates).
                            with ui.element('div').classes('w-full h-full px-3 pb-3 pt-2'):
                                with ui.element('div').props('id="cids-density-root"')\
                                    .classes('w-full h-full flex items-end gap-2'):
                                    for i in range(len(state.density_bins)):
                                        ui.element('div')\
                                            .props(f'id="cids-density-bar-{i}"')\
                                            .classes('flex-1 bg-zinc-200/60 border border-gray-600')\
                                            .style('height: 2%')

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
                            # Prompt line (outside scroll so it stays visible)
                            ui.label('>_').classes('text-gray-500 mt-1')

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
    ui.run(
        native=False,
        port=8899, # Changed port to avoid zombie process conflicts
        title='CALAMUM OPS V2',
        dark=True,
        show=False, 
        reload=False
    )
