from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    source_root = project_root / 'local_untracked' / 'analysis' / 'datasets' / 'p3_demo_current_collection_20260406' / 'dataset'
    target_root = project_root / 'local_untracked' / 'analysis' / 'datasets' / 'p3_demo_current_collection_20260410_provenance_labeled'
    source_manifest_path = source_root / 'dataset_manifest.json'
    features_csv = source_root / 'features.csv'
    splits_csv = source_root / 'splits.csv'
    split_manifest_json = source_root / 'split_manifest.json'
    labels_csv = target_root / 'labels.csv'
    target_manifest_path = target_root / 'dataset_manifest.json'
    label_policy_path = project_root / 'local_untracked' / 'reports' / 'CALAMUM_R6_PROVENANCE_LABEL_POLICY_20260410.md'

    source_manifest = json.loads(source_manifest_path.read_text(encoding='utf-8'))
    rows = list(csv.DictReader(features_csv.open('r', encoding='utf-8', newline='')))
    labels_by_id: dict[str, str] = {}
    conflicts: dict[str, list[str]] = {}
    seen = defaultdict(set)

    for row in rows:
        record_id = str(row.get('record_id', '')).strip()
        is_canary = str(row.get('is_canary', '')).strip()
        if not record_id:
            raise ValueError('features.csv row missing record_id')
        if is_canary not in {'0', '1'}:
            raise ValueError(f'unexpected is_canary value for {record_id!r}: {is_canary!r}')
        seen[record_id].add(is_canary)
        if len(seen[record_id]) > 1:
            conflicts[record_id] = sorted(seen[record_id])
        labels_by_id.setdefault(record_id, is_canary)

    if conflicts:
        raise ValueError(f'conflicting provenance labels detected: {conflicts}')

    target_root.mkdir(parents=True, exist_ok=True)
    with labels_csv.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(['record_id', 'label'])
        for record_id in sorted(labels_by_id):
            writer.writerow([record_id, labels_by_id[record_id]])

    label_counts = Counter(labels_by_id.values())
    manifest = dict(source_manifest)
    manifest.update(
        {
            'created_at_utc': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
            'features_csv': str(features_csv.resolve()),
            'splits_csv': str(splits_csv.resolve()),
            'split_manifest_json': str(split_manifest_json.resolve()),
            'labels_csv': str(labels_csv.resolve()),
            'has_labels': True,
            'label_definition': {
                'label_column': 'label',
                'label_name': 'source_lane_label',
                'label_meaning': {
                    '0': 'real_live_recent',
                    '1': 'sim_canary_recent',
                },
                'policy_ref': str(label_policy_path.resolve()),
                'interpretation': 'bounded provenance labels derived from the existing is_canary feature; not threat-vector ground truth',
            },
            'label_summary': {
                'unique_record_ids': len(labels_by_id),
                'label_counts': {
                    '0': int(label_counts.get('0', 0)),
                    '1': int(label_counts.get('1', 0)),
                },
            },
            'source_dataset_manifest': str(source_manifest_path.resolve()),
        }
    )
    target_manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding='utf-8')

    summary = {
        'target_manifest': str(target_manifest_path.resolve()),
        'labels_csv': str(labels_csv.resolve()),
        'unique_record_ids': len(labels_by_id),
        'label_counts': {
            '0': int(label_counts.get('0', 0)),
            '1': int(label_counts.get('1', 0)),
        },
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
