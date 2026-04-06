from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from ._util import JsonlLine, iter_jsonl, stable_record_id, utc_now_iso


FORBIDDEN_KEYS: Set[str] = {
    # Raw semantic payload (never allowed)
    'content',
    'message',
    'text',
    'body',
    'prompt',
    'system_prompt',
    'raw',
}


@dataclass
class ValidationSummary:
    input_path: str
    created_at_utc: str
    total_lines: int
    ok_records: int
    error_lines: int
    forbidden_key_hits: int
    signature_present: int
    signature_verified: int
    signature_failed: int
    unknown_keys: int
    unknown_keys_examples: List[str]


def _try_import_obfuscator() -> Optional[Any]:
    """Import Obfuscator from src root without assuming packaging."""
    try:
        # The test harness typically injects src into sys.path already.
        from obfuscator_lib import Obfuscator  # type: ignore

        return Obfuscator
    except Exception:
        return None


def validate_jsonl_file(
    input_path: Path,
    *,
    strict_unknown_keys: bool = False,
    allowed_keys: Optional[Set[str]] = None,
    verify_signatures: bool = False,
    max_lines: Optional[int] = None,
) -> Tuple[ValidationSummary, List[str]]:
    """Validate a JSONL file.

    Returns (summary, errors).

    Notes:
    - This validator is intentionally stdlib-only.
    - It always blocks forbidden keys (semantic payload).
    - When enabled, signature verification uses `CALAMUM_DATA_SIGNING_KEY`.
    """
    errs: List[str] = []
    unknown_examples: List[str] = []
    unknown_count = 0
    forbidden_hits = 0
    sig_present = 0
    sig_verified = 0
    sig_failed = 0
    ok = 0
    total = 0
    error_lines = 0

    Obfuscator = _try_import_obfuscator()
    if verify_signatures and Obfuscator is None:
        errs.append('signature verification requested but obfuscator_lib.Obfuscator could not be imported')

    for jl in iter_jsonl(input_path, max_lines=max_lines):
        total += 1
        if jl.error is not None or jl.obj is None:
            error_lines += 1
            errs.append(f'{input_path.name}:{jl.line_no}: {jl.error}')
            continue

        rec = jl.obj

        # Forbidden keys (privacy gate)
        hit = False
        for k in FORBIDDEN_KEYS:
            if k in rec:
                forbidden_hits += 1
                hit = True
        if hit:
            error_lines += 1
            errs.append(f'{input_path.name}:{jl.line_no}: forbidden_raw_payload_key')
            continue

        # Unknown keys (optional strictness)
        if allowed_keys is not None:
            extra = sorted([k for k in rec.keys() if k not in allowed_keys])
            if extra:
                unknown_count += len(extra)
                if len(unknown_examples) < 10:
                    unknown_examples.extend(extra[: max(0, 10 - len(unknown_examples))])
                if strict_unknown_keys:
                    error_lines += 1
                    errs.append(f'{input_path.name}:{jl.line_no}: unknown_keys={",".join(extra[:5])}')
                    continue

        # Signature verification (optional)
        if 'signature' in rec:
            sig_present += 1
            if verify_signatures and Obfuscator is not None:
                try:
                    if Obfuscator.verify_record(rec):
                        sig_verified += 1
                    else:
                        sig_failed += 1
                        error_lines += 1
                        errs.append(f'{input_path.name}:{jl.line_no}: signature_invalid')
                        continue
                except Exception:
                    sig_failed += 1
                    error_lines += 1
                    errs.append(f'{input_path.name}:{jl.line_no}: signature_check_error')
                    continue

        # Basic sanity: stable id computable
        _ = stable_record_id(rec)

        ok += 1

    summary = ValidationSummary(
        input_path=str(input_path),
        created_at_utc=utc_now_iso(),
        total_lines=total,
        ok_records=ok,
        error_lines=error_lines,
        forbidden_key_hits=forbidden_hits,
        signature_present=sig_present,
        signature_verified=sig_verified,
        signature_failed=sig_failed,
        unknown_keys=unknown_count,
        unknown_keys_examples=sorted(list(dict.fromkeys(unknown_examples))),
    )
    return summary, errs


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description='Validate Calamum obfuscated JSONL telemetry (names-only).')
    p.add_argument('--input', required=True, type=Path, help='Path to JSONL telemetry file')
    p.add_argument('--max-lines', type=int, default=None, help='Optional line cap for sampling/CI')
    p.add_argument('--verify-signatures', action='store_true', help='Verify HMAC signature if present')
    p.add_argument('--strict-unknown-keys', action='store_true', help='Fail if unknown keys are present')
    p.add_argument('--json', action='store_true', help='Emit JSON summary')
    args = p.parse_args(argv)

    # Allowed keys list (union; tolerate new keys unless strict is set)
    allowed = {
        'timestamp', 'ts',
        'type', 'event_type',
        'packet_family', 'packet_version', 'venue_id', 'entity_kind',
        'source_id_hash',
        'author_hash', 'sender_hash',
        'content_length', 'content_length_words',
        'has_code_block', 'code_block_count',
        'has_link', 'link_count',
        'tags_count', 'mentions_count',
        'line_count', 'question_count', 'exclamation_count',
        'contains_ignore_previous', 'contains_system_prompt_reference',
        'contains_developer_message_reference', 'contains_env_var_reference',
        'prompt_injection_score', 'matched_pattern_labels', 'matched_pattern_count',
        'f_complexity', 'f_code_density', 'f_toxicity', 'f_timestamp_epoch',
        'node_id', 'mode', 'kind',
        'signature',
        'tv_id',
    }

    summary, errors = validate_jsonl_file(
        args.input,
        strict_unknown_keys=bool(args.strict_unknown_keys),
        allowed_keys=allowed,
        verify_signatures=bool(args.verify_signatures),
        max_lines=args.max_lines,
    )

    if args.json:
        print(json.dumps({'summary': asdict(summary), 'errors': errors[:50]}, indent=2, sort_keys=True))
    else:
        print(f"[validate_jsonl] input={args.input.name} ok={summary.ok_records} errors={summary.error_lines}")
        if errors:
            for e in errors[:20]:
                print(f"  - {e}")
            if len(errors) > 20:
                print(f"  ... ({len(errors) - 20} more)")

    return 0 if summary.error_lines == 0 else 2


if __name__ == '__main__':
    raise SystemExit(main())
