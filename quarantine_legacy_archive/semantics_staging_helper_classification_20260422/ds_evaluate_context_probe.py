"""Probe: verify wizard baseline context flows to evaluate finalization."""
import sys, json
sys.path.insert(0, 'src')
import observerctl

state = observerctl._ds_wizard_new_state('evaluate')
state.source = 'real'
state.mode = 'live'

# Get the first saved baseline selector token for real/live
saved = observerctl._ds_saved_baseline_entries('real', 'live')
if not saved:
    print('FAIL: no saved baselines found for real/live')
    sys.exit(1)
selector = saved[0].get('selector_token', '')
print('Using saved baseline selector: {}'.format(selector))

# Hydrate from saved baseline
observerctl._ds_wizard_hydrate_baseline_reference(state, baseline_ref=selector)

print('=== Wizard state after baseline hydration ===')
for key in ['source', 'mode', 'baseline_window_id', 'baseline_analysis_packet', 'dataset_manifest', 'features_csv', 'labels_csv']:
    val = state.values.get(key, '<not set>')
    src = state.hydrated_from.get(key, '<not hydrated>')
    short_val = str(val)[-80:] if len(str(val)) > 80 else str(val)
    print('  {}: {} (from: {})'.format(key, short_val, src))

print()
print('=== Values that _ds_wizard_attempt_execute would pass to _ds_evaluate ===')
print('  source={}'.format(state.values.get('source', state.source or '')))
print('  mode={}'.format(state.values.get('mode', state.mode or '')))
print('  baseline_window_id={}'.format(state.values.get('baseline_window_id', '')))
bap = str(state.values.get('baseline_analysis_packet', ''))
print('  baseline_analysis_packet=...{}'.format(bap[-80:] if len(bap) > 80 else bap))

# Verify these are non-empty (which means they'd hit the report context)
source_val = str(state.values.get('source', state.source or '')).strip()
mode_val = str(state.values.get('mode', state.mode or '')).strip()
bwid = str(state.values.get('baseline_window_id', '')).strip()
bap_val = str(state.values.get('baseline_analysis_packet', '')).strip()

print()
print('=== Context injection verdict ===')
if source_val and mode_val and (bwid or bap_val):
    print('PASS: evaluate run context would carry baseline info for report surfacing')
    print('  source={}, mode={}'.format(source_val, mode_val))
    print('  baseline_window_id={}'.format(bwid or '<empty>'))
    print('  baseline_analysis_packet present: {}'.format(bool(bap_val)))
else:
    print('FAIL: baseline info would NOT reach report context')
    print('  source={} mode={} bwid={} bap={}'.format(source_val, mode_val, bwid, bool(bap_val)))
