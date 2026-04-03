import datetime
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

try:
    from calamum_config import get_calamum_control_dir
except ImportError:
    from ..calamum_config import get_calamum_control_dir

class CalamumController:
    """
    Interface for controlling the Calamum Moltbook Observer container.
    Wraps Docker commands and internal signaling.
    """
    
    def __init__(self):
        self.node_id = "calamum-node-01"

    def _find_repo_root(self) -> Path:
        """Best-effort repo root discovery.

        Preference order:
        1) directory containing `codesentinel.json`
        2) directory containing `.git/`
        3) directory containing `logs/`
        4) fallback to the directory containing this file

        Rationale: a local `src/logs/` directory may exist for legacy artifacts;
        we must not treat that as the workspace root.
        """
        cur = Path(__file__).resolve()
        for parent in [cur] + list(cur.parents):
            if (parent / 'codesentinel.json').exists():
                return parent
        for parent in [cur] + list(cur.parents):
            if (parent / '.git').exists():
                return parent
        for parent in [cur] + list(cur.parents):
            if (parent / 'logs').exists():
                return parent
        return cur.parent

    def _emit_signal(self, name: str, payload: Optional[dict] = None) -> Path:
        # Always use canonical Calamum control-dir resolution.
        # `get_calamum_control_dir()` already honors CALAMUM_CONTROL_DIR and
        # otherwise defaults to the Calamum project control plane.
        out_dir = get_calamum_control_dir()
        out_dir.mkdir(parents=True, exist_ok=True)

        ts = datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00', 'Z')
        record: Dict[str, Any] = {
            'ts': ts,
            'node_id': self.node_id,
            'signal': name,
        }
        if payload:
            record['payload'] = payload

        path = out_dir / f'{name}.signal.json'
        # Overwrite with latest intent; this is a control surface, not a ledger.
        path.write_text(json.dumps(record, indent=2, sort_keys=True), encoding='utf-8')
        return path
    
    def kill_signal(self):
        """
        Sends an emergency KILL signal to the observer process.
        Returns: Tuple (Success: bool, Message: str)
        """
        # Logic: Touch a .kill_switch file that the sentinel watches, 
        # or execute a docker kill command.
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00', 'Z')
        try:
            path = self._emit_signal('kill', {'requested_at': timestamp})
            return True, f"KILL signal staged ({path.name})"
        except Exception as e:
            return False, str(e)

    def isolate_node(self):
        """
        Cuts network access for the node (except Ops channel).
        """
        try:
            path = self._emit_signal('isolate', {'scope': 'ingress_only'})
            return True, f"Isolation signal staged ({path.name})"
        except Exception as e:
            return False, str(e)

    def force_refresh(self):
        """
        Triggers a log rotation and config reload.
        """
        try:
            path = self._emit_signal('refresh', {'kind': 'config_reload'})
            return True, f"Refresh signal staged ({path.name})"
        except Exception as e:
            return False, str(e)

    def reset_watchdog(self):
        """Request a watchdog reset.
        """
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00', 'Z')
        try:
            path = self._emit_signal('watchdog_reset', {'requested_at': timestamp})
            return True, f"Watchdog reset staged ({path.name})"
        except Exception as e:
            return False, str(e)

# Singleton instance
controller = CalamumController()
