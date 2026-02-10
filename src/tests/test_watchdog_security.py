from __future__ import annotations

import sys
import json
import time
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure the Calamum observer `src/` directory is importable when tests run from repo root.
_SRC_DIR = Path(__file__).resolve().parents[1]
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

# Import target modules
import calamum_watchdog
import calamum_observer_agent
try:
    import obfuscator_lib
except ImportError:
    obfuscator_lib = None

def test_signed_heartbeat_lifecycle(tmp_path: Path, monkeypatch) -> None:
    """Verify Watchdog signs heartbeat and Agent verifies it correctly."""
    
    if not obfuscator_lib:
        return # Skip if deps missing

    # Setup Env
    log_dir = tmp_path / "logs"
    health_dir = log_dir / "health"
    health_dir.mkdir(parents=True)
    
    monkeypatch.setenv("CALAMUM_LOG_DIR", str(log_dir))
    monkeypatch.setenv("CALAMUM_DATA_SIGNING_KEY", "test-secret-key")
    
    # 1. Watchdog Creates Signed Heartbeat
    wd = calamum_watchdog.WatchdogSupervisor(interval_sec=0.1)
    wd.health_dir = health_dir
    wd.my_heartbeat = health_dir / "calamum_ops_watchdog.heartbeat"
    
    wd._touch_heartbeat()
    
    assert wd.my_heartbeat.exists()
    data = json.loads(wd.my_heartbeat.read_text("utf-8"))
    assert "signature" in data
    assert data["status"] == "alive"
    
    # 2. Agent Verifies Fresh & Signed Heartbeat
    # Mock 'time' to ensure freshness
    with patch("time.time", return_value=time.time()):
        is_alive = calamum_observer_agent._is_watchdog_alive(wd.my_heartbeat, max_age=10.0)
        assert is_alive is True

    # 3. Agent Rejects Stale Heartbeat
    # Simulate time jump
    future_time = time.time() + 60.0
    with patch("time.time", return_value=future_time):
        # We must ensure the file mtime is 'simulated' as old.
        # Since _is_watchdog_alive reads actual disk mtime, we can set the file mtime back.
        # OR, since we mocked time.time() to +60, the current disk mtime (set in step 1) is already old relative to 'future_time'.
        is_alive = calamum_observer_agent._is_watchdog_alive(wd.my_heartbeat, max_age=10.0)
        assert is_alive is False

    # 4. Agent Rejects Unsigned/Tampered Heartbeat
    # Tamper with the file
    data["status"] = "dead" # Change content without updating signature
    wd.my_heartbeat.write_text(json.dumps(data), "utf-8")
    
    is_alive = calamum_observer_agent._is_watchdog_alive(wd.my_heartbeat, max_age=10.0)
    assert is_alive is False

def test_keepalive_integration_mocked(tmp_path: Path, monkeypatch) -> None:
    """Verify Agent attempts to emit keepalive metrics."""
    # Mock the imported module in sys.modules so the agent picks up the mock
    mock_helper_cls = MagicMock()
    mock_instance = MagicMock()
    mock_helper_cls.return_value = mock_instance
    
    # Inject mock into Agent's namespace
    monkeypatch.setattr(calamum_observer_agent, "KeepaliveHelper", mock_helper_cls)
    monkeypatch.setenv("CALAMUM_STDOUT_KEEPALIVE_SEC", "1")
    
    # Setup Minimal Agent Config
    cfg = calamum_observer_agent.AgentConfig(
        repo_root=tmp_path,
        node_id="test-node",
        interval_sec=0.1,
        mode="canary",
        data_dir=tmp_path / "data",
        output_jsonl=tmp_path / "out.jsonl",
        control_dir=tmp_path / "control",
        observer_heartbeat=tmp_path / "hb",
        watchdog_heartbeat=None 
    )
    
    # We want to run one iteration.
    monkeypatch.setattr(calamum_observer_agent, "_touch", MagicMock())
    monkeypatch.setattr(calamum_observer_agent, "handle_control_signals", lambda c, n: (False, None))
    monkeypatch.setattr(calamum_observer_agent, "append_record", MagicMock())
    # Mock watchdog alive to TRUE so we don't get stuck in isolation logic printing to stderr only
    monkeypatch.setattr(calamum_observer_agent, "_is_watchdog_alive", lambda p, max_age: True)
    
    # Run 1 iteration
    calamum_observer_agent.run_agent(cfg, max_iterations=1)
    
    # Check if KeepaliveHelper was instantiated and used
    mock_helper_cls.assert_called_with("CalamumAgent", interval_seconds=1.0)
    mock_instance.emit.assert_called()
