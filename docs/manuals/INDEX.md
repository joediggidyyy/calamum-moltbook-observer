# Manual Index

**Document ID**: `CALAMUM_MANUAL_INDEX_20260324`  
**Status**: Public manual catalog  
**Owner**: ORACL-Prime  
**Project**: Calamum Moltbook Observer  
**Last updated**: 2026-03-25

## Purpose

This index catalogs the public manual-class documents for **Calamum Moltbook Observer**.

Manuals are the stable reference layer between the root project overviews and the runtime and architecture details. They are intended for readers who need operational or runtime clarity.

## Manual catalog

| Document | Purpose | Audience | When to read it |
|---|---|---|---|
| [`OBSERVER_WORKFLOW_MANUAL_20260324.md`](OBSERVER_WORKFLOW_MANUAL_20260324.md) | Guides readers through the end-to-end operating path from preparation and baseline work through execution, analysis, and reporting handoff. | Operators, runtime reviewers, analysts | Read when you want the authoritative guided path through the application before dropping into deeper architecture, transition, or command-reference detail. |
| [`OBSERVER_SECURITY_MODEL_20260324.md`](OBSERVER_SECURITY_MODEL_20260324.md) | Defines the public security architecture, posture model, baseline-monitoring security role, and enforcement boundaries for the observer runtime. | Security reviewers, operators, runtime reviewers | Read when you need the architectural security model before dropping into command-level transition behavior. |
| [`OBSERVERCTL_DS_CLI_AND_WIZARD_PROPOSAL_20260325.md`](OBSERVERCTL_DS_CLI_AND_WIZARD_PROPOSAL_20260325.md) | Captures the active working plan for the `observerctl ds` namespace, including the few-command automation lane and the advanced `ds wizard` console flow. | Operators, analysts, CLI implementers | Read when you need the current planning baseline for the observer data-science command surface and wizard UX. |
| [`OBSERVERCTL_RUNTIME_OPERATOR_GUIDE_20260221.md`](OBSERVERCTL_RUNTIME_OPERATOR_GUIDE_20260221.md) | Provides the day-to-day operator workflow, command-family map, transition playbooks, and troubleshooting guidance for CLI-driven runtime work. | Operators, runtime reviewers | Read when you need hands-on runtime workflow guidance after understanding the security and transition models. |
| [`OBSERVERCTL_MODE_TRANSITION_MATRIX_20260221.md`](OBSERVERCTL_MODE_TRANSITION_MATRIX_20260221.md) | Defines the public runtime transition model, gate behavior, posture mapping, and denial semantics for `observerctl`. | Operators, runtime reviewers, security reviewers | Read when you need command-level runtime and transition behavior. |

## Recommended reading order

1. [`Project README`](../../README.md) — project scope and high-level orientation.
2. [`Security Policy`](../../SECURITY.md) — public security doctrine and evidence boundary.
3. [`OBSERVER_WORKFLOW_MANUAL_20260324.md`](OBSERVER_WORKFLOW_MANUAL_20260324.md) — guided end-to-end operating path through preparation, execution, and analysis.
4. [`OBSERVERCTL_DS_CLI_AND_WIZARD_PROPOSAL_20260325.md`](OBSERVERCTL_DS_CLI_AND_WIZARD_PROPOSAL_20260325.md) — current working plan for the observer data-science command surface and advanced wizard UX.
5. [`OBSERVER_SECURITY_MODEL_20260324.md`](OBSERVER_SECURITY_MODEL_20260324.md) — posture, baseline-monitoring, and enforcement architecture.
6. [`OBSERVERCTL_MODE_TRANSITION_MATRIX_20260221.md`](OBSERVERCTL_MODE_TRANSITION_MATRIX_20260221.md) — runtime state, posture, and transition contract.
7. [`OBSERVERCTL_RUNTIME_OPERATOR_GUIDE_20260221.md`](OBSERVERCTL_RUNTIME_OPERATOR_GUIDE_20260221.md) — deeper command-family reference, playbooks, and troubleshooting guidance.

## Related surfaces

| Document | Why it sits next to the manuals |
|---|---|
| [`Project README`](../../README.md) | Provides the public project overview before readers drop into reference material. |
| [`Security Policy`](../../SECURITY.md) | Defines the root security posture that the manual surfaces elaborate or operationalize. |
| [`Data Methodology`](../../DATA_METHODOLOGY.md) | Defines telemetry and packet-contract concerns that sit beside, rather than inside, the runtime manuals. |
| [`Documentation Index`](../INDEX.md) | Returns to the higher-level documentation router. |