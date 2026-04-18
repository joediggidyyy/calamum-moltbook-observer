# Calamum Manual Index

Version: `1.0.1`
Updated: 2026-04-18

This index routes readers through the public manual-class documents for Calamum Moltbook Observer.

The manual library rooted here is part of the shipped application documentation payload. Derived publication packets under `../reports/` remain tracked repository surfaces rather than current installable-package manual payload.

## Manual library

| Section      | Purpose                                                        | Start with                                       |
| ------------ | -------------------------------------------------------------- | ------------------------------------------------ |
| runtime      | end-to-end operating path plus command-level runtime reference | [`runtime/INDEX.md`](runtime/INDEX.md)           |
| data science | DS commands, the guided wizard, and reporting linkage          | [`data-science/INDEX.md`](data-science/INDEX.md) |
| reference    | security architecture and the formal transition contract       | [`reference/INDEX.md`](reference/INDEX.md)       |

## Suggested reading paths

| If you want to understand...                      | Read                                                                                                                                                                         |
| ------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| the overall project and where to begin            | [`../../README.md`](../../README.md) -> [`../INDEX.md`](../INDEX.md)                                                                                                         |
| the safest runtime path through the system        | [`runtime/INDEX.md`](runtime/INDEX.md) -> [`runtime/RUNTIME_WORKFLOWS.md`](runtime/RUNTIME_WORKFLOWS.md) -> [`runtime/RUNTIME_OPERATIONS.md`](runtime/RUNTIME_OPERATIONS.md) |
| posture, denial behavior, and security boundaries | [`reference/SECURITY_MODEL.md`](reference/SECURITY_MODEL.md) -> [`reference/RUNTIME_TRANSITIONS.md`](reference/RUNTIME_TRANSITIONS.md)                                       |
| the analysis and reporting lane                   | [`data-science/DS_OPERATIONS.md`](data-science/DS_OPERATIONS.md) -> [`data-science/DS_WIZARD.md`](data-science/DS_WIZARD.md) -> [`../reports/INDEX.md`](../reports/INDEX.md) |

## Related surfaces

| Document                                                 | Why it sits next to the manuals                      |
| -------------------------------------------------------- | ---------------------------------------------------- |
| [`../../README.md`](../../README.md)                     | public project overview and first-stop entry surface |
| [`../../SECURITY.md`](../../SECURITY.md)                 | public security doctrine and evidence boundary       |
| [`../../DATA_METHODOLOGY.md`](../../DATA_METHODOLOGY.md) | telemetry and packet-contract context                |
| [`../INDEX.md`](../INDEX.md)                             | top-level documentation router                       |