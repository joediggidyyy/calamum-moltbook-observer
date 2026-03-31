from __future__ import annotations

import hashlib
import json
import re
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


_DS_WORKFLOW_ALIASES = {
    'run-demo': 'demo',
    'run-pipeline': 'pipeline',
}
_RUN_ID_SANITIZE_RE = re.compile(r'[^A-Za-z0-9._-]+')


def canonical_ds_workflow_name(workflow: str) -> str:
    normalized = str(workflow or '').strip().lower().replace('_', '-')
    return _DS_WORKFLOW_ALIASES.get(normalized, normalized or 'run')


def compact_utc_stamp(timestamp_utc: Optional[str] = None) -> str:
    raw = str(timestamp_utc or utc_now_iso()).strip()
    if raw.endswith('+00:00'):
        raw = raw[:-6] + 'Z'
    return raw.replace(':', '').replace('-', '').replace('.', '')


def sanitize_run_id(raw: str) -> str:
    cleaned = _RUN_ID_SANITIZE_RE.sub('-', str(raw or '').strip())
    cleaned = cleaned.strip('-. _')
    return cleaned


def default_run_id(workflow: str, timestamp_utc: Optional[str] = None) -> str:
    workflow_name = canonical_ds_workflow_name(workflow)
    candidate = '{0}_{1}'.format(workflow_name, compact_utc_stamp(timestamp_utc))
    cleaned = sanitize_run_id(candidate)
    return cleaned or '{0}_run'.format(workflow_name)


def ds_runs_dir(start: Path) -> Path:
    return default_analysis_dir(start) / 'runs'


def ds_indexes_dir(start: Path) -> Path:
    return default_analysis_dir(start) / 'indexes'


def ds_drafts_dir(start: Path) -> Path:
    return default_analysis_dir(start) / 'drafts'


def ds_publication_dir(start: Path) -> Path:
    root = find_project_root(start)
    return root / 'docs' / 'reports' / 'ds'


def ds_publication_runs_dir(start: Path) -> Path:
    return ds_publication_dir(start) / 'runs'


def ds_publication_aggregates_dir(start: Path) -> Path:
    return ds_publication_dir(start) / 'aggregates'


def ds_published_run_dir(start: Path, timestamp_utc: str, run_id: str) -> Path:
    timestamp_text = str(timestamp_utc or '').strip()
    year = timestamp_text[:4] if len(timestamp_text) >= 4 and timestamp_text[:4].isdigit() else 'unknown'
    year_month = timestamp_text[:7] if len(timestamp_text) >= 7 and timestamp_text[4] == '-' else '{0}-unknown'.format(year)
    resolved_run_id = sanitize_run_id(run_id) or default_run_id('run', timestamp_text or None)
    return ds_publication_runs_dir(start) / year / year_month / resolved_run_id


def librarian_dataset_manifest_path(start: Path) -> Path:
    return ds_indexes_dir(start) / 'librarian_dataset_manifest.json'


def librarian_dataset_catalog_path(start: Path) -> Path:
    return ds_indexes_dir(start) / 'librarian_dataset_catalog.jsonl'


def dataset_access_dir(start: Path) -> Path:
    return ds_indexes_dir(start) / 'dataset_access'


def default_run_root(start: Path, workflow: str, run_id: str) -> Path:
    workflow_name = canonical_ds_workflow_name(workflow)
    resolved_run_id = sanitize_run_id(run_id) or default_run_id(workflow_name)
    return ds_runs_dir(start) / workflow_name / resolved_run_id


def resolve_run_root_and_artifact_dir(
    explicit_path: Optional[Path],
    artifact_dir_name: str,
    aliases: Optional[Iterable[str]] = None,
) -> Tuple[Optional[Path], Optional[Path]]:
    if explicit_path is None:
        return None, None
    artifact_names = {str(artifact_dir_name or '').strip().lower()}
    for alias in aliases or []:
        text = str(alias or '').strip().lower()
        if text:
            artifact_names.add(text)
    if explicit_path.name.strip().lower() in artifact_names:
        return explicit_path.parent, explicit_path
    return explicit_path, explicit_path / str(artifact_dir_name).strip()


def normalize_repo_or_absolute_path(path: Optional[Path], project_root: Path) -> str:
    if path is None:
        return ''
    try:
        resolved_path = Path(path).resolve()
    except Exception:
        resolved_path = Path(path)
    try:
        resolved_root = Path(project_root).resolve()
    except Exception:
        resolved_root = Path(project_root)
    try:
        return resolved_path.relative_to(resolved_root).as_posix()
    except Exception:
        return resolved_path.as_posix()


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
    return _git_stdout(cwd, 'rev-parse', 'HEAD')


def _git_stdout(cwd: Path, *args: str) -> Optional[str]:
    try:
        out = subprocess.check_output(['git'] + list(args), cwd=str(cwd), stderr=subprocess.DEVNULL)
        text = out.decode('utf-8', errors='replace').strip()
        if text:
            return text
    except Exception:
        return None
    return None


def try_get_git_branch(cwd: Path) -> Optional[str]:
    return _git_stdout(cwd, 'rev-parse', '--abbrev-ref', 'HEAD')


def try_is_git_dirty(cwd: Path) -> Optional[bool]:
    try:
        out = subprocess.check_output(['git', 'status', '--porcelain'], cwd=str(cwd), stderr=subprocess.DEVNULL)
        return bool(out.decode('utf-8', errors='replace').strip())
    except Exception:
        return None


def collect_git_provenance(cwd: Path) -> Dict[str, Any]:
    return {
        'head': try_get_git_sha(cwd),
        'branch': try_get_git_branch(cwd),
        'is_dirty': try_is_git_dirty(cwd),
    }


@dataclass
class JsonlLine:
    line_no: int
    raw: str
    obj: Optional[Dict[str, Any]]
    error: Optional[str]


import gzip

def iter_jsonl(path: Path, max_lines: Optional[int] = None) -> Iterator[JsonlLine]:
    """Stream JSONL lines from a file (best-effort, names-only) supporting optional GZIP."""
    i = 0
    
    if path.suffix == '.gz':
        opener = lambda p: gzip.open(p, 'rt', encoding='utf-8')
    else:
        opener = lambda p: p.open('r', encoding='utf-8')

    with opener(path) as f:
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
