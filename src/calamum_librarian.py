"""Calamum Librarian (Archive Management Daemon).

Responsibilities:
1.  **Compress**: Scans `archive/` for raw `.jsonl` files and compresses them to `.gz`.
2.  **Validate**: Ensures data integrity (JSON validity) and counts records.
3.  **Sign**: Calculates SHA256 of the final artifact for non-repudiation.
4.  **Manifest**: Updates `archive/manifest.json` with the authoritative record of history.
5.  **Feedback**: Adjusts `rotation_policy.json` based on actual data density to target ~100k records/file.

Design:
-   Async-friendly (though currently runs in a simple loop for stability).
-   Idempotent: Safe to restart.
-   Fail-safe: Corrupt files are quarantined, not deleted.
"""

__version__ = "1.1.0"

import gzip
import hashlib
import json
import os
import shutil
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from analysis._util import (
    dataset_access_dir,
    find_project_root,
    librarian_dataset_catalog_path,
    librarian_dataset_manifest_path,
    normalize_repo_or_absolute_path,
    sanitize_run_id,
    sha256_path,
    utc_now_iso,
)
from calamum_config import get_calamum_data_dir, get_calamum_control_dir, get_calamum_health_dir
from obfuscator_lib import payload_sha256, sign_detached_payload, verify_detached_payload

try:
    from calamum_keepalive import KeepaliveHelper
except ImportError:
    KeepaliveHelper = None

# Constants
DEFAULT_TARGET_RECORDS = 100_000
DEFAULT_BYTES_PER_RECORD = 350
MANIFEST_FILENAME = 'manifest.json'
POLICY_FILENAME = 'rotation_policy.json'
QUARANTINE_DIR_NAME = 'quarantine'
DATASET_SELECTOR_SCHEMA_VERSION = '1.0'
DATASET_ACCESS_REQUEST_TTL_SEC = 300
DATASET_ACCESS_CLASS_LOCAL = 'local'
DATASET_ACCESS_CLASS_PROTECTED = 'protected-source'


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


