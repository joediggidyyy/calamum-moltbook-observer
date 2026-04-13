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

__version__ = "1.0.1"

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
    default_analysis_dir,
    dataset_access_dir,
    ds_indexes_dir,
    ds_publication_internal_dir,
    find_project_root,
    librarian_dataset_catalog_path,
    librarian_dataset_manifest_path,
    librarian_vault_access_dir,
    librarian_vault_audit_log_path,
    librarian_vault_baseline_path,
    librarian_vault_control_state_path,
    librarian_vault_dataset_catalog_path,
    librarian_vault_dataset_manifest_path,
    librarian_vault_integrity_dir,
    librarian_vault_quarantine_dir,
    librarian_vault_report_quarantine_dir,
    librarian_vault_root,
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
VAULT_SCHEMA_VERSION = '1.0'
VAULT_BASELINE_KIND = 'librarian_vault_checksum'
VAULT_CONTROL_KIND = 'librarian_vault_control_state'
VAULT_AUDIT_KIND = 'librarian_vault_audit'

_DATASET_SCOPE_SOURCE_PATTERNS = {
    'real': (
        ('resource_real_', 8),
        ('source=real', 8),
        ('source:real', 7),
        ('"source":"real"', 8),
        ("'source': 'real'", 8),
        ('\\real\\', 4),
        ('/real/', 4),
        ('_real_', 4),
        ('(real)', 3),
        (' real ', 2),
        ('real-', 2),
        ('real_', 2),
        ('collected', 2),
    ),
    'sim': (
        ('resource_sim_', 8),
        ('source=sim', 8),
        ('source:sim', 7),
        ('"source":"sim"', 8),
        ("'source': 'sim'", 8),
        ('\\sim\\', 4),
        ('/sim/', 4),
        ('_sim_', 4),
        ('(sim)', 3),
        (' sim ', 2),
        ('sim-', 2),
        ('sim_', 2),
        ('simulation', 2),
    ),
}

_DATASET_SCOPE_MODE_PATTERNS = {
    'watch': (
        ('resource_real_watch_', 8),
        ('resource_sim_watch_', 8),
        ('\\watch\\', 4),
        ('/watch/', 4),
        ('_watch_', 4),
        ('(watch)', 3),
        (' watch ', 2),
        ('watch-', 2),
        ('watch_', 2),
    ),
    'canary': (
        ('resource_real_canary_', 8),
        ('resource_sim_canary_', 8),
        ('\\canary\\', 4),
        ('/canary/', 4),
        ('_canary_', 4),
        ('(canary)', 3),
        (' canary ', 2),
        ('canary-', 2),
        ('canary_', 2),
    ),
    'live': (
        ('resource_real_live_', 8),
        ('resource_sim_live_', 8),
        ('\\live\\', 4),
        ('/live/', 4),
        ('_live_', 4),
        ('(live)', 3),
        (' live ', 2),
        ('live-', 2),
        ('live_', 2),
    ),
    'honeypot': (
        ('resource_real_honeypot_', 8),
        ('resource_sim_honeypot_', 8),
        ('\\honeypot\\', 4),
        ('/honeypot/', 4),
        ('_honeypot_', 4),
        ('(honeypot)', 3),
        (' honeypot ', 2),
        ('honeypot-', 2),
        ('honeypot_', 2),
    ),
}

_DATASET_ALIAS_MODE_TOKENS = {
    'watch': 'wat',
    'canary': 'can',
    'live': 'liv',
    'honeypot': 'hon',
}


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
    vault_root = librarian_vault_root(project_anchor)
    authority_snapshot_path = librarian_vault_dataset_manifest_path(project_anchor)
    authority_catalog_path = librarian_vault_dataset_catalog_path(project_anchor)
    authority_access_root = librarian_vault_access_dir(project_anchor)
    integrity_root = librarian_vault_integrity_dir(project_anchor)
    baseline_path = librarian_vault_baseline_path(project_anchor)
    audit_path = librarian_vault_audit_log_path(project_anchor)
    control_state_path = librarian_vault_control_state_path(project_anchor)
    quarantine_root = librarian_vault_quarantine_dir(project_anchor)
    return {
        'project_root': project_root,
        'vault_root': vault_root,
        'snapshot_path': snapshot_path,
        'catalog_path': catalog_path,
        'access_root': access_root,
        'authority_snapshot_path': authority_snapshot_path,
        'authority_catalog_path': authority_catalog_path,
        'authority_access_root': authority_access_root,
        'integrity_root': integrity_root,
        'baseline_path': baseline_path,
        'audit_path': audit_path,
        'control_state_path': control_state_path,
        'quarantine_root': quarantine_root,
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


def _copy_text_projection(source: Path, target: Path) -> None:
    if not source.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source.read_text(encoding='utf-8'), encoding='utf-8')


def _copy_tree_projection(source_root: Path, target_root: Path) -> None:
    if not source_root.exists():
        return
    for candidate in sorted(source_root.rglob('*')):
        if not candidate.is_file():
            continue
        destination = target_root / candidate.relative_to(source_root)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(candidate, destination)


def _directory_has_files(path: Path) -> bool:
    if not path.exists():
        return False
    for candidate in path.rglob('*'):
        if candidate.is_file():
            return True
    return False


def _vault_default_control_state() -> Dict[str, Any]:
    return {
        'schema_version': VAULT_SCHEMA_VERSION,
        'kind': VAULT_CONTROL_KIND,
        'locked': False,
        'lock_reason': '',
        'locked_at_utc': '',
        'unlocked_at_utc': '',
        'updated_at_utc': utc_now_iso(),
    }


def _load_vault_control_state(paths: Dict[str, Path]) -> Dict[str, Any]:
    payload = _read_json_dict(paths['control_state_path'], default=_vault_default_control_state())
    state = _vault_default_control_state()
    if isinstance(payload, dict):
        state.update(payload)
    state['locked'] = bool(state.get('locked', False))
    state['lock_reason'] = str(state.get('lock_reason', '') or '').strip()
    state['locked_at_utc'] = str(state.get('locked_at_utc', '') or '').strip()
    state['unlocked_at_utc'] = str(state.get('unlocked_at_utc', '') or '').strip()
    return state


def _save_vault_control_state(paths: Dict[str, Path], payload: Dict[str, Any]) -> Dict[str, Any]:
    state = _vault_default_control_state()
    if isinstance(payload, dict):
        state.update(payload)
    state['locked'] = bool(state.get('locked', False))
    state['lock_reason'] = str(state.get('lock_reason', '') or '').strip()
    state['locked_at_utc'] = str(state.get('locked_at_utc', '') or '').strip()
    state['unlocked_at_utc'] = str(state.get('unlocked_at_utc', '') or '').strip()
    state['updated_at_utc'] = utc_now_iso()
    _write_json_atomic(paths['control_state_path'], state)
    return state


def _vault_integrity_files(paths: Dict[str, Path]) -> List[Path]:
    tracked: List[Path] = []
    for key in ('authority_snapshot_path', 'authority_catalog_path'):
        candidate = paths[key]
        if candidate.exists():
            tracked.append(candidate)
    if paths['authority_access_root'].exists():
        for candidate in sorted(paths['authority_access_root'].rglob('*')):
            if candidate.is_file():
                tracked.append(candidate)
    if paths['quarantine_root'].exists():
        for candidate in sorted(paths['quarantine_root'].rglob('*')):
            if candidate.is_file():
                tracked.append(candidate)
    return tracked


