import hashlib
import hmac
import json
import os
import re
from typing import Any, Dict, Iterable, List

__version__ = "1.1.0"

_PACKET_VERSION = 'p1'
_VENUE_ID = 'moltbook'


def _content_signal_summary(content: str) -> Dict[str, Any]:
    text = str(content or '')
    links = re.findall(r'https?://\S+', text, re.IGNORECASE)
    code_markers = len(re.findall(r'```', text))
    words = re.findall(r'\b\w+\b', text)
    lines = text.splitlines()

    pattern_specs = [
        ('ignore_previous', r'ignore\s+(?:all\s+)?(?:previous|prior)'),
        ('system_prompt_reference', r'\bsystem\s+prompt\b'),
        ('developer_message_reference', r'\bdeveloper\s+message\b'),
        (
            'env_var_reference',
            r'(?:\$[A-Z_][A-Z0-9_]*|\$\{[A-Z_][A-Z0-9_]*\}|%[A-Z_][A-Z0-9_]*%|process\.env\.|os\.getenv\(|\.env\b|[A-Z][A-Z0-9_]{2,}_(?:KEY|TOKEN|SECRET|PASSWORD)\b)',
        ),
    ]

    matched_labels: List[str] = []
    for label, pattern in pattern_specs:
        if re.search(pattern, text, re.IGNORECASE):
            matched_labels.append(label)

    prompt_injection_score = sum(
        1
        for label in matched_labels
        if label in {'ignore_previous', 'system_prompt_reference', 'developer_message_reference'}
    )

    code_block_count = int((code_markers + 1) / 2) if code_markers else 0

    return {
        'content_length_words': len(words),
        'line_count': len(lines) if text else 0,
        'code_block_count': code_block_count,
        'has_link': bool(links),
        'link_count': len(links),
        'question_count': text.count('?'),
        'exclamation_count': text.count('!'),
        'contains_ignore_previous': 'ignore_previous' in matched_labels,
        'contains_system_prompt_reference': 'system_prompt_reference' in matched_labels,
        'contains_developer_message_reference': 'developer_message_reference' in matched_labels,
        'contains_env_var_reference': 'env_var_reference' in matched_labels,
        'prompt_injection_score': prompt_injection_score,
        'matched_pattern_labels': matched_labels,
        'matched_pattern_count': len(matched_labels),
    }


def _canonical_payload_bytes(payload: Dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(',', ':')).encode('utf-8')


_ROLE_SIGNING_ENV_NAMES = {
    'requester': 'CALAMUM_REQUESTER_SIGNING_KEY',
    'operator': 'CALAMUM_REQUESTER_SIGNING_KEY',
    'librarian': 'CALAMUM_LIBRARIAN_ATTESTATION_KEY',
    'source': 'CALAMUM_SOURCE_RELEASE_KEY',
    'vault': 'CALAMUM_LIBRARIAN_VAULT_KEY',
    'vault-integrity': 'CALAMUM_LIBRARIAN_VAULT_KEY',
}
_SHARED_SIGNING_ENV_NAME = 'CALAMUM_DATA_SIGNING_KEY'
_DEV_SIGNING_ENV_NAME = 'CALAMUM_ALLOW_DEV_SIGNING_KEY'


def role_signing_env_name(role: str) -> str:
    role_token = str(role or 'default').strip().lower() or 'default'
    return str(_ROLE_SIGNING_ENV_NAMES.get(role_token, '') or '')


def signing_env_presence(required_roles: Iterable[str] = ()) -> Dict[str, Any]:
    names: List[str] = []
    for role in required_roles:
        env_name = role_signing_env_name(str(role or ''))
        if env_name and env_name not in names:
            names.append(env_name)
    for env_name in (_SHARED_SIGNING_ENV_NAME, _DEV_SIGNING_ENV_NAME):
        if env_name not in names:
            names.append(env_name)

    present = False
    for env_name in names:
        if env_name == _DEV_SIGNING_ENV_NAME:
            if _bool_env(env_name):
                present = True
                break
            continue
        if str(os.getenv(env_name) or '').strip():
            present = True
            break

    return {
        'names': names,
        'present': present,
    }


def _role_signing_secret(role: str) -> bytes:
    role_token = str(role or 'default').strip().lower() or 'default'
    env_name = role_signing_env_name(role_token)
    role_secret = str(os.getenv(env_name) or '').strip() if env_name else ''
    if role_secret:
        return role_secret.encode('utf-8')
    secret = _get_signing_secret(required_role=role_token)
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


def _get_signing_secret(required_role: str = '') -> bytes:
    """Return the signing secret for telemetry signatures.

    Security posture:
    - In normal operation, CALAMUM_DATA_SIGNING_KEY is required for the shared
      compatibility root used by telemetry signing.
    - Detached librarian/requester/source/vault signatures may alternatively use
      role-specific keys when they are present.
    - For local/dev-only workflows, an insecure fallback may be enabled by
      setting CALAMUM_ALLOW_DEV_SIGNING_KEY=1.

    Never log the secret.
    """
    key = os.getenv(_SHARED_SIGNING_ENV_NAME)
    if key:
        return key.encode('utf-8')

    if _bool_env(_DEV_SIGNING_ENV_NAME):
        return b'dev-key-do-not-use-in-prod'

    role_env = role_signing_env_name(required_role)
    required_names = []
    if role_env:
        required_names.append(role_env)
    required_names.append(_SHARED_SIGNING_ENV_NAME)

    raise EnvironmentError(
        '{0} is required for signing/verification. For local dev only, set {1}=1 '
        'to use an insecure fallback.'.format(
            ' or '.join(required_names),
            _DEV_SIGNING_ENV_NAME,
        )
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
            "packet_family": "obs.content_item",
            "packet_version": _PACKET_VERSION,
            "venue_id": _VENUE_ID,
            "entity_kind": "content_item",
            "timestamp": sample.get("timestamp"),
            "type": sample.get("type", "unknown"),
            "content_length": len(sample.get("content", "")),
            "has_code_block": "```" in sample.get("content", ""),
            "author_hash": Obfuscator._hash(sample.get("author", "unknown")),
            # Metadata analysis
            "tags_count": len(sample.get("tags", [])),
            "mentions_count": len(sample.get("mentions", [])),
        }
        source_id = str(sample.get("id", "") or "").strip()
        if source_id:
            safe_record["source_id_hash"] = Obfuscator._hash(source_id)
        safe_record.update(_content_signal_summary(sample.get("content", "")))
        return safe_record
    
    @staticmethod
    def obfuscate_notification(notification: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handles inbound notifications (DM, Follow, Mention).
        Strictly strips DM content.
        """
        safe_record = {
            "packet_family": "obs.interaction_event",
            "packet_version": _PACKET_VERSION,
            "venue_id": _VENUE_ID,
            "entity_kind": "interaction_event",
            "timestamp": notification.get("timestamp"),
            "event_type": notification.get("event_type", "unknown"), # dm, follow, mention
            "sender_hash": Obfuscator._hash(notification.get("sender", "unknown")),
        }
        source_id = str(notification.get("id", "") or "").strip()
        if source_id:
            safe_record["source_id_hash"] = Obfuscator._hash(source_id)
        
        # Only log content metrics if it's a message-bearing event
        if "content" in notification:
            safe_record["content_length"] = len(notification.get("content", ""))
            safe_record.update(_content_signal_summary(notification.get("content", "")))
        
        return safe_record

    @staticmethod
    def _hash(val: str) -> str:
        return hashlib.sha256(val.encode("utf-8")).hexdigest()[:16]
