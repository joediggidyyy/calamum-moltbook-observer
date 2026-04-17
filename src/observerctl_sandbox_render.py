from __future__ import annotations

import json
import textwrap

from typing import Any, Dict, List, Optional

from observerctl_terminal import style_heading, style_text


Packet = Dict[str, Any]


_ACTION_ROUTE = {
    'sandbox-list': 'SANDBOX/CATALOG',
    'sandbox-show': 'SANDBOX/DETAIL',
    'sandbox-run': 'SANDBOX/EXECUTION',
    'sandbox-runs-list': 'SANDBOX/RUNS',
    'sandbox-runs-show': 'SANDBOX/RUN-DETAIL',
}


def _status_token(decision: str) -> str:
    normalized = str(decision or '').strip().lower()
    if normalized in ('go', 'ok', 'pass', 'success'):
        return '[OK]'
    if normalized in ('no-go', 'fail', 'failed', 'error', 'err'):
        return '[FAIL]'
    return '[INFO]'


def _section_lines(label: str, value: Any, width: int = 60) -> List[str]:
    prefix = '  {0:<16}: '.format(label)
    continuation = '  {0:<16}  '.format('')
    text = str(value)
    wrapped = textwrap.wrap(text, width=width, break_long_words=False, break_on_hyphens=False)
    if not wrapped:
        return [prefix.rstrip()]
    lines = [prefix + wrapped[0]]
    for part in wrapped[1:]:
        lines.append(continuation + part)
    return lines


def _text_value(value: Any) -> str:
    return '' if value is None else str(value)


def _compact_value(value: Any) -> str:
    if value is None:
        return ''
    if isinstance(value, bool):
        return 'True' if value else 'False'
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        if len(value) <= 4 and all(not isinstance(item, (dict, list)) for item in value):
            serialized = json.dumps(value)
            if len(serialized) <= 120:
                return serialized
        return '{0} items'.format(len(value))
    if isinstance(value, dict):
        scalar_values = list(value.values())
        if scalar_values and all(isinstance(item, str) for item in scalar_values):
            if any(('\\' in str(item)) or ('/' in str(item)) for item in scalar_values):
                return '{0} keys'.format(len(value))
        if len(value) <= 4 and all(
            not isinstance(item, dict)
            and not (isinstance(item, list) and len(item) > 4)
            for item in value.values()
        ):
            serialized = json.dumps(value, sort_keys=True)
            if len(serialized) <= 160:
                return serialized
        return '{0} keys'.format(len(value))
    return str(value)


def _nonempty_mapping_count(mapping: Dict[str, Any]) -> int:
    return sum(1 for value in mapping.values() if value not in (None, '', [], {}))


def _header(packet: Packet, outcome: str, detail: str) -> List[str]:
    action = str(packet.get('action', '') or '').strip().lower()
    route = _ACTION_ROUTE.get(action, 'SANDBOX')
    timestamp = str(packet.get('timestamp_utc', '') or '').strip()
    decision = str(packet.get('decision', '') or '').strip()
    return [
        '[ ORACL-Prime :: observerctl ] {0} {1}'.format(route, timestamp),
        '',
        '{0} {1} - {2}'.format(_status_token(decision), outcome, detail),
        '',
    ]


def _contract_section(packet: Packet) -> List[str]:
    lines = [style_heading('Contract')]
    lines.extend(_section_lines('Template Class', str(packet.get('template_class', '') or '')))
    lines.extend(_section_lines('Template Variant', str(packet.get('template_variant', '') or '')))
    lines.extend(_section_lines('Runtime Surface', str(packet.get('runtime_cli_surface', '') or '')))
    lines.append('')
    return lines


def render_human_packet(packet: Packet) -> Optional[List[str]]:
    action = str(packet.get('action', '') or '').strip().lower()
    if action == 'sandbox-list':
        return _render_list(packet)
    if action == 'sandbox-show':
        return _render_show(packet)
    if action == 'sandbox-run':
        return _render_run(packet)
    if action == 'sandbox-runs-list':
        return _render_runs_list(packet)
    if action == 'sandbox-runs-show':
        return _render_runs_show(packet)
    return None


