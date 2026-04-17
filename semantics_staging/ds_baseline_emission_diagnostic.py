"""
Diagnostic script: DS comparison-baseline emission and hydration state.

Checks:
  1. Librarian dataset catalog — all entries with their stage + registration_kind
  2. On-disk comparison baseline packets — what's actually emitted
  3. Saved baselines surface for each mode — what's discoverable
  4. Wizard hydration from saved baseline — what fields populate
  5. Stage lineage correctness — canary→live, honeypot→live/honeypot
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))
os.environ.setdefault('CALAMUM_DATA_SIGNING_KEY', 'diagnostic-probe-key')

import observerctl as m


def _section(title):
    print('\n' + '=' * 60)
    print(title)
    print('=' * 60)


def _check_librarian_entries():
    _section('1. Librarian Dataset Catalog')
    entries = m._ds_librarian_dataset_entries()
    print('total entries: {0}'.format(len(entries)))
    for e in entries:
        entry_id = e.get('entry_id', '')
        mode = e.get('mode', '')
        source = e.get('source', '')
        reg_kind = e.get('registration_kind', '')
        has_labels = e.get('has_labels', False)
        explicit_stage = e.get('comparison_baseline_stage', '')
        inferred_stage = m._ds_comparison_baseline_stage(e)
        eligible = m._ds_is_eligible_comparison_baseline(e)
        print('\n  entry_id: {0}'.format(entry_id))
        print('    source/mode:          {0}/{1}'.format(source, mode))
        print('    registration_kind:    {0}'.format(reg_kind))
        print('    has_labels:           {0}'.format(has_labels))
        print('    explicit_stage:       {0}'.format(repr(explicit_stage)))
        print('    inferred_stage:       {0}'.format(repr(inferred_stage)))
        print('    eligible:             {0}'.format(eligible))


def _check_on_disk_packets():
    _section('2. On-Disk Comparison Baseline Packets')
    baselines_root = m._project_root() / 'local_untracked' / 'analysis' / 'baselines'
    if not baselines_root.exists():
        print('baselines root does not exist: {0}'.format(baselines_root))
        return
    for packet_dir in sorted(baselines_root.iterdir()):
        if not packet_dir.is_dir():
            continue
        packet_file = packet_dir / 'comparison_baseline_packet.json'
        if not packet_file.exists():
            print('\n  dir: {0}  (no packet)'.format(packet_dir.name))
            continue
        payload = json.loads(packet_file.read_text(encoding='utf-8'))
        print('\n  dir: {0}'.format(packet_dir.name))
        print('    artifact_family:      {0}'.format(payload.get('artifact_family', '')))
        print('    baseline_stage:       {0}'.format(payload.get('baseline_stage', '')))
        print('    baseline_window_id:   {0}'.format(payload.get('baseline_window_id', '')))
        print('    source/mode:          {0}/{1}'.format(payload.get('source', ''), payload.get('mode', '')))
        print('    has_labels:           {0}'.format(payload.get('has_labels', '')))
        print('    dataset_manifest:     {0}'.format(payload.get('dataset_manifest_path', '')))
        print('    features_csv:         {0}'.format(payload.get('features_csv_path', '')))
        print('    labels_csv:           {0}'.format(payload.get('labels_csv_path', '')))
        print('    record_count:         {0}'.format(payload.get('record_count', '')))
        provenance = payload.get('provenance', {})
        print('    emitted_at:           {0}'.format(provenance.get('emitted_at_utc', '')))


def _check_saved_baselines():
    _section('3. Saved Baselines Surface')
    for source, mode in [('real', 'live'), ('real', 'honeypot'), ('real', 'canary')]:
        entries = m._ds_saved_baseline_entries(source, mode)
        print('\n  {0}/{1}: count={2}'.format(source, mode, len(entries)))
        for e in entries:
            print('    selector: {0}  stage: {1}  window: {2}'.format(
                e.get('selector_token', ''),
                e.get('baseline_stage', ''),
                e.get('baseline_window_id', ''),
            ))


def _check_wizard_hydration():
    _section('4. Wizard Hydration From Saved Baseline')
    entries = m._ds_saved_baseline_entries('real', 'live')
    if not entries:
        print('  no saved baselines for real/live; skipping hydration test')
        entries_hp = m._ds_saved_baseline_entries('real', 'honeypot')
        if entries_hp:
            print('  trying honeypot instead...')
            state = m._ds_wizard_new_state('evaluate')
            state.source = 'real'
            state.mode = 'honeypot'
            state.values['source'] = 'real'
            state.values['mode'] = 'honeypot'
            try:
                state = m._ds_wizard_hydrate_baseline_reference(state, '1')
                issues = m._ds_wizard_validation_issues(state)
                print('  after hydration:')
                for key in ('dataset_manifest', 'features_csv', 'labels_csv', 'baseline_analysis_packet', 'baseline_window_id'):
                    val = state.values.get(key, '')
                    src = state.hydrated_from.get(key, '')
                    print('    {0}: {1} (from: {2})'.format(key, repr(val)[:80], src))
                print('  validation_issues: {0}'.format(issues))
            except Exception as exc:
                print('  hydration error: {0}'.format(exc))
        return

    state = m._ds_wizard_new_state('evaluate')
    state.source = 'real'
    state.mode = 'live'
    state.values['source'] = 'real'
    state.values['mode'] = 'live'
    try:
        state = m._ds_wizard_hydrate_baseline_reference(state, '1')
        issues = m._ds_wizard_validation_issues(state)
        print('  after hydrating saved baseline #1 for real/live:')
        for key in ('dataset_manifest', 'features_csv', 'labels_csv', 'baseline_analysis_packet', 'baseline_window_id'):
            val = state.values.get(key, '')
            src = state.hydrated_from.get(key, '')
            print('    {0}: {1} (from: {2})'.format(key, repr(val)[:80], src))
        print('  validation_issues: {0}'.format(issues))
    except Exception as exc:
        print('  hydration error: {0}'.format(exc))


def _check_lineage_correctness():
    _section('5. Stage Lineage Correctness')
    print('  live consumes:     {0}'.format(m._ds_lineage_target_baseline_stages('live')))
    print('  honeypot consumes: {0}'.format(m._ds_lineage_target_baseline_stages('honeypot')))
    print('  canary consumes:   {0}'.format(m._ds_lineage_target_baseline_stages('canary')))

    # Check: does a canary entry correctly map to canary_reviewed?
    canary_entries = [e for e in m._ds_librarian_dataset_entries() if e.get('mode') == 'canary']
    for e in canary_entries:
        stage = m._ds_comparison_baseline_stage(e)
        print('  canary entry {0} -> stage: {1}'.format(e.get('entry_id', ''), stage))

    # Check: is canary_reviewed in the live targets?
    live_targets = m._ds_lineage_target_baseline_stages('live')
    print('  canary_reviewed in live targets: {0}'.format('canary_reviewed' in live_targets))

    # Check: are there entries where stage assignment might be wrong?
    _section('6. Potential Stage Misassignment Check')
    for e in m._ds_librarian_dataset_entries():
        stage = m._ds_comparison_baseline_stage(e)
        mode = e.get('mode', '')
        reg = e.get('registration_kind', '')
        if stage and mode:
            expected_suffix = mode + '_reviewed'
            # canary/live don't follow this pattern exactly
            if mode == 'canary':
                expected = 'canary_reviewed'
            elif mode == 'honeypot':
                expected = 'honeypot_reviewed'
            elif mode == 'live':
                expected = 'live_reviewed'
            else:
                expected = ''
            if stage != expected:
                print('  WARNING: {0} mode={1} reg={2} stage={3} expected={4}'.format(
                    e.get('entry_id', ''), mode, reg, stage, expected))
            else:
                print('  OK: {0} mode={1} stage={2}'.format(e.get('entry_id', ''), mode, stage))
        elif not stage:
            print('  SKIP (no stage): {0} mode={1} reg={2}'.format(e.get('entry_id', ''), mode, reg))


if __name__ == '__main__':
    _check_librarian_entries()
    _check_on_disk_packets()
    _check_saved_baselines()
    _check_wizard_hydration()
    _check_lineage_correctness()
    print('\n' + '=' * 60)
    print('DIAGNOSTIC COMPLETE')
    print('=' * 60)
