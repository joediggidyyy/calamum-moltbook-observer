# Quest Map: Operation "Live Wire" (Real-World Deployment)

> **Context**: Transitioning Calamum Observer from "Dreaming Mode" (Simulation) to "Live Listening" (Real Moltbook API).

**Status**: READY TO START
**Prerequisites**:
- [x] Hardened Container (`stage2`)
- [x] Sentinel Watchdog (`sentinel.py`)
- [x] Legal/Strategic Approval (`CALAMUM_LIVE_DEPLOYMENT_STRATEGY_20260202.md`)

---

## 🗺️ The Mission Path

### Phase A: The "Red Pill" (Code Switching)
- [ ] **Task 1**: Edit `src/moltbook_client.py`
    - *Action*: Un-comment the `requests` import and the `requests.get()` calls.
    - *Constraint*: Verify only `GET` requests are enabled.
- [ ] **Task 2**: Create Air-Gapped Credentials
    - *Action*: Create `projects/calamum-moltbook-observer/src/.env`
    - *Content*: `MOLTBOOK_API_KEY=your_actual_key_here`
    - *Verification*: Ensure `.gitignore` blocks this file.

### Phase B: The "Sound Check" (Connectivity)
- [ ] **Task 3**: Dry Run (Local Python)
    - *Action*: Run `python src/calamum_sampler.py --dry-run` on the host.
    - *Goal*: Verify authentication works without crashing.

### Phase C: The "Bell Jar" (Hardened Deployment)
- [ ] **Task 4**: Launch Container
    - *Command*: `powershell src/deployment/secure_run.ps1 -Mode live`
    - *Observation*: Watch `sentinel.py` logs for immediate kills (false positives).
- [ ] **Task 5**: Verify Telemetry
    - *Check*: `logs/data/calamum/moltbook_samples_obfuscated.jsonl`
    - *Verify*: Timestamps are current; content is obfuscated.

### Phase D: "Set and Forget" (Persistence)
- [ ] **Task 6**: Commit to Long-Term Storage
    - *Action*: Ensure logs are rotating.
    - *Action*: Set up a daily "Pulse Check" to ensure the container hasn't been killed by the Sentinel.

---

**Next Stop**: After 24h of data, we begin **DATA780 Analysis** (Blind ML).
