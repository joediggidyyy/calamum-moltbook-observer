# Frame B Gate Posture Evidence

- Frame: `B`
- Scenario focus: `S1`
- Probe run id: `frameb-posture-transition-bypass-20260421T180507Z`
- Source report json: `report_tmp/frameb_posture_transition_bypass_probe/runs/frameb-posture-transition-bypass-20260421T180507Z/frameb_posture_transition_bypass_probe.json`
- Source report md: `report_tmp/frameb_posture_transition_bypass_probe/runs/frameb-posture-transition-bypass-20260421T180507Z/frameb_posture_transition_bypass_probe.md`
- Overall result: `pass`

## Conclusion

Frame B S1 confirmed that `observerctl` fails closed when a fresh-looking go gate packet is replayed after the active current-state tuple changes. The retained denial packet emitted `critical_check_failed:gate_packet_state_mismatch`, the final state remained `watch`, and no posture write was performed.

## Retained findings

- Current from-state observed by mode-set: `sim:watch`
- Gate from-state carried by the replayed gate packet: `sim:canary`
- Mode-set reason codes: `["critical_check_failed:gate_packet_state_mismatch"]`
- Final mode after denial: `watch`

## Result matrix

- `current_state_mutated_after_gate`: `True`
- `fresh_gate_packet_seeded`: `True`
- `live_mode_not_persisted`: `True`
- `matching_run_context_seeded`: `True`
- `mode_set_denied`: `True`
- `posture_write_skipped_on_denial`: `True`
- `state_mismatch_reason_emitted`: `True`

## Artifact paths

- Last gate packet: `report_tmp/frameb_posture_transition_bypass_probe/runs/frameb-posture-transition-bypass-20260421T180507Z/sandbox_logs/control/calamum/observerctl_last_gate.json`
- Run context: `report_tmp/frameb_posture_transition_bypass_probe/runs/frameb-posture-transition-bypass-20260421T180507Z/sandbox_logs/control/calamum/observerctl_run_context.json`
- Security report ref: `report_tmp/frameb_posture_transition_bypass_probe/runs/frameb-posture-transition-bypass-20260421T180507Z/security_report_transition.md`
- Posture state path (should remain absent on denial): `report_tmp/frameb_posture_transition_bypass_probe/runs/frameb-posture-transition-bypass-20260421T180507Z/sandbox_logs/control/calamum/watchdog_posture_state.json`

## Passing condition used here

For this probe, a denial is the passing result. The goal was to verify that a gate packet alone cannot drag the runtime into `live` once the active current-state tuple no longer matches the packet that authorized the transition.

## Packet excerpt

- Decision: `no-go`
- Reason codes: `["critical_check_failed:gate_packet_state_mismatch"]`
- Expected to-state: `sim:live`
- Evidence refs: `["C:/Users/joedi/Documents/CodeSentinel-1/report_tmp/frameb_posture_transition_bypass_probe/runs/frameb-posture-transition-bypass-20260421T180507Z/security_report_transition.md", "C:/Users/joedi/Documents/CodeSentinel-1/report_tmp/frameb_posture_transition_bypass_probe/runs/frameb-posture-transition-bypass-20260421T180507Z/sandbox_logs/control/calamum/observerctl_run_context.json"]`

