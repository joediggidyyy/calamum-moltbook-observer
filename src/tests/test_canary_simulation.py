import pytest
import sys
from pathlib import Path

# Add src to python path
current_dir = Path(__file__).resolve().parent
src_dir = current_dir.parent
if str(src_dir) not in sys.path:
    sys.path.append(str(src_dir))

from calamum_sampler import simulate_moltbook_notifications

def test_simulate_notifications_generation():
    """Verify notification simulation yields correct structure."""
    notifications = list(simulate_moltbook_notifications())
    assert len(notifications) == 10
    
    sample = notifications[0]
    assert "timestamp" in sample
    assert "sender" in sample
    assert "event_type" in sample
    assert sample["event_type"] in ["dm", "mention", "follow"]
    
    if sample["event_type"] in ["dm", "mention"]:
        assert "content" in sample

def test_simulate_notifications_randomness():
    """Verify that we get varied notifications."""
    notifications = list(simulate_moltbook_notifications())
    senders = set(n["sender"] for n in notifications)
    types = set(n["event_type"] for n in notifications)
    
    # We expect variability in a batch of 10
    assert len(senders) > 1 
    assert len(types) > 1
