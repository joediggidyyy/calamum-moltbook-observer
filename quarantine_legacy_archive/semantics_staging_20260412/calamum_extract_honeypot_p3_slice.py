from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List


def _parse_iso8601(value: str) -> datetime:
    text = str(value or '').strip()
    if text.endswith('Z'):
        text = text[:-1] + '+00:00'
    return datetime.fromisoformat(text).astimezone(timezone.utc)


def _iter_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    with path.open('r', encoding='utf-8') as handle:
        for line in handle:
            if not line.strip():
                continue
            yield json.loads(line)


def main() -> int:
    parser = argparse.ArgumentParser(description='Extract a bounded honeypot P3 slice from the canonical metrics route.')
    parser.add_argument('--input', required=True)
    parser.add_argument('--start-ts', required=True)
    parser.add_argument('--output-dir', required=True)
    args = parser.parse_args()

    input_path = Path(args.input).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    start_ts = _parse_iso8601(args.start_ts)
    stop_ts = datetime.now(timezone.utc)

    rows: List[Dict[str, Any]] = []
    for row in _iter_jsonl(input_path):
        ts_text = str(row.get('ts', '') or '').strip()
        if not ts_text:
            continue
        try:
            row_ts = _parse_iso8601(ts_text)
        except Exception:
            continue
        if row_ts < start_ts or row_ts > stop_ts:
            continue
        rows.append(row)

    slice_path = output_dir / 'honeypot_slice.jsonl'
    with slice_path.open('w', encoding='utf-8') as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + '\n')

    write_ts_values = [str(row.get('ts', '') or '').strip() for row in rows if str(row.get('ts', '') or '').strip()]
    source_ts_values = [str(row.get('timestamp', '') or '').strip() for row in rows if str(row.get('timestamp', '') or '').strip()]
    source_ids = sorted({str(row.get('source_id_hash', '') or '').strip() for row in rows if str(row.get('source_id_hash', '') or '').strip()})

    manifest = {
        'slice_kind': 'honeypot_p3_candidate_input',
        'input_path': str(input_path).replace('\\', '/'),
        'slice_path': str(slice_path).replace('\\', '/'),
        'start_ts_utc': start_ts.isoformat().replace('+00:00', 'Z'),
        'stop_ts_utc': stop_ts.isoformat().replace('+00:00', 'Z'),
        'record_count': len(rows),
        'source_id_hash_count': len(source_ids),
        'source_id_hashes': source_ids,
        'write_ts_first': write_ts_values[0] if write_ts_values else '',
        'write_ts_last': write_ts_values[-1] if write_ts_values else '',
        'source_timestamp_first': source_ts_values[0] if source_ts_values else '',
        'source_timestamp_last': source_ts_values[-1] if source_ts_values else '',
    }

    manifest_path = output_dir / 'slice_manifest.json'
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding='utf-8')

    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