def _render_list(packet: Packet) -> List[str]:
    definitions = packet.get('definitions', []) if isinstance(packet.get('definitions', []), list) else []
    lines = _header(packet, 'SANDBOX_DEFINITIONS_LISTED', 'Canonical sandbox definitions are available.')
    lines.extend(_contract_section(packet))
    lines.extend([
        style_heading('Catalog'),
    ])
    lines.extend(_section_lines('Definition Count', len(definitions)))
    lines.extend([
        '',
        style_heading('Definitions'),
    ])
    for row in definitions:
        if not isinstance(row, dict):
            continue
        lines.append(style_text(str(row.get('id', '') or ''), 'structure'))
        lines.extend(_section_lines('Title', str(row.get('title', '') or '')))
        lines.extend(_section_lines('Purpose', str(row.get('summary', '') or '')))
        lines.extend(_section_lines('Class', str(row.get('category', '') or '')))
        lines.extend(_section_lines('Writes', str(row.get('writes_to', '') or '')))
        lines.extend(_section_lines('Status', str(row.get('status', '') or '')))
        lines.append('')
    return lines


def _render_show(packet: Packet) -> List[str]:
    definition = packet.get('definition', {}) if isinstance(packet.get('definition', {}), dict) else {}
    decision = str(packet.get('decision', '') or '').strip().lower()
    if decision in ('no-go', 'fail', 'failed', 'error', 'err') or not definition:
        definition_id = str(packet.get('definition_id', '') or '').strip()
        reason_codes = packet.get('reason_codes', []) if isinstance(packet.get('reason_codes', []), list) else []
        lines = _header(packet, 'SANDBOX_DEFINITION_NOT_FOUND', 'Sandbox definition details are unavailable for the requested identifier.')
        lines.append(style_heading('Lookup'))
        lines.extend(_section_lines('Requested', definition_id or 'none supplied'))
        lines.append('')
        if reason_codes:
            lines.append(style_heading('Reasons'))
            for reason in reason_codes:
                lines.extend(_section_lines('Reason', str(reason)))
            lines.append('')
        lines.append(style_heading('Next'))
        lines.extend(_section_lines('Definitions', 'observerctl sandbox list'))
        if definition_id:
            lines.extend(_section_lines('Retained Run', 'If this identifier is a saved run id, use observerctl sandbox runs show {0}'.format(definition_id)))
        else:
            lines.extend(_section_lines('Retained Run', 'Use observerctl sandbox runs list to browse saved run ids.'))
        lines.append('')
        lines.extend(_contract_section(packet))
        return lines
    aliases = definition.get('aliases', []) if isinstance(definition.get('aliases', []), list) else []
    alias_text = ', '.join(str(item) for item in aliases if str(item).strip())
    if not alias_text:
        selector_policy = str(definition.get('selector_policy', '') or '').strip()
        alias_text = 'none ({0})'.format(selector_policy) if selector_policy else 'none'
    lines = _header(packet, 'SANDBOX_DEFINITION_READY', 'Definition details are available for review.')
    lines.append(style_heading('Identity'))
    lines.extend(_section_lines('Definition', str(definition.get('id', '') or '')))
    lines.extend(_section_lines('Title', str(definition.get('title', '') or '')))
    lines.extend(_section_lines('Status', str(definition.get('status', '') or '')))
    lines.extend(_section_lines('Category', str(definition.get('category', '') or '')))
    lines.append('')
    lines.append(style_heading('Selection'))
    lines.extend(_section_lines('Canonical', str(definition.get('id', '') or '')))
    lines.extend(_section_lines('Aliases', alias_text))
    lines.extend(_section_lines('Command', str(definition.get('command', '') or '')))
    lines.append('')
    lines.append(style_heading('Purpose'))
    lines.extend(_section_lines('Summary', str(definition.get('summary', '') or '')))
    lines.extend(_section_lines('Purpose', str(definition.get('purpose', '') or '')))
    lines.append('')
    lines.append(style_heading('Execution'))
    lines.extend(_section_lines('Writes', str(definition.get('writes_to', '') or '')))
    lines.extend(_section_lines('Run Indexing', 'append-only' if str(definition.get('run_index_path', '') or '').strip() else 'not indexed'))
    lines.append('')
    lines.append(style_heading('Outputs'))
    if str(definition.get('run_index_path', '') or '').strip():
        lines.extend(_section_lines('Run Index', str(definition.get('run_index_path', '') or '')))
    else:
        lines.extend(_section_lines('Run Index', 'none'))
    lines.append('')
    lines.append(style_heading('Guardrails'))
    lines.extend(_section_lines('Output Rule', 'names-only terminal output'))
    lines.extend(_section_lines('Secrets', 'no secret printing'))
    lines.extend(_section_lines('Execution Mode', 'script-first execution reminder applies'))
    lines.append('')
    lines.extend(_contract_section(packet))
    return lines


