import re

with open('src/observerctl.py', 'r') as f:
    text = f.read()

# We want to replace everything from _ds_wizard_render_wide down to the end of _ds_wizard_render_stacked
match = re.search(r'def _ds_wizard_render_wide\(state: _DSWizardState, width: int\) -> List\[str\]:.*?(?=def _ds_wizard_attempt_execute\(state: _DSWizardState\) -> Dict\[str, Any\]:)', text, re.DOTALL)

if not match:
    print('Failed to match')
    exit(1)

new_render_code = '''def _ds_wizard_build_pane(state: _DSWizardState) -> List[str]:
    lines: List[str] = []
    visible_sections = _ds_wizard_visible_sections(state)
    current_section = state.active_section if state.active_section in visible_sections else 'flow'
    lines.extend(_ds_wizard_summary_rows(state))
    lines.append('')
    if current_section == 'flow':
        lines.append('workflows:')
        for idx, workflow in enumerate(_DS_WIZARD_WORKFLOWS, start=1):
            marker = '*' if workflow == state.workflow else ' '
            lines.append('{0}. [{1}] {2}'.format(idx, marker, workflow))
        if not state.workflow:
            lines.append('')
            lines.append('hint: Select a numbered workflow to establish your session objective;')
            lines.append('      this configures the engine and shapes the data you will need.')
    elif current_section in ('cmd', 'check', 'run', 'exit'):
        if current_section == 'cmd':
            lines.append('command preview:')
            lines.append(_ds_wizard_command_preview(state))
        elif current_section == 'check':
            lines.append('validation:')
            issues = _ds_wizard_validation_issues(state)
            if not issues:
                lines.append('- ready')
            else:
                for issue in issues:
                    lines.append('- {0}'.format(issue))
        elif current_section == 'run':
            lines.append('execute handoff:')
            lines.append(_ds_wizard_command_preview(state))
            lines.append('blocked: {0}'.format('yes' if len(_ds_wizard_validation_issues(state)) > 0 else 'no'))
        else:
            lines.append('type exit to leave the wizard')
    else:
        lines.append('{0}:'.format(current_section))
        for idx, spec in enumerate(_ds_wizard_fields_for_section(state, current_section), start=1):
            lines.append('{0}. {1:<22} {2:<8} {3}'.format(idx, spec.key, _ds_wizard_status_token(state, spec), _ds_wizard_stringify_value(_ds_wizard_field_value(state, spec.key))))
    return lines

def _ds_wizard_render_transient(state: _DSWizardState, lines: List[str]) -> None:
    if str(state.transient_view or '').strip():
        lines.append('')
        if state.transient_view == 'scope-help':
            lines.extend(_ds_wizard_scope_help_lines(state))
        elif state.transient_view == 'item-peek':
            lines.extend(_ds_wizard_item_peek_lines(state, state.transient_target))
        elif state.transient_view == 'educational':
            lines.append('hint: {0}'.format(state.transient_target))

def _ds_wizard_render_wide(state: _DSWizardState, width: int) -> List[str]:
    visible_sections = _ds_wizard_visible_sections(state)
    current_section = state.active_section if state.active_section in visible_sections else 'flow'
    
    left_rail_width = 25
    left_lines = ['ObserverCTL', '']
    left_lines.append('Menu:')
    for sec in visible_sections:
        if sec == 'exit':
            continue
        marker = '*' if sec == current_section else ' '
        left_lines.append(' [{0}] {1}'.format(marker, sec))
    
    right_lines = []
    right_lines.append('path: {0}'.format(_ds_wizard_path_label(state)))
    right_lines.append('')
    right_lines.extend(_ds_wizard_build_pane(state))
    
    lines: List[str] = []
    max_len = max(len(left_lines), len(right_lines))
    for i in range(max_len):
        l = left_lines[i] if i < len(left_lines) else ''
        r = right_lines[i] if i < len(right_lines) else ''
        lines.append('{0:<{1}} {2}'.format(l, left_rail_width, r))
    
    lines.append('')
    lines.append('actions: open | next/prev | validate | cmd | ? | exit')
    _ds_wizard_render_transient(state, lines)
    return lines

def _ds_wizard_render_narrow(state: _DSWizardState, width: int) -> List[str]:
    # Placeholder for single-focus breadcrumb mode.
    return _ds_wizard_render_stacked(state)

def _ds_wizard_render_stacked(state: _DSWizardState) -> List[str]:
    visible_sections = _ds_wizard_visible_sections(state)
    lines: List[str] = []
    lines.append('ObserverCTL DS Wizard')
    lines.append('path: {0}'.format(_ds_wizard_path_label(state)))
    lines.append('')
    if state.active_page == 'landing':
        lines.extend(_ds_wizard_landing_summary_rows(state))
        lines.append('')
        lines.append('home:')
        lines.append('1. workflow')
        lines.append('2. configure')
        lines.append('3. review and run')
        lines.append('4. help and utilities')
        lines.append('5. exit')
        lines.append('')
        lines.append('actions: open number/name | validate | ? | exit')
    else:
        lines.extend(_ds_wizard_build_pane(state))
        lines.append('')
        lines.append('sections: {0}'.format(', '.join(sec for sec in visible_sections if sec != 'exit')))
        lines.append('actions: open | next/prev | validate | cmd | ? | exit')
    
    _ds_wizard_render_transient(state, lines)
    return lines

'''

new_text = text[:match.start()] + new_render_code + text[match.end():]
with open('src/observerctl.py', 'w') as f:
    f.write(new_text)
print('Patched successfully!')
