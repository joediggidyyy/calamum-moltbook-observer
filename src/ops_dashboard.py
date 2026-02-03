from nicegui import ui
from datetime import datetime
import os
import random
import asyncio
from pathlib import Path
from typing import Dict, Optional
from ops.controller import controller # Import the controller
from ops.telemetry import TelemetryProvider, load_config

# --- CONFIGURATION & THEME ---
THEME_BG = 'bg-zinc-900'
THEME_FG = 'text-gray-300'
THEME_ACCENT = 'border-gray-600'
THEME_FONT = 'font-mono'

# Visible build stamp to confirm the UI is served by the latest backend instance.
# (Helps diagnose cases where a hidden old process keeps running and the launcher can't bind the port.)
BUILD_STAMP = '2026-02-03'

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
        self.log_lines: list[str] = [
            '14:00 [INF] Sentinel initialized loop [hash:x89a]',
            '14:01 [WRN] Pulse lag detected (+40ms)',
        ]
        self.density_bins = [0] * 12
        self.watchdog_active = True
        self.watchdog_last_reset = datetime.now()

state = SystemState()

# Telemetry provider (best-effort: will fall back to simulation if it can't read sources)
telemetry = TelemetryProvider(load_config(Path(__file__)))

# --- COMPONENTS ---

def create_header(toggle_drawer_fn):
    with ui.row().classes('w-full justify-between items-center border-b border-gray-700 pb-2 mb-2 h-16'):
        with ui.row().classes('items-center gap-4'):
            ui.icon('hub', size='md').classes('text-gray-400')
            with ui.column().classes('gap-0'):
                ui.label('CALAMUM OPS').classes(f'text-xl {THEME_FONT} font-bold tracking-wider text-white')
                ui.label()\
                    .bind_text_from(state, 'mode', lambda m: f"MODE: [ {normalize_mode(m)} ]")\
                    .classes('text-xs text-gray-500 uppercase')\
                    .tooltip(MODE_TOOLTIP)
        
        with ui.row().classes('gap-6 items-center'):
            # Watchdog indicator
            watchdog_badge = ui.badge('WD: ACTIVE', color='green-10').classes('font-bold text-[10px]')
            watchdog_badge.tooltip('Watchdog: monitors the observer loop heartbeat. Reset in Control Deck.')

            # Observer indicator (low-profile, beside WD)
            observer_badge = ui.badge('OBS: ACTIVE', color='green-10').classes('font-bold text-[10px]')
            observer_badge.tooltip('Observer: process status for the active node.')

            # Records Counter
            with ui.row().classes('items-center gap-2'):
                ui.label('RECORDS:').classes('text-xs text-gray-500')
                ui.label().bind_text_from(state, 'records_collected', lambda x: f"{x:,}").classes('text-xl font-bold text-white')

            ui.separator().props('vertical').classes('h-8 border-gray-700')

            # Clock + build stamp
            with ui.column().classes('gap-0 items-end'):
                clock = ui.label(datetime.now().strftime('%H:%M:%S')).classes('text-gray-400 font-mono')
                ui.label(f'BUILD {BUILD_STAMP}').classes('text-[10px] text-gray-600 font-mono leading-none')
            ui.timer(1.0, lambda: clock.set_text(datetime.now().strftime('%H:%M:%S')))

            ui.button(icon='menu', on_click=toggle_drawer_fn).props('flat round color=white')

            def _update_watchdog_badge() -> None:
                if state.watchdog_active:
                    watchdog_badge.text = 'WD: ACTIVE'
                    watchdog_badge.props('color=green-10')
                else:
                    watchdog_badge.text = 'WD: STALE'
                    watchdog_badge.props('color=orange-9')

                if state.is_running:
                    observer_badge.text = 'OBS: ACTIVE'
                    observer_badge.props('color=green-10')
                else:
                    observer_badge.text = 'OBS: DOWN'
                    observer_badge.props('color=red-10')

            ui.timer(0.5, _update_watchdog_badge)