def _render_run(packet: Packet) -> List[str]:
    result = str(packet.get('result', '') or '')
    lines = _header(packet, 'SANDBOX_RUN_RECORDED', 'Sandbox definition execution completed with result {0}.'.format(result or 'unknown'))
    lines.extend(_contract_section(packet))
    lines.extend([
        style_heading('Execution'),
    ])
    lines.extend(_section_lines('Definition', str(packet.get('definition_id', '') or '')))
    lines.extend(_section_lines('Result', result))
    return_code = packet.get('returncode') if 'returncode' in packet else ''
    lines.extend(_section_lines('Return Code', _text_value(return_code)))
    run_id = str(packet.get('run_id', '') or '').strip()
    if run_id:
        lines.extend(_section_lines('Run ID', run_id))
    lines.append('')
    lines.append(style_heading('Artifacts'))
    for key in ('report_json', 'review_json', 'report_md', 'review_md', 'run_index', 'run_dir'):
        value = str((packet.get('artifacts', {}) or {}).get(key, '') or '').strip() if isinstance(packet.get('artifacts', {}), dict) else ''
        if value:
            lines.extend(_section_lines(key, value))
    next_review = str(packet.get('next_review_command', '') or '').strip()
    if next_review:
        lines.append('')
        lines.append(style_heading('Next'))
        lines.extend(_section_lines('Review Command', next_review))
    return lines


def _render_runs_list(packet: Packet) -> List[str]:
    runs = packet.get('runs', []) if isinstance(packet.get('runs', []), list) else []
    lines = _header(packet, 'SANDBOX_RUNS_LISTED', 'Retained sandbox runs are available for review.')
    lines.extend(_contract_section(packet))
    lines.extend([
        style_heading('Catalog'),
    ])
    lines.extend(_section_lines('Run Count', len(runs)))
    lines.extend([
        '',
        style_heading('Runs'),
    ])
    for row in runs:
        if not isinstance(row, dict):
            continue
        lines.append(style_text(str(row.get('run_id', '') or ''), 'structure'))
        lines.extend(_section_lines('Definition', str(row.get('definition_id', '') or '')))
        lines.extend(_section_lines('Timestamp', str(row.get('timestamp_utc', '') or '')))
        lines.extend(_section_lines('Result', str(row.get('result', '') or '')))
        lines.extend(_section_lines('Report', str(row.get('report_path', '') or '')))
        lines.append('')
    return lines


