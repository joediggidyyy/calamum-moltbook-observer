from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from observerctl_sandbox_registry import get_definitions


RunRow = Dict[str, Any]


_CURRENT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _CURRENT_DIR.parent
_REPO_ROOT = _PROJECT_ROOT.parents[1]


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not path.exists():
        return rows
    for raw_line in path.read_text(encoding='utf-8', errors='ignore').splitlines():
        line = str(raw_line or '').strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _report_path_from_row(row: Dict[str, Any]) -> str:
    for key in ('report_json', 'review_json', 'report_md', 'review_md'):
        value = str(row.get(key, '') or '').strip()
        if value:
            return value.replace('\\', '/')
    return ''


def _resolve_repo_path(path_text: str) -> Path:
    raw = str(path_text or '').strip()
    if not raw:
        return Path()
    path = Path(raw.replace('/', os.sep))
    if path.is_absolute():
        return path
    return _REPO_ROOT / path


def list_runs() -> List[RunRow]:
    rows: List[RunRow] = []
    for definition in get_definitions():
        run_index_path = Path(str(definition.get('run_index_path', '') or '').replace('/', '\\')) if str(definition.get('run_index_path', '')).strip() else None
        if not run_index_path or not run_index_path.exists():
            continue
        for row in _read_jsonl(run_index_path):
            rows.append({
                'run_id': str(row.get('run_id', '') or ''),
                'definition_id': str(definition.get('id', '') or ''),
                'timestamp_utc': str(row.get('timestamp_utc', '') or ''),
                'result': str(row.get('next_bite_result', row.get('result', 'recorded')) or 'recorded'),
                'report_path': _report_path_from_row(row),
                'run_dir': str(row.get('run_dir', '') or ''),
                'index_path': str(run_index_path).replace('\\', '/'),
            })
    rows.sort(key=lambda item: str(item.get('timestamp_utc', '') or ''), reverse=True)
    return rows


def get_run(run_id: str) -> Optional[Tuple[RunRow, Dict[str, Any]]]:
    wanted = str(run_id or '').strip()
    if not wanted:
        return None
    for row in list_runs():
        if str(row.get('run_id', '')).strip() != wanted:
            continue
        report_path = _resolve_repo_path(str(row.get('report_path', '') or '')) if str(row.get('report_path', '')).strip() else None
        report_payload = _read_json(report_path) if report_path and report_path.exists() and report_path.suffix.lower() == '.json' else {}
        return row, report_payload
    return None
