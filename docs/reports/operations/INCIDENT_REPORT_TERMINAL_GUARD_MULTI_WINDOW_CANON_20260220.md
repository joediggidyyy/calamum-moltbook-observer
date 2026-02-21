# Incident Report: Terminal Guard Multi-Window Canonization (2026-02-20)

**Incident ID**: INC_TERMINAL_GUARD_MULTI_WINDOW_CANON_20260220  
**Status**: mitigated  
**Owner**: ORACL-Prime  
**Stakeholder**: joediggidyyy

## Summary

A terminal-safety edge case was identified in multi-window VS Code operation: terminal location/window affinity alone is not a safe authorization boundary for prune actions. Without explicit protection semantics, a rogue shell could outlive authorized lanes.

## Impact

- Risk of terminating an authorized operator or agent shell during hygiene pruning.
- Potential loss of lane continuity and trust baseline (-delta posture risk).

## Root cause

- Implicit trust model based on chronology/window assumptions.
- Missing canonical requirement for explicit lane registration before prune.

## Mitigation implemented

1. Hardened prune logic to fail closed when no protected terminals are registered.
2. Enforced protected-terminal exclusion from kill candidates.
3. Added one-shot helper wrapper to simplify correct registration workflow.

### Artifacts

- `semantics_staging/ops_prune_vscode_pwsh_shells.ps1`
- `semantics_staging/ops_register_terminal_lanes.ps1`
- `docs/policies/operations/OPERATIONS_POLICY/PP_OPS_PROTOCOL_POL_TERMINAL_HYGIENE_AND_EXECUTION_LANES_20260101.md`
- `docs/policies/operations/OPERATIONS_POLICY/pp/PP_OPS_PROTOCOL_POL_TERMINAL_HYGIENE_AND_EXECUTION_LANES_20260101.json`

## Validation evidence

- Dry-run prune with protected terminals registers only unprotected targets.
- Dry-run prune with empty guard reports `fail_closed_no_protected_terminals=true` and kills zero terminals.

## Preventive controls

- Canonical policy now requires lane registration before prune.
- Helper workflow standardizes setup for agent and operator lanes.
- Override path remains explicit-only and non-default.
