"""Calamum Observer Agent (local, end-to-end wiring).

This is a lightweight daemon-style loop that:
- Touches observer + watchdog heartbeat markers
- Appends synthetic JSONL records to logs/data/calamum
- Consumes control signals emitted by the Ghost Console (logs/control/calamum/*.signal.json)

It is intended for local full-stack validation without Docker.
No secrets are required.
"""

from __future__ import annotations

__version__ = "1.1.0"

import argparse
import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, cast

# Local imports
try:
    import calamum_sampler
    import obfuscator_lib
    import stage4_features
    from calamum_keepalive import KeepaliveHelper
    from moltbook_client import MoltbookAPIClient
except ImportError:
    # Allow running even if siblings are tricky to import (e.g. specialized envs)
    calamum_sampler = None
    obfuscator_lib = None
    stage4_features = None
    KeepaliveHelper = None
    MoltbookAPIClient = None

from calamum_config import get_calamum_data_dir, get_calamum_control_dir, get_calamum_health_dir, ACTIVE_MAGNET_THRESHOLD


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def _normalize_source(source: str) -> str:
    s = (source or 'sim').strip().lower()
    if s == 'live':
        return 'real'
    if s in ('sim', 'real'):
        return s
    return 'sim'


def _posture_for_mode(mode: str) -> str:
    m = (mode or '').strip().lower()
    return 'lockdown' if m in ('live', 'honeypot') else 'isolation'


def _observer_output_jsonl_path(data_dir: Path, source: str, mode: str) -> Path:
    """Return the canonical observer-derived output path.

    Separation policy:
    - source scope is explicit (`sim` or `real`)
    - mode scope is explicit (`watch`/`canary`/`live`/`honeypot`)
    - file name remains stable so sim and real runs are structurally identical
    """
    src = _normalize_source(source)
    m = (mode or 'watch').strip().lower() or 'watch'
    return data_dir / 'observer_derived' / src / m / 'moltbook_metrics.jsonl'


def _load_ssot_route(control_dir: Path, fallback_source: str, fallback_mode: str) -> Tuple[str, str]:
    """Return runtime route from observerctl state (SSOT), with safe fallbacks."""
    src = _normalize_source(fallback_source)
    mode = (fallback_mode or 'watch').strip().lower() or 'watch'
    if mode not in ('watch', 'canary', 'live', 'honeypot', 'active-gated'):
        mode = 'watch'

    path = control_dir / 'observerctl_state.json'
    try:
        if path.exists():
            payload = json.loads(path.read_text(encoding='utf-8'))
            if isinstance(payload, dict):
                src = _normalize_source(str(payload.get('source', src) or src))
                cand_mode = str(payload.get('mode', mode) or mode).strip().lower().replace('_', '-')
                if cand_mode == 'activegated':
                    cand_mode = 'active-gated'
                if cand_mode in ('watch', 'canary', 'live', 'honeypot', 'active-gated'):
                    mode = cand_mode
    except Exception:
        pass

    return src, mode


def _record_linkage(control_dir: Path, mode: str) -> Dict[str, str]:
    ts = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    ctx_path = control_dir / 'observerctl_run_context.json'
    ctx: Dict[str, Any] = {}
    try:
        if ctx_path.exists():
            raw = json.loads(ctx_path.read_text(encoding='utf-8'))
            if isinstance(raw, dict):
                ctx = raw
    except Exception:
        ctx = {}

    run_id = (os.getenv('CALAMUM_RUN_ID') or str(ctx.get('run_id', '')) or '').strip()
    if not run_id:
        run_id = f"observer-agent-{ts}"

    posture_trigger_id = (os.getenv('CALAMUM_POSTURE_TRIGGER_ID') or str(ctx.get('posture_trigger_id', '')) or '').strip()
    if not posture_trigger_id:
        posture_trigger_id = f"pt-{(mode or 'watch').strip().lower()}-{ts}"

    security_report_ref = (os.getenv('CALAMUM_SECURITY_REPORT_REF') or str(ctx.get('security_report_ref', '')) or '').strip()

    return {
        'run_id': run_id,
        'posture_trigger_id': posture_trigger_id,
        'posture_trigger': _posture_for_mode(mode),
        'security_report_ref': security_report_ref,
    }


