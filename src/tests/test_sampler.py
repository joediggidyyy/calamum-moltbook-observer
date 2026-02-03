import pytest
import sys
from pathlib import Path

# Add src to python path
current_dir = Path(__file__).resolve().parent
src_dir = current_dir.parent
if str(src_dir) not in sys.path:
    sys.path.append(str(src_dir))

from calamum_sampler import simulate_moltbook_feed, simulate_moltbook_notifications

def test_simulate_feed_generation():
    """Verify feed simulation yields correct structure and count."""
    feed = list(simulate_moltbook_feed())
    assert len(feed) == 50
    
    sample = feed[0]
    assert "timestamp" in sample
    assert "author" in sample
    assert "content" in sample
    assert "type" in sample
    assert sample["type"] in ["post", "reply", "repost"]

def test_simulate_feed_randomness():
    """Verify that we get different entries."""
    feed = list(simulate_moltbook_feed())
    authors = set(f["author"] for f in feed)
    contents = set(f["content"] for f in feed)
    
    # Should be more than 1 author and content type picked
    assert len(authors) > 1
    assert len(contents) > 1

def test_simulate_notifications():
    """Verify notification simulation yields correct structure."""
    notifs = list(simulate_moltbook_notifications())
    assert len(notifs) == 10
    
    sample = notifs[0]
    assert "event_type" in sample
    assert "sender" in sample
    
    # Check conditional content logic
    dm_samples = [n for n in notifs if n["event_type"] in ["dm", "mention"]]
    for dm in dm_samples:
        assert "content" in dm

    follow_samples = [n for n in notifs if n["event_type"] == "follow"]
    for follow in follow_samples:
        # Follow events in this sim code don't seem to add content.
        # Let's verify that based on the code reading:
        # if evt_type in ["dm", "mention"]: notification["content"] = ...
        assert "content" not in follow
