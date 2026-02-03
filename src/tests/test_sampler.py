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

