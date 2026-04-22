# Frame G Publication Boundary Evidence

- Frame: `G`
- Scenario focus: `S12`, `S13`, `S14`
- S12 probe run id: `frameg-public-report-boundary-escape-20260422T015208Z`
- S13 probe run id: `frameg-bootstrap-root-starvation-20260422T015215Z`
- S14 probe run id: `frameg-sandbox-catalog-authority-drift-20260422T015223Z`
- Source S12 report json: `report_tmp/frameg_public_report_boundary_escape_probe/runs/frameg-public-report-boundary-escape-20260422T015208Z/frameg_public_report_boundary_escape_probe.json`
- Source S12 report md: `report_tmp/frameg_public_report_boundary_escape_probe/runs/frameg-public-report-boundary-escape-20260422T015208Z/frameg_public_report_boundary_escape_probe.md`
- Source S13 report json: `report_tmp/frameg_bootstrap_root_starvation_probe/runs/frameg-bootstrap-root-starvation-20260422T015215Z/frameg_bootstrap_root_starvation_probe.json`
- Source S13 report md: `report_tmp/frameg_bootstrap_root_starvation_probe/runs/frameg-bootstrap-root-starvation-20260422T015215Z/frameg_bootstrap_root_starvation_probe.md`
- Source S14 report json: `report_tmp/frameg_sandbox_catalog_authority_drift_probe/runs/frameg-sandbox-catalog-authority-drift-20260422T015223Z/frameg_sandbox_catalog_authority_drift_probe.json`
- Source S14 report md: `report_tmp/frameg_sandbox_catalog_authority_drift_probe/runs/frameg-sandbox-catalog-authority-drift-20260422T015223Z/frameg_sandbox_catalog_authority_drift_probe.md`
- Overall result: `pass`

## Conclusion

Frame G execution produced pass evidence across the publication-boundary escape, bootstrap-root starvation, and sandbox catalog authority-drift lanes.

S12 showed that reader-facing tracked publication stayed human-facing after the source report surfaces were seeded with absolute-path noise and a local-only authority lure. The published report JSON and markdown removed the absolute project root, removed the local authority lure, and kept generated figure paths relative.

S13 showed that runtime bootstrap degraded truthfully when `reports_operations_root` was blocked. Both the check-only and mutating bootstrap paths returned `decision: no-go`, emitted `critical_check_failed:runtime_bootstrap_blocked_reports_operations_root`, and still exposed partial root creation instead of fabricating healthy readiness.

S14 showed that sandbox catalog selection remained exact-name-only and that stale retained-run references failed closed. The catalog denied the prefix alias `metadata-contract-reg`, kept the canonical definition id at `metadata-contract`, and `sandbox runs show` returned `critical_check_failed:sandbox_run_report_missing` rather than presenting a missing report as trustworthy review material.

## Retained findings

### S12 public report boundary escape

- Observed boundary result: `public_report_boundary_preserved`
- Generated surfaces markdown: `report_tmp/frameg_public_report_boundary_escape_probe/runs/frameg-public-report-boundary-escape-20260422T015208Z/sandbox_root/docs/reports/reference/GENERATED_REPORT_SURFACES.md`
- Local authority lure: `C:/Operators/RuntimeAuthority/local_only/not-for-public.json`
- Published figure: `docs/reports/collections/frameg-public-boundary/processing/score/figures/20260422T001500000000Z.score/score_distribution.png`

### S13 bootstrap root starvation

- Observed boundary result: `bootstrap_root_starvation_degraded_truthfully`
- Blocked root id: `reports_operations_root`
- Blocked root path: `report_tmp/frameg_bootstrap_root_starvation_probe/runs/frameg-bootstrap-root-starvation-20260422T015215Z/sandbox_root/local_untracked/reports/operations`
- Bootstrap reason codes: `critical_check_failed:runtime_bootstrap_blocked_reports_operations_root`
- Created roots: `17`
- Missing root id on check-only pass: `analysis_root`

### S14 sandbox catalog authority drift

- Observed boundary result: `sandbox_catalog_authority_drift_visible_fail_closed`
- Alias candidate: `metadata-contract-reg`
- Canonical definition id: `metadata-contract`
- Catalog count: `28`
- Stale report json: `report_tmp/frame4_metadata_contract_probe/runs/metadata-contract-stale-20260422T015223Z/report.json`
- Stale run id: `metadata-contract-stale-20260422T015223Z`
- Stale review reason codes: `critical_check_failed:sandbox_run_report_missing`