def _get_stdout_keepalive_interval_sec() -> float:
    """Return the stdout keepalive interval in seconds.

    0 disables keepalive.
    """
    raw = os.getenv('CALAMUM_STDOUT_KEEPALIVE_SEC', '60')
    try:
        val = float(raw)
        if val < 0:
            return 0.0
        return val
    except Exception:
        return 60.0


def _find_repo_root(start: Path) -> Path:
    cur = start.resolve()
    for parent in [cur] + list(cur.parents):
        if (parent / 'logs').exists():
            return parent
    return cur


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)


def _is_watchdog_alive(path: Optional[Path], max_age: float = 30.0) -> bool:
    if not path or not path.exists():
        return False
        
    try:
        # 1. Age Check (using filesystem metadata first for speed)
        mtime = path.stat().st_mtime
        if time.time() - mtime > max_age:
            # Stale file
            return False
            
        # 2. Signature Validation (Prevent Impersonation)
        if obfuscator_lib:
            try:
                data = json.loads(path.read_text(encoding='utf-8'))
                if not obfuscator_lib.Obfuscator.verify_record(data):
                    print(f"[{_utc_now_iso()}] [SECURITY] Watchdog heartbeat signature INVALID!", file=sys.stderr)
                    return False
            except Exception:
                # Malformed JSON or read error -> treat as dead/untrusted
                return False
                
        return True
    
    except Exception:
        return False


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return None


def _write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True), encoding='utf-8')


@dataclass
class AgentConfig:
    repo_root: Path
    node_id: str
    interval_sec: float
    mode: str

    # Paths
    data_dir: Path
    output_jsonl: Path
    control_dir: Path
    observer_heartbeat: Path
    watchdog_heartbeat: Optional[Path]

    # Data source (sim/live)
    source: str = "sim"


def load_config(
    argv_repo_root: Optional[str],
    mode: str,
    interval_sec: float,
    node_id: str,
    source: str = "sim",
) -> AgentConfig:
    # Use consolidated config
    data_dir = get_calamum_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)

    # We determine repo_root as best effort for back-compat or just use the parent of src
    if argv_repo_root:
        repo_root = Path(argv_repo_root).resolve()
    else:
        repo_root = Path(__file__).resolve().parents[1]

    src = _normalize_source(source)
    m = (mode or "").strip().lower()

    output_jsonl = _observer_output_jsonl_path(data_dir=data_dir, source=src, mode=m)

    control_dir = get_calamum_control_dir()
    control_dir.mkdir(parents=True, exist_ok=True)

    health_dir = get_calamum_health_dir()
    observer_heartbeat = Path(os.getenv(
        'CALAMUM_OBSERVER_HEARTBEAT_PATH',
        str(health_dir / 'calamum_observer.heartbeat'),
    ))
    # Watchdog responsibility: we monitor IT, it monitors US.
    watchdog_heartbeat = Path(os.getenv(
        'CALAMUM_WATCHDOG_HEARTBEAT_PATH',
        str(health_dir / 'calamum_ops_watchdog.heartbeat'),
    ))

    return AgentConfig(
        repo_root=repo_root,
        node_id=node_id,
        interval_sec=interval_sec,
        mode=mode,
        source=src,
        data_dir=data_dir,
        output_jsonl=output_jsonl,
        control_dir=control_dir,
        observer_heartbeat=observer_heartbeat,
        watchdog_heartbeat=watchdog_heartbeat,
    )


