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

def test_sign_record():
    """Verify digital signature generation."""
    record = {"foo": "bar", "val": 123}
    
    # Sign it
    signed = Obfuscator.sign_record(record)
    
    # Structure
    assert "signature" in signed
    assert signed["foo"] == "bar"
    
    # Determinism
    signed2 = Obfuscator.sign_record(record)
    assert signed["signature"] == signed2["signature"]
    
    # Tamper check (signature fails if data changes? 
    # Note: verify method not currently exposed, but we can verify different data yields different sig)
    record2 = {"foo": "baz", "val": 123}
    signed3 = Obfuscator.sign_record(record2)
    assert signed["signature"] != signed3["signature"]

def test_verify_record():
    """Verify signature validation."""
    record = {"foo": "bar"}
    signed = Obfuscator.sign_record(record)
    
    # Valid
    assert Obfuscator.verify_record(signed) is True
    
    # Tampered data
    tampered = signed.copy()
    tampered["foo"] = "baz"
    assert Obfuscator.verify_record(tampered) is False
    
    # Tampered signature
    tampered_sig = signed.copy()
    tampered_sig["signature"] = "deadbeef"
    assert Obfuscator.verify_record(tampered_sig) is False
    
    # No signature
    assert Obfuscator.verify_record(record) is False

def test_sign_record_custom_key():
    """Verify environment key changes signature."""
    record = {"foo": "bar"}
    
    os.environ['CALAMUM_DATA_SIGNING_KEY'] = 'key1'
    sig1 = Obfuscator.sign_record(record)['signature']
    
    os.environ['CALAMUM_DATA_SIGNING_KEY'] = 'key2'
    sig2 = Obfuscator.sign_record(record)['signature']
    
    assert sig1 != sig2
    
    # Cleanup env
    del os.environ['CALAMUM_DATA_SIGNING_KEY']
