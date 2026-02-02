import hashlib
import json
from typing import Dict, Any

class Obfuscator:
    """
    Ensures ZERO context leakage from Moltbook telemetry.
    Strips raw text. Hashes identifiers. Retains structural metadata only.
    """
    
    @staticmethod
    def obfuscate_sample(sample: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transforms a raw sample into a safe, obfuscated record.
        """
        safe_record = {
            "timestamp": sample.get("timestamp"),
            "type": sample.get("type", "unknown"),
            "content_length": len(sample.get("content", "")),
            "has_code_block": "```" in sample.get("content", ""),
            "author_hash": Obfuscator._hash(sample.get("author", "unknown")),
            # Metadata analysis
            "tags_count": len(sample.get("tags", [])),
            "mentions_count": len(sample.get("mentions", [])),
        }
        return safe_record
    
    @staticmethod
    def obfuscate_notification(notification: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handles inbound notifications (DM, Follow, Mention).
        Strictly strips DM content.
        """
        safe_record = {
            "timestamp": notification.get("timestamp"),
            "event_type": notification.get("event_type", "unknown"), # dm, follow, mention
            "sender_hash": Obfuscator._hash(notification.get("sender", "unknown")),
        }
        
        # Only log content metrics if it's a message-bearing event
        if "content" in notification:
            safe_record["content_length"] = len(notification.get("content", ""))
            safe_record["has_link"] = "http" in notification.get("content", "")
        
        return safe_record

    @staticmethod
    def _hash(val: str) -> str:
        return hashlib.sha256(val.encode("utf-8")).hexdigest()[:16]
