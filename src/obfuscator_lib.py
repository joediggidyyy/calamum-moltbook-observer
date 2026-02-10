import hashlib
import hmac
import json
import os
from typing import Dict, Any

__version__ = "1.1.0"


def _bool_env(name: str) -> bool:
    val = (os.getenv(name) or '').strip().lower()
    return val in {'1', 'true', 'yes', 'y', 'on'}


def _get_signing_secret() -> bytes:
    """Return the signing secret for telemetry signatures.

    Security posture:
    - In normal operation, CALAMUM_DATA_SIGNING_KEY is required.
    - For local/dev-only workflows, an insecure fallback may be enabled by
      setting CALAMUM_ALLOW_DEV_SIGNING_KEY=1.

    Never log the secret.
    """
    key = os.getenv('CALAMUM_DATA_SIGNING_KEY')
    if key:
        return key.encode('utf-8')

    if _bool_env('CALAMUM_ALLOW_DEV_SIGNING_KEY'):
        return b'dev-key-do-not-use-in-prod'

    raise EnvironmentError(
        'CALAMUM_DATA_SIGNING_KEY is required for signing/verification. '
        'For local dev only, set CALAMUM_ALLOW_DEV_SIGNING_KEY=1 to use an insecure fallback.'
    )


class Obfuscator:
    """
    Ensures ZERO context leakage from Moltbook telemetry.
    Strips raw text. Hashes identifiers. Retains structural metadata only.
    """
    
    @staticmethod
    def sign_record(record: Dict[str, Any]) -> Dict[str, Any]:
        """
        Appends a cryptographic signature to the record to prove authenticity.
        Uses HMAC-SHA256 with CALAMUM_DATA_SIGNING_KEY.
        """
        secret = _get_signing_secret()
        
        # Sort keys for deterministic signature
        payload = json.dumps(record, sort_keys=True).encode('utf-8')
        signature = hmac.new(secret, payload, hashlib.sha256).hexdigest()
        
        # Return a new dict to avoid side effects if caller reuses record
        signed = record.copy()
        signed['signature'] = signature
        return signed

    @staticmethod
    def verify_record(signed_record: Dict[str, Any]) -> bool:
        """
        Verifies the cryptographic signature of a record.
        """
        if 'signature' not in signed_record:
            return False

        secret = _get_signing_secret()
        
        # separate signature from payload
        payload_data = signed_record.copy()
        expected_sig = payload_data.pop('signature')
        
        # recreate signature
        payload = json.dumps(payload_data, sort_keys=True).encode('utf-8')
        calculated_sig = hmac.new(secret, payload, hashlib.sha256).hexdigest()
        
        return hmac.compare_digest(calculated_sig, expected_sig)

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
