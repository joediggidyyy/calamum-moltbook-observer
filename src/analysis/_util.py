from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def find_project_root(start: Path) -> Path:
    """Best-effort Calamum *project* root discovery.

    Prefer the project marker `PROJECT_MANIFEST.json`.
    """
    cur = start.resolve()
    for parent in [cur] + list(cur.parents):
        if (parent / 'PROJECT_MANIFEST.json').exists() and (parent / 'src').exists():
            return parent
    return cur


def default_analysis_dir(start: Path) -> Path:
    root = find_project_root(start)
    return root / 'local_untracked' / 'analysis'


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def stable_record_id(record: Dict[str, Any]) -> str:
    """Compute a deterministic record identifier.

    Preference order:
    - signature (already deterministic for the signed payload)
    - sha256(canonical json)
    """
    sig = record.get('signature')
    if isinstance(sig, str) and sig:
        return sig
    payload = json.dumps(record, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return sha256_bytes(payload)


def try_get_git_sha(cwd: Path) -> Optional[str]:
    try:
        out = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=str(cwd), stderr=subprocess.DEVNULL)
        sha = out.decode('utf-8', errors='replace').strip()
        if sha:
            return sha
    except Exception:
        return None
    return None


@dataclass
class JsonlLine:
    line_no: int
    raw: str
    obj: Optional[Dict[str, Any]]
    error: Optional[str]


def iter_jsonl(path: Path, max_lines: Optional[int] = None) -> Iterator[JsonlLine]:
    """Stream JSONL lines from a file (best-effort, names-only)."""
    i = 0
    with path.open('r', encoding='utf-8') as f:
        for line_no, raw in enumerate(f, start=1):
            if max_lines is not None and i >= max_lines:
                break
            i += 1
            s = raw.strip('\n')
            if not s.strip():
                yield JsonlLine(line_no=line_no, raw=s, obj=None, error='empty')
                continue
            try:
                obj = json.loads(s)
                if not isinstance(obj, dict):
                    yield JsonlLine(line_no=line_no, raw=s, obj=None, error='not_object')
                    continue
                yield JsonlLine(line_no=line_no, raw=s, obj=obj, error=None)
            except Exception:
                yield JsonlLine(line_no=line_no, raw=s, obj=None, error='json_parse_error')


def deterministic_split_bucket(record_id: str, seed: int) -> float:
    """Map (seed, record_id) to a stable float in [0, 1)."""
    payload = f'{seed}:{record_id}'.encode('utf-8')
    digest = hashlib.sha256(payload).digest()
    # Use first 8 bytes as an int for stable mapping.
    n = int.from_bytes(digest[:8], 'big', signed=False)
    return (n % 10_000_000) / 10_000_000.0