def _vault_fingerprint_rows(paths: Dict[str, Path]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for candidate in _vault_integrity_files(paths):
        rows.append(
            {
                'path': normalize_repo_or_absolute_path(candidate, paths['vault_root']),
                'sha256': sha256_path(candidate),
                'size_bytes': int(candidate.stat().st_size),
            }
        )
    return rows


def _count_files_recursive(path: Path) -> int:
    if not path.exists() or not path.is_dir():
        return 0
    return int(sum(1 for candidate in path.rglob('*') if candidate.is_file()))


def _path_file_exists_count(*paths_to_check: Path) -> int:
    return int(sum(1 for candidate in paths_to_check if candidate.exists() and candidate.is_file()))


def _vault_managed_surface_counts(paths: Dict[str, Path]) -> Dict[str, Any]:
    authority_file_count = _path_file_exists_count(paths['authority_snapshot_path'], paths['authority_catalog_path'])
    delegated_access_file_count = _count_files_recursive(paths['authority_access_root'])
    integrity_file_count = _count_files_recursive(paths['integrity_root'])
    quarantine_file_count = _count_files_recursive(paths['quarantine_root'])
    vault_file_count = int(
        authority_file_count
        + delegated_access_file_count
        + integrity_file_count
        + quarantine_file_count
    )

    projection_manifest_file_count = _path_file_exists_count(paths['snapshot_path'], paths['catalog_path'])
    projection_access_file_count = _count_files_recursive(paths['access_root'])
    projection_file_count = int(projection_manifest_file_count + projection_access_file_count)

    catalog_entries = _load_dataset_snapshot(paths)
    approved_selector_entry_count = int(sum(1 for entry in catalog_entries if _entry_is_admitted_dataset_selector(entry)))

    return {
        'authority_file_count': int(authority_file_count),
        'delegated_access_file_count': int(delegated_access_file_count),
        'integrity_file_count': int(integrity_file_count),
        'quarantine_file_count': int(quarantine_file_count),
        'vault_file_count': int(vault_file_count),
        'projection_manifest_file_count': int(projection_manifest_file_count),
        'projection_access_file_count': int(projection_access_file_count),
        'projection_file_count': int(projection_file_count),
        'catalog_entry_count': int(len(catalog_entries)),
        'approved_selector_entry_count': int(approved_selector_entry_count),
    }


def _vault_checksum_payload(paths: Dict[str, Path]) -> Dict[str, Any]:
    tracked_files = _vault_fingerprint_rows(paths)
    checksum = hashlib.sha256(
        json.dumps(tracked_files, sort_keys=True, separators=(',', ':')).encode('utf-8')
    ).hexdigest()
    return {
        'schema_version': VAULT_SCHEMA_VERSION,
        'kind': VAULT_BASELINE_KIND,
        'updated_at_utc': utc_now_iso(),
        'vault_root': normalize_repo_or_absolute_path(paths['vault_root'], paths['project_root']),
        'tracked_file_count': int(len(tracked_files)),
        'checksum_sha256': checksum,
        'tracked_files': tracked_files,
    }


def _write_vault_baseline(paths: Dict[str, Path], *, reason: str) -> Dict[str, Any]:
    payload = _vault_checksum_payload(paths)
    payload['reason'] = str(reason or '').strip() or 'unspecified'
    _write_json_atomic(paths['baseline_path'], payload)
    return payload


def _append_vault_audit_record(
    paths: Dict[str, Path],
    *,
    action: str,
    status: str,
    ordinary_mutation: bool,
    reason: str = '',
    reason_codes: Optional[List[str]] = None,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    checksum_payload = _vault_checksum_payload(paths)
    control_state = _load_vault_control_state(paths)
    _append_jsonl_record(
        paths['audit_path'],
        {
            'schema_version': VAULT_SCHEMA_VERSION,
            'kind': VAULT_AUDIT_KIND,
            'timestamp_utc': utc_now_iso(),
            'action': str(action or '').strip(),
            'status': str(status or '').strip() or 'ok',
            'ordinary_mutation': bool(ordinary_mutation),
            'reason': str(reason or '').strip(),
            'reason_codes': list(reason_codes or []),
            'locked': bool(control_state.get('locked', False)),
            'checksum_sha256': str(checksum_payload.get('checksum_sha256', '') or '').strip(),
            'details': dict(details or {}),
        },
    )


def _vault_artifact_refs(paths: Dict[str, Path]) -> Dict[str, str]:
    return {
        'librarian_vault_root': normalize_repo_or_absolute_path(paths['vault_root'], paths['project_root']),
        'librarian_vault_authority_manifest_json': normalize_repo_or_absolute_path(paths['authority_snapshot_path'], paths['project_root']),
        'librarian_vault_catalog_jsonl': normalize_repo_or_absolute_path(paths['authority_catalog_path'], paths['project_root']),
        'librarian_vault_access_root': normalize_repo_or_absolute_path(paths['authority_access_root'], paths['project_root']),
        'librarian_vault_baseline_json': normalize_repo_or_absolute_path(paths['baseline_path'], paths['project_root']),
        'librarian_vault_audit_jsonl': normalize_repo_or_absolute_path(paths['audit_path'], paths['project_root']),
        'librarian_vault_control_state_json': normalize_repo_or_absolute_path(paths['control_state_path'], paths['project_root']),
    }


def _sync_vault_projections(paths: Dict[str, Path]) -> None:
    _copy_text_projection(paths['authority_snapshot_path'], paths['snapshot_path'])
    _copy_text_projection(paths['authority_catalog_path'], paths['catalog_path'])
    _copy_tree_projection(paths['authority_access_root'], paths['access_root'])


def _bootstrap_librarian_vault(paths: Dict[str, Path]) -> None:
    for key in ('vault_root', 'authority_access_root', 'integrity_root', 'quarantine_root'):
        paths[key].mkdir(parents=True, exist_ok=True)

    seeded_from_projection = False
    if not paths['authority_snapshot_path'].exists() and paths['snapshot_path'].exists():
        _copy_text_projection(paths['snapshot_path'], paths['authority_snapshot_path'])
        seeded_from_projection = True
    if not paths['authority_catalog_path'].exists() and paths['catalog_path'].exists():
        _copy_text_projection(paths['catalog_path'], paths['authority_catalog_path'])
        seeded_from_projection = True
    if not _directory_has_files(paths['authority_access_root']) and _directory_has_files(paths['access_root']):
        _copy_tree_projection(paths['access_root'], paths['authority_access_root'])
        seeded_from_projection = True

    if not paths['control_state_path'].exists():
        _save_vault_control_state(paths, _vault_default_control_state())

    _sync_vault_projections(paths)

    if seeded_from_projection or not paths['baseline_path'].exists():
        _write_vault_baseline(paths, reason='bootstrap')
        _append_vault_audit_record(
            paths,
            action='librarian-vault-bootstrap',
            status='ok',
            ordinary_mutation=False,
            reason='bootstrap',
            details={'seeded_from_projection': bool(seeded_from_projection)},
        )


def _build_dataset_snapshot_payload(catalog_path: Path, project_root: Path, entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        'schema_version': DATASET_SELECTOR_SCHEMA_VERSION,
        'family_id': 'librarian_dataset',
        'updated_at_utc': utc_now_iso(),
        'catalog_path': normalize_repo_or_absolute_path(catalog_path, project_root),
        'entries': _sorted_dataset_entries(entries),
    }


def _vault_integrity_state(paths: Dict[str, Path]) -> Dict[str, Any]:
    _bootstrap_librarian_vault(paths)
    baseline = _read_json_dict(paths['baseline_path'], default={})
    current = _vault_checksum_payload(paths)
    baseline_checksum = str(baseline.get('checksum_sha256', '') or '').strip()
    current_checksum = str(current.get('checksum_sha256', '') or '').strip()
    if not baseline_checksum:
        status = 'warn'
        reason_codes = ['critical_check_failed:librarian_vault_baseline_missing']
    elif baseline_checksum != current_checksum:
        status = 'err'
        reason_codes = ['critical_check_failed:librarian_vault_integrity_mismatch']
    else:
        status = 'ok'
        reason_codes = []
    return {
        'status': status,
        'reason_codes': reason_codes,
        'baseline': baseline,
        'current': current,
    }


def _vault_locked(paths: Dict[str, Path]) -> bool:
    return bool(_load_vault_control_state(paths).get('locked', False))


def _vault_locked_packet(paths: Dict[str, Path], *, action: str, summary: str) -> Dict[str, Any]:
    return {
        'timestamp_utc': utc_now_iso(),
        'runtime_cli_surface': 'observerctl',
        'decision': 'no-go',
        'action': str(action or '').strip(),
        'summary': str(summary or '').strip(),
        'reason_codes': ['critical_check_failed:librarian_vault_locked'],
        'artifacts': _vault_artifact_refs(paths),
    }


def _resolve_catalog_ref(project_root: Path, ref: str) -> Path:
    path = Path(str(ref or '').strip())
    if not path.is_absolute():
        path = project_root / path
    return path.resolve()


def _dataset_scope_token(value: str, allowed: Tuple[str, ...]) -> str:
    token = str(value or '').strip().lower()
    return token if token in allowed else 'unknown'


def _dataset_scope_candidate_texts(
    manifest_path: Path,
    payload: Dict[str, Any],
    *,
    display_name: str = '',
    run_id: str = '',
    source_binding: str = '',
) -> List[str]:
    texts: List[str] = [
        str(manifest_path),
        str(display_name or ''),
        str(run_id or ''),
        str(source_binding or ''),
        str(payload.get('features_csv', '') or ''),
        str(payload.get('labels_csv', '') or ''),
        str(payload.get('splits_csv', '') or ''),
        str(payload.get('split_manifest_json', '') or ''),
    ]
    for item in list(payload.get('inputs', []) or []):
        if isinstance(item, dict):
            texts.append(str(item.get('path', '') or ''))
            texts.append(str(item.get('source', '') or ''))
            texts.append(str(item.get('mode', '') or ''))
            texts.append(str(item.get('profile', '') or ''))
            texts.append(str(item.get('stream_type', '') or ''))
        else:
            texts.append(str(item or ''))
    return [str(text).strip().lower() for text in texts if str(text or '').strip()]


def _infer_dataset_scope_token(texts: List[str], patterns_by_token: Dict[str, Tuple[Tuple[str, int], ...]]) -> str:
    scores: Dict[str, int] = {}
    for token, patterns in patterns_by_token.items():
        score = 0
        for text in texts:
            for pattern, weight in patterns:
                if pattern in text:
                    score += int(weight)
        scores[token] = score

    if not scores:
        return 'unknown'
    best_score = max(scores.values())
    if best_score <= 0:
        return 'unknown'
    winners = [token for token, score in scores.items() if score == best_score]
    return winners[0] if len(winners) == 1 else 'unknown'


def _dataset_scope_weighted_token(scores: Dict[str, int]) -> str:
    if not scores:
        return 'unknown'
    best_score = max(scores.values())
    if best_score <= 0:
        return 'unknown'
    winners = [token for token, score in scores.items() if score == best_score]
    return winners[0] if len(winners) == 1 else 'unknown'


def _dataset_scope_input_weight(value: Any) -> int:
    try:
        weight = int(value)
    except Exception:
        return 1
    return weight if weight > 0 else 1


def _infer_dataset_scope_from_inputs(payload: Dict[str, Any]) -> Tuple[str, str]:
    inputs = list(payload.get('inputs', []) or [])
    if not inputs:
        return 'unknown', 'unknown'

    source_scores: Dict[str, int] = {'sim': 0, 'real': 0}
    mode_scores: Dict[str, int] = {'watch': 0, 'canary': 0, 'live': 0, 'honeypot': 0}

    for item in inputs:
        item_texts: List[str] = []
        item_weight = 1
        if isinstance(item, dict):
            item_texts = [
                str(item.get('path', '') or ''),
                str(item.get('source', '') or ''),
                str(item.get('mode', '') or ''),
                str(item.get('profile', '') or ''),
                str(item.get('stream_type', '') or ''),
                str(item.get('name', '') or ''),
                str(item.get('label', '') or ''),
            ]
            item_weight = _dataset_scope_input_weight(
                item.get('records', item.get('record_count', item.get('total_records', 1)))
            )
        else:
            item_texts = [str(item or '')]

        normalized_texts = [str(text).strip().lower() for text in item_texts if str(text or '').strip()]
        if not normalized_texts:
            continue

        source_token = _infer_dataset_scope_token(normalized_texts, _DATASET_SCOPE_SOURCE_PATTERNS)
        mode_token = _infer_dataset_scope_token(normalized_texts, _DATASET_SCOPE_MODE_PATTERNS)
        if source_token in source_scores:
            source_scores[source_token] += item_weight
        if mode_token in mode_scores:
            mode_scores[mode_token] += item_weight

    return _dataset_scope_weighted_token(source_scores), _dataset_scope_weighted_token(mode_scores)


def _infer_dataset_scope(
    manifest_path: Path,
    payload: Dict[str, Any],
    *,
    source: str = '',
    mode: str = '',
    display_name: str = '',
    run_id: str = '',
    source_binding: str = '',
) -> Tuple[str, str]:
    resolved_source = _dataset_scope_token(source, ('sim', 'real'))
    resolved_mode = _dataset_scope_token(mode, ('watch', 'canary', 'live', 'honeypot'))
    if resolved_source != 'unknown' and resolved_mode != 'unknown':
        return resolved_source, resolved_mode

    texts = _dataset_scope_candidate_texts(
        manifest_path,
        payload,
        display_name=display_name,
        run_id=run_id,
        source_binding=source_binding,
    )
    if resolved_source == 'unknown':
        resolved_source = _infer_dataset_scope_token(texts, _DATASET_SCOPE_SOURCE_PATTERNS)
    if resolved_mode == 'unknown':
        resolved_mode = _infer_dataset_scope_token(texts, _DATASET_SCOPE_MODE_PATTERNS)
    if resolved_source == 'unknown' or resolved_mode == 'unknown':
        input_source, input_mode = _infer_dataset_scope_from_inputs(payload)
        if resolved_source == 'unknown':
            resolved_source = input_source
        if resolved_mode == 'unknown':
            resolved_mode = input_mode
    return resolved_source, resolved_mode


def _normalize_dataset_scope_entry(paths: Dict[str, Path], entry: Dict[str, Any]) -> Dict[str, Any]:
    row = dict(entry or {})
    source = _dataset_scope_token(str(row.get('source', '') or ''), ('sim', 'real'))
    mode = _dataset_scope_token(str(row.get('mode', '') or ''), ('watch', 'canary', 'live', 'honeypot'))
    if source != 'unknown' and mode != 'unknown':
        row['source'] = source
        row['mode'] = mode
        return row

    resolver = dict(row.get('resolver', {}) or {}) if isinstance(row.get('resolver', {}), dict) else {}
    manifest_ref = str(resolver.get('dataset_manifest_path', '') or '').strip()
    if not manifest_ref:
        row['source'] = source
        row['mode'] = mode
        return row

    try:
        manifest_path = _resolve_catalog_ref(paths['project_root'], manifest_ref)
    except Exception:
        row['source'] = source
        row['mode'] = mode
        return row
    if not manifest_path.exists():
        row['source'] = source
        row['mode'] = mode
        return row

    payload = _read_json_dict(manifest_path, default={})
    if not payload:
        row['source'] = source
        row['mode'] = mode
        return row

    inferred_source, inferred_mode = _infer_dataset_scope(
        manifest_path,
        payload,
        source=source,
        mode=mode,
        display_name=str(row.get('display_name', '') or '').strip(),
        run_id=str(row.get('run_id', '') or '').strip(),
        source_binding=str(row.get('source_binding', '') or '').strip(),
    )
    row['source'] = inferred_source
    row['mode'] = inferred_mode
    return row


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
    resolver = dict(entry.get('resolver', {}) or {}) if isinstance(entry.get('resolver', {}), dict) else {}
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
        'registration_kind': str(entry.get('registration_kind', '') or '').strip(),
        'baseline_window_id': str(entry.get('baseline_window_id', '') or '').strip(),
        'baseline_analysis_packet': str(resolver.get('baseline_analysis_packet', '') or '').strip(),
        'baseline_analysis_index_path': str(resolver.get('baseline_analysis_index_path', '') or '').strip(),
        'baseline_decision_state': str(entry.get('baseline_decision_state', '') or '').strip(),
        'baseline_summary': str(entry.get('baseline_summary', '') or '').strip(),
        'baseline_sample_counts': dict(entry.get('baseline_sample_counts', {}) or {}) if isinstance(entry.get('baseline_sample_counts', {}), dict) else {},
        'baseline_recorded_at_utc': str(entry.get('baseline_recorded_at_utc', '') or '').strip(),
        'display_alias': _dataset_entry_display_alias(entry, resolver),
        'dataset_manifest_sha256': str(resolver.get('dataset_manifest_sha256', '') or '').strip(),
    }


def _dataset_entry_display_alias(entry: Dict[str, Any], resolver: Dict[str, Any]) -> str:
    explicit_alias = str(entry.get('display_alias', '') or '').strip()
    if explicit_alias:
        return explicit_alias
    source = str(entry.get('source', '') or '').strip().lower()
    mode = str(entry.get('mode', '') or '').strip().lower()
    manifest_sha = str(resolver.get('dataset_manifest_sha256', '') or '').strip().lower()
    scoped_alias = _dataset_display_alias_from_scope(source, mode, manifest_sha)
    if scoped_alias:
        return scoped_alias
    for candidate in (
        entry.get('run_id', ''),
        entry.get('display_name', ''),
        entry.get('entry_id', ''),
    ):
        text = str(candidate or '').strip()
        if text:
            return sanitize_run_id(text) or text
    return ''


def _dataset_display_alias_from_scope(source: str, mode: str, manifest_sha: str) -> str:
    source_token = str(source or '').strip().lower()
    mode_token = str(mode or '').strip().lower()
    sha_token = str(manifest_sha or '').strip().lower()
    mode_alias = _DATASET_ALIAS_MODE_TOKENS.get(mode_token, '')
    source_alias = 's' if source_token == 'sim' else ('r' if source_token == 'real' else '')
    if not mode_alias or not source_alias or len(sha_token) < 4:
        return ''
    return '{0}-{1}{2}'.format(mode_alias, source_alias, sha_token[-4:])


def _dataset_manifest_fallback_alias(manifest_path: Path, payload: Dict[str, Any], manifest_sha: str) -> str:
    for candidate in (
        payload.get('display_alias', ''),
        payload.get('run_id', ''),
        payload.get('display_name', ''),
    ):
        text = sanitize_run_id(str(candidate or '').strip())
        if text:
            return text
    sha_token = str(manifest_sha or '').strip().lower()
    if len(sha_token) >= 6:
        return 'dataset-{0}'.format(sha_token[-6:])
    return sanitize_run_id(manifest_path.stem) or 'dataset'


def dataset_display_alias_for_manifest(project_anchor: Path, dataset_manifest_ref: Any) -> str:
    paths = _dataset_catalog_paths(project_anchor)
    _bootstrap_librarian_vault(paths)
    project_root = paths['project_root']
    token = str(dataset_manifest_ref or '').strip()
    if not token:
        return ''
    try:
        manifest_path = _resolve_catalog_ref(project_root, token)
    except Exception:
        return ''
    if not manifest_path.exists():
        return ''

    manifest_sha = sha256_path(manifest_path)
    manifest_key = normalize_repo_or_absolute_path(manifest_path, project_root)

    for entry in _load_dataset_snapshot(paths):
        if not isinstance(entry, dict):
            continue
        resolver = dict(entry.get('resolver', {}) or {}) if isinstance(entry.get('resolver', {}), dict) else {}
        entry_manifest_key = str(resolver.get('dataset_manifest_path', '') or '').strip()
        entry_manifest_sha = str(resolver.get('dataset_manifest_sha256', '') or '').strip().lower()
        if entry_manifest_key == manifest_key or (entry_manifest_sha and entry_manifest_sha == manifest_sha.lower()):
            alias = _dataset_entry_display_alias(entry, resolver)
            if alias:
                return alias

    payload = _read_json_dict(manifest_path, default={})
    if not payload:
        return 'dataset-{0}'.format(manifest_sha[-6:]) if len(manifest_sha) >= 6 else ''
    inferred_source, inferred_mode = _infer_dataset_scope(
        manifest_path,
        payload,
        display_name=str(payload.get('display_name', '') or manifest_path.parent.name or manifest_path.stem).strip(),
        run_id=str(payload.get('run_id', '') or '').strip(),
        source_binding='dataset_manifest_sha256:{0}'.format(manifest_sha),
    )
    scoped_alias = _dataset_display_alias_from_scope(inferred_source, inferred_mode, manifest_sha)
    if scoped_alias:
        return scoped_alias
    return _dataset_manifest_fallback_alias(manifest_path, payload, manifest_sha)


def _load_dataset_snapshot(paths: Dict[str, Path]) -> List[Dict[str, Any]]:
    _bootstrap_librarian_vault(paths)
    payload = _read_json_dict(paths['authority_snapshot_path'], default={})
    entries = payload.get('entries', []) if isinstance(payload.get('entries', []), list) else []
    if entries:
        return _sorted_dataset_entries(
            [_normalize_dataset_scope_entry(paths, entry) for entry in entries if isinstance(entry, dict)]
        )

    entries = []
    if paths['authority_catalog_path'].exists():
        for line in paths['authority_catalog_path'].read_text(encoding='utf-8').splitlines():
            text = str(line or '').strip()
            if not text:
                continue
            try:
                row = json.loads(text)
            except Exception:
                continue
            if isinstance(row, dict):
                entries.append(_normalize_dataset_scope_entry(paths, row))
    return _sorted_dataset_entries(entries)


def _save_dataset_snapshot(paths: Dict[str, Path], entries: List[Dict[str, Any]]) -> None:
    _bootstrap_librarian_vault(paths)
    ordered_entries = _sorted_dataset_entries(entries)
    _write_json_atomic(
        paths['authority_snapshot_path'],
        _build_dataset_snapshot_payload(paths['authority_catalog_path'], paths['project_root'], ordered_entries),
    )
    _write_json_atomic(
        paths['snapshot_path'],
        _build_dataset_snapshot_payload(paths['catalog_path'], paths['project_root'], ordered_entries),
    )


def _entry_is_admitted_dataset_selector(entry: Dict[str, Any]) -> bool:
    status = str(entry.get('status', '') or '').strip().lower()
    readiness = str(entry.get('readiness', '') or '').strip().lower()
    registration_kind = str(entry.get('registration_kind', '') or '').strip().lower()
    return status == 'approved' and readiness == 'ready' and registration_kind == 'manual-register'


def _approved_dataset_entries(paths: Dict[str, Path]) -> List[Dict[str, Any]]:
    return [entry for entry in _load_dataset_snapshot(paths) if _entry_is_admitted_dataset_selector(entry)]


def _resolve_dataset_entry(paths: Dict[str, Path], selector: str) -> Optional[Dict[str, Any]]:
    token = str(selector or '').strip()
    if not token:
        return None
    entries = _approved_dataset_entries(paths)
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


def _analysis_evidence_index_path(project_anchor: Path, source: str, mode: str) -> Path:
    return default_analysis_dir(project_anchor) / 'observer_derived' / source / mode / 'evidence' / 'index.jsonl'


def _resolve_analysis_ref(project_root: Path, ref: str) -> Optional[Path]:
    text = str(ref or '').strip()
    if not text:
        return None
    path = Path(text.replace('/', os.sep))
    if not path.is_absolute():
        path = project_root / path
    try:
        return path.resolve()
    except Exception:
        return path


def _latest_dataset_baseline_context(project_anchor: Path, project_root: Path, source: str, mode: str) -> Dict[str, Any]:
    source_token = _dataset_scope_token(source, ('sim', 'real'))
    mode_token = _dataset_scope_token(mode, ('watch', 'canary', 'live', 'honeypot'))
    if source_token == 'unknown' or mode_token == 'unknown':
        return {}

    index_path = _analysis_evidence_index_path(project_anchor, source_token, mode_token)
    if not index_path.exists():
        return {}

    try:
        lines = [line for line in index_path.read_text(encoding='utf-8', errors='ignore').splitlines() if str(line).strip()]
    except Exception:
        return {}

    for line in reversed(lines):
        try:
            row = json.loads(line)
        except Exception:
            continue
        if not isinstance(row, dict):
            continue
        if str(row.get('event', '') or '').strip().lower() != 'baseline_analysis':
            continue

        packet_ref = str(row.get('packet_path', '') or '').strip()
        packet_path = _resolve_analysis_ref(project_root, packet_ref)
        packet = _read_json_dict(packet_path, default={}) if packet_path is not None and packet_path.exists() else {}

        baseline_window_id = str(
            packet.get('baseline_window_id', '')
            or row.get('baseline_window_id', '')
            or row.get('window_id', '')
            or ''
        ).strip()
        decision_state = str(packet.get('decision', row.get('decision', '')) or '').strip().lower()
        sample_counts = dict(packet.get('sample_counts', {}) or {}) if isinstance(packet.get('sample_counts', {}), dict) else {}

        baseline_packet_ref = ''
        if packet_path is not None and packet_path.exists():
            baseline_packet_ref = normalize_repo_or_absolute_path(packet_path, project_root)
        elif packet_ref:
            baseline_packet_ref = str(packet_ref).strip()

        return {
            'baseline_window_id': baseline_window_id,
            'baseline_analysis_packet': baseline_packet_ref,
            'baseline_analysis_index_path': normalize_repo_or_absolute_path(index_path, project_root),
            'baseline_decision_state': decision_state,
            'baseline_summary': str(packet.get('summary', '') or '').strip(),
            'baseline_sample_counts': sample_counts,
            'baseline_recorded_at_utc': str(packet.get('timestamp_utc', '') or row.get('timestamp_utc', '') or '').strip(),
        }
    return {}


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
    resolved_source, resolved_mode = _infer_dataset_scope(
        manifest_path,
        payload,
        source=source,
        mode=mode,
        display_name=display,
        run_id=entry_run_id,
        source_binding=resolved_binding,
    )

    resolver = {
        'dataset_manifest_path': normalize_repo_or_absolute_path(manifest_path, project_root),
        'dataset_manifest_sha256': manifest_sha,
        'features_csv_path': normalize_repo_or_absolute_path(features_path, project_root) if features_ref_raw else '',
        'labels_csv_path': normalize_repo_or_absolute_path(labels_path, project_root) if labels_ref_raw and labels_path is not None else '',
    }
    baseline_context = _latest_dataset_baseline_context(project_anchor, project_root, resolved_source, resolved_mode)
    baseline_packet_ref = str(baseline_context.get('baseline_analysis_packet', '') or '').strip()
    baseline_index_ref = str(baseline_context.get('baseline_analysis_index_path', '') or '').strip()
    if baseline_packet_ref:
        resolver['baseline_analysis_packet'] = baseline_packet_ref
    if baseline_index_ref:
        resolver['baseline_analysis_index_path'] = baseline_index_ref

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
        'source': resolved_source,
        'mode': resolved_mode,
        'source_binding': resolved_binding,
        'report_manifest_ref': str(report_manifest_ref or '').strip(),
        'registration_kind': str(registration_kind or 'manual').strip() or 'manual',
        'baseline_window_id': str(baseline_context.get('baseline_window_id', '') or '').strip(),
        'baseline_decision_state': str(baseline_context.get('baseline_decision_state', '') or '').strip(),
        'baseline_summary': str(baseline_context.get('baseline_summary', '') or '').strip(),
        'baseline_sample_counts': dict(baseline_context.get('baseline_sample_counts', {}) or {}) if isinstance(baseline_context.get('baseline_sample_counts', {}), dict) else {},
        'baseline_recorded_at_utc': str(baseline_context.get('baseline_recorded_at_utc', '') or '').strip(),
        'resolver': resolver,
    }