def _render_runs_show(packet: Packet) -> List[str]:
    run = packet.get('run', {}) if isinstance(packet.get('run', {}), dict) else {}
    report = packet.get('report', {}) if isinstance(packet.get('report', {}), dict) else {}
    decision = str(packet.get('decision', '') or '').strip().lower()
    if decision in ('no-go', 'fail', 'failed', 'error', 'err') or not run:
        run_id = str(packet.get('run_id', '') or '').strip()
        reason_codes = packet.get('reason_codes', []) if isinstance(packet.get('reason_codes', []), list) else []
        lines = _header(packet, 'SANDBOX_RUN_DETAIL_NOT_FOUND', 'Retained sandbox run details are unavailable for the requested identifier.')
        lines.append(style_heading('Lookup'))
        lines.extend(_section_lines('Requested', run_id or 'none supplied'))
        lines.append('')
        if reason_codes:
            lines.append(style_heading('Reasons'))
            for reason in reason_codes:
                lines.extend(_section_lines('Reason', str(reason)))
            lines.append('')
        lines.append(style_heading('Next'))
        lines.extend(_section_lines('Saved Runs', 'observerctl sandbox runs list'))
        lines.extend(_section_lines('Definitions', 'observerctl sandbox list'))
        lines.append('')
        lines.extend(_contract_section(packet))
        return lines
    lines = _header(packet, 'SANDBOX_RUN_DETAIL_READY', 'Retained sandbox run details are available.')
    lines.extend(_contract_section(packet))
    lines.extend([
        style_heading('Run'),
    ])
    lines.extend(_section_lines('Run ID', str(run.get('run_id', '') or '')))
    lines.extend(_section_lines('Definition', str(run.get('definition_id', '') or '')))
    lines.extend(_section_lines('Timestamp', str(run.get('timestamp_utc', '') or '')))
    lines.extend(_section_lines('Result', str(run.get('result', '') or '')))
    lines.extend(_section_lines('Report Path', str(run.get('report_path', '') or '')))
    if str(run.get('index_path', '') or '').strip():
        lines.extend(_section_lines('Index Path', str(run.get('index_path', '') or '')))
    if str(run.get('run_dir', '') or '').strip():
        lines.extend(_section_lines('Run Dir', str(run.get('run_dir', '') or '')))
    lines.append('')

    report_result = str(report.get('next_bite_result', '') or '').strip()
    result_matrix = report.get('result_matrix', {}) if isinstance(report.get('result_matrix', {}), dict) else {}
    command_runs = report.get('command_runs', {}) if isinstance(report.get('command_runs', {}), dict) else {}
    artifact_paths = report.get('artifact_paths', {}) if isinstance(report.get('artifact_paths', {}), dict) else {}
    findings = report.get('findings', {}) if isinstance(report.get('findings', {}), dict) else {}
    passed_checks = sum(1 for value in result_matrix.values() if bool(value))
    failed_checks = [key for key, value in result_matrix.items() if not bool(value)]

    lines.append(style_heading('Review'))
    if report_result:
        lines.extend(_section_lines('Next Bite Result', report_result))
    if result_matrix:
        lines.extend(_section_lines('Checks Passed', '{0}/{1}'.format(passed_checks, len(result_matrix))))
        if failed_checks:
            for key in failed_checks[:5]:
                lines.extend(_section_lines('Failed Check', key))
            if len(failed_checks) > 5:
                lines.extend(_section_lines('Failed Check', '{0} more'.format(len(failed_checks) - 5)))
        else:
            lines.extend(_section_lines('Review Signal', 'all retained checks passed'))
    if command_runs:
        lines.extend(_section_lines('Command Runs', len(command_runs)))
    if artifact_paths:
        lines.extend(_section_lines('Artifact Paths', _nonempty_mapping_count(artifact_paths)))

    surfaced_findings = 0
    for key, value in findings.items():
        compact = _compact_value(value)
        if not compact:
            continue
        if surfaced_findings == 0:
            lines.append('')
            lines.append(style_heading('Findings'))
        lines.extend(_section_lines(key, compact))
        surfaced_findings += 1
        if surfaced_findings >= 5:
            break
    if len(findings) > surfaced_findings:
        lines.extend(_section_lines('More Findings', '{0}'.format(len(findings) - surfaced_findings)))
    return lines
