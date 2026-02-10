# Recovery / Quarantine Remediation Plan (VAULT Template)

Designed for remediation PRs that propose to restore contents from the archive/quarantine into active trees.

Fields

- Incident ID / Quarantine Manifest entry ID:
- Source archive path:
- Destination target path:
- Owner / Remediation leader:
- Estimator inputs (size, integration_points, tests_needed, docs_needed, approvals_needed, risk)

Quests & tasks

1. Verify canonical copy & checksum — hours: 1 — complexity: 5
2. Run full tests in staging (dry-run) — hours: 4 — complexity: 15
3. Prepare PR on a recovery branch — hours: 2 — complexity: 10
4. Security review + forensics sign-off — hours: 3 — complexity: 20
5. Merge plan + monitored deployment — hours: 4 — complexity: 10

Acceptance Criteria

- Checksums validated for canonical copy
- CI green on staging and smoke tests
- Security & release approvals attached