def handle_control_signals(control_dir: Path, node_id: str) -> Tuple[bool, Optional[str]]:
    """Handle control signals, returning (should_exit, note)."""

    mapping = {
        'kill.signal.json': 'kill',
        'isolate.signal.json': 'isolate',
        'refresh.signal.json': 'refresh',
        'watchdog_reset.signal.json': 'watchdog_reset',
    }

    if not control_dir.exists():
        return False, None

    for filename, sig_name in mapping.items():
        path = control_dir / filename
        if not path.exists():
            continue

        doc = _read_json(path)
        if not isinstance(doc, dict):
            # If unreadable, skip rather than crash.
            continue

        if doc.get('handled_at'):
            continue

        # Mark handled (idempotent)
        doc['handled_at'] = _utc_now_iso()
        doc['handled_by'] = node_id
        _write_json(path, doc)

        if sig_name == 'kill':
            return True, 'KILL received'
        if sig_name == 'isolate':
            # Local-only isolation marker for integrations to observe.
            _write_json(control_dir / 'isolation.state.json', {
                'ts': _utc_now_iso(),
                'node_id': node_id,
                'isolated': True,
            })
            return False, 'ISOLATE handled'
        if sig_name == 'refresh':
            # Agent is intentionally lightweight; treat refresh as an acknowledgement.
            # (Avoid coupling to runtime state here; run_agent may re-read env/config in future.)
            return False, 'REFRESH handled'
        if sig_name == 'watchdog_reset':
            return False, 'WATCHDOG_RESET handled'

    return False, None


_GEN_BY_KEY: Dict[str, Any] = {}
_BACKOFF_UNTIL_TS: Dict[str, float] = {}

# Live client cache (never logged; used to avoid re-creating sessions).
_LIVE_CLIENT: Any = None
_LIVE_CLIENT_HOST: str = ""
_LIVE_CLIENT_FP8: str = ""


def _get_live_client_best_effort() -> Optional[Any]:
    """Return a cached MoltbookAPIClient, or None if live mode is unavailable.

    Requirements:
    - MoltbookAPIClient importable
    - MOLTBOOK_API_KEY present
    """
    global _LIVE_CLIENT, _LIVE_CLIENT_HOST, _LIVE_CLIENT_FP8

    if MoltbookAPIClient is None:
        return None

    api_key = (os.getenv("MOLTBOOK_API_KEY") or "").strip()
    if not api_key:
        return None

    host = (os.getenv("MOLTBOOK_HOST") or "https://www.moltbook.com/api/v1").strip()
    try:
        fp8 = hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:8]
    except Exception:
        fp8 = ""

    if _LIVE_CLIENT is None or host != _LIVE_CLIENT_HOST or fp8 != _LIVE_CLIENT_FP8:
        _LIVE_CLIENT = MoltbookAPIClient(host, api_key)
        _LIVE_CLIENT_HOST = host
        _LIVE_CLIENT_FP8 = fp8
    return _LIVE_CLIENT


def _get_live_empty_backoff_sec() -> float:
    raw = os.getenv("CALAMUM_LIVE_EMPTY_BACKOFF_SEC", "10")
    try:
        v = float(raw)
        if v < 0:
            return 0.0
        return float(min(300.0, v))
    except Exception:
        return 10.0


def _get_live_batch_limit() -> int:
    raw = os.getenv("CALAMUM_LIVE_BATCH_LIMIT", "50")
    try:
        n = int(raw)
    except Exception:
        n = 50
    return int(max(1, min(200, n)))


