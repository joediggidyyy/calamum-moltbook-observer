# Contributing to Calamum Moltbook Observer

> **Managed by CodeSentinel** | *Operations governed by automated watchdog policy.*

## Contribution boundary

This repository is maintained as a public product and review surface for *Calamum Moltbook Observer*.

- Pull requests are welcome.
- Changes that alter runtime behavior, public contracts, or report publication behavior should update the corresponding public docs in the same pass.
- Local operator evidence, local runtime state, and non-tracked generated artifacts should remain outside the tracked public surface.

## Core contribution rules

All contributions must preserve the project’s privacy, safety, and evidence-boundary posture.

- Keep telemetry and reports names-only.
- Keep secrets out of tracked files, examples, logs, and screenshots.
- Preserve the `obfuscator_lib` safety boundary and fail-closed observer behavior.
- Treat `docs/reports/` as a generated public surface, not as a hand-authored source of truth.

The public policy surfaces for these rules are `README.md`, `SECURITY.md`, and `DATA_METHODOLOGY.md`.

## Local setup

1. Install the project in editable mode:
	- `python -m pip install -e .`
2. Add extras only when you need them:
	- `python -m pip install -e ".[ds]"` for the DS / report / visualization lane
	- `python -m pip install -e ".[dashboard]"` for Ghost Console surfaces

## Typical validation workflow

1. Use `observerctl ops bootstrap --check --json` to validate the local runtime-root family before command-level runtime work.
2. Use `src/deployment/secure_run.ps1` when you need to validate the hardened runtime path.
3. Use the native `observerctl` surface for data-science and report work:
	- `observerctl ds build ...`
	- `observerctl ds train ...`
	- `observerctl ds evaluate ...`
	- `observerctl ds score ...`
	- `observerctl ds run demo --json`
	- `observerctl ops bootstrap --json` when you are preparing a fresh local runtime tree for a new environment or temp project root
4. Run targeted tests for the surfaces you changed:
	- `pytest src/tests/`
	- or a focused slice such as `pytest src/tests/test_observerctl.py -k ds_`
5. If your change alters public behavior, update the public entry docs in the same pass:
	- `README.md`
	- `SECURITY.md`
	- `DATA_METHODOLOGY.md`
	- `docs/INDEX.md`

## Generated public report surfaces

The tracked report lane is rebuilt from canonical local DS run artifacts.

- Public reader-facing outputs live under `docs/reports/`.
- Canonical machine-readable authority remains under `local_untracked/analysis/`.
- When command or report behavior changes, regenerate the report lane from the DS workflow rather than editing dated collection packets by hand.

The public report entrypoint is `docs/reports/INDEX.md`.

## Live-source caution

Live-source work requires operator-local credentials such as `MOLTBOOK_API_KEY` and should remain names-only end to end.
Ensure the watchdog runtime (`src/sentinel.py`) is active during any live-wire testing.
