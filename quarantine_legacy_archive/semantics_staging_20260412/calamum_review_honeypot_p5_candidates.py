from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / 'src'
if str(SRC_ROOT) not in sys.path:
	sys.path.insert(0, str(SRC_ROOT))

from analysis.dataset_builder import build_dataset  # noqa: E402
from analysis.tv_review import apply_suggested_labels_to_dataset_manifest, run_tv_review  # noqa: E402


def _materialize_dataset(
	input_path: Path,
	dataset_dir: Path,
	suggested_labels_path: Path,
	*,
	seed: int,
	labeled_unique_count: int,
) -> Dict[str, str]:
	dataset_dir.mkdir(parents=True, exist_ok=True)
	build_dataset([input_path], out_dir=dataset_dir, seed=int(seed))

	manifest_path = dataset_dir / 'dataset_manifest.json'
	if not manifest_path.exists():
		raise FileNotFoundError('dataset manifest not found after dataset materialization')

	apply_suggested_labels_to_dataset_manifest(
		manifest_path,
		suggested_labels_path,
		labeled_unique_count=int(labeled_unique_count),
	)

	manifest_payload = json.loads(manifest_path.read_text(encoding='utf-8'))
	if not isinstance(manifest_payload, dict):
		raise ValueError('dataset manifest is not a JSON object after materialization')
	manifest_payload['source'] = 'real'
	manifest_payload['mode'] = 'honeypot'
	inputs = list(manifest_payload.get('inputs', []) or [])
	updated_inputs: List[Any] = []
	for item in inputs:
		if isinstance(item, dict):
			row = dict(item)
			row['source'] = 'real'
			row['mode'] = 'honeypot'
			updated_inputs.append(row)
		else:
			updated_inputs.append(item)
	manifest_payload['inputs'] = updated_inputs

	labels_path = dataset_dir / 'labels.csv'
	if int(labeled_unique_count) <= 0:
		if labels_path.exists():
			labels_path.unlink()
		manifest_payload['labels_csv'] = None
		manifest_payload['has_labels'] = False

	manifest_path.write_text(json.dumps(manifest_payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')
	return {
		'dataset_manifest_json': str(manifest_path).replace('\\', '/'),
		'features_csv': str(dataset_dir / 'features.csv').replace('\\', '/'),
		'labels_csv': str(labels_path).replace('\\', '/') if int(labeled_unique_count) > 0 else '',
		'splits_csv': str(dataset_dir / 'splits.csv').replace('\\', '/'),
		'split_manifest_json': str(dataset_dir / 'split_manifest.json').replace('\\', '/'),
	}


def main() -> int:
	parser = argparse.ArgumentParser(description='Summarize one honeypot candidate slice for conservative P5 review.')
	parser.add_argument('--input', required=True, help='Path to the frozen honeypot slice JSONL.')
	parser.add_argument('--output-dir', required=True, help='Directory for review summary outputs.')
	parser.add_argument('--dataset-dir', default='', help='Optional dataset directory to materialize for P5/P6 handoff.')
	parser.add_argument('--seed', type=int, default=1337, help='Deterministic split seed for optional dataset materialization.')
	args = parser.parse_args()

	input_path = Path(str(args.input)).resolve()
	output_dir = Path(str(args.output_dir)).resolve()
	output_dir.mkdir(parents=True, exist_ok=True)

	summary = run_tv_review(
		[input_path],
		output_dir,
		inventory_filename='review_inventory.csv',
		suggested_labels_filename='suggested_labels.csv',
	)
	labeled_unique_count = int(summary.get('labeled_unique_count', 0) or 0)
	suggested_labels_path = Path(str(summary.get('suggested_labels_csv', '') or ''))
	dataset_artifacts: Dict[str, str] = {}
	if str(args.dataset_dir or '').strip():
		dataset_dir = Path(str(args.dataset_dir)).resolve()
		dataset_artifacts = _materialize_dataset(
			input_path,
			dataset_dir,
			suggested_labels_path,
			seed=int(args.seed),
			labeled_unique_count=int(labeled_unique_count),
		)

	summary_payload = dict(summary)
	summary_payload['input_path'] = str(input_path).replace('\\', '/')
	summary_payload.pop('input_paths', None)
	summary_payload.update(dataset_artifacts)
	summary_path = output_dir / 'review_summary.json'
	summary_path.write_text(json.dumps(summary_payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')

	print(json.dumps(summary_payload, indent=2, sort_keys=True))
	return 0


if __name__ == '__main__':
	raise SystemExit(main())
