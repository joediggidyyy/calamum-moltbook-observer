import os
from pathlib import Path

def _find_repo_root(start: Path) -> Path:
    """Best-effort repo root discovery for consistent Calamum log locations.

    Preference order:
    1) directory containing `codesentinel.json`
    2) directory containing `.git/`
    3) directory containing `logs/`
    4) fallback to `start`
    """
    cur = start.resolve()
    for parent in [cur] + list(cur.parents):
        if (parent / 'codesentinel.json').exists():
            return parent
    for parent in [cur] + list(cur.parents):
        if (parent / '.git').exists():
            return parent
    for parent in [cur] + list(cur.parents):
        if (parent / 'logs').exists():
            return parent
    return cur


# Consolidate log directory logic.
# Convention: Default to repo-root `logs/` unless overridden.
# This can be injected via CALAMUM_LOG_DIR.

def get_calamum_log_dir() -> Path:
    """Return the base log directory for Calamum components.
    
    Priority:
    1. CALAMUM_LOG_DIR environment variable.
    2. repo-root 'logs/' (best-effort discovery)
    3. fallback to 'logs/' directory relative to this file (src/logs/).
    """
    env_val = os.getenv('CALAMUM_LOG_DIR')
    if env_val:
        return Path(env_val).resolve()

    repo_root = _find_repo_root(Path(__file__).resolve())
    repo_logs = repo_root / 'logs'
    if repo_logs.exists():
        return repo_logs

    # Fallback: src/logs/
    return Path(__file__).resolve().parent / 'logs'

def get_calamum_data_dir() -> Path:
    """Return the data subdirectory."""
    # Allow explicit override of data dir, or fall back to log_dir/data/calamum
    env_val = os.getenv('CALAMUM_DATA_DIR')
    if env_val:
        return Path(env_val).resolve()
    # Updated to enforce subdirectory per V2 Design
    return get_calamum_log_dir() / 'data' / 'calamum'

def get_calamum_control_dir() -> Path:
    """Return the control signal subdirectory."""
    env_val = os.getenv('CALAMUM_CONTROL_DIR')
    if env_val:
        return Path(env_val).resolve()
    return get_calamum_log_dir() / 'control' / 'calamum'

def get_calamum_health_dir() -> Path:
    """Return the health/heartbeat subdirectory."""
    return get_calamum_log_dir() / 'health'
