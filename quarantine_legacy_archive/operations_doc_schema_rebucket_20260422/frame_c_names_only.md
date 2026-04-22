# Frame C Names-Only Evidence

- Frame: `C`
- Scenario focus: `S3`
- Probe run id: `framec-names-only-persistence-escape-20260421T184137Z`
- Source report json: `report_tmp/framec_names_only_persistence_escape_probe/runs/framec-names-only-persistence-escape-20260421T184137Z/framec_names_only_persistence_escape_probe.json`
- Source report md: `report_tmp/framec_names_only_persistence_escape_probe/runs/framec-names-only-persistence-escape-20260421T184137Z/framec_names_only_persistence_escape_probe.md`
- Overall result: `pass`

## Conclusion

Frame C S3 confirmed that the retained packet, control artifacts, and command streams stayed names-only even when hostile raw-content, secret-like, and sensitive-path lure material was seeded nearby in the sandbox. The boundary scan found no forbidden lure labels in the retained outputs reviewed for this frame.

## Retained findings

- Forbidden token labels reviewed: `["raw_content_lure", "fake_secret_token", "sensitive_path_lure"]`
- Scanned retained path count: `6`
- File hits: `{}`
- Command stream hits: `{}`

## Result matrix

- `command_output_preserved_names_only`: `True`
- `evidence_pack_command_returncode_zero`: `True`
- `hostile_input_seed_written`: `True`
- `mode_gate_command_returncode_zero`: `True`
- `retained_file_outputs_preserved_names_only`: `True`
- `retained_output_packet_written`: `True`
- `scanned_retained_output_count_at_least_three`: `True`

## Artifact paths

- Hostile input seed (excluded from retained-output scans): `report_tmp/framec_names_only_persistence_escape_probe/runs/framec-names-only-persistence-escape-20260421T184137Z/inbound/hostile_payload.txt`
- Security report: `report_tmp/framec_names_only_persistence_escape_probe/runs/framec-names-only-persistence-escape-20260421T184137Z/security_report.md`
- Posture state: `report_tmp/framec_names_only_persistence_escape_probe/runs/framec-names-only-persistence-escape-20260421T184137Z/sandbox_logs/control/calamum/watchdog_posture_state.json`
- Resource state: `report_tmp/framec_names_only_persistence_escape_probe/runs/framec-names-only-persistence-escape-20260421T184137Z/sandbox_logs/control/calamum/watchdog_resource_state.json`
- Last gate packet: `report_tmp/framec_names_only_persistence_escape_probe/runs/framec-names-only-persistence-escape-20260421T184137Z/sandbox_logs/control/calamum/observerctl_last_gate.json`
- Run context: `report_tmp/framec_names_only_persistence_escape_probe/runs/framec-names-only-persistence-escape-20260421T184137Z/sandbox_logs/control/calamum/observerctl_run_context.json`
- Output packet: `report_tmp/framec_names_only_persistence_escape_probe/runs/framec-names-only-persistence-escape-20260421T184137Z/framec_names_only_packet.json`

## Passing condition used here

For this probe, the passing result is the absence of the seeded lure labels from the retained outputs and command surfaces. The report deliberately names only the lure labels, not the lure values themselves.

