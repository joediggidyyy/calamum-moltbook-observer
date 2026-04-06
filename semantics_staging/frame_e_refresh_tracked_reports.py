from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / 'src'))

    from analysis.report_aggregate import refresh_tracked_ds_publication

    project_anchor = repo_root / 'src' / 'observerctl.py'
    latest_index_path = repo_root / 'local_untracked' / 'analysis' / 'indexes' / 'ds_latest.json'
    latest_payload = json.loads(latest_index_path.read_text(encoding='utf-8'))
    latest_run = latest_payload.get('latest_run', {}) if isinstance(latest_payload, dict) else {}
    report_paths = latest_run.get('report_paths', {}) if isinstance(latest_run, dict) else {}
    manifest_rel = str(report_paths.get('manifest', '') or '').strip()
    if not manifest_rel:
        raise SystemExit('Latest DS index does not contain a manifest path for regeneration.')

    manifest_path = repo_root / manifest_rel
    if not manifest_path.exists():
        raise SystemExit(f'Manifest path not found: {manifest_path}')

    manifest_payload = json.loads(manifest_path.read_text(encoding='utf-8'))
    publication_state = refresh_tracked_ds_publication(
        project_anchor=project_anchor,
        current_manifest_payload=manifest_payload,
    )
    print(json.dumps(publication_state, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
