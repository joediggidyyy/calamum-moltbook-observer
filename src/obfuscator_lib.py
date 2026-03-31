import hashlib
import hmac
import json
import os
from typing import Dict, Any

__version__ = "1.1.0"


def _canonical_payload_bytes(payload: Dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(',', ':')).encode('utf-8')


def _role_signing_secret(role: str) -> bytes:
    role_token = str(role or 'default').strip().lower() or 'default'
    secret = _get_signing_secret()
    return hmac.new(secret, ('calamum-role:{0}'.format(role_token)).encode('utf-8'), hashlib.sha256).digest()


def payload_sha256(payload: Dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_payload_bytes(payload)).hexdigest()


def sign_detached_payload(payload: Dict[str, Any], *, role: str, purpose: str) -> Dict[str, Any]:
    role_token = str(role or 'default').strip().lower() or 'default'
    purpose_token = str(purpose or 'payload').strip() or 'payload'
    payload_bytes = _canonical_payload_bytes(payload)
    mac_payload = purpose_token.encode('utf-8') + b'\n' + payload_bytes
    signature = hmac.new(_role_signing_secret(role_token), mac_payload, hashlib.sha256).hexdigest()
    return {
        'algorithm': 'hmac-sha256',
        'role': role_token,
        'purpose': purpose_token,
        'payload_sha256': hashlib.sha256(payload_bytes).hexdigest(),
        'signature': signature,
    }


def verify_detached_payload(
    payload: Dict[str, Any],
    detached_signature: Dict[str, Any],
    *,
    expected_role: str,
    expected_purpose: str,
) -> bool:
    if not isinstance(detached_signature, dict):
        return False
    role_token = str(expected_role or 'default').strip().lower() or 'default'
    purpose_token = str(expected_purpose or 'payload').strip() or 'payload'
    if str(detached_signature.get('algorithm', '')).strip().lower() != 'hmac-sha256':
        return False
    if str(detached_signature.get('role', '')).strip().lower() != role_token:
        return False
    if str(detached_signature.get('purpose', '')).strip() != purpose_token:
        return False
    payload_bytes = _canonical_payload_bytes(payload)
    payload_digest = hashlib.sha256(payload_bytes).hexdigest()
    if str(detached_signature.get('payload_sha256', '')).strip() != payload_digest:
        return False
    mac_payload = purpose_token.encode('utf-8') + b'\n' + payload_bytes
    expected_signature = hmac.new(_role_signing_secret(role_token), mac_payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected_signature, str(detached_signature.get('signature', '')).strip())


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