def _get_next_item(mode: str, source: str = "sim") -> Optional[Dict[str, Any]]:
    """Return the next raw item for the configured mode.

    Stage mapping:
    - CANARY: inbound-only notifications (dm/follow/mention)
    - other modes: public feed samples (post/reply/repost)
    """
    m = (mode or '').strip().lower()
    src = _normalize_source(source)
    gen_key = f"{src}:{m or 'default'}"

    # Backoff when live returns empty (prevents hammering a dead endpoint).
    now = time.time()
    until = float(_BACKOFF_UNTIL_TS.get(gen_key, 0.0) or 0.0)
    if until and now < until:
        return None

    def _new_gen() -> Any:
        if src == "real":
            client = _get_live_client_best_effort()
            if not client:
                # Mode-based gate: API key is mandatory only for lockdown lanes.
                # For watch/canary we preserve operator motion by falling back to
                # simulator generators while keeping route semantics explicit.
                if m in ('live', 'honeypot'):
                    return None
                if not calamum_sampler:
                    return None
                sampler = cast(Any, calamum_sampler)
                if m == 'canary' and hasattr(sampler, 'simulate_moltbook_notifications'):
                    return sampler.simulate_moltbook_notifications()
                return sampler.simulate_moltbook_feed()
            if m == 'canary':
                return client.fetch_notifications()
            return client.fetch_feed(limit=_get_live_batch_limit())

        # Sim mode
        if not calamum_sampler:
            return None
        sampler = cast(Any, calamum_sampler)
        if m == 'canary' and hasattr(sampler, 'simulate_moltbook_notifications'):
            return sampler.simulate_moltbook_notifications()
        return sampler.simulate_moltbook_feed()

    # Stored as: { "gen": iterator_or_None, "yielded": int }
    state = _GEN_BY_KEY.get(gen_key)
    if not isinstance(state, dict):
        state = {"gen": None, "yielded": 0}

    for _ in range(2):
        gen = state.get("gen")
        if gen is None:
            state = {"gen": _new_gen(), "yielded": 0}
            gen = state.get("gen")
            if gen is None:
                _GEN_BY_KEY[gen_key] = state
                return None

        try:
            item = next(gen)
            state["yielded"] = int(state.get("yielded") or 0) + 1
            _GEN_BY_KEY[gen_key] = state
            return item
        except StopIteration:
            # Empty batch (no yields) => backoff in live mode.
            if src == "real" and int(state.get("yielded") or 0) == 0:
                backoff = _get_live_empty_backoff_sec()
                if backoff > 0:
                    _BACKOFF_UNTIL_TS[gen_key] = time.time() + float(backoff)
            state = {"gen": None, "yielded": 0}
            _GEN_BY_KEY[gen_key] = state
            continue
        except Exception:
            state = {"gen": None, "yielded": 0}
            _GEN_BY_KEY[gen_key] = state
            continue

    return None


def get_dynamic_rotation_limit(control_dir: Path) -> int:
    """Read the rotation policy or return default."""
    # Configurable fallback default (e.g. 50MB) rather than hardcoded 1KB for testing
    DEFAULT = 50 * 1024 * 1024 
    
    policy_path = control_dir / 'rotation_policy.json'
    if not policy_path.exists():
        return DEFAULT
        
    try:
        data = json.loads(policy_path.read_text(encoding='utf-8'))
        return data.get('max_bytes', DEFAULT)
    except Exception:
        return DEFAULT


def _rotation_prefix_for(path: Path) -> str:
    stem = (path.stem or "active").strip()
    if stem.endswith("_metrics"):
        stem = stem[: -len("_metrics")]
    return stem or "active"


def rotate_active_log(jsonl_path: Path, data_dir: Path) -> None:
    """Atomic rotation: Rename active -> archive/<prefix>_<ts>.jsonl"""
    archive_dir = data_dir / 'archive'
    archive_dir.mkdir(parents=True, exist_ok=True)
    
    ts_str = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
    prefix = _rotation_prefix_for(jsonl_path)
    new_name = f"{prefix}_{ts_str}.jsonl"
    dest = archive_dir / new_name
    
    try:
        # Atomic rename is fast
        jsonl_path.rename(dest)
    except OSError:
        # If open or locked, we might fail. 
        # But we use atomic 'with open' for writes, so file should be closed here.
        pass


