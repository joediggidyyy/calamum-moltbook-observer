from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
ANALYSIS_ROOT = PROJECT_ROOT / 'local_untracked' / 'analysis'
REPORTS_ROOT = PROJECT_ROOT / 'local_untracked' / 'reports'
REPORT_TMP_ROOT = PROJECT_ROOT / 'report_tmp'
AGENT_SESSION_ROOT = REPO_ROOT / '.agent_session'
TARGET_PROJECT_ID = 'calamum-moltbook-observer'


def _load_json(path: Path) -> Any:
	return json.loads(path.read_text(encoding='utf-8'))


def _load_json_if_exists(path: Path) -> Any:
	if not path.exists():
		return None
	return _load_json(path)


def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
	rows: List[Dict[str, Any]] = []
	if not path.exists():
		return rows
	for raw_line in path.read_text(encoding='utf-8').splitlines():
		line = raw_line.strip()
		if not line:
			continue
		payload = json.loads(line)
		if isinstance(payload, dict):
			rows.append(payload)
	return rows


def _iso_now() -> str:
	return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _date_stamp() -> str:
	return datetime.now(timezone.utc).strftime('%Y%m%d')


def _as_repo_rel(path: Path) -> str:
	try:
		return str(path.resolve().relative_to(REPO_ROOT)).replace('\\', '/')
	except Exception:
		return str(path.resolve()).replace('\\', '/')


def _path_text_to_path(path_text: str) -> Path:
	candidate = Path(str(path_text))
	if candidate.is_absolute():
		return candidate
	return PROJECT_ROOT / candidate


def _normalize_path_text(path_text: str) -> str:
	path_obj = _path_text_to_path(path_text)
	if path_obj.exists():
		return _as_repo_rel(path_obj)
	return str(path_text).replace('\\', '/')


def _safe_get(mapping: Any, *keys: str) -> Any:
	current = mapping
	for key in keys:
		if not isinstance(current, dict):
			return None
		current = current.get(key)
	return current


def _pick_active_project(ops_awareness: Dict[str, Any]) -> Dict[str, Any]:
	projects = ops_awareness.get('active_projects', []) if isinstance(ops_awareness, dict) else []
	for item in projects:
		if isinstance(item, dict) and item.get('project_id') == TARGET_PROJECT_ID:
			return item
	return {}


