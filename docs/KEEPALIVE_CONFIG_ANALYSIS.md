# Keepalive Architecture Analysis: Distributed vs. Centralized

**Date:** 2026-02-10
**Context:** Job 0011 "Active Logging Keepalive"
**Subject:** Selection of Keepalive/Heartbeat architecture for the Calamum stack.

## 1. Configurations

### Configuration A: Distributed (Independent Pulse)
**Mechanism:** 
- `Observer Agent`, `Librarian`, and `Watchdog` each instantiate `KeepaliveHelper`.
- Each component writes its own `STDOUT` line periodically (e.g., every 60s).
- **Structure:** `{"component": "Agent", "status": "RUNNING", "metrics": {...}}`

**Pros:**
- **High Fidelity:** Telemetry (e.g., "buffer_size", "files_archived") is emitted directly from the source.
- **Fault Independence:** If the Watchdog crashes, the Operator still sees the Agent is alive and working.
- **Debugging:** Immediate visual confirmation of which sub-component is stalled.

**Cons:**
- **Noise:** Increases stdout traffic (3x frequency).
- **Coordination:** Requires thread-safe/interleaved logging if capturing to a single physical file (usually handled effectively by OS pipelines however).

### Configuration B: Centralized (Watchdog-Only)
**Mechanism:**
- Only `Watchdog` emits `STDOUT`. Agent and Librarian are silent.
- Watchdog checks disk-based heartbeats (file touches) or PIDs.
- Watchdog reports aggregate health: `{"component": "Watchdog", "children": {"agent": "ok", "librarian": "ok"}}`

**Pros:**
- **Cleanliness:** Single, predictable output stream.
- **Authority:** Reinforces Watchdog as the sole source of truth.

**Cons:**
- **Proxy Latency:** Metrics are delayed or boolean-only (Alive/Dead). Rich internal metrics (like "bytes_processed") are hard to bubble up without complex IPC.
- **Blind Spots:** If Watchdog hangs, the entire system *appears* dead, even if data collection is safe.
- **False Negatives:** A slow filesystem can cause the Watchdog to report failure even if the Agent is fine.

## 2. Recommendation

**Selected Configuration: Distributed (Config A)**

**Rationale:** 
For a "Blind ML Execution" run, **Maximum Observability** is critical. 
1. We need to know if the **Librarian** specifically is stuck compressing a large file (metrics: `pending_files`).
2. We need to know if the **Agent** is throttling (metrics: `buffer_usage`).
3. We cannot rely on the Watchdog as a single point of failure for *monitoring*—we need to know the raw state of the components.

**Proposed Implementation:**
1. Revert `calamum_observer_agent.py` and `calamum_librarian.py` to use `KeepaliveHelper`.
2. Ensure `KeepaliveHelper` includes a `component` field in the JSON output to allow easy grep/filtering.
3. Keep Watchdog running as a supervisor (checking PIDs/Files) but let it emit its *own* heartbeat too.

**Verdict:** Restore the distributed keepalive changes.
