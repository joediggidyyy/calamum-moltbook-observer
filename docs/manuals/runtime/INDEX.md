# Calamum Runtime Index

Updated: 2026-04-03

This section covers day-to-day runtime use of the Calamum observer stack, from local bootstrap readiness through closure and analysis handoff.

## What lives here

| Document | Purpose | Read it when you need... |
| --- | --- | --- |
| [`RUNTIME_WORKFLOWS.md`](RUNTIME_WORKFLOWS.md) | End-to-end operating path from bootstrap readiness through closure and analysis handoff | the safest order of operations for local bootstrap, baseline, runtime, and closeout work |
| [`RUNTIME_OPERATIONS.md`](RUNTIME_OPERATIONS.md) | Command-family map, runtime playbooks, evidence paths, and troubleshooting | command-level reference while running `observerctl` |

## Read next

| If you are trying to understand... | Go to |
| --- | --- |
| how to prepare or validate the local runtime-root family before runtime work | [`RUNTIME_WORKFLOWS.md`](RUNTIME_WORKFLOWS.md) |
| posture, security boundaries, and fail-closed design | [`../reference/SECURITY_MODEL.md`](../reference/SECURITY_MODEL.md) |
| the exact transition contract and denial reasons | [`../reference/RUNTIME_TRANSITIONS.md`](../reference/RUNTIME_TRANSITIONS.md) |
| the analysis and reporting lane | [`../data-science/DS_OPERATIONS.md`](../data-science/DS_OPERATIONS.md) |
| the documentation map for the whole project | [`../../INDEX.md`](../../INDEX.md) |