class Librarian:
    def __init__(self, interval_sec: float = 10.0):
        self.interval_sec = interval_sec
        self.data_dir = get_calamum_data_dir()
        self.archive_dir = self.data_dir / 'archive'
        self.quarantine_dir = self.archive_dir / QUARANTINE_DIR_NAME
        self.manifest_path = self.archive_dir / MANIFEST_FILENAME
        self.control_dir = get_calamum_control_dir()
        self.policy_path = self.control_dir / POLICY_FILENAME
        self.health_dir = get_calamum_health_dir()
        self.heartbeat_path = self.health_dir / 'calamum_librarian.heartbeat'
        self.status_path = self.health_dir / 'calamum_librarian_status.json'
        
        # Ensure Dirs
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        self.quarantine_dir.mkdir(parents=True, exist_ok=True)
        self.control_dir.mkdir(parents=True, exist_ok=True)
        self.health_dir.mkdir(parents=True, exist_ok=True)

    def _touch_heartbeat(self, status: str = "ok", details: Optional[Dict] = None) -> None:
        """Update heartbeat and status file for Watchdog/Sentinel."""
        try:
            # Simple touch
            self.heartbeat_path.touch(exist_ok=True)
            
            # Rich status for Watchdog to consume
            status_data = {
                "ts": time.time(),
                "status": status,
                "version": __version__,
                "details": details or {}
            }
            # Atomic write
            temp = self.status_path.with_suffix('.tmp')
            temp.write_text(json.dumps(status_data), encoding='utf-8')
            temp.replace(self.status_path)
        except Exception as e:
            print(f"[Librarian] Heartbeat failed: {e}")

    def _calculate_file_hash(self, path: Path) -> str:
        """Calculate SHA256 of a file."""
        sha = hashlib.sha256()
        with open(path, 'rb') as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                sha.update(chunk)
        return sha.hexdigest()

    def _load_manifest(self) -> Dict[str, dict]:
        if not self.manifest_path.exists():
            return {}
        try:
            return json.loads(self.manifest_path.read_text(encoding='utf-8'))
        except Exception:
            # If manifest is corrupt, we might need a backup. For now, return empty (risk of double processing?)
            # Better: Rename corrupt manifest and start fresh?
            # Decision: Log error and return empty, but backup old one.
            backup = self.manifest_path.with_suffix('.bak')
            if not backup.exists():
                shutil.copy(self.manifest_path, backup)
            return {}

    def _save_manifest(self, manifest: Dict[str, dict]) -> None:
        # Atomic write
        temp = self.manifest_path.with_suffix('.tmp')
        temp.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding='utf-8')
        temp.replace(self.manifest_path)

    def _update_policy(self, avg_bytes: float) -> None:
        """Update the rotation policy based on observed density."""
        target_size = int(avg_bytes * DEFAULT_TARGET_RECORDS)
        # Dampening: Don't let it swing too wild. Clamp between 10MB and 200MB.
        target_size = max(10_000_000, min(200_000_000, target_size))
        
        policy = {
            'generated_at': time.time(),
            'target_records': DEFAULT_TARGET_RECORDS,
            'observed_avg_bytes': round(avg_bytes, 2),
            'max_bytes': target_size,
            'reason': f"Adaptive: {DEFAULT_TARGET_RECORDS} recs * {round(avg_bytes, 2)} bytes"
        }
        
        # Serialize
        content = json.dumps(policy, indent=2, sort_keys=True)
        
        # Atomic write
        temp = self.policy_path.with_suffix('.tmp')
        temp.write_text(content, encoding='utf-8')
        temp.replace(self.policy_path)

    def _process_file(self, jsonl_path: Path) -> Optional[Tuple[int, int, str]]:
        """Compress, validate, and hash.

        Returns: (records_count, total_uncompressed_bytes, artifact_sha256)
        """
        print(f"[Librarian] Processing {jsonl_path.name}...")
        
        records_count = 0
        total_bytes = 0
        
        gz_path = jsonl_path.with_suffix('.jsonl.gz')
        
        has_errors = False
        
        try:
            with open(jsonl_path, 'rb') as f_in, gzip.open(gz_path, 'wb') as f_out:
                for line in f_in:
                    # Metrics
                    total_bytes += len(line)
                    records_count += 1
                    
                    # Validate JSON structure (lightweight)
                    # We decoded to check validity.
                    try:
                        line_str = line.decode('utf-8')
                        _ = json.loads(line_str) 
                        # If valid, write to GZ
                        f_out.write(line)
                    except json.JSONDecodeError:
                        print(f"[Librarian] Corruption detected in {jsonl_path.name}")
                        has_errors = True
                        break # Stop processing specific file
            
            if has_errors:
                 if gz_path.exists():
                     gz_path.unlink()
                 return None

            # Validation complete.
            if records_count == 0:
                print(f"[Librarian] Warning: Empty file {jsonl_path.name}")
                
            # Verify Artifact
            artifact_hash = self._calculate_file_hash(gz_path)
            
            return records_count, total_bytes, artifact_hash
            
        except Exception as e:
            print(f"[Librarian] Error processing {jsonl_path.name}: {e}")
            if gz_path.exists():
                gz_path.unlink()
            return None

    def run_once(self) -> None:
        manifest = self._load_manifest()
        updates_made = False
        
        # Look for raw .jsonl files in archive/
        # (excluding those already in manifest? No, look for files that exist on disk as .jsonl)
        
        candidates = sorted(self.archive_dir.glob('*.jsonl'))
        if not candidates:
            return

        total_new_bytes = 0
        total_new_records = 0

        for jsonl in candidates:
            # Skip if it looks like an active file (shouldn't be in archive/ usually, but just in case)
            # The agent moves them here when done, so all .jsonl in archive/ are candidates.
            
            # Lock check: ensure file isn't being written to? 
            # Agent atomic move guarantees it's closed.
            
            result = self._process_file(jsonl)
            if result:
                count, bytes_size, sha = result
                
                # Update Manifest
                manifest[jsonl.name] = {
                    'processed_at': time.time(),
                    'records': count,
                    'uncompressed_bytes': bytes_size,
                    'artifact_path': jsonl.with_suffix('.jsonl.gz').name,
                    'artifact_sha256': sha
                }
                
                # Remove raw file
                jsonl.unlink()
                
                updates_made = True
                
                # Stats for policy
                total_new_bytes += bytes_size
                total_new_records += count
            else:
                # Move to quarantine
                shutil.move(str(jsonl), str(self.quarantine_dir / jsonl.name))

        if updates_made:
            self._save_manifest(manifest)
            
            # Feedback Loop
            if total_new_records > 0:
                avg = total_new_bytes / total_new_records
                self._update_policy(avg)
                print(f"[Librarian] Policy updated. Avg bytes: {avg:.2f}")

    def loop(self):
        print(f"[Librarian] Watching {self.archive_dir}")
        
        # Initialize shared keepalive helper (if available)
        keepalive_helper = None
        if KeepaliveHelper:
            # Use raw env read or logic here if not moved; reusing existing logic behavior
            # Default to 60s if not set, handled by helper if passed specific value
            interval_raw = os.getenv('CALAMUM_STDOUT_KEEPALIVE_SEC', '60')
            try:
                interval = float(interval_raw)
            except Exception:
                interval = 60.0
            
            if interval > 0:
                keepalive_helper = KeepaliveHelper("CalamumLibrarian", interval_seconds=interval)

        while True:
            try:
                self.run_once()
                self._touch_heartbeat("ok", {"msg": "Loop iteration complete"})

                # Operator-friendly liveness signal (stdout; rate-limited)
                if keepalive_helper:
                    pending = None
                    try:
                        pending = len(list(self.archive_dir.glob('*.jsonl')))
                    except Exception:
                        pending = None
                    
                    keepalive_helper.emit("RUNNING", {"pending_archive_jsonl": pending})
            except Exception as e:
                print(f"[Librarian] Crash in loop: {e}")
                self._touch_heartbeat("error", {"error": str(e)})
            time.sleep(self.interval_sec)


