import pytest
import sys
import os
from pathlib import Path

# Add src to python path so tests can run relative or absolute
current_dir = Path(__file__).resolve().parent
src_dir = current_dir.parent
if str(src_dir) not in sys.path:
    sys.path.append(str(src_dir))

from obfuscator_lib import Obfuscator

def test_obfuscate_sample_strips_content():
    """Verify that sample content is stripped and structure preserved."""
    raw_sample = {
        "timestamp": "2023-01-01T00:00:00",
        "author": "sensitive_user",
        "type": "post",
        "content": "This is a sensitive message with ```code```",
        "tags": ["tag1", "tag2"],
        "mentions": ["@user"]
    }

    safe = Obfuscator.obfuscate_sample(raw_sample)

    assert "content" not in safe
    assert safe["timestamp"] == raw_sample["timestamp"]
    assert safe["type"] == raw_sample["type"]
    assert safe["content_length"] == len(raw_sample["content"])
    assert safe["has_code_block"] is True
    assert safe["tags_count"] == 2
    assert safe["mentions_count"] == 1
    # Check author is hashed
    assert safe["author_hash"] != raw_sample["author"]
    assert len(safe["author_hash"]) == 16  # sha256 truncated

def test_obfuscate_sample_defaults():
    """Verify handling of missing fields."""
    raw_sample = {}
    safe = Obfuscator.obfuscate_sample(raw_sample)

    assert safe["type"] == "unknown"
    assert safe["content_length"] == 0
    assert safe["has_code_block"] is False
    assert safe["tags_count"] == 0

def test_obfuscate_notification():
    """Verify notification obfuscation."""
    raw_notif = {
        "timestamp": "2023-01-01T00:00:00",
        "sender": "sensitive_sender",
        "event_type": "dm",
        "content": "Secret DM with http://link.com"
    }

    safe = Obfuscator.obfuscate_notification(raw_notif)

    assert "content" not in safe
    assert safe["event_type"] == "dm"
    assert safe["sender_hash"] != raw_notif["sender"]
    assert safe["content_length"] > 0
    assert safe["has_link"] is True

def test_obfuscate_notification_passive_event():
    """Verify passive events (follow) don't have content metrics."""
    raw_notif = {
        "timestamp": "2023-01-01T00:00:00",
        "sender": "fan_user",
        "event_type": "follow"
    }

    safe = Obfuscator.obfuscate_notification(raw_notif)

    assert safe["event_type"] == "follow"
    assert "content_length" not in safe
    assert "has_link" not in safe
