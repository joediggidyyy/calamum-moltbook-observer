# Pre-merge Snapshot / Restore Plan (VAULT Template)

Use this to record a safe snapshot and restore plan when touching critical instruction files or other high-impact material.

Fields

- Snapshot location (semantics_vault or archive path):
- Snapshot checksum & id:
- Restore plan summary:
- Rollback steps:
- CI smoke-tests required:

Checklist

- Take snapshot (signed & audited)
- Validate signature & checksum
- Dry-run CI on snapshot branch
- Request security & release approval
- Apply in monitored stepwise rollout