def _dataset_catalog_paths(project_anchor: Path) -> Dict[str, Path]:
    project_root = find_project_root(project_anchor)
    snapshot_path = librarian_dataset_manifest_path(project_anchor)
    catalog_path = librarian_dataset_catalog_path(project_anchor)
    access_root = dataset_access_dir(project_anchor)
    return {
        'project_root': project_root,
        'snapshot_path': snapshot_path,
        'catalog_path': catalog_path,
        'access_root': access_root,
    }


def _read_json_dict(path: Path, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    fallback = dict(default or {})
    try:
        if path.exists():
            payload = json.loads(path.read_text(encoding='utf-8'))
            if isinstance(payload, dict):
                return payload
    except Exception:
        pass
    return fallback


def _write_json_atomic(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding='utf-8')
    temp.replace(path)


def _append_jsonl_record(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8') as handle:
        handle.write(json.dumps(payload, sort_keys=True) + '\n')


def _resolve_catalog_ref(project_root: Path, ref: str) -> Path:
    path = Path(str(ref or '').strip())
    if not path.is_absolute():
        path = project_root / path
    return path.resolve()


def _utc_after_seconds(seconds: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=int(seconds))).isoformat().replace('+00:00', 'Z')


def _is_not_expired(expires_at_utc: str) -> bool:
    text = str(expires_at_utc or '').strip()
    if not text:
        return False
    try:
        expiry = datetime.fromisoformat(text.replace('Z', '+00:00'))
    except Exception:
        return False
    return expiry >= datetime.now(timezone.utc)


def _sorted_dataset_entries(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(
        [entry for entry in entries if isinstance(entry, dict)],
        key=lambda entry: (
            str(entry.get('recorded_at_utc', '')),
            str(entry.get('entry_id', '')),
        ),
        reverse=True,
    )


def _dataset_selector_entry(entry: Dict[str, Any], index: int) -> Dict[str, Any]:
    return {
        'index': int(index),
        'entry_id': str(entry.get('entry_id', '')),
        'display_name': str(entry.get('display_name', '')),
        'recorded_at_utc': str(entry.get('recorded_at_utc', '')),
        'workflow': str(entry.get('workflow', '')),
        'family': str(entry.get('family', 'dataset_manifest')),
        'run_id': str(entry.get('run_id', '')),
        'record_count': int(entry.get('record_count', 0) or 0),
        'has_labels': bool(entry.get('has_labels', False)),
        'status': str(entry.get('status', 'held')),
        'readiness': str(entry.get('readiness', 'unknown')),
        'access_class': str(entry.get('access_class', DATASET_ACCESS_CLASS_LOCAL)),
        'requires_librarian_attestation': bool(entry.get('requires_librarian_attestation', False)),
        'source': str(entry.get('source', 'unknown') or 'unknown'),
        'mode': str(entry.get('mode', 'unknown') or 'unknown'),
    }


def _load_dataset_snapshot(paths: Dict[str, Path]) -> List[Dict[str, Any]]:
    payload = _read_json_dict(paths['snapshot_path'], default={})
    entries = payload.get('entries', []) if isinstance(payload.get('entries', []), list) else []
    if entries:
        return _sorted_dataset_entries([entry for entry in entries if isinstance(entry, dict)])

    entries = []
    if paths['catalog_path'].exists():
        for line in paths['catalog_path'].read_text(encoding='utf-8').splitlines():
            text = str(line or '').strip()
            if not text:
                continue
            try:
                row = json.loads(text)
            except Exception:
                continue
            if isinstance(row, dict):
                entries.append(row)
    return _sorted_dataset_entries(entries)


def _save_dataset_snapshot(paths: Dict[str, Path], entries: List[Dict[str, Any]]) -> None:
    payload = {
        'schema_version': DATASET_SELECTOR_SCHEMA_VERSION,
        'family_id': 'librarian_dataset',
        'updated_at_utc': utc_now_iso(),
        'catalog_path': normalize_repo_or_absolute_path(paths['catalog_path'], paths['project_root']),
        'entries': _sorted_dataset_entries(entries),
    }
    _write_json_atomic(paths['snapshot_path'], payload)


def _resolve_dataset_entry(paths: Dict[str, Path], selector: str) -> Optional[Dict[str, Any]]:
    token = str(selector or '').strip()
    if not token:
        return None
    entries = _load_dataset_snapshot(paths)
    if token.isdigit():
        idx = int(token)
        if 1 <= idx <= len(entries):
            entry = entries[idx - 1]
            return {'entry': entry, 'selector_entry': _dataset_selector_entry(entry, idx)}
        return None
    lowered = token.lower()
    for idx, entry in enumerate(entries, start=1):
        if lowered in {
            str(entry.get('entry_id', '')).strip().lower(),
            str(entry.get('run_id', '')).strip().lower(),
            str(entry.get('display_name', '')).strip().lower(),
        }:
            return {'entry': entry, 'selector_entry': _dataset_selector_entry(entry, idx)}
    return None


def _build_dataset_entry(
    project_anchor: Path,
    dataset_manifest_path: Path,
    *,
    access_class: str,
    display_name: str,
    run_id: str,
    workflow: str,
    recorded_at_utc: str,
    registration_kind: str,
    report_manifest_ref: str = '',
    source: str = 'unknown',
    mode: str = 'unknown',
    source_binding: str = '',
) -> Dict[str, Any]:
    project_root = find_project_root(project_anchor)
    manifest_path = dataset_manifest_path.resolve()
    payload = json.loads(manifest_path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise ValueError('dataset manifest is not a JSON object')

    features_ref_raw = str(payload.get('features_csv', '') or '').strip()
    labels_ref_raw = str(payload.get('labels_csv', '') or '').strip()
    features_path = _resolve_catalog_ref(project_root, features_ref_raw) if features_ref_raw else Path('')
    labels_path = _resolve_catalog_ref(project_root, labels_ref_raw) if labels_ref_raw else None
    manifest_sha = sha256_path(manifest_path)
    access_token = str(access_class or DATASET_ACCESS_CLASS_LOCAL).strip().lower() or DATASET_ACCESS_CLASS_LOCAL
    if access_token not in (DATASET_ACCESS_CLASS_LOCAL, DATASET_ACCESS_CLASS_PROTECTED):
        access_token = DATASET_ACCESS_CLASS_LOCAL
    entry_run_id = str(run_id or '').strip()
    base_token = sanitize_run_id(entry_run_id or display_name or manifest_path.parent.name or manifest_path.stem)
    if entry_run_id:
        entry_id = 'dataset-{0}'.format(base_token or entry_run_id)
    else:
        entry_id = 'dataset-{0}-{1}'.format(base_token or 'manifest', manifest_sha[:10])

    readiness_issues: List[str] = []
    if not features_ref_raw or not features_path.exists():
        readiness_issues.append('missing_features_csv')
    if labels_ref_raw and labels_path is not None and not labels_path.exists():
        readiness_issues.append('missing_labels_csv')

    readiness = 'ready' if len(readiness_issues) == 0 else 'artifact-missing'
    status = 'approved' if readiness == 'ready' else 'held'
    resolved_binding = str(source_binding or 'dataset_manifest_sha256:{0}'.format(manifest_sha)).strip()
    display = str(display_name or entry_run_id or manifest_path.parent.name or manifest_path.stem).strip()

    resolver = {
        'dataset_manifest_path': normalize_repo_or_absolute_path(manifest_path, project_root),
        'dataset_manifest_sha256': manifest_sha,
        'features_csv_path': normalize_repo_or_absolute_path(features_path, project_root) if features_ref_raw else '',
        'labels_csv_path': normalize_repo_or_absolute_path(labels_path, project_root) if labels_ref_raw and labels_path is not None else '',
    }

    return {
        'schema_version': DATASET_SELECTOR_SCHEMA_VERSION,
        'family': 'dataset_manifest',
        'entry_id': entry_id,
        'display_name': display,
        'recorded_at_utc': str(recorded_at_utc or payload.get('created_at_utc') or utc_now_iso()),
        'workflow': str(workflow or 'manual-register').strip() or 'manual-register',
        'run_id': entry_run_id,
        'record_count': int(payload.get('total_records', 0) or 0),
        'has_labels': bool(payload.get('has_labels', False)),
        'status': status,
        'readiness': readiness,
        'readiness_issues': readiness_issues,
        'access_class': access_token,
        'requires_librarian_attestation': bool(access_token == DATASET_ACCESS_CLASS_PROTECTED),
        'source': str(source or 'unknown') or 'unknown',
        'mode': str(mode or 'unknown') or 'unknown',
        'source_binding': resolved_binding,
        'report_manifest_ref': str(report_manifest_ref or '').strip(),
        'registration_kind': str(registration_kind or 'manual').strip() or 'manual',
        'resolver': resolver,
    }


def _upsert_dataset_entry(paths: Dict[str, Path], entry: Dict[str, Any]) -> Dict[str, Any]:
    existing = _load_dataset_snapshot(paths)
    remaining = [row for row in existing if str(row.get('entry_id', '')).strip() != str(entry.get('entry_id', '')).strip()]
    merged = [entry] + remaining
    merged = _sorted_dataset_entries(merged)
    _append_jsonl_record(paths['catalog_path'], entry)
    _save_dataset_snapshot(paths, merged)
    return {
        'entry': entry,
        'snapshot_path': normalize_repo_or_absolute_path(paths['snapshot_path'], paths['project_root']),
        'catalog_path': normalize_repo_or_absolute_path(paths['catalog_path'], paths['project_root']),
    }


def refresh_librarian_dataset_catalog_from_run_manifest(project_anchor: Path, manifest_payload: Dict[str, Any]) -> Dict[str, Any]:
    artifacts = dict(manifest_payload.get('artifacts', {}) or {}) if isinstance(manifest_payload, dict) else {}
    dataset_ref = str(artifacts.get('dataset_manifest', '') or '').strip()
    if not dataset_ref:
        return {
            'decision': 'go',
            'catalog_updated': False,
        }

    paths = _dataset_catalog_paths(project_anchor)
    project_root = paths['project_root']
    dataset_manifest_path = _resolve_catalog_ref(project_root, dataset_ref)
    if not dataset_manifest_path.exists():
        return {
            'decision': 'no-go',
            'catalog_updated': False,
            'reason_codes': ['critical_check_failed:librarian_dataset_manifest_missing'],
            'summary': 'Dataset catalog refresh skipped because the dataset manifest could not be resolved.',
        }

    workflow = str(manifest_payload.get('workflow', '') or '').strip() or 'manual-register'
    run_id = str(manifest_payload.get('run_id', '') or '').strip()
    report_paths = dict(manifest_payload.get('report_paths', {}) or {}) if isinstance(manifest_payload.get('report_paths', {}), dict) else {}
    entry = _build_dataset_entry(
        project_anchor,
        dataset_manifest_path,
        access_class=DATASET_ACCESS_CLASS_LOCAL,
        display_name=run_id or workflow,
        run_id=run_id,
        workflow=workflow,
        recorded_at_utc=str(manifest_payload.get('timestamp_utc', '') or utc_now_iso()),
        registration_kind='run-refresh',
        report_manifest_ref=str(report_paths.get('manifest', '') or '').strip(),
        source_binding='run-manifest:{0}'.format(run_id or workflow),
    )
    update = _upsert_dataset_entry(paths, entry)
    selector_entries = [_dataset_selector_entry(entry, idx) for idx, entry in enumerate(_load_dataset_snapshot(paths), start=1)]
    return {
        'timestamp_utc': utc_now_iso(),
        'runtime_cli_surface': 'observerctl',
        'decision': 'go',
        'action': 'librarian-dataset-refresh',
        'catalog_updated': True,
        'entry': _dataset_selector_entry(entry, 1),
        'selector_entries': selector_entries,
        'snapshot_path': update['snapshot_path'],
        'catalog_path': update['catalog_path'],
    }


def register_librarian_dataset_packet(
    project_anchor: Path,
    dataset_manifest_path: Path,
    *,
    access_class: str = DATASET_ACCESS_CLASS_LOCAL,
    display_name: str = '',
    run_id: str = '',
) -> Dict[str, Any]:
    paths = _dataset_catalog_paths(project_anchor)
    project_root = paths['project_root']
    manifest_path = dataset_manifest_path if dataset_manifest_path.is_absolute() else (project_root / dataset_manifest_path)
    manifest_path = manifest_path.resolve()
    if not manifest_path.exists():
        return {
            'timestamp_utc': utc_now_iso(),
            'runtime_cli_surface': 'observerctl',
            'decision': 'no-go',
            'action': 'librarian-dataset-register',
            'summary': 'Dataset registration failed because the manifest path does not exist.',
            'reason_codes': ['critical_check_failed:librarian_dataset_manifest_missing'],
        }

    entry = _build_dataset_entry(
        project_anchor,
        manifest_path,
        access_class=access_class,
        display_name=display_name,
        run_id=run_id,
        workflow='manual-register',
        recorded_at_utc=utc_now_iso(),
        registration_kind='manual-register',
        source_binding='manual-register:{0}'.format(manifest_path.name),
    )
    update = _upsert_dataset_entry(paths, entry)
    resolved = _resolve_dataset_entry(paths, str(entry.get('entry_id', '')))
    selector_entry = resolved.get('selector_entry', {}) if isinstance(resolved, dict) else {}
    return {
        'timestamp_utc': utc_now_iso(),
        'runtime_cli_surface': 'observerctl',
        'decision': 'go',
        'action': 'librarian-dataset-register',
        'summary': 'Dataset registered in the librarian-approved catalog.',
        'reason_codes': [],
        'dataset': selector_entry,
        'artifacts': {
            'librarian_dataset_manifest_json': update['snapshot_path'],
            'librarian_dataset_catalog_jsonl': update['catalog_path'],
        },
    }


def list_librarian_datasets_packet(project_anchor: Path) -> Dict[str, Any]:
    paths = _dataset_catalog_paths(project_anchor)
    entries = _load_dataset_snapshot(paths)
    selector_entries = [_dataset_selector_entry(entry, idx) for idx, entry in enumerate(entries, start=1)]
    return {
        'timestamp_utc': utc_now_iso(),
        'runtime_cli_surface': 'observerctl',
        'decision': 'go',
        'action': 'librarian-datasets',
        'summary': 'Approved dataset selector surface ready.' if selector_entries else 'No approved datasets are registered yet.',
        'count': int(len(selector_entries)),
        'selector_entries': selector_entries,
        'artifacts': {
            'librarian_dataset_manifest_json': normalize_repo_or_absolute_path(paths['snapshot_path'], paths['project_root']),
            'librarian_dataset_catalog_jsonl': normalize_repo_or_absolute_path(paths['catalog_path'], paths['project_root']),
        },
        'reason_codes': [],
    }


def _write_signed_access_packet(path: Path, payload: Dict[str, Any], *, role: str, purpose: str) -> Dict[str, Any]:
    document = {
        'schema_version': DATASET_SELECTOR_SCHEMA_VERSION,
        'packet': payload,
        'detached_signature': sign_detached_payload(payload, role=role, purpose=purpose),
    }
    _write_json_atomic(path, document)
    return document


def release_librarian_dataset_packet(
    project_anchor: Path,
    selector: str,
    *,
    requester_id: str = 'observerctl',
    requested_action: str = 'hydrate-dataset',
) -> Dict[str, Any]:
    paths = _dataset_catalog_paths(project_anchor)
    resolved = _resolve_dataset_entry(paths, selector)
    if not isinstance(resolved, dict):
        return {
            'timestamp_utc': utc_now_iso(),
            'runtime_cli_surface': 'observerctl',
            'decision': 'no-go',
            'action': 'librarian-dataset-release',
            'summary': 'Dataset release failed because the approved selector could not be resolved.',
            'reason_codes': ['critical_check_failed:librarian_dataset_not_found'],
        }

    entry = dict(resolved.get('entry', {}) or {})
    selector_entry = dict(resolved.get('selector_entry', {}) or {})
    project_root = paths['project_root']
    resolver = dict(entry.get('resolver', {}) or {})
    manifest_ref = str(resolver.get('dataset_manifest_path', '') or '').strip()
    manifest_path = _resolve_catalog_ref(project_root, manifest_ref)
    artifacts = {
        'librarian_dataset_manifest_json': normalize_repo_or_absolute_path(paths['snapshot_path'], project_root),
        'librarian_dataset_catalog_jsonl': normalize_repo_or_absolute_path(paths['catalog_path'], project_root),
    }

    if str(entry.get('readiness', '')).strip() != 'ready' or not manifest_path.exists():
        return {
            'timestamp_utc': utc_now_iso(),
            'runtime_cli_surface': 'observerctl',
            'decision': 'no-go',
            'action': 'librarian-dataset-release',
            'summary': 'Dataset release failed because the approved entry is not ready.',
            'reason_codes': ['critical_check_failed:librarian_dataset_not_ready'],
            'dataset': selector_entry,
            'artifacts': artifacts,
        }

    if str(entry.get('access_class', DATASET_ACCESS_CLASS_LOCAL)).strip() != DATASET_ACCESS_CLASS_PROTECTED:
        artifacts['dataset_manifest_path'] = normalize_repo_or_absolute_path(manifest_path, project_root)
        return {
            'timestamp_utc': utc_now_iso(),
            'runtime_cli_surface': 'observerctl',
            'decision': 'go',
            'action': 'librarian-dataset-release',
            'summary': 'Local approved dataset resolved without delegated release.',
            'reason_codes': [],
            'release_mode': DATASET_ACCESS_CLASS_LOCAL,
            'dataset': selector_entry,
            'dataset_manifest_path': normalize_repo_or_absolute_path(manifest_path, project_root),
            'artifacts': artifacts,
        }

    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    access_dir = paths['access_root'] / sanitize_run_id(str(entry.get('entry_id', 'dataset'))) / stamp
    access_dir.mkdir(parents=True, exist_ok=True)
    request_path = access_dir / 'request.json'
    attestation_path = access_dir / 'attestation.json'
    release_path = access_dir / 'release_receipt.json'

    request_payload = {
        'schema_version': DATASET_SELECTOR_SCHEMA_VERSION,
        'kind': 'dataset_access_request',
        'created_at_utc': utc_now_iso(),
        'expires_at_utc': _utc_after_seconds(DATASET_ACCESS_REQUEST_TTL_SEC),
        'requester_id': str(requester_id or 'observerctl').strip() or 'observerctl',
        'requested_action': str(requested_action or 'hydrate-dataset').strip() or 'hydrate-dataset',
        'entry_id': str(entry.get('entry_id', '')),
        'run_id': str(entry.get('run_id', '')),
        'access_class': str(entry.get('access_class', DATASET_ACCESS_CLASS_PROTECTED)),
        'source_binding': str(entry.get('source_binding', '')),
        'dataset_manifest_sha256': str(resolver.get('dataset_manifest_sha256', '')),
    }
    request_doc = _write_signed_access_packet(
        request_path,
        request_payload,
        role='requester',
        purpose='dataset_access_request',
    )
    request_valid = verify_detached_payload(
        request_payload,
        dict(request_doc.get('detached_signature', {}) or {}),
        expected_role='requester',
        expected_purpose='dataset_access_request',
    ) and _is_not_expired(str(request_payload.get('expires_at_utc', '')))
    if not request_valid:
        return {
            'timestamp_utc': utc_now_iso(),
            'runtime_cli_surface': 'observerctl',
            'decision': 'no-go',
            'action': 'librarian-dataset-release',
            'summary': 'Delegated dataset request verification failed before release.',
            'reason_codes': ['critical_check_failed:librarian_dataset_request_invalid'],
            'dataset': selector_entry,
            'artifacts': dict(artifacts, dataset_access_request_json=normalize_repo_or_absolute_path(request_path, project_root)),
        }

    attestation_payload = {
        'schema_version': DATASET_SELECTOR_SCHEMA_VERSION,
        'kind': 'dataset_access_attestation',
        'created_at_utc': utc_now_iso(),
        'request_payload_sha256': payload_sha256(request_payload),
        'entry_id': str(entry.get('entry_id', '')),
        'run_id': str(entry.get('run_id', '')),
        'requester_id': str(request_payload.get('requester_id', '')),
        'requested_action': str(request_payload.get('requested_action', '')),
        'access_class': str(entry.get('access_class', DATASET_ACCESS_CLASS_PROTECTED)),
        'readiness': str(entry.get('readiness', 'unknown')),
        'source_binding': str(entry.get('source_binding', '')),
        'dataset_manifest_sha256': str(resolver.get('dataset_manifest_sha256', '')),
        'granted': True,
    }
    attestation_doc = _write_signed_access_packet(
        attestation_path,
        attestation_payload,
        role='librarian',
        purpose='dataset_access_attestation',
    )
    attestation_valid = verify_detached_payload(
        attestation_payload,
        dict(attestation_doc.get('detached_signature', {}) or {}),
        expected_role='librarian',
        expected_purpose='dataset_access_attestation',
    )
    if not attestation_valid:
        return {
            'timestamp_utc': utc_now_iso(),
            'runtime_cli_surface': 'observerctl',
            'decision': 'no-go',
            'action': 'librarian-dataset-release',
            'summary': 'Delegated librarian attestation verification failed before release.',
            'reason_codes': ['critical_check_failed:librarian_dataset_attestation_invalid'],
            'dataset': selector_entry,
            'artifacts': dict(
                artifacts,
                dataset_access_request_json=normalize_repo_or_absolute_path(request_path, project_root),
                dataset_access_attestation_json=normalize_repo_or_absolute_path(attestation_path, project_root),
            ),
        }

    release_payload = {
        'schema_version': DATASET_SELECTOR_SCHEMA_VERSION,
        'kind': 'dataset_access_release',
        'created_at_utc': utc_now_iso(),
        'request_payload_sha256': payload_sha256(request_payload),
        'attestation_payload_sha256': payload_sha256(attestation_payload),
        'entry_id': str(entry.get('entry_id', '')),
        'run_id': str(entry.get('run_id', '')),
        'requester_id': str(request_payload.get('requester_id', '')),
        'requested_action': str(request_payload.get('requested_action', '')),
        'access_class': str(entry.get('access_class', DATASET_ACCESS_CLASS_PROTECTED)),
        'source_binding': str(entry.get('source_binding', '')),
        'dataset_manifest_path': normalize_repo_or_absolute_path(manifest_path, project_root),
        'granted': True,
        'verified_request': True,
        'verified_attestation': True,
    }
    _write_signed_access_packet(
        release_path,
        release_payload,
        role='source',
        purpose='dataset_access_release',
    )

    artifacts.update({
        'dataset_manifest_path': normalize_repo_or_absolute_path(manifest_path, project_root),
        'dataset_access_request_json': normalize_repo_or_absolute_path(request_path, project_root),
        'dataset_access_attestation_json': normalize_repo_or_absolute_path(attestation_path, project_root),
        'dataset_access_release_receipt_json': normalize_repo_or_absolute_path(release_path, project_root),
    })
    return {
        'timestamp_utc': utc_now_iso(),
        'runtime_cli_surface': 'observerctl',
        'decision': 'go',
        'action': 'librarian-dataset-release',
        'summary': 'Protected-source approved dataset released through observer-local delegated attestation.',
        'reason_codes': [],
        'release_mode': DATASET_ACCESS_CLASS_PROTECTED,
        'dataset': selector_entry,
        'dataset_manifest_path': normalize_repo_or_absolute_path(manifest_path, project_root),
        'artifacts': artifacts,
    }

if __name__ == "__main__":
    lib = Librarian()
    lib.loop()
