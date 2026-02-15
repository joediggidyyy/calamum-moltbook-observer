import os
from pathlib import Path

def _find_repo_root(start: Path) -> Path:
    """Best-effort Calamum *project* root discovery.

    The Calamum operational root is intentionally the project root
    (`projects/calamum-moltbook-observer/`), not the workspace root.

    Preference order:
      1) CALAMUM_REPO_ROOT (explicit override)
      2) directory containing `PROJECT_MANIFEST.json` (Calamum project marker)
      3) directory containing `logs/` (project-local logs)
      4) fallback to workspace-level repo markers (`codesentinel.json`, `.git/`)
      5) fallback to `start`
    """
    env_root = os.getenv('CALAMUM_REPO_ROOT')
    if env_root:
        try:
            p = Path(env_root).resolve()
            if p.exists():
                return p
        except Exception:
            pass

    cur = start.resolve()

    # Project-first markers
    for parent in [cur] + list(cur.parents):
        if (parent / 'PROJECT_MANIFEST.json').exists():
            return parent
    for parent in [cur] + list(cur.parents):
        if (parent / 'logs').exists() and (parent / 'src').exists():
            return parent

    # Workspace-level fallbacks (for dev/test)
    for parent in [cur] + list(cur.parents):
        if (parent / 'codesentinel.json').exists():
            return parent
    for parent in [cur] + list(cur.parents):
        if (parent / '.git').exists():
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
    3. (no src-local fallback) return the discovered repo-root logs path even if it does not exist yet.
    """
    env_val = os.getenv('CALAMUM_LOG_DIR')
    if env_val:
        return Path(env_val).resolve()

    repo_root = _find_repo_root(Path(__file__).resolve())
    return (repo_root / 'logs')

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

# Blind ML Configuration
# Threshold for Active Magnet Gating (Stage 4)
# Selected via Run 001 (Canary V1)
_DEFAULT_ACTIVE_MAGNET_THRESHOLD = -0.0451  # <1% FPR on benign baseline (Canary V1)


def _float_env(name: str):
    """Parse a float from an env var.

    Returns None when unset or unparsable.
    """
    val = os.getenv(name)
    if val is None:
        return None
    val = val.strip()
    if not val:
        return None
    try:
        return float(val)
    except ValueError:
        return None


# Allow deployment to pin/override the gating threshold without editing source.
# Prefer namespaced env var, but accept legacy name for compatibility.
_env_threshold = _float_env('CALAMUM_ACTIVE_MAGNET_THRESHOLD')
if _env_threshold is None:
    _env_threshold = _float_env('ACTIVE_MAGNET_THRESHOLD')

ACTIVE_MAGNET_THRESHOLD = (
    _env_threshold if _env_threshold is not None else _DEFAULT_ACTIVE_MAGNET_THRESHOLD
)
