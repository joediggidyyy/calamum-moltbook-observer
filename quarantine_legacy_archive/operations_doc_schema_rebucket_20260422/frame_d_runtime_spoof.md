# Frame D Runtime Spoof Evidence

- Frame: `D`
- Scenario focus: `S5`
- Probe run id: `framed-watchdog-heartbeat-spoof-resistance-20260421T194743Z`
- Source report json: `report_tmp/framed_watchdog_heartbeat_spoof_resistance_probe/runs/framed-watchdog-heartbeat-spoof-resistance-20260421T194743Z/framed_watchdog_heartbeat_spoof_resistance_probe.json`
- Source report md: `report_tmp/framed_watchdog_heartbeat_spoof_resistance_probe/runs/framed-watchdog-heartbeat-spoof-resistance-20260421T194743Z/framed_watchdog_heartbeat_spoof_resistance_probe.md`
- Overall result: `pass`

## Conclusion

Frame D S5 confirmed that a stale observer-heartbeat signal did not survive as clean runtime health. The watchdog lane surfaced the spoof-like signal explicitly through advisory reasoning while the service footprint remained visible and the canary gate avoided a false critical denial.

## Retained findings

- Watchdog advisory reason codes: `["major_check_failed:observer_heartbeat_stale_service_alive"]`
- Gate reason codes: `[]`
- Observer service state: `{"state": "degraded", "status": "ok"}`
- Collection state: `{"collecting_fresh_max_age_seconds": 40.0, "metrics_age_seconds": null, "metrics_exists": false, "metrics_path": "C:\\Users\\joedi\\Documents\\CodeSentinel-1\\report_tmp\\framed_watchdog_heartbeat_spoof_resistance_probe\\runs\\framed-watchdog-heartbeat-spoof-resistance-20260421T194743Z\\sandbox_logs\\data\\calamum\\observer_derived\\sim\\watch\\moltbook_metrics.jsonl", "observer_heartbeat_status": "err", "observer_pid_alive": true, "runtime_state": "degraded", "source_fetch_error_kind": null, "source_fetch_status": "ok", "state": "idle", "status": "ok"}`

## Result matrix

- `collection_state_remains_legible`: `True`
- `evidence_packet_written`: `True`
- `mode_gate_preserves_no_false_critical`: `True`
- `runtime_service_state_preserved`: `True`
- `stale_observer_heartbeat_seeded`: `True`
- `watchdog_advisory_reason_emitted`: `True`
- `watchdog_check_completed`: `True`
- `watchdog_false_critical_denial_avoided`: `True`

## Artifact paths

- Observer heartbeat: `report_tmp/framed_watchdog_heartbeat_spoof_resistance_probe/runs/framed-watchdog-heartbeat-spoof-resistance-20260421T194743Z/sandbox_logs/health/calamum_observer.heartbeat`
- Ops watchdog heartbeat: `report_tmp/framed_watchdog_heartbeat_spoof_resistance_probe/runs/framed-watchdog-heartbeat-spoof-resistance-20260421T194743Z/sandbox_logs/health/calamum_ops_watchdog.heartbeat`
- Agent pid: `report_tmp/framed_watchdog_heartbeat_spoof_resistance_probe/runs/framed-watchdog-heartbeat-spoof-resistance-20260421T194743Z/sandbox_root/calamum_agent.pid`
- Posture state: `report_tmp/framed_watchdog_heartbeat_spoof_resistance_probe/runs/framed-watchdog-heartbeat-spoof-resistance-20260421T194743Z/sandbox_logs/control/calamum/watchdog_posture_state.json`
- Resource state: `report_tmp/framed_watchdog_heartbeat_spoof_resistance_probe/runs/framed-watchdog-heartbeat-spoof-resistance-20260421T194743Z/sandbox_logs/control/calamum/watchdog_resource_state.json`
- Output packet: `report_tmp/framed_watchdog_heartbeat_spoof_resistance_probe/runs/framed-watchdog-heartbeat-spoof-resistance-20260421T194743Z/framed_watchdog_heartbeat_spoof_resistance_packet.json`

## Passing condition used here

For this probe, the passing result is an explicit degraded or advisory heartbeat-truth signal rather than a false clean-health narrative. The probe remains names-only and bounded to runtime spoof semantics.