def _upsert_dataset_entry(paths: Dict[str, Path], entry: Dict[str, Any]) -> Dict[str, Any]:
    _bootstrap_librarian_vault(paths)
    existing = _load_dataset_snapshot(paths)
    remaining = [row for row in existing if str(row.get('entry_id', '')).strip() != str(entry.get('entry_id', '')).strip()]
    merged = [entry] + remaining
    merged = _sorted_dataset_entries(merged)
    _append_jsonl_record(paths['authority_catalog_path'], entry)
    _save_dataset_snapshot(paths, merged)
    _sync_vault_projections(paths)
    return {
        'entry': entry,
        'snapshot_path': normalize_repo_or_absolute_path(paths['snapshot_path'], paths['project_root']),
        'catalog_path': normalize_repo_or_absolute_path(paths['catalog_path'], paths['project_root']),
        'vault_snapshot_path': normalize_repo_or_absolute_path(paths['authority_snapshot_path'], paths['project_root']),
        'vault_catalog_path': normalize_repo_or_absolute_path(paths['authority_catalog_path'], paths['project_root']),
    }


def refresh_librarian_dataset_catalog_from_run_manifest(project_anchor: Path, manifest_payload: Dict[str, Any]) -> Dict[str, Any]:
    artifacts = dict(manifest_payload.get('artifacts', {}) or {}) if isinstance(manifest_payload, dict) else {}
    dataset_ref = str(artifacts.get('dataset_manifest', '') or '').strip()
    if not dataset_ref:
        return {
            'timestamp_utc': utc_now_iso(),
            'runtime_cli_surface': 'observerctl',
            'action': 'librarian-dataset-refresh',
            'decision': 'go',
            'catalog_updated': False,
            'summary': 'No dataset authority change was needed for this DS run.',
            'reason_codes': [],
        }

    return {
        'timestamp_utc': utc_now_iso(),
        'runtime_cli_surface': 'observerctl',
        'decision': 'go',
        'action': 'librarian-dataset-refresh',
        'catalog_updated': False,
        'summary': 'DS run artifacts were recorded without changing librarian-approved dataset authority; explicit librarian registration is required for selector admission.',
        'reason_codes': [],
        'dataset_manifest_ref': dataset_ref,
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
    _bootstrap_librarian_vault(paths)
    project_root = paths['project_root']
    if _vault_locked(paths):
        return _vault_locked_packet(
            paths,
            action='librarian-dataset-register',
            summary='Dataset registration denied because the protected librarian vault is locked.',
        )
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
    baseline = _write_vault_baseline(paths, reason='librarian-dataset-register')
    _append_vault_audit_record(
        paths,
        action='librarian-dataset-register',
        status='ok',
        ordinary_mutation=True,
        reason='manual-register',
        details={
            'entry_id': str(entry.get('entry_id', '') or '').strip(),
            'baseline_checksum': str(baseline.get('checksum_sha256', '') or '').strip(),
        },
    )
    resolved = _resolve_dataset_entry(paths, str(entry.get('entry_id', '')))
    selector_entry = resolved.get('selector_entry', {}) if isinstance(resolved, dict) else {}
    artifacts = {
        **_vault_artifact_refs(paths),
        'librarian_dataset_manifest_json': update['snapshot_path'],
        'librarian_dataset_catalog_jsonl': update['catalog_path'],
        'librarian_vault_baseline_checksum': str(baseline.get('checksum_sha256', '') or '').strip(),
    }
    baseline_packet_ref = str(selector_entry.get('baseline_analysis_packet', '') or '').strip()
    baseline_index_ref = str(selector_entry.get('baseline_analysis_index_path', '') or '').strip()
    if baseline_packet_ref:
        artifacts['baseline_analysis_packet'] = baseline_packet_ref
    if baseline_index_ref:
        artifacts['baseline_analysis_index_jsonl'] = baseline_index_ref
    return {
        'timestamp_utc': utc_now_iso(),
        'runtime_cli_surface': 'observerctl',
        'decision': 'go',
        'action': 'librarian-dataset-register',
        'summary': 'Dataset registered in the librarian-approved catalog.',
        'reason_codes': [],
        'dataset': selector_entry,
        'artifacts': artifacts,
    }


def list_librarian_datasets_packet(project_anchor: Path) -> Dict[str, Any]:
    paths = _dataset_catalog_paths(project_anchor)
    _bootstrap_librarian_vault(paths)
    entries = _approved_dataset_entries(paths)
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
            **_vault_artifact_refs(paths),
            'librarian_dataset_manifest_json': normalize_repo_or_absolute_path(paths['snapshot_path'], paths['project_root']),
            'librarian_dataset_catalog_jsonl': normalize_repo_or_absolute_path(paths['catalog_path'], paths['project_root']),
        },
        'reason_codes': [],
    }