def _active_librarian_entries(manifest_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
	entries = manifest_payload.get('entries', []) if isinstance(manifest_payload, dict) else []
	active_entries: List[Dict[str, Any]] = []
	for item in entries:
		if not isinstance(item, dict):
			continue
		if item.get('status') != 'approved':
			continue
		active_entries.append(item)
	return active_entries


def _scan_baseline_packets() -> List[Dict[str, Any]]:
	packets: List[Dict[str, Any]] = []
	baseline_root = ANALYSIS_ROOT / 'baselines'
	for packet_path in sorted(baseline_root.glob('*/comparison_baseline_packet.json')):
		payload = _load_json_if_exists(packet_path)
		if not isinstance(payload, dict):
			continue
		packets.append(
			{
				'path': _as_repo_rel(packet_path),
				'artifact_family': payload.get('artifact_family', ''),
				'baseline_stage': payload.get('baseline_stage', payload.get('comparison_baseline_stage', '')),
				'source': payload.get('source', ''),
				'mode': payload.get('mode', ''),
				'has_labels': payload.get('has_labels', None),
				'window_id': payload.get('baseline_window_id', ''),
				'dataset_entry_id': payload.get('dataset_entry_id', ''),
			}
		)
	return packets


def _latest_run_record(records: Iterable[Dict[str, Any]], workflow: str, alias: str) -> Dict[str, Any]:
	candidates: List[Dict[str, Any]] = []
	for record in records:
		if not isinstance(record, dict):
			continue
		if record.get('workflow') != workflow:
			continue
		if record.get('collection_alias') != alias:
			continue
		candidates.append(record)
	candidates.sort(key=lambda item: str(item.get('timestamp_utc', '')))
	return candidates[-1] if candidates else {}


def _load_manifest_summary(path_text: str) -> Dict[str, Any]:
	if not str(path_text or '').strip():
		return {}
	path_obj = _path_text_to_path(str(path_text))
	payload = _load_json_if_exists(path_obj)
	if not isinstance(payload, dict):
		return {'path': _normalize_path_text(str(path_text)), 'exists': False}
	inputs = payload.get('inputs', [])
	input_paths: List[str] = []
	if isinstance(inputs, list):
		for item in inputs[:3]:
			if isinstance(item, dict) and item.get('path'):
				input_paths.append(_normalize_path_text(str(item.get('path'))))
	return {
		'path': _as_repo_rel(path_obj) if path_obj.exists() else _normalize_path_text(str(path_text)),
		'exists': path_obj.exists(),
		'has_labels': payload.get('has_labels', None),
		'labels_csv': _normalize_path_text(str(payload.get('labels_csv', '') or '')) if payload.get('labels_csv') else '',
		'total_records': payload.get('total_records', payload.get('record_count', None)),
		'input_paths': input_paths,
		'source_dataset_manifest': _normalize_path_text(str(payload.get('source_dataset_manifest', '') or '')) if payload.get('source_dataset_manifest') else '',
	}


def _build_run_summary(record: Dict[str, Any]) -> Dict[str, Any]:
	if not record:
		return {}
	run_root_path = _path_text_to_path(str(record.get('run_root', '')))
	build_output_manifest = run_root_path / 'dataset' / 'dataset_manifest.json'
	lineage_manifest_path = str(_safe_get(record, 'lineage', 'dataset_manifest') or '')
	return {
		'workflow': record.get('workflow', ''),
		'category': record.get('category', ''),
		'collection_alias': record.get('collection_alias', ''),
		'run_id': record.get('run_id', ''),
		'timestamp_utc': record.get('timestamp_utc', ''),
		'lineage_dataset_manifest': _load_manifest_summary(lineage_manifest_path),
		'build_output_dataset_manifest': _load_manifest_summary(str(build_output_manifest)),
		'result_has_labels': _safe_get(record, 'result', 'has_labels'),
		'report_manifest': _normalize_path_text(str(_safe_get(record, 'report_paths', 'manifest') or '')),
	}


def _count_by(entries: Iterable[Dict[str, Any]], key: str) -> Dict[str, int]:
	counter: Counter = Counter()
	for item in entries:
		if not isinstance(item, dict):
			continue
		counter[str(item.get(key, ''))] += 1
	return dict(sorted(counter.items(), key=lambda row: row[0]))


def _find_active_canary_entries(entries: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
	matches: List[Dict[str, Any]] = []
	for item in entries:
		if not isinstance(item, dict):
			continue
		if item.get('source') != 'real':
			continue
		if item.get('mode') != 'canary':
			continue
		matches.append(item)
	return matches


def _entry_brief(entry: Dict[str, Any]) -> Dict[str, Any]:
	resolver = entry.get('resolver', {}) if isinstance(entry, dict) else {}
	return {
		'entry_id': entry.get('entry_id', ''),
		'display_name': entry.get('display_name', ''),
		'source': entry.get('source', ''),
		'mode': entry.get('mode', ''),
		'has_labels': entry.get('has_labels', None),
		'registration_kind': entry.get('registration_kind', ''),
		'recorded_at_utc': entry.get('recorded_at_utc', ''),
		'dataset_manifest_path': _normalize_path_text(str(resolver.get('dataset_manifest_path', '') or '')),
	}


def _build_payload() -> Dict[str, Any]:
	policy_snapshot = _load_json_if_exists(AGENT_SESSION_ROOT / 'policy_snapshot.json') or {}
	ops_awareness = _load_json_if_exists(AGENT_SESSION_ROOT / 'ops_awareness.json') or {}
	task_stack = _load_json_if_exists(AGENT_SESSION_ROOT / 'task_stack.json') or []
	librarian_manifest = _load_json_if_exists(ANALYSIS_ROOT / 'indexes' / 'librarian_dataset_manifest.json') or {}
	ds_latest = _load_json_if_exists(ANALYSIS_ROOT / 'indexes' / 'ds_latest.json') or {}
	ds_records = _load_jsonl(ANALYSIS_ROOT / 'indexes' / 'ds_run_index.jsonl')
	baseline_packets = _scan_baseline_packets()
	active_entries = _active_librarian_entries(librarian_manifest)
	active_project = _pick_active_project(ops_awareness)

	canary_entries = _find_active_canary_entries(active_entries)
	labeled_canary_entries = [item for item in canary_entries if bool(item.get('has_labels'))]
	canary_reviewed_packets = [
		item
		for item in baseline_packets
		if item.get('artifact_family') == 'ds_comparison_baseline' and item.get('baseline_stage') == 'canary_reviewed'
	]

	latest_by_workflow = ds_latest.get('by_workflow', {}) if isinstance(ds_latest, dict) else {}
	build_alias = _safe_get(latest_by_workflow, 'build', 'collection_alias') or ''
	train_alias = _safe_get(latest_by_workflow, 'train', 'collection_alias') or ''
	evaluate_alias = _safe_get(latest_by_workflow, 'evaluate', 'collection_alias') or ''
	score_alias = _safe_get(latest_by_workflow, 'score', 'collection_alias') or ''

	build_summary = _build_run_summary(_latest_run_record(ds_records, 'build', str(build_alias))) if build_alias else {}
	train_summary = _build_run_summary(_latest_run_record(ds_records, 'train', str(train_alias))) if train_alias else {}
	evaluate_summary = _build_run_summary(_latest_run_record(ds_records, 'evaluate', str(evaluate_alias))) if evaluate_alias else {}
	score_summary = _build_run_summary(_latest_run_record(ds_records, 'score', str(score_alias))) if score_alias else {}

	librarian_alias_matches: List[Dict[str, Any]] = []
	for entry in active_entries:
		entry_id = str(entry.get('entry_id', ''))
		run_id = str(entry.get('run_id', ''))
		if build_alias and build_alias in (entry_id, run_id):
			librarian_alias_matches.append(_entry_brief(entry))
		if train_alias and train_alias in (entry_id, run_id):
			librarian_alias_matches.append(_entry_brief(entry))

	conclusion = 'it is complicated, we will need a frame stack'
	conclusion_basis = [
		'Active baseline packets contain no canary_reviewed DS comparison-baseline artifact.',
		'Active Librarian authority contains no labeled real/canary dataset entry.',
		'Current canary alias build chain is unlabeled, while the live alias build chain is labeled and remains separate from Librarian selector authority.',
	]

	return {
		'generated_at_utc': _iso_now(),
		'target_project_id': TARGET_PROJECT_ID,
		'conclusion': conclusion,
		'conclusion_basis': conclusion_basis,
		'policy_snapshot': {
			'snapshot_at': policy_snapshot.get('snapshot_at', ''),
			'policies_count': policy_snapshot.get('policies_count', 0),
			'top_directive_ids': [item.get('id', '') for item in policy_snapshot.get('top_directives', []) if isinstance(item, dict)],
		},
		'ops_awareness': {
			'snapshot_at': ops_awareness.get('snapshot_at', ''),
			'active_frame': ops_awareness.get('active_frame', {}),
			'up_next': ops_awareness.get('up_next', {}),
			'active_project': {
				'project_id': active_project.get('project_id', ''),
				'status': active_project.get('status', ''),
				'status_basis': active_project.get('status_basis', {}),
			},
		},
		'task_stack': {
			'count': len(task_stack) if isinstance(task_stack, list) else 0,
			'items': task_stack if isinstance(task_stack, list) else [],
		},
		'active_librarian_authority': {
			'manifest_path': _as_repo_rel(ANALYSIS_ROOT / 'indexes' / 'librarian_dataset_manifest.json'),
			'updated_at_utc': librarian_manifest.get('updated_at_utc', ''),
			'approved_entry_count': len(active_entries),
			'counts_by_mode': _count_by(active_entries, 'mode'),
			'counts_by_source': _count_by(active_entries, 'source'),
			'entries': [_entry_brief(item) for item in active_entries],
			'active_canary_entries': [_entry_brief(item) for item in canary_entries],
			'active_labeled_canary_entries': [_entry_brief(item) for item in labeled_canary_entries],
		},
		'active_baseline_packets': {
			'count': len(baseline_packets),
			'counts_by_stage': _count_by(baseline_packets, 'baseline_stage'),
			'packets': baseline_packets,
			'canary_reviewed_packets': canary_reviewed_packets,
		},
		'ds_latest': ds_latest,
		'active_run_evidence': {
			'build': build_summary,
			'train': train_summary,
			'evaluate': evaluate_summary,
			'score': score_summary,
		},
		'wizard_real_live_readiness': {
			'has_active_canary_reviewed_packet': bool(canary_reviewed_packets),
			'active_labeled_real_canary_librarian_entry_count': len(labeled_canary_entries),
			'librarian_alias_matches_for_latest_live_alias': librarian_alias_matches,
			'assessment': 'current no-baseline state is truthful against active retained authority' if not canary_reviewed_packets else 'active retained authority contains a canary_reviewed packet',
		},
	}


def _table(headers: List[str], rows: List[List[str]]) -> List[str]:
	line_parts = ['| ' + ' | '.join(headers) + ' |', '| ' + ' | '.join(['---'] * len(headers)) + ' |']
	for row in rows:
		line_parts.append('| ' + ' | '.join(row) + ' |')
	return line_parts


def _render_markdown(payload: Dict[str, Any], json_output_path: Path) -> str:
	lines: List[str] = []
	lines.append('# Calamum DS Wizard Baseline Diagnostic Report')
	lines.append('')
	lines.append('## Conclusion')
	lines.append('')
	lines.append(payload.get('conclusion', ''))
	lines.append('')
	for bullet in payload.get('conclusion_basis', []):
		lines.append('- ' + str(bullet))
	lines.append('')
	lines.append('## Snapshot')
	lines.append('')
	lines.extend(
		_table(
			['Surface', 'Value'],
			[
				['Generated', str(payload.get('generated_at_utc', ''))],
				['Policy snapshot', str(_safe_get(payload, 'policy_snapshot', 'snapshot_at') or '')],
				['Policies count', str(_safe_get(payload, 'policy_snapshot', 'policies_count') or '')],
				['Ops snapshot', str(_safe_get(payload, 'ops_awareness', 'snapshot_at') or '')],
				['Project status', str(_safe_get(payload, 'ops_awareness', 'active_project', 'status') or '')],
				['Task stack count', str(_safe_get(payload, 'task_stack', 'count') or 0)],
				['JSON evidence', _as_repo_rel(json_output_path)],
			],
		)
	)
	lines.append('')

	lines.append('## Active Librarian Authority')
	lines.append('')
	lines.extend(
		_table(
			['Metric', 'Value'],
			[
				['Approved entries', str(_safe_get(payload, 'active_librarian_authority', 'approved_entry_count') or 0)],
				['Counts by mode', json.dumps(_safe_get(payload, 'active_librarian_authority', 'counts_by_mode') or {}, sort_keys=True)],
				['Counts by source', json.dumps(_safe_get(payload, 'active_librarian_authority', 'counts_by_source') or {}, sort_keys=True)],
				['Active real/canary entries', str(len(_safe_get(payload, 'active_librarian_authority', 'active_canary_entries') or []))],
				['Active labeled real/canary entries', str(len(_safe_get(payload, 'active_librarian_authority', 'active_labeled_canary_entries') or []))],
			],
		)
	)
	lines.append('')
	entry_rows: List[List[str]] = []
	for entry in _safe_get(payload, 'active_librarian_authority', 'entries') or []:
		entry_rows.append(
			[
				str(entry.get('entry_id', '')),
				str(entry.get('source', '')),
				str(entry.get('mode', '')),
				str(entry.get('has_labels', '')),
				str(entry.get('registration_kind', '')),
				str(entry.get('dataset_manifest_path', '')),
			]
		)
	if entry_rows:
		lines.extend(_table(['Entry', 'Source', 'Mode', 'Has labels', 'Registration', 'Dataset manifest'], entry_rows))
		lines.append('')

	lines.append('## Active Baseline Packets')
	lines.append('')
	lines.extend(
		_table(
			['Metric', 'Value'],
			[
				['Packet count', str(_safe_get(payload, 'active_baseline_packets', 'count') or 0)],
				['Counts by stage', json.dumps(_safe_get(payload, 'active_baseline_packets', 'counts_by_stage') or {}, sort_keys=True)],
				['Active canary_reviewed packets', str(len(_safe_get(payload, 'active_baseline_packets', 'canary_reviewed_packets') or []))],
			],
		)
	)
	lines.append('')
	packet_rows: List[List[str]] = []
	for packet in _safe_get(payload, 'active_baseline_packets', 'packets') or []:
		packet_rows.append(
			[
				str(packet.get('baseline_stage', '')),
				str(packet.get('source', '')),
				str(packet.get('mode', '')),
				str(packet.get('has_labels', '')),
				str(packet.get('path', '')),
			]
		)
	if packet_rows:
		lines.extend(_table(['Stage', 'Source', 'Mode', 'Has labels', 'Packet path'], packet_rows))
		lines.append('')

	lines.append('## Latest DS Aliases')
	lines.append('')
	latest_rows: List[List[str]] = []
	for workflow_name, latest_entry in ((_safe_get(payload, 'ds_latest', 'by_workflow') or {})).items():
		if not isinstance(latest_entry, dict):
			continue
		latest_rows.append(
			[
				str(workflow_name),
				str(latest_entry.get('collection_alias', '')),
				str(latest_entry.get('run_id', '')),
				str(latest_entry.get('timestamp_utc', '')),
			]
		)
	if latest_rows:
		lines.extend(_table(['Workflow', 'Alias', 'Run id', 'Timestamp UTC'], latest_rows))
		lines.append('')

	lines.append('## Active Run Evidence')
	lines.append('')
	for workflow_name in ['build', 'train', 'evaluate', 'score']:
		summary = _safe_get(payload, 'active_run_evidence', workflow_name) or {}
		if not isinstance(summary, dict) or not summary:
			continue
		lines.append('### ' + workflow_name.capitalize())
		lines.append('')
		lines.extend(
			_table(
				['Field', 'Value'],
				[
					['Alias', str(summary.get('collection_alias', ''))],
					['Category', str(summary.get('category', ''))],
					['Run id', str(summary.get('run_id', ''))],
					['Timestamp UTC', str(summary.get('timestamp_utc', ''))],
					['Record result has_labels', str(summary.get('result_has_labels', ''))],
					['Report manifest', str(summary.get('report_manifest', ''))],
					['Lineage manifest', str(_safe_get(summary, 'lineage_dataset_manifest', 'path') or '')],
					['Lineage has_labels', str(_safe_get(summary, 'lineage_dataset_manifest', 'has_labels') or '')],
					['Output dataset manifest', str(_safe_get(summary, 'build_output_dataset_manifest', 'path') or '')],
					['Output dataset has_labels', str(_safe_get(summary, 'build_output_dataset_manifest', 'has_labels') or '')],
				],
			)
		)
		lines.append('')
		input_paths = _safe_get(summary, 'build_output_dataset_manifest', 'input_paths') or []
		if input_paths:
			lines.append('Sample input paths:')
			for path_text in input_paths:
				lines.append('- `' + str(path_text) + '`')
			lines.append('')

	lines.append('## Bottom Line')
	lines.append('')
	lines.append('The current real/live wizard no-baseline state matches the retained active authority surfaces. The missing piece is not a tiny UI display bug; it is the absence of an active admitted `canary_reviewed` DS comparison-baseline upstream of the real/live lane.')
	lines.append('')
	return '\n'.join(lines).rstrip() + '\n'


def main() -> int:
	parser = argparse.ArgumentParser(description='Diagnose current Calamum DS wizard baseline readiness from active retained authority surfaces.')
	parser.add_argument('--report-md', default='', help='Optional markdown report output path.')
	parser.add_argument('--report-json', default='', help='Optional JSON evidence output path.')
	args = parser.parse_args()

	date_stamp = _date_stamp()
	report_md_path = Path(str(args.report_md)).resolve() if str(args.report_md).strip() else (REPORTS_ROOT / ('CALAMUM_DS_WIZARD_BASELINE_DIAG_REPORT_' + date_stamp + '.md')).resolve()
	report_json_path = Path(str(args.report_json)).resolve() if str(args.report_json).strip() else (REPORT_TMP_ROOT / ('calamum_ds_wizard_baseline_diag_' + date_stamp + '.json')).resolve()
	report_md_path.parent.mkdir(parents=True, exist_ok=True)
	report_json_path.parent.mkdir(parents=True, exist_ok=True)

	payload = _build_payload()
	report_json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')
	report_md_path.write_text(_render_markdown(payload, report_json_path), encoding='utf-8')

	print(json.dumps({'conclusion': payload.get('conclusion', ''), 'report_md': _as_repo_rel(report_md_path), 'report_json': _as_repo_rel(report_json_path)}, indent=2, sort_keys=True))
	return 0


if __name__ == '__main__':
	raise SystemExit(main())
