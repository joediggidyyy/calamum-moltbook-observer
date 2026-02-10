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
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Tuple

from calamum_config import get_calamum_data_dir, get_calamum_control_dir, get_calamum_health_dir

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

if __name__ == "__main__":
    lib = Librarian()
    lib.loop()
