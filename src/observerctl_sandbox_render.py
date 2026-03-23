from __future__ import annotations

import textwrap

from typing import Any, Dict, List, Optional


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
    lines = ['Contract']
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
        'Catalog',
    ])
    lines.extend(_section_lines('Definition Count', len(definitions)))
    lines.extend([
        '',
        'Definitions',
    ])
    for row in definitions:
        if not isinstance(row, dict):
            continue
        lines.append('- {0}'.format(str(row.get('id', '') or '')))
        lines.extend(_section_lines('Title', str(row.get('title', '') or '')))
        lines.extend(_section_lines('Purpose', str(row.get('summary', '') or '')))
        lines.extend(_section_lines('Class', str(row.get('category', '') or '')))
        lines.extend(_section_lines('Writes', str(row.get('writes_to', '') or '')))
        lines.extend(_section_lines('Status', str(row.get('status', '') or '')))
        lines.append('')
    return lines


def _render_show(packet: Packet) -> List[str]:
    definition = packet.get('definition', {}) if isinstance(packet.get('definition', {}), dict) else {}
    aliases = definition.get('aliases', []) if isinstance(definition.get('aliases', []), list) else []
    alias_text = ', '.join(str(item) for item in aliases if str(item).strip())
    if not alias_text:
        selector_policy = str(definition.get('selector_policy', '') or '').strip()
        alias_text = 'none ({0})'.format(selector_policy) if selector_policy else 'none'
    lines = _header(packet, 'SANDBOX_DEFINITION_READY', 'Definition details are available for review.')
    lines.append('Identity')
    lines.extend(_section_lines('Definition', str(definition.get('id', '') or '')))
    lines.extend(_section_lines('Title', str(definition.get('title', '') or '')))
    lines.extend(_section_lines('Status', str(definition.get('status', '') or '')))
    lines.extend(_section_lines('Category', str(definition.get('category', '') or '')))
    lines.append('')
    lines.append('Selection')
    lines.extend(_section_lines('Canonical', str(definition.get('id', '') or '')))
    lines.extend(_section_lines('Aliases', alias_text))
    lines.extend(_section_lines('Command', str(definition.get('command', '') or '')))
    lines.append('')
    lines.append('Purpose')
    lines.extend(_section_lines('Summary', str(definition.get('summary', '') or '')))
    lines.extend(_section_lines('Purpose', str(definition.get('purpose', '') or '')))
    lines.append('')
    lines.append('Execution')
    lines.extend(_section_lines('Writes', str(definition.get('writes_to', '') or '')))
    lines.extend(_section_lines('Run Indexing', 'append-only' if str(definition.get('run_index_path', '') or '').strip() else 'not indexed'))
    lines.append('')
    lines.append('Outputs')
    if str(definition.get('run_index_path', '') or '').strip():
        lines.extend(_section_lines('Run Index', str(definition.get('run_index_path', '') or '')))
    else:
        lines.extend(_section_lines('Run Index', 'none'))
    lines.append('')
    lines.append('Guardrails')
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
        'Execution',
    ])
    lines.extend(_section_lines('Definition', str(packet.get('definition_id', '') or '')))
    lines.extend(_section_lines('Result', result))
    lines.extend(_section_lines('Return Code', str(packet.get('returncode', '') or '')))
    run_id = str(packet.get('run_id', '') or '').strip()
    if run_id:
        lines.extend(_section_lines('Run ID', run_id))
    lines.append('')
    lines.append('Artifacts')
    for key in ('report_json', 'review_json', 'report_md', 'review_md', 'run_index', 'run_dir'):
        value = str((packet.get('artifacts', {}) or {}).get(key, '') or '').strip() if isinstance(packet.get('artifacts', {}), dict) else ''
        if value:
            lines.extend(_section_lines(key, value))
    next_review = str(packet.get('next_review_command', '') or '').strip()
    if next_review:
        lines.append('')
        lines.append('Next')
        lines.extend(_section_lines('Review Command', next_review))
    return lines


def _render_runs_list(packet: Packet) -> List[str]:
    runs = packet.get('runs', []) if isinstance(packet.get('runs', []), list) else []
    lines = _header(packet, 'SANDBOX_RUNS_LISTED', 'Retained sandbox runs are available for review.')
    lines.extend(_contract_section(packet))
    lines.extend([
        'Catalog',
    ])
    lines.extend(_section_lines('Run Count', len(runs)))
    lines.extend([
        '',
        'Runs',
    ])
    for row in runs:
        if not isinstance(row, dict):
            continue
        lines.append('- {0}'.format(str(row.get('run_id', '') or '')))
        lines.extend(_section_lines('Definition', str(row.get('definition_id', '') or '')))
        lines.extend(_section_lines('Timestamp', str(row.get('timestamp_utc', '') or '')))
        lines.extend(_section_lines('Result', str(row.get('result', '') or '')))
        lines.extend(_section_lines('Report', str(row.get('report_path', '') or '')))
        lines.append('')
    return lines


def _render_runs_show(packet: Packet) -> List[str]:
    run = packet.get('run', {}) if isinstance(packet.get('run', {}), dict) else {}
    report = packet.get('report', {}) if isinstance(packet.get('report', {}), dict) else {}
    lines = _header(packet, 'SANDBOX_RUN_DETAIL_READY', 'Retained sandbox run details are available.')
    lines.extend(_contract_section(packet))
    lines.extend([
        'Run',
    ])
    lines.extend(_section_lines('Run ID', str(run.get('run_id', '') or '')))
    lines.extend(_section_lines('Definition', str(run.get('definition_id', '') or '')))
    lines.extend(_section_lines('Timestamp', str(run.get('timestamp_utc', '') or '')))
    lines.extend(_section_lines('Result', str(run.get('result', '') or '')))
    lines.extend(_section_lines('Report Path', str(run.get('report_path', '') or '')))
    if str(run.get('index_path', '') or '').strip():
        lines.extend(_section_lines('Index Path', str(run.get('index_path', '') or '')))
    lines.append('')
    lines.append('Review')
    for key in ('next_bite_result', 'all_sample_fields_present', 'all_index_fields_present'):
        if key in report:
            lines.extend(_section_lines(key, report.get(key)))
    return lines