def append_record(
    jsonl_path: Path,
    node_id: str,
    mode: str,
    control_dir: Path,
    data_dir: Path,
    source: str = "sim",
) -> None:
    # 0. Check Rotation FIRST
    if jsonl_path.exists():
        try:
            size = jsonl_path.stat().st_size
            limit = get_dynamic_rotation_limit(control_dir)
            if size >= limit:
                rotate_active_log(jsonl_path, jsonl_path.parent)
        except OSError:
            pass # Skipping rotation check on stat fail

    # 1. Get raw item
    raw = _get_next_item(mode, source=source)
    if not raw:
        # Fallback if sampler unavailable
        return

    # 2. Obfuscate & Sign
    if obfuscator_lib:
        try:
            if (mode or '').strip().lower() == 'canary':
                # Stage 3: strict inbound-only schema
                record = obfuscator_lib.Obfuscator.obfuscate_notification(raw)
                # Preserve a stable "type" field for downstream consumers that
                # expect it, while retaining the canonical event_type.
                if 'type' not in record and 'event_type' in record:
                    record['type'] = record.get('event_type', 'unknown')
            else:
                record = obfuscator_lib.Obfuscator.obfuscate_sample(raw)

            content_text = str(raw.get('content', '') or '')
            if stage4_features and ((mode or '').strip().lower() != 'canary' or content_text):
                try:
                    record.update(
                        stage4_features.extract_stage4_features(
                            content_text,
                            str(raw.get('timestamp', '') or ''),
                        )
                    )
                except Exception:
                    pass

            record = obfuscator_lib.Obfuscator.sign_record(record)
        except Exception:
            # Code safety: fail safe if obfuscation crashes
            return
    else:
        record = raw

    # Envelope
    record['node_id'] = node_id
    record['mode'] = mode.upper()
    if (mode or '').strip().lower() == 'canary':
        record['kind'] = 'obfuscated_inbound_event'
    else:
        record['kind'] = 'obfuscated_content'
    # Ensure timestamp is preserved or added
    if 'ts' not in record:
        record['ts'] = _utc_now_iso()

    linkage = _record_linkage(control_dir, mode)
    record['run_id'] = linkage.get('run_id', '')
    record['posture_trigger_id'] = linkage.get('posture_trigger_id', '')
    record['posture_trigger'] = linkage.get('posture_trigger', '')
    record['security_report_ref'] = linkage.get('security_report_ref', '')

    # 3. Atomic Write (Context Manager)
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with jsonl_path.open('a', encoding='utf-8') as f:
            f.write(json.dumps(record) + '\n')
    except OSError:
        # Handle file locking or permission transient errors
        pass


