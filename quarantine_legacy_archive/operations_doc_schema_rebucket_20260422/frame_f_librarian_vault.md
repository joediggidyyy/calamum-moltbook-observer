# Frame F Librarian Vault Evidence

- Frame: `F`
- Scenario focus: `S9`, `S10`
- S9 probe run id: `librarian-access-exchange-20260421T233950Z`
- S10 probe run id: `librarian-vault-controls-20260421T233952Z`
- Source S9 report json: `report_tmp/librarian_access_exchange_probe/runs/librarian-access-exchange-20260421T233950Z/librarian_access_exchange_probe.json`
- Source S9 report md: `report_tmp/librarian_access_exchange_probe/runs/librarian-access-exchange-20260421T233950Z/librarian_access_exchange_probe.md`
- Source S10 report json: `report_tmp/librarian_vault_controls_probe/runs/librarian-vault-controls-20260421T233952Z/librarian_vault_controls_probe.json`
- Source S10 report md: `report_tmp/librarian_vault_controls_probe/runs/librarian-vault-controls-20260421T233952Z/librarian_vault_controls_probe.md`
- Overall result: `pass`

## Conclusion

Frame F execution produced pass evidence across the delegated-release abuse and maintenance-window abuse lanes.

S9 showed that the delegated protected-source access chain stayed valid only while the signed request, attestation, and release payloads remained intact. When those retained signed payloads were altered, detached-signature verification failed closed.

S10 showed that a manual maintenance-window unlock preserved operator control but denied both ordinary registration and ordinary release with `critical_check_failed:librarian_vault_maintenance_window_open`, then returned the vault to a locked, rebaselined, and verified state.

## Retained findings

### S9 delegated release abuse

- Observed boundary result: `delegated_release_abuse_packets_fail_signature_verification`
- Request role: `requester`
- Attestation role: `librarian`
- Release role: `source`
- Tampered request action: `publish-live`
- Tampered release manifest: `forged_dataset_manifest.json`
- Requester id: `sandbox-probe`

### S10 maintenance-window abuse

- Observed boundary result: `maintenance_window_abuse_denied_fail_closed`
- Unlock summary: `Protected librarian vault unlocked for manual maintenance.`
- Register denial reason codes: `critical_check_failed:librarian_vault_maintenance_window_open`
- Release denial reason codes: `critical_check_failed:librarian_vault_maintenance_window_open`
- Audit actions: `librarian-vault-bootstrap`, `librarian-dataset-register`, `librarian-vault-unlock`, `librarian-vault-lock`, `librarian-vault-rebaseline`
- Verify integrity status: `ok`

## Result matrix

### S9 result matrix

- `signature_roles_are_separated`: `True`
- `protected_dataset_registered`: `True`
- `protected_dataset_released`: `True`
- `shared_signing_root_not_required`: `True`
- `request_signature_verified`: `True`
- `attestation_signature_verified`: `True`
- `release_receipt_signature_verified`: `True`
- `delegated_access_projection_written`: `True`
- `vault_baseline_written`: `True`
- `vault_audit_written`: `True`
- `tampered_request_rejected`: `True`
- `tampered_attestation_rejected`: `True`
- `tampered_release_receipt_rejected`: `True`

### S10 result matrix

- `seed_dataset_registered`: `True`
- `vault_status_reported`: `True`
- `vault_unlock_succeeded`: `True`
- `unlocked_register_denied`: `True`
- `unlocked_release_denied`: `True`
- `vault_lock_succeeded`: `True`
- `vault_rebaseline_succeeded`: `True`
- `vault_verify_succeeded`: `True`
- `vault_control_state_written`: `True`
- `vault_audit_records_control_actions`: `True`

## Artifact paths

### S9 artifact paths

- Request packet: `report_tmp/librarian_access_exchange_probe/runs/librarian-access-exchange-20260421T233950Z/sandbox_root/local_untracked/analysis/indexes/dataset_access/dataset-probe-protected-dataset/20260421T233951Z/request.json`
- Attestation packet: `report_tmp/librarian_access_exchange_probe/runs/librarian-access-exchange-20260421T233950Z/sandbox_root/local_untracked/analysis/indexes/dataset_access/dataset-probe-protected-dataset/20260421T233951Z/attestation.json`
- Release receipt: `report_tmp/librarian_access_exchange_probe/runs/librarian-access-exchange-20260421T233950Z/sandbox_root/local_untracked/analysis/indexes/dataset_access/dataset-probe-protected-dataset/20260421T233951Z/release_receipt.json`
- Vault baseline: `report_tmp/librarian_access_exchange_probe/runs/librarian-access-exchange-20260421T233950Z/sandbox_root/local_untracked/analysis/vaults/librarian/integrity/vault_checksum.json`
- Vault audit: `report_tmp/librarian_access_exchange_probe/runs/librarian-access-exchange-20260421T233950Z/sandbox_root/local_untracked/analysis/vaults/librarian/integrity/vault_audit.jsonl`

### S10 artifact paths

- Seed manifest: `report_tmp/librarian_vault_controls_probe/runs/librarian-vault-controls-20260421T233952Z/artifacts/datasets/vault_primary/dataset_manifest.json`
- Locked manifest: `report_tmp/librarian_vault_controls_probe/runs/librarian-vault-controls-20260421T233952Z/artifacts/datasets/vault_secondary/dataset_manifest.json`
- Vault control state: `report_tmp/librarian_vault_controls_probe/runs/librarian-vault-controls-20260421T233952Z/sandbox_root/local_untracked/analysis/vaults/librarian/integrity/vault_control_state.json`
- Vault baseline: `report_tmp/librarian_vault_controls_probe/runs/librarian-vault-controls-20260421T233952Z/sandbox_root/local_untracked/analysis/vaults/librarian/integrity/vault_checksum.json`
- Vault audit: `report_tmp/librarian_vault_controls_probe/runs/librarian-vault-controls-20260421T233952Z/sandbox_root/local_untracked/analysis/vaults/librarian/integrity/vault_audit.jsonl`

## Passing condition used here

For Frame F, the passing condition is not permissive access. The passing condition is bounded fail-closed behavior:

- the delegated release chain remains valid only for the untampered signed payload set, and
- the maintenance-window unlock blocks ordinary register and release mutations until the vault is locked and reverified again.
