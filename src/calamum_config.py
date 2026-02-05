import os
from pathlib import Path

# Consolidate log directory logic.
# Convention: Default to local 'logs/' directory within the src tree if not overridden.
# This variable can be injected via CALAMUM_LOG_DIR.

def get_calamum_log_dir() -> Path:
    """Return the base log directory for Calamum components.
    
    Priority:
    1. CALAMUM_LOG_DIR environment variable.
    2. 'logs/' directory relative to this file (src/logs/).
    """
    env_val = os.getenv('CALAMUM_LOG_DIR')
    if env_val:
        return Path(env_val).resolve()
    
    # Default to src/logs/
    # This file is in src/, so .parent is src/
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
    return get_calamum_log_dir() / 'control'

def get_calamum_health_dir() -> Path:
    """Return the health/heartbeat subdirectory."""
    return get_calamum_log_dir() / 'health'