def _report_store_paths(project_anchor: Path) -> Dict[str, Path]:
    project_root = find_project_root(project_anchor)
    reports_root = project_root / 'docs' / 'reports'
    collections_root = reports_root / 'collections'
    vault_quarantine_root = librarian_vault_report_quarantine_dir(project_anchor) / (sanitize_run_id(project_root.name) or project_root.name)
    return {
        'project_root': project_root,
        'reports_root': reports_root,
        'collections_root': collections_root,
        'vault_quarantine_root': vault_quarantine_root,
    }


def _report_store_collection_rows(paths: Dict[str, Path]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    collections_root = paths['collections_root']
    project_root = paths['project_root']
    if not collections_root.exists():
        return rows

    for alias_dir in sorted(candidate for candidate in collections_root.iterdir() if candidate.is_dir()):
        collection_dir = alias_dir / 'collection'
        processing_dir = alias_dir / 'processing'
        collection_packets = sorted(collection_dir.glob('*.collection.md')) if collection_dir.exists() else []
        processing_packets = sorted(path for path in processing_dir.rglob('*.md')) if processing_dir.exists() else []
        stale_report_path = collection_dir / 'report.md'
        rows.append(
            {
                'collection_alias': alias_dir.name,
                'path': normalize_repo_or_absolute_path(alias_dir, project_root),
                'collection_packet_count': int(len(collection_packets)),
                'processing_packet_count': int(len(processing_packets)),
                'stale_report_md_present': bool(stale_report_path.exists()),
                'stale_report_md_path': normalize_repo_or_absolute_path(stale_report_path, project_root) if stale_report_path.exists() else '',
                'latest_collection_packet': normalize_repo_or_absolute_path(collection_packets[-1], project_root) if collection_packets else '',
                'latest_processing_packet': normalize_repo_or_absolute_path(processing_packets[-1], project_root) if processing_packets else '',
            }
        )
    return rows


def _report_store_auxiliary_reset_paths(project_anchor: Path) -> Dict[str, Path]:
    indexes_root = ds_indexes_dir(project_anchor)
    internal_root = ds_publication_internal_dir(project_anchor)
    return {
        'ledger_path': indexes_root / 'ds_run_index.jsonl',
        'latest_index_path': indexes_root / 'ds_latest.json',
        'internal_collections_root': internal_root / 'collections',
    }


def _archive_reset_surface(source: Path, destination: Path) -> Optional[Path]:
    if not source.exists():
        return None
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(destination))
    return destination


