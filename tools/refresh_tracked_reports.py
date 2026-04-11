from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Optional


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / 'src'
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from analysis.report_aggregate import refresh_tracked_ds_publication  # noqa: E402


def _read_manifest_payload(manifest_path: Path) -> Optional[Mapping[str, Any]]:
    try:
        payload = json.loads(manifest_path.read_text(encoding='utf-8'))
    except Exception as exc:  # pragma: no cover - defensive CLI failure path
        raise SystemExit(f'Unable to read manifest payload from {manifest_path}: {exc}') from exc
    if not isinstance(payload, dict):
        raise SystemExit(f'Manifest payload must be a JSON object: {manifest_path}')
    return payload


def _resolve_manifest_path(raw_value: str) -> Path:
    candidate = Path(str(raw_value).strip())
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate.resolve()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Refresh tracked docs/reports publication from canonical local DS run artifacts.'
    )
    parser.add_argument(
        '--manifest',
        help='Optional path to a specific run manifest JSON. When omitted, the tool refreshes from the canonical saved-run ledger without selecting a current run.',
    )
    parser.add_argument(
        '--explicit-republish',
        action='store_true',
        help='Override republish-required control state and force regeneration.',
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    manifest_payload: Optional[Mapping[str, Any]] = None
    if args.manifest:
        manifest_path = _resolve_manifest_path(args.manifest)
        if not manifest_path.exists():
            raise SystemExit(f'Manifest path not found: {manifest_path}')
        manifest_payload = _read_manifest_payload(manifest_path)

    payload = refresh_tracked_ds_publication(
        project_anchor=PROJECT_ROOT / 'src' / 'observerctl.py',
        current_manifest_payload=manifest_payload,
        explicit_republish=bool(args.explicit_republish),
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if str(payload.get('decision', '')).strip().lower() in {'go', 'skipped'} else 2


if __name__ == '__main__':
    raise SystemExit(main())