def create_integrity_diamond_chart() -> ui.echart:
    """Radar chart using ECharts for stable sizing (no toolbars/modebar)."""
    option = {
        'backgroundColor': 'transparent',
        'tooltip': {'show': False},
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
        'grid': {'left': 8, 'right': 8, 'top': 10, 'bottom': 8, 'containLabel': False},
        'xAxis': {
            'type': 'category',
            'data': x,
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
                'data': state.density_bins,
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

# --- MAIN LAYOUT ---

@ui.page('/')
def main_page():
    # Update Theme Colors - Set primary to Dark Gray to fix button contrast default
    ui.colors(primary='#27272a', secondary='#1f2937', accent='#e5e7eb', dark='#18181b')
    
    # Global Style injection
    ui.add_head_html('''
        <style>
            :root {
                --cids-min-w: 1100px;
                --cids-min-h: 720px;
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

            /* Optional: crisper text when scaled */
            #cids-scale-root * { -webkit-font-smoothing: antialiased; }

            /* Hide scrollbars while still allowing programmatic scroll */
            .no-scrollbar {
                scrollbar-width: none; /* Firefox */
                -ms-overflow-style: none; /* IE/Edge legacy */
            }
            .no-scrollbar::-webkit-scrollbar { display: none; }
        </style>
    ''')
    
    # Drawer for Control Deck
    # Force mobile overlay behavior so click-away closes the drawer (restores older UX)
    drawer = ui.right_drawer(value=False).classes('bg-zinc-900 border-l border-gray-700 p-4')\
        .props('width=300 overlay behavior=mobile breakpoint=99999')
    with drawer:
        ui.label('CONTROL DECK').classes('text-xl font-bold border-b border-gray-700 pb-2 w-full mb-4 text-white')
        
        with ui.column().classes('w-full gap-4'):
            # Buttons (Grayscale Style) - Explicit Colors via Props
            def btn_props():
                return 'push color=grey-9 text-color=white'

             # Status Indicator
            with ui.row().classes('w-full items-center justify-between'):
                ui.label('STATUS')
                status_badge = ui.badge('NOMINAL', color='green-10').classes('font-bold')

            ui.separator().classes('bg-gray-700')

            # Watchdog controls
            with ui.row().classes('w-full justify-between items-center'):
                with ui.row().classes('items-center gap-2'):
                    ui.label('WATCHDOG').classes('text-sm text-gray-400')
                    ui.icon('help_outline', size='xs').classes('text-gray-600')\
                        .tooltip('Watchdog: expects periodic loop heartbeats. Reset nudges the timer (stub).')
                wd_state = ui.badge('ACTIVE', color='green-10').classes('font-bold text-[10px]')

            ui.button('WATCHDOG RESET', on_click=lambda: handle_control('WD_RESET')).props(btn_props()).classes('w-full border border-gray-700')
            ui.label().bind_text_from(state, 'watchdog_last_reset', lambda d: f"Last reset: {d.strftime('%H:%M:%S')}").classes('text-xs text-gray-500 -mt-2')

            def _update_wd_state() -> None:
                if state.watchdog_active:
                    wd_state.text = 'ACTIVE'
                    wd_state.props('color=green-10')
                else:
                    wd_state.text = 'STALE'
                    wd_state.props('color=orange-9')
            ui.timer(0.5, _update_wd_state)
            
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
            
            ui.button('KILL SWITCH', on_click=lambda: handle_control('KILL')).props('push color=red-10 text-color=white').classes('w-full py-6 mt-auto font-bold tracking-widest border border-red-900')

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
        with ui.element('div').props('id="cids-scale-root"').classes('p-6 bg-zinc-900 text-gray-300 font-mono gap-4 flex flex-col'):
        
            create_header(lambda: drawer.toggle())
        
            # Primary Grid (Takes remaining height)
            with ui.row().classes('w-full flex-grow min-h-0 gap-4'):
             
                # RADAR CHART (Left, 50%)
                with ui.card().classes('flex-1 min-w-0 h-full min-h-0 bg-zinc-900 border border-gray-700 rounded-none p-0 flex flex-col'):
                    with ui.row().classes('w-full border-b border-gray-800 p-2 justify-between items-center bg-zinc-950'):
                        ui.label('SYSTEM INTEGRITY').classes('text-xs font-bold text-gray-500')
                        ui.icon('radar', size='xs').classes('text-gray-600')
                    # Chart Container (Flex Grow)
                    with ui.column().classes('w-full flex-grow min-h-0 overflow-hidden'):
                        radar = create_integrity_diamond_chart()

                # RIGHT COLUMN (Bio-Rhythm + Density + System Log)
                with ui.column().classes('flex-1 min-w-0 h-full min-h-0 gap-4'):
                
                    # BIORHYTHM (Top Third)
                    with ui.card().classes('w-full h-1/3 min-h-0 bg-zinc-900 border border-gray-700 rounded-none p-0 flex flex-col'):
                        with ui.row().classes('w-full border-b border-gray-800 p-2 justify-between items-center bg-zinc-950'):
                            ui.label('RESOURCE METRICS').classes('text-xs font-bold text-gray-500')
                            with ui.row().classes('items-center gap-2'):
                                ui.icon('help_outline', size='xs').classes('text-gray-600')\
                                    .tooltip('Resource Metrics: CPU% (solid white) + MEM% (dotted gray). Sourced via psutil at 2Hz.')
                                ui.icon('query_stats', size='xs').classes('text-gray-600')
                        with ui.column().classes('w-full flex-grow min-h-0 overflow-hidden'):
                            biorhythm = create_biorhythm_chart()

                    # DENSITY HISTOGRAM (Middle Third)
                    with ui.card().classes('w-full h-1/3 min-h-0 bg-zinc-900 border border-gray-700 rounded-none p-0 flex flex-col'):
                        with ui.row().classes('w-full border-b border-gray-800 p-2 justify-between items-center bg-zinc-950'):
                            ui.label('DENSITY HISTOGRAM').classes('text-xs font-bold text-gray-500')
                            with ui.row().classes('items-center gap-2'):
                                ui.icon('help_outline', size='xs').classes('text-gray-600')\
                                    .tooltip('Density Histogram: relative collection volume over the last 12 time slices (normalized 0-100).')
                                ui.icon('bar_chart', size='xs').classes('text-gray-600')
                        with ui.column().classes('w-full flex-grow min-h-0 overflow-hidden'):
                            density = create_density_histogram_chart()
                
                    # SYSTEM LOG (Bottom Third)
                    with ui.card().classes('w-full h-1/3 min-h-0 bg-zinc-900 border border-gray-700 rounded-none p-0 flex flex-col'):
                        with ui.row().classes('w-full border-b border-gray-800 p-2 justify-between items-center bg-zinc-950'):
                            ui.label('SYSTEM LOG').classes('text-xs font-bold text-gray-500')
                            ui.icon('terminal', size='xs').classes('text-gray-600')

                        # No scrollbars: show only the most recent lines
                        with ui.column().classes('w-full flex-grow min-h-0 p-2 bg-black font-mono text-xs gap-1'):
                            log_labels: list[ui.label] = []
                            for line in state.log_lines[-7:]:
                                log_labels.append(ui.label(line).classes('text-gray-400 w-full'))
                            ui.label('>_').classes('text-gray-500 mt-1')

                def add_log(msg: str) -> None:
                    ts = datetime.now().strftime('%H:%M:%S')
                    line = f"{ts} {msg}"
                    state.log_lines.append(line)
                    state.log_lines = state.log_lines[-50:]

                    # Update visible labels (no scroll)
                    lines = state.log_lines[-7:]
                    for i in range(len(log_labels)):
                        log_labels[i].set_text(lines[i] if i < len(lines) else '')

    # --- UPDATE LOOP ---
    def update_sim_fallback():
        """Fallback simulation if telemetry sources are unavailable."""
        state.cpu_history.append(random.randint(10, 40) + (random.randint(0, 50) if random.random() > 0.9 else 0))
        state.cpu_history.pop(0)
        state.mem_history.append(random.randint(20, 30))
        state.mem_history.pop(0)
        state.availability_score = max(0, min(100, state.availability_score + random.randint(-5, 5)))
        state.records_collected += random.randint(0, 5)
        state.density_bins = state.density_bins[1:] + [max(0, min(100, int(random.gauss(40, 18))))]
        radar.options['series'][0]['data'][0]['value'] = [
            state.availability_score,
            state.integrity_score,
            state.capacity_score,
            state.freshness_score,
        ]
        radar.update()
        biorhythm.options['series'][0]['data'] = state.cpu_history
        biorhythm.options['series'][1]['data'] = state.mem_history
        biorhythm.update()
        density.options['series'][0]['data'] = state.density_bins
        density.update()

    def update_live():
        """Real telemetry update loop (file + heartbeat + psutil)."""
        try:
            snap = telemetry.update()

            # CPU/MEM -> histories
            state.cpu_history.append(int(max(0, min(100, snap.get('cpu', 0.0)))))
            state.cpu_history = state.cpu_history[-50:]
            state.mem_history.append(int(max(0, min(100, snap.get('mem', 0.0)))))
            state.mem_history = state.mem_history[-50:]

            # Records + density
            total = int(snap.get('total_records', 0))
            new = int(snap.get('new_records', 0))
            state.records_collected = total
            bins = snap.get('density_bins')
            if isinstance(bins, list) and len(bins) == len(state.density_bins):
                state.density_bins = [int(max(0, min(100, x))) for x in bins]

            # WD/OBS
            state.watchdog_active = bool(snap.get('watchdog_active', False))
            state.is_running = bool(snap.get('observer_active', False))

            # Update charts
            radar.options['series'][0]['data'][0]['value'] = [
                state.availability_score,
                state.integrity_score,
                state.capacity_score,
                state.freshness_score,
            ]
            radar.update()

            biorhythm.options['series'][0]['data'] = state.cpu_history
            biorhythm.options['series'][1]['data'] = state.mem_history
            biorhythm.update()

            density.options['series'][0]['data'] = state.density_bins
            density.update()

            # Status badge: tie to OBS + CPU
            latest_cpu = state.cpu_history[-1] if state.cpu_history else 0
            if not state.is_running:
                status_badge.text = 'CRITICAL'
                status_badge.props('color=red-10')
            elif latest_cpu >= 80:
                status_badge.text = 'DEGRADED'
                status_badge.props('color=orange-9')
            else:
                status_badge.text = 'NOMINAL'
                status_badge.props('color=green-10')

            # Add a low-noise log line only when new data arrives
            if new > 0:
                src = snap.get('active_jsonl_path')
                if src:
                    add_log(f"Ingested +{new} records ({Path(src).name})")
                else:
                    add_log(f"Ingested +{new} records")

        except Exception:
            update_sim_fallback()
            
    # Use ui.timer for client-side updates instead of app.on_startup
    ui.timer(0.5, update_live)

# --- EXECUTION CONFIG ---
# We use native=False to avoid pythonnet/pywebview dependency issues on Python 3.14
# The launcher script handles the "App Mode" window creation.
if __name__ in {"__main__", "__mp_main__"}:
    ui.run(
        native=False,
        port=8899, # Changed port to avoid zombie process conflicts
        title='CALAMUM OPS V2',
        dark=True,
        show=False, 
        reload=False
    )
