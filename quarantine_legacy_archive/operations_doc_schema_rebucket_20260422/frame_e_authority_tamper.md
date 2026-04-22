# Frame E Authority Tamper Evidence

- Frame: `E`
- Scenario focus: `S7`
- Probe run id: `framee-baseline-authority-tamper-20260421T215047Z`
- Source report json: `report_tmp/framee_baseline_authority_tamper_probe/runs/framee-baseline-authority-tamper-20260421T215047Z/framee_baseline_authority_tamper_probe.json`
- Source report md: `report_tmp/framee_baseline_authority_tamper_probe/runs/framee-baseline-authority-tamper-20260421T215047Z/framee_baseline_authority_tamper_probe.md`
- Overall result: `pass`

## Conclusion

Frame E S7 confirmed that an explicit forged selector-linkage packet did not outrank authoritative dataset state. The repaired comparison-baseline packet restored the canonical selector ids before report context reuse, and the report context stayed anchored to the repaired authoritative packet.

## Retained findings

- Observed boundary result: `baseline_authority_tamper_repaired_from_authoritative_selector`
- Authority entry id: `dataset-framee-reviewed-canary-authority`
- Authority run id: `framee-reviewed-canary-authority`
- Tampered selector entry id: `forged-selector-entry`
- Repaired selector entry id: `dataset-framee-reviewed-canary-authority`
- Repaired selector run id: `framee-reviewed-canary-authority`
- Report-context baseline packet: `report_tmp/framee_baseline_authority_tamper_probe/runs/framee-baseline-authority-tamper-20260421T215047Z/sandbox_root/local_untracked/analysis/baselines/dataset-framee-reviewed-canary-authority/comparison_baseline_packet.json`

## Result matrix

- `canary_authority_registered`: `True`
- `comparison_baseline_candidate_exists_before_tamper`: `True`
- `explicit_candidate_repaired_from_authority`: `True`
- `live_target_registered`: `True`
- `repaired_packet_restored_selector_entry`: `True`
- `repaired_packet_restored_selector_run`: `True`
- `report_context_keeps_expected_window_id`: `True`
- `report_context_packet_restored_selector_entry`: `True`
- `report_context_uses_repaired_packet`: `True`
- `selector_linkage_tamper_written`: `True`

## Artifact paths

- Comparison baseline packet: `report_tmp/framee_baseline_authority_tamper_probe/runs/framee-baseline-authority-tamper-20260421T215047Z/sandbox_root/local_untracked/analysis/baselines/dataset-framee-reviewed-canary-authority/comparison_baseline_packet.json`
- Report manifest json: `report_tmp/framee_baseline_authority_tamper_probe/runs/framee-baseline-authority-tamper-20260421T215047Z/sandbox_root/local_untracked/analysis/runs/evaluate/framee-baseline-authority-report/report/manifest.json`
- Report json: `report_tmp/framee_baseline_authority_tamper_probe/runs/framee-baseline-authority-tamper-20260421T215047Z/sandbox_root/local_untracked/analysis/runs/evaluate/framee-baseline-authority-report/report/report.json`
- Report md: `report_tmp/framee_baseline_authority_tamper_probe/runs/framee-baseline-authority-tamper-20260421T215047Z/sandbox_root/local_untracked/analysis/runs/evaluate/framee-baseline-authority-report/report/report.md`
- Review policy packet: `report_tmp/framee_baseline_authority_tamper_probe/runs/framee-baseline-authority-tamper-20260421T215047Z/framee_review_policy_packet.md`

## Passing condition used here

For this probe, the passing result is repaired selector authority rather than silent acceptance of the forged packet. The evidence remains names-only and bounded to the S7 authority seam.