## Result matrix

### S12 result matrix

- `absolute_project_root_removed_from_public_json`: `True`
- `absolute_project_root_removed_from_public_markdown`: `True`
- `human_facing_generated_surfaces_contract_present`: `True`
- `local_authority_lure_removed_from_reader_surfaces`: `True`
- `publication_refresh_go`: `True`
- `published_collection_markdown_written`: `True`
- `published_figure_rewritten_relative`: `True`
- `published_processing_markdown_written`: `True`
- `published_report_json_written`: `True`
- `source_report_seed_contains_absolute_path`: `True`
- `stable_collection_landing_absent`: `True`

### S13 result matrix

- `blocked_root_not_converted_to_directory`: `True`
- `blocked_root_reason_emitted`: `True`
- `blocked_root_seed_written`: `True`
- `blocked_root_status_preserved`: `True`
- `check_bootstrap_marks_missing_root`: `True`
- `check_bootstrap_no_go`: `True`
- `missing_root_reason_emitted`: `True`
- `mutating_bootstrap_no_go`: `True`
- `other_roots_created_under_partial_success`: `True`
- `partial_success_not_reported_as_go`: `True`

### S14 result matrix

- `canonical_definition_show_go`: `True`
- `canonical_selector_policy_exact_name_only`: `True`
- `catalog_ids_unique`: `True`
- `catalog_list_go`: `True`
- `prefix_alias_lookup_denied`: `True`
- `stale_run_index_row_written`: `True`
- `stale_run_payload_not_presented_as_reviewable`: `True`
- `stale_run_reason_emitted`: `True`
- `stale_run_review_no_go`: `True`
- `stale_run_visible_in_catalog_list`: `True`

## Artifact paths

### S12 artifact paths

- Source report json: `report_tmp/frameg_public_report_boundary_escape_probe/runs/frameg-public-report-boundary-escape-20260422T015208Z/frameg_public_report_boundary_escape_probe.json`
- Source report md: `report_tmp/frameg_public_report_boundary_escape_probe/runs/frameg-public-report-boundary-escape-20260422T015208Z/frameg_public_report_boundary_escape_probe.md`
- Generated surfaces markdown: `report_tmp/frameg_public_report_boundary_escape_probe/runs/frameg-public-report-boundary-escape-20260422T015208Z/sandbox_root/docs/reports/reference/GENERATED_REPORT_SURFACES.md`
- Published figure: `docs/reports/collections/frameg-public-boundary/processing/score/figures/20260422T001500000000Z.score/score_distribution.png`

### S13 artifact paths

- Source report json: `report_tmp/frameg_bootstrap_root_starvation_probe/runs/frameg-bootstrap-root-starvation-20260422T015215Z/frameg_bootstrap_root_starvation_probe.json`
- Source report md: `report_tmp/frameg_bootstrap_root_starvation_probe/runs/frameg-bootstrap-root-starvation-20260422T015215Z/frameg_bootstrap_root_starvation_probe.md`
- Blocked root path: `report_tmp/frameg_bootstrap_root_starvation_probe/runs/frameg-bootstrap-root-starvation-20260422T015215Z/sandbox_root/local_untracked/reports/operations`

### S14 artifact paths

- Source report json: `report_tmp/frameg_sandbox_catalog_authority_drift_probe/runs/frameg-sandbox-catalog-authority-drift-20260422T015223Z/frameg_sandbox_catalog_authority_drift_probe.json`
- Source report md: `report_tmp/frameg_sandbox_catalog_authority_drift_probe/runs/frameg-sandbox-catalog-authority-drift-20260422T015223Z/frameg_sandbox_catalog_authority_drift_probe.md`
- Stale report json: `report_tmp/frame4_metadata_contract_probe/runs/metadata-contract-stale-20260422T015223Z/report.json`

## Passing condition used here

For Frame G, the passing condition is not permissive publication or silent recovery. The passing condition is bounded reviewer-safe behavior:

- tracked publication remains human-facing and strips local-only residue;
- bootstrap starvation emits truthful no-go while partial creation stays visible; and
- catalog drift stays exact-name-only while stale retained-run review fails closed.
