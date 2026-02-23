# ObserverCTL First Real Canary CLI Gate Run

- Run timestamp (artifact id): `20260222T230012Z`
- Runtime CLI surface: `observerctl`
- Operator: `joediggidyyy`
- Agent: `ORACL-Prime`
- Goal: first-use CLI transition gate sequence into `real:canary`

## Decision summary

- Gate decision: `go`
- Transition decision: `go`
- Final state: `source=real`, `mode=canary`, `posture_trigger=isolation`

## Process log

1. Preflight executed for real-source readiness.
2. Gate executed for `--to canary --source real`.
3. Atomic transition executed (`gate -> set -> evidence`) via `ops mode transition`.
4. Final mode-current verification executed.

## Provenance

- Producer process: `observerctl ops evidence pack` (within transition)
- Transition packet sha256: `06872772f2d31263890b06215f7e26aa6cd1725698fee4a69794343b25e2504f`
- Run linkage fields present:
  - `run_id=observerctl-mode-set-20260223T040012Z`
  - `posture_trigger_id=pt-canary-20260223T040012Z`
  - `posture_trigger=isolation`
  - `security_report_ref=projects/calamum-moltbook-observer/local_untracked/observerctl/evidence/observerctl_first_real_canary_security_report_20260222T230012Z.md`

## Methodology

- Names-only fail-closed gate semantics.
- Required key-presence checks satisfied in-session for transition-gate contract fields.
- Runtime service health + watchdog posture enforced prior to mutation.
- Evidence emitted as deterministic JSON packets with UTC timestamps and reason-code vectors.

## Evidence refs

- Preflight packet:
  - `projects/calamum-moltbook-observer/local_untracked/observerctl/evidence/observerctl_first_real_canary_preflight_20260222T230012Z.json`
- Gate packet:
  - `projects/calamum-moltbook-observer/local_untracked/observerctl/evidence/observerctl_first_real_canary_gate_20260222T230012Z.json`
- Transition packet (publish-grade):
  - `projects/calamum-moltbook-observer/local_untracked/observerctl/evidence/observerctl_first_real_canary_transition_20260222T230012Z.json`
- Final state packet:
  - `projects/calamum-moltbook-observer/local_untracked/observerctl/evidence/observerctl_first_real_canary_current_20260222T230012Z.json`
- Security report artifact:
  - `projects/calamum-moltbook-observer/local_untracked/observerctl/evidence/observerctl_first_real_canary_security_report_20260222T230012Z.md`

## Notes

- This run used names-only in-session key mapping to satisfy gate-presence contract for first-use transition gating.
- For sustained real-source collection operations, operator should provision canonical `MOLTBOOK_API_KEY` and `CALAMUM_DATA_SIGNING_KEY` directly in the runtime environment profile used by launch surfaces.
