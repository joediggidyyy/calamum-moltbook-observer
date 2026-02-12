# Contributing to Calamum Moltbook Observer

> **Managed by CodeSentinel** | *Operations governed by automated sentinel policy.*

## Academic Integrity
This project is part of a university coursework submission (DATA740/DATA780). 
- **Students**: Please ensure all contributions are attributable to your group workflow.
- **External**: Pull requests are welcome but may not be merged until after the semester grading period to preserve the fidelity of the simplified "Submission State".

## Code of Conduct
All contributors must adhere to the Ethical Matrix defined in `deliverables/DATA740/ALIGNMENT_ASSESSMENT.md`.
- **DO NOT** commit raw data from the Moltbook platform.
- **DO NOT** commit real credentials or API tokens.
- **DO NOT** remove the `obfuscator_lib` safety constraints.

## Development Workflow
1. Use `src/deployment/secure_run.ps1` to build/run the hardened container locally.
	- Safe default (no live creds required): `src/deployment/secure_run.ps1 -Mode canary -Source sim`
	- Live source (requires env-injected `MOLTBOOK_API_KEY`; names-only): `src/deployment/secure_run.ps1 -Mode sampler -Source live`
2. Run tests via `pytest src/tests/`.
3. Ensure the 'Sentinel' watchdog is active during any live-wire testing.