def _report_store_archive_manifest(
    paths: Dict[str, Path],
    *,
    action: str,
    reason: str,
    archive_root: Path,
    archived_paths: List[Path],
    archived_aliases: Optional[List[str]] = None,
    archived_auxiliary_paths: Optional[List[Path]] = None,
    live_target: Path,
) -> Dict[str, Any]:
    project_root = paths['project_root']
    auxiliary_paths = list(archived_auxiliary_paths or [])
    alias_rows = sorted({str(alias).strip() for alias in list(archived_aliases or []) if str(alias).strip()})
    if not alias_rows:
        alias_rows = [path.name for path in archived_paths]
    manifest = {
        'action': str(action or '').strip(),
        'reason': str(reason or '').strip(),
        'quarantine_surface': 'librarian_vault_quarantine',
        'project_root': str(project_root),
        'archive_root': str(archive_root),
        'quarantine_root': str(archive_root),
        'live_target': str(live_target),
        'archived_paths': [str(path) for path in archived_paths],
        'archived_aliases': alias_rows,
        'archived_alias_count': int(len(alias_rows)),
        'archived_auxiliary_paths': [str(path) for path in auxiliary_paths],
        'archived_auxiliary_count': int(len(auxiliary_paths)),
        'archived_at_utc': utc_now_iso(),
    }
    archive_root.mkdir(parents=True, exist_ok=True)
    (archive_root / 'archive_manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding='utf-8')
    return manifest


def librarian_report_store_packet(
    project_anchor: Path,
    *,
    show: bool = False,
    purge: bool = False,
    republish: bool = False,
    delete_alias: str = '',
) -> Dict[str, Any]:
    from analysis.report_aggregate import set_tracked_ds_publication_republish_state, tracked_ds_publication_republish_state

    paths = _report_store_paths(project_anchor)
    vault_paths = _dataset_catalog_paths(project_anchor)
    _bootstrap_librarian_vault(vault_paths)

    project_root = paths['project_root']
    collections_root = paths['collections_root']
    reports_root = paths['reports_root']
    vault_quarantine_root = paths['vault_quarantine_root']
    republish_state = tracked_ds_publication_republish_state(project_anchor=project_anchor)
    base_artifacts = {
        **_vault_artifact_refs(vault_paths),
        'reports_root': normalize_repo_or_absolute_path(reports_root, project_root),
        'collections_root': normalize_repo_or_absolute_path(collections_root, project_root),
        'vault_quarantine_root': normalize_repo_or_absolute_path(vault_quarantine_root, project_root),
        'archive_parent': normalize_repo_or_absolute_path(vault_quarantine_root, project_root),
        'publication_control_json': str(republish_state.get('control_path', '') or ''),
    }

    delete_token = str(delete_alias or '').strip()
    if not show and not purge and not republish and not delete_token:
        show = True

    action_count = int(bool(show)) + int(bool(purge)) + int(bool(republish)) + int(bool(delete_token))
    if action_count != 1:
        return {
            'timestamp_utc': utc_now_iso(),
            'runtime_cli_surface': 'observerctl',
            'decision': 'no-go',
            'action': 'librarian-store-reports',
            'summary': 'Choose exactly one report-store action: --show, --purge, --republish, or --delete <wizard-alias>.',
            'reason_codes': ['policy_denied:librarian_store_reports_action_conflict'],
            'republish_required': bool(republish_state.get('republish_required', False)),
            'artifacts': dict(base_artifacts),
        }

    if show:
        rows = _report_store_collection_rows(paths)
        stale_count = int(sum(1 for row in rows if bool(row.get('stale_report_md_present', False))))
        return {
            'timestamp_utc': utc_now_iso(),
            'runtime_cli_surface': 'observerctl',
            'decision': 'go',
            'action': 'librarian-store-reports-show',
            'summary': 'Tracked report collection aliases enumerated.' if rows else 'No tracked report collection aliases are materialized.',
            'count': int(len(rows)),
            'stale_report_md_count': stale_count,
            'report_collections': rows,
            'republish_required': bool(republish_state.get('republish_required', False)),
            'reason_codes': [],
            'artifacts': dict(base_artifacts),
        }

    if republish:
        from analysis.report_aggregate import refresh_tracked_ds_publication

        publication = refresh_tracked_ds_publication(project_anchor=project_anchor, explicit_republish=True)
        aggregate_paths = publication.get('aggregate_paths', {}) if isinstance(publication.get('aggregate_paths', {}), dict) else {}
        current_run = publication.get('current_run', {}) if isinstance(publication.get('current_run', {}), dict) else {}
        refreshed_state = tracked_ds_publication_republish_state(project_anchor=project_anchor)
        return {
            'timestamp_utc': utc_now_iso(),
            'runtime_cli_surface': 'observerctl',
            'decision': 'go',
            'action': 'librarian-store-reports-republish',
            'summary': 'Tracked report publication rebuilt from the canonical saved-run ledger.',
            'count': int(len(_report_store_collection_rows(paths))),
            'published_run_count': int(publication.get('published_run_count', 0) or 0),
            'current_run_id': str(current_run.get('run_id', '') or '').strip(),
            'report_collections': _report_store_collection_rows(paths),
            'republish_required': bool(refreshed_state.get('republish_required', False)),
            'reason_codes': [],
            'artifacts': {
                **_vault_artifact_refs(vault_paths),
                'reports_root': normalize_repo_or_absolute_path(reports_root, project_root),
                'collections_root': normalize_repo_or_absolute_path(collections_root, project_root),
                'vault_quarantine_root': normalize_repo_or_absolute_path(vault_quarantine_root, project_root),
                'archive_parent': normalize_repo_or_absolute_path(vault_quarantine_root, project_root),
                'publication_control_json': str(refreshed_state.get('control_path', '') or ''),
                'ds_run_index_jsonl': normalize_repo_or_absolute_path(_report_store_auxiliary_reset_paths(project_anchor)['ledger_path'], project_root),
                'ds_latest_json': normalize_repo_or_absolute_path(_report_store_auxiliary_reset_paths(project_anchor)['latest_index_path'], project_root),
                'aggregate_report_md': str(aggregate_paths.get('aggregate_report_md', '') or ''),
                'latest_md': str(aggregate_paths.get('latest_md', '') or ''),
                'generated_surfaces_md': str(aggregate_paths.get('generated_surfaces_md', '') or ''),
            },
        }

    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    vault_quarantine_root.mkdir(parents=True, exist_ok=True)

    if purge:
        from analysis.report_aggregate import reset_tracked_ds_publication_state

        archived_paths: List[Path] = []
        archived_auxiliary_paths: List[Path] = []
        archived_aliases = [str(row.get('collection_alias', '') or '').strip() for row in _report_store_collection_rows(paths) if isinstance(row, dict)]
        archive_root = vault_quarantine_root / 'report_collections_reset_{0}'.format(stamp)
        report_archive_targets = {
            reports_root / 'INDEX.md': archive_root / 'docs' / 'reports' / 'INDEX.md',
            reports_root / 'aggregates': archive_root / 'docs' / 'reports' / 'aggregates',
            reports_root / 'reference': archive_root / 'docs' / 'reports' / 'reference',
            collections_root: archive_root / 'docs' / 'reports' / 'collections',
        }
        for source, destination in report_archive_targets.items():
            archived_path = _archive_reset_surface(source, destination)
            if archived_path is not None:
                archived_paths.append(archived_path)

        auxiliary_paths = _report_store_auxiliary_reset_paths(project_anchor)
        archive_targets = {
            'ledger_path': archive_root / 'analysis_indexes' / 'ds_run_index.jsonl',
            'latest_index_path': archive_root / 'analysis_indexes' / 'ds_latest.json',
            'internal_collections_root': archive_root / 'analysis_indexes' / 'ds_publication' / 'collections',
        }
        for key, destination in archive_targets.items():
            archived_path = _archive_reset_surface(auxiliary_paths[key], destination)
            if archived_path is not None:
                archived_auxiliary_paths.append(archived_path)

        reset_packet = reset_tracked_ds_publication_state(project_anchor=project_anchor)
        manifest = _report_store_archive_manifest(
            paths,
            action='archive-and-reset-report-collections',
            reason='move materialized tracked report publication into the librarian vault quarantine and reset live reporting to zero-state',
            archive_root=archive_root,
            archived_paths=archived_paths,
            archived_aliases=archived_aliases,
            archived_auxiliary_paths=archived_auxiliary_paths,
            live_target=reports_root,
        )
        baseline = _write_vault_baseline(vault_paths, reason='librarian-store-reports-purge')
        _append_vault_audit_record(
            vault_paths,
            action='librarian-store-reports-purge',
            status='ok',
            ordinary_mutation=True,
            reason='tracked-report-quarantine',
            details={
                'archived_alias_count': int(manifest.get('archived_alias_count', 0) or 0),
                'archive_root': normalize_repo_or_absolute_path(archive_root, project_root),
                'baseline_checksum': str(baseline.get('checksum_sha256', '') or '').strip(),
            },
        )
        return {
            'timestamp_utc': utc_now_iso(),
            'runtime_cli_surface': 'observerctl',
            'decision': 'go',
            'action': 'librarian-store-reports-purge',
            'summary': 'Tracked report publication moved into the librarian vault quarantine, selector authority cleared, and live report surfaces reset to zero-state.',
            'archived_aliases': list(manifest.get('archived_aliases', []) or []),
            'archived_alias_count': int(manifest.get('archived_alias_count', 0) or 0),
            'archived_auxiliary_count': int(manifest.get('archived_auxiliary_count', 0) or 0),
            'report_collections': _report_store_collection_rows(paths),
            'republish_required': bool(reset_packet.get('republish_required', False)),
            'reason_codes': [],
            'artifacts': {
                **_vault_artifact_refs(vault_paths),
                'reports_root': normalize_repo_or_absolute_path(reports_root, project_root),
                'collections_root': normalize_repo_or_absolute_path(collections_root, project_root),
                'vault_quarantine_root': normalize_repo_or_absolute_path(vault_quarantine_root, project_root),
                'vault_quarantine_manifest_json': normalize_repo_or_absolute_path(archive_root / 'archive_manifest.json', project_root),
                'archive_root': normalize_repo_or_absolute_path(archive_root, project_root),
                'archive_manifest_json': normalize_repo_or_absolute_path(archive_root / 'archive_manifest.json', project_root),
                'librarian_vault_baseline_checksum': str(baseline.get('checksum_sha256', '') or '').strip(),
                'publication_control_json': str(reset_packet.get('publication_control_path', '') or ''),
                'ds_run_index_jsonl': str(((reset_packet.get('index_paths', {}) if isinstance(reset_packet.get('index_paths', {}), dict) else {}).get('ledger_path', '') or '').strip()),
                'ds_latest_json': str(((reset_packet.get('index_paths', {}) if isinstance(reset_packet.get('index_paths', {}), dict) else {}).get('latest_index_path', '') or '').strip()),
                'aggregate_report_md': str(((reset_packet.get('aggregate_paths', {}) if isinstance(reset_packet.get('aggregate_paths', {}), dict) else {}).get('aggregate_report_md', '') or '').strip()),
                'latest_md': str(((reset_packet.get('aggregate_paths', {}) if isinstance(reset_packet.get('aggregate_paths', {}), dict) else {}).get('latest_md', '') or '').strip()),
                'generated_surfaces_md': str(((reset_packet.get('aggregate_paths', {}) if isinstance(reset_packet.get('aggregate_paths', {}), dict) else {}).get('generated_surfaces_md', '') or '').strip()),
            },
        }

    alias_dir = collections_root / delete_token
    if not alias_dir.exists() or not alias_dir.is_dir():
        return {
            'timestamp_utc': utc_now_iso(),
            'runtime_cli_surface': 'observerctl',
            'decision': 'no-go',
            'action': 'librarian-store-reports-delete',
            'summary': 'Tracked report collection alias could not be resolved for archive-first delete.',
            'reason_codes': ['critical_check_failed:librarian_report_collection_not_found'],
            'delete_alias': delete_token,
            'report_collections': _report_store_collection_rows(paths),
            'artifacts': dict(base_artifacts),
        }

    archive_root = vault_quarantine_root / 'report_collection_delete_{0}_{1}'.format(sanitize_run_id(delete_token) or 'collection', stamp)
    destination_dir = archive_root / 'collections' / alias_dir.name
    destination_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(alias_dir), str(destination_dir))
    control_state = set_tracked_ds_publication_republish_state(
        project_anchor=project_anchor,
        republish_required=True,
        reason='tracked-report-alias-archived',
    )
    manifest = _report_store_archive_manifest(
        paths,
        action='archive-and-delete-report-collection',
        reason='move one tracked report collection alias into the librarian vault quarantine',
        archive_root=archive_root,
        archived_paths=[destination_dir],
        archived_aliases=[alias_dir.name],
        live_target=collections_root,
    )
    baseline = _write_vault_baseline(vault_paths, reason='librarian-store-reports-delete')
    _append_vault_audit_record(
        vault_paths,
        action='librarian-store-reports-delete',
        status='ok',
        ordinary_mutation=True,
        reason='tracked-report-quarantine',
        details={
            'delete_alias': alias_dir.name,
            'archive_root': normalize_repo_or_absolute_path(archive_root, project_root),
            'baseline_checksum': str(baseline.get('checksum_sha256', '') or '').strip(),
        },
    )
    collections_root.mkdir(parents=True, exist_ok=True)
    return {
        'timestamp_utc': utc_now_iso(),
        'runtime_cli_surface': 'observerctl',
        'decision': 'go',
        'action': 'librarian-store-reports-delete',
        'summary': 'Tracked report collection alias moved into the librarian vault quarantine and automatic republish is now blocked until an explicit republish.',
        'delete_alias': delete_token,
        'archived_aliases': list(manifest.get('archived_aliases', []) or []),
        'archived_alias_count': int(manifest.get('archived_alias_count', 0) or 0),
        'report_collections': _report_store_collection_rows(paths),
        'republish_required': bool(control_state.get('republish_required', False)),
        'reason_codes': [],
        'artifacts': {
            **_vault_artifact_refs(vault_paths),
            'reports_root': normalize_repo_or_absolute_path(reports_root, project_root),
            'collections_root': normalize_repo_or_absolute_path(collections_root, project_root),
            'vault_quarantine_root': normalize_repo_or_absolute_path(vault_quarantine_root, project_root),
            'vault_quarantine_manifest_json': normalize_repo_or_absolute_path(archive_root / 'archive_manifest.json', project_root),
            'archive_root': normalize_repo_or_absolute_path(archive_root, project_root),
            'archive_manifest_json': normalize_repo_or_absolute_path(archive_root / 'archive_manifest.json', project_root),
            'librarian_vault_baseline_checksum': str(baseline.get('checksum_sha256', '') or '').strip(),
            'publication_control_json': str(control_state.get('control_path', '') or ''),
        },
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
    _bootstrap_librarian_vault(paths)
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
        **_vault_artifact_refs(paths),
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
    authority_access_dir = paths['authority_access_root'] / sanitize_run_id(str(entry.get('entry_id', 'dataset'))) / stamp
    projection_access_dir = paths['access_root'] / sanitize_run_id(str(entry.get('entry_id', 'dataset'))) / stamp
    authority_access_dir.mkdir(parents=True, exist_ok=True)
    projection_access_dir.mkdir(parents=True, exist_ok=True)
    request_path = authority_access_dir / 'request.json'
    attestation_path = authority_access_dir / 'attestation.json'
    release_path = authority_access_dir / 'release_receipt.json'
    projection_request_path = projection_access_dir / 'request.json'
    projection_attestation_path = projection_access_dir / 'attestation.json'
    projection_release_path = projection_access_dir / 'release_receipt.json'

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
    _write_json_atomic(projection_request_path, request_doc)
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
            'artifacts': dict(artifacts, dataset_access_request_json=normalize_repo_or_absolute_path(projection_request_path, project_root)),
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
    _write_json_atomic(projection_attestation_path, attestation_doc)
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
                dataset_access_request_json=normalize_repo_or_absolute_path(projection_request_path, project_root),
                dataset_access_attestation_json=normalize_repo_or_absolute_path(projection_attestation_path, project_root),
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
    release_doc = _write_signed_access_packet(
        release_path,
        release_payload,
        role='source',
        purpose='dataset_access_release',
    )
    _write_json_atomic(projection_release_path, release_doc)
    baseline = _vault_checksum_payload(paths)
    _append_vault_audit_record(
        paths,
        action='librarian-dataset-release',
        status='ok',
        ordinary_mutation=True,
        reason='delegated-release',
        details={
            'entry_id': str(entry.get('entry_id', '') or '').strip(),
            'requester_id': str(request_payload.get('requester_id', '') or '').strip(),
            'baseline_checksum': str(baseline.get('checksum_sha256', '') or '').strip(),
        },
    )

    artifacts.update({
        'dataset_manifest_path': normalize_repo_or_absolute_path(manifest_path, project_root),
        'dataset_access_request_json': normalize_repo_or_absolute_path(projection_request_path, project_root),
        'dataset_access_attestation_json': normalize_repo_or_absolute_path(projection_attestation_path, project_root),
        'dataset_access_release_receipt_json': normalize_repo_or_absolute_path(projection_release_path, project_root),
        'librarian_vault_baseline_checksum': str(baseline.get('checksum_sha256', '') or '').strip(),
    })
    baseline_packet_ref = str(selector_entry.get('baseline_analysis_packet', '') or '').strip()
    baseline_index_ref = str(selector_entry.get('baseline_analysis_index_path', '') or '').strip()
    if baseline_packet_ref:
        artifacts['baseline_analysis_packet'] = baseline_packet_ref
    if baseline_index_ref:
        artifacts['baseline_analysis_index_jsonl'] = baseline_index_ref
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


def librarian_vault_status_packet(project_anchor: Path) -> Dict[str, Any]:
    paths = _dataset_catalog_paths(project_anchor)
    integrity = _vault_integrity_state(paths)
    control_state = _load_vault_control_state(paths)
    current = dict(integrity.get('current', {}) or {})
    baseline = dict(integrity.get('baseline', {}) or {})
    managed = _vault_managed_surface_counts(paths)
    return {
        'timestamp_utc': utc_now_iso(),
        'runtime_cli_surface': 'observerctl',
        'decision': 'go',
        'action': 'librarian-vault-status',
        'summary': 'Protected librarian vault control plane ready.',
        'lock_state': 'locked' if bool(control_state.get('locked', False)) else 'unlocked',
        'integrity_status': str(integrity.get('status', 'warn') or 'warn'),
        'locked': bool(control_state.get('locked', False)),
        'reason_codes': list(integrity.get('reason_codes', []) or []),
        'integrity': {
            'current_checksum_sha256': str(current.get('checksum_sha256', '') or '').strip(),
            'baseline_checksum_sha256': str(baseline.get('checksum_sha256', '') or '').strip(),
            'tracked_file_count': int(current.get('tracked_file_count', 0) or 0),
        },
        'managed_surfaces': managed,
        'artifacts': _vault_artifact_refs(paths),
    }


def librarian_vault_verify_packet(project_anchor: Path) -> Dict[str, Any]:
    paths = _dataset_catalog_paths(project_anchor)
    integrity = _vault_integrity_state(paths)
    current = dict(integrity.get('current', {}) or {})
    baseline = dict(integrity.get('baseline', {}) or {})
    status = str(integrity.get('status', 'warn') or 'warn')
    managed = _vault_managed_surface_counts(paths)
    return {
        'timestamp_utc': utc_now_iso(),
        'runtime_cli_surface': 'observerctl',
        'decision': 'go' if status == 'ok' else 'no-go',
        'action': 'librarian-vault-verify',
        'summary': 'Protected librarian vault integrity verified.' if status == 'ok' else 'Protected librarian vault integrity verification failed.',
        'integrity_status': status,
        'reason_codes': list(integrity.get('reason_codes', []) or []),
        'integrity': {
            'current_checksum_sha256': str(current.get('checksum_sha256', '') or '').strip(),
            'baseline_checksum_sha256': str(baseline.get('checksum_sha256', '') or '').strip(),
            'tracked_file_count': int(current.get('tracked_file_count', 0) or 0),
        },
        'managed_surfaces': managed,
        'artifacts': _vault_artifact_refs(paths),
    }


def librarian_vault_lock_packet(project_anchor: Path, *, reason: str = '') -> Dict[str, Any]:
    paths = _dataset_catalog_paths(project_anchor)
    _bootstrap_librarian_vault(paths)
    control_state = _load_vault_control_state(paths)
    control_state['locked'] = True
    control_state['lock_reason'] = str(reason or '').strip() or 'operator-requested-lock'
    control_state['locked_at_utc'] = utc_now_iso()
    saved_state = _save_vault_control_state(paths, control_state)
    _append_vault_audit_record(
        paths,
        action='librarian-vault-lock',
        status='ok',
        ordinary_mutation=False,
        reason=str(saved_state.get('lock_reason', '') or '').strip(),
    )
    return {
        'timestamp_utc': utc_now_iso(),
        'runtime_cli_surface': 'observerctl',
        'decision': 'go',
        'action': 'librarian-vault-lock',
        'summary': 'Protected librarian vault locked for non-ordinary maintenance.',
        'lock_state': 'locked',
        'locked': True,
        'reason_codes': [],
        'artifacts': _vault_artifact_refs(paths),
    }


def librarian_vault_unlock_packet(project_anchor: Path, *, reason: str = '') -> Dict[str, Any]:
    paths = _dataset_catalog_paths(project_anchor)
    _bootstrap_librarian_vault(paths)
    control_state = _load_vault_control_state(paths)
    control_state['locked'] = False
    control_state['lock_reason'] = str(reason or '').strip()
    control_state['unlocked_at_utc'] = utc_now_iso()
    saved_state = _save_vault_control_state(paths, control_state)
    _append_vault_audit_record(
        paths,
        action='librarian-vault-unlock',
        status='ok',
        ordinary_mutation=False,
        reason=str(saved_state.get('lock_reason', '') or '').strip(),
    )
    return {
        'timestamp_utc': utc_now_iso(),
        'runtime_cli_surface': 'observerctl',
        'decision': 'go',
        'action': 'librarian-vault-unlock',
        'summary': 'Protected librarian vault unlocked for ordinary signed mutations.',
        'lock_state': 'unlocked',
        'locked': False,
        'reason_codes': [],
        'artifacts': _vault_artifact_refs(paths),
    }


def librarian_vault_rebaseline_packet(project_anchor: Path, *, reason: str = '') -> Dict[str, Any]:
    paths = _dataset_catalog_paths(project_anchor)
    _bootstrap_librarian_vault(paths)
    baseline = _write_vault_baseline(paths, reason=str(reason or '').strip() or 'operator-requested-rebaseline')
    _append_vault_audit_record(
        paths,
        action='librarian-vault-rebaseline',
        status='ok',
        ordinary_mutation=False,
        reason=str(reason or '').strip() or 'operator-requested-rebaseline',
        details={'baseline_checksum': str(baseline.get('checksum_sha256', '') or '').strip()},
    )
    return {
        'timestamp_utc': utc_now_iso(),
        'runtime_cli_surface': 'observerctl',
        'decision': 'go',
        'action': 'librarian-vault-rebaseline',
        'summary': 'Protected librarian vault baseline refreshed.',
        'integrity_status': 'ok',
        'reason_codes': [],
        'artifacts': dict(_vault_artifact_refs(paths), librarian_vault_baseline_checksum=str(baseline.get('checksum_sha256', '') or '').strip()),
    }

if __name__ == "__main__":
    lib = Librarian()
    lib.loop()