def run_agent(cfg: AgentConfig, max_iterations: Optional[int] = None) -> int:
    i = 0
    # Health log path (separated from data)
    health_log = get_calamum_health_dir() / 'calamum_observer.heartbeat.jsonl'

    # Initialize shared keepalive helper (if available)
    keepalive_helper = None
    if KeepaliveHelper:
        interval = _get_stdout_keepalive_interval_sec()
        if interval > 0:
            keepalive_helper = KeepaliveHelper("CalamumAgent", interval_seconds=interval)

    while True:
        # Route is controlled by observerctl SSOT state. The agent follows it
        # on every loop so data writes cannot drift into a stale lane.
        ssot_source, ssot_mode = _load_ssot_route(cfg.control_dir, cfg.source, cfg.mode)
        if ssot_source != cfg.source or ssot_mode != cfg.mode:
            cfg.source = ssot_source
            cfg.mode = ssot_mode
            cfg.output_jsonl = _observer_output_jsonl_path(cfg.data_dir, cfg.source, cfg.mode)
            print(
                f"[{_utc_now_iso()}] [ROUTE] observerctl SSOT route -> source={cfg.source} mode={cfg.mode}",
                file=sys.stderr,
            )

        # Operator-friendly liveness signal (stdout; rate-limited)
        if keepalive_helper:
            out_size = None
            out_age_s = None
            try:
                if cfg.output_jsonl.exists():
                    st = cfg.output_jsonl.stat()
                    out_size = int(st.st_size)
                    out_age_s = round(max(0.0, time.time() - float(st.st_mtime)), 1)
            except Exception:
                pass
            
            metrics = {
                "mode": cfg.mode.upper(),
                "source": (cfg.source or "sim").upper(),
                "tick": i,
                "out_size": out_size,
                "age_s": out_age_s
            }
            keepalive_helper.emit("RUNNING", metrics)

        # Heartbeats (File Touch)
        _touch(cfg.observer_heartbeat)
        
        # STAGE 4: Active Magnet Gating Check
        if cfg.mode == 'active-gated':
            # This verifies the threshold is loaded and consulted.
            # Since strict Read-Only is enforced, we log the gating decision.
            print(f"[{_utc_now_iso()}] [STAGE4] Gating Check: Threshold {ACTIVE_MAGNET_THRESHOLD} active. Status: MONITORING (Read-Only)", file=sys.stderr)

        # Security: Verify Watchdog Presence (Isolation Logic)
        # If Watchdog is dead or missing, we must Isolate (stop emitting data).
        watchdog_ok = _is_watchdog_alive(cfg.watchdog_heartbeat, max_age=45.0)
        
        # Heartbeats (Log - separated)
        try:
            health_log.parent.mkdir(parents=True, exist_ok=True)
            status_str = 'alive' if watchdog_ok else 'isolated_no_watchdog'
            with health_log.open('a', encoding='utf-8') as f:
                f.write(json.dumps({
                    'ts': _utc_now_iso(),
                    'node_id': cfg.node_id, 
                    'status': status_str,
                    'uptime_ticks': i
                }) + '\n')
        except Exception:
            pass

        # Consume control signals
        should_exit, note = handle_control_signals(cfg.control_dir, cfg.node_id)
        if note:
            # Log significant events to stdout/stderr
            print(f"[{_utc_now_iso()}] CONTROL: {note}", file=sys.stderr)
            
        if should_exit:
            return 0

        # Emit a sample record (Real Data) - ONLY if Watchdog is healthy
        if watchdog_ok:
            append_record(
                cfg.output_jsonl,
                cfg.node_id,
                cfg.mode,
                cfg.control_dir,
                cfg.data_dir,
                source=cfg.source,
            )
        else:
            # Rate-limited whine about isolation
            if i % 10 == 0:
                print(f"[{_utc_now_iso()}] [ISOLATION] Watchdog missing/stale. Data emission paused.", file=sys.stderr)

        i += 1
        if max_iterations is not None and i >= max_iterations:
            return 0

        time.sleep(cfg.interval_sec)


def main() -> int:
    parser = argparse.ArgumentParser(description='Calamum Observer Agent (local daemon)')
    parser.add_argument('--repo-root', help='Override repo root (must contain logs/)')
    parser.add_argument('--mode', default=os.getenv('CALAMUM_OPS_MODE', 'canary'))
    parser.add_argument('--source', default=_normalize_source(os.getenv('CALAMUM_MOLTBOOK_SOURCE', 'sim')), choices=['sim', 'real', 'live'])
    parser.add_argument('--interval-sec', type=float, default=float(os.getenv('CALAMUM_AGENT_INTERVAL_SEC', '2.0')))
    parser.add_argument('--node-id', default=os.getenv('CALAMUM_NODE_ID', 'calamum-node-01'))
    parser.add_argument('--max-iterations', type=int, help='For tests: stop after N iterations')
    args = parser.parse_args()

    cfg = load_config(args.repo_root, args.mode, args.interval_sec, args.node_id, source=args.source)
    return run_agent(cfg, max_iterations=args.max_iterations)


if __name__ == '__main__':
    raise SystemExit(main())
