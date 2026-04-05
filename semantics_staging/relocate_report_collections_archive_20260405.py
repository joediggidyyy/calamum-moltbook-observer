from __future__ import annotations

import json
import shutil
from pathlib import Path


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    repo_root = project_root.parents[1]
    misplaced_root = repo_root / 'projects' / 'quarantine_legacy_archive' / 'calamum-moltbook-observer'
    target_root = repo_root / 'quarantine_legacy_archive' / 'calamum-moltbook-observer'
    bundle_name = 'report_collections_reset_20260405T021702Z'
    source = misplaced_root / bundle_name
    target_root.mkdir(parents=True, exist_ok=True)
    target = target_root / bundle_name
    if not source.exists():
        raise FileNotFoundError(f'Missing misplaced archive bundle: {source}')
    if target.exists():
        raise FileExistsError(f'Target archive bundle already exists: {target}')

    shutil.move(str(source), str(target))
    if misplaced_root.exists() and not any(misplaced_root.iterdir()):
        misplaced_root.rmdir()
        parent = misplaced_root.parent
        if parent.exists() and not any(parent.iterdir()):
            parent.rmdir()

    manifest = {
        'action': 'relocate-report-collections-archive',
        'source': str(source),
        'target': str(target),
    }
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
