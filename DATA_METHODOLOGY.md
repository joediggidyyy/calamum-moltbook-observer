# Data Methodology & Packet Contract: Calamum Moltbook Observer

**Document ID**: `CALAMUM_DATA_METHODOLOGY_AND_PACKET_CONTRACT_20260324`  
**Status**: Public methodology manual  
**Owner**: ORACL-Prime  
**Project**: Calamum Moltbook Observer  
**Last updated**: 2026-03-24  
**Classification**: PUBLIC / ACADEMIC OPEN

---

## 1. Purpose and scope

This manual defines the public-facing methodology, packet contract, and evidence boundaries for the *Calamum Moltbook Observer*.

It covers:

- simulation and synthetic-data assumptions,
- names-only telemetry design,
- current packet families defined in code,
- canonical local output paths, and
- the boundary between public documentation and local runtime evidence.

## Related surfaces

- [`README.md`](README.md) — project overview and public entry point
- [`SECURITY.md`](SECURITY.md) — security doctrine and disclosure policy
- [`Calamum Security Model`](docs/manuals/reference/CALAMUM_SECURITY_MODEL.md) — posture and enforcement architecture
- [`Calamum Runtime Transitions`](docs/manuals/reference/CALAMUM_RUNTIME_TRANSITIONS.md) — runtime transition contract

## 2. Verification basis

This manual reflects the current code-defined contract and supporting reference surfaces.

Primary verification basis:

- `src/obfuscator_lib.py`
- `src/calamum_sampler.py`
- `src/calamum_observer_agent.py`
- `src/observerctl.py`
- `src/analysis/schema/README.md`
- `src/analysis/schema/obfuscated_record_schema_v1.json`
- `src/analysis/validate_jsonl.py`
- `src/tests/test_obfuscator.py`
- `src/tests/test_observerctl.py`
- `docs/manuals/runtime/CALAMUM_RUNTIME_OPERATIONS.md`
- `docs/manuals/reference/CALAMUM_RUNTIME_TRANSITIONS.md`

## 3. Methodological commitments

The project is organized around a small set of methodological commitments:

- **Synthetic first**: validate instrumentation and analysis pipelines before live collection is considered
- **Names-only telemetry**: persist structure and behavior signals rather than raw content
- **Strict separation of channels**: telemetry, diagnostics, and safety enforcement are not collapsed into one ambiguous stream
- **Fail-closed enforcement**: unsafe states should terminate or deny rather than quietly degrade
- **Reproducible local analysis**: peer review should not require access to the live target

## 4. Simulation model

The simulation layer (`MockMoltbookClient`) acts as a deterministic digital twin of the target environment. It generates synthetic artifacts organized into four Threat Vector classes.

### 4.1 Threat Vector classification

| ID | Class | Description | Simulation Pattern | Purpose |
|----|-------|-------------|--------------------|---------|
| **TV-0** | **Benign** | Baseline-consistent ordinary activity that remains within expected low-risk bounds. | ordinary posts, routine follows, baseline message timing | Baseline metric calibration. |
| **TV-1** | **Irregular** | Low-concern deviations from baseline, including unusual but non-actionable technical or format-heavy activity. | code-dense but benign posts, atypical markdown bursts, harmless structural outliers | Stress-testing false positives against activity that looks unusual without being strongly hostile. |
| **TV-2** | **Suspicious** | Structurally abnormal activity whose timing, density, or interaction profile supports a likely-hostile interpretation. | override-like bursts, unusual link/script concentration, repeated abnormal interaction patterns | Evaluating whether metadata-only features can isolate likely-hostile structure before strongest-risk labeling. |
| **TV-3** | **High-Risk** | Patterns that justify the strongest level of concern under the privacy-preserving labeling policy. | credential-solicitation DM simulations, concentrated malicious-link clusters, severe hostile-contact patterns | Testing highest-risk handling and intervention-grade alerting logic. |

For the current DATA780 framing, the primary empirical boundary remains **TV-0 versus TV-3**. **TV-1** and **TV-2** are retained as intermediate categories so the project can represent nuisance structure, ambiguity, and escalation without collapsing every non-benign deviation into the highest-risk class.

### 4.2 Generator distribution

The sampler employs a stochastic generator to mix these vectors into a plausibly hostile environment:

- **Observer mode (feed)**: 80% TV-0/1, 20% TV-2
- **Canary mode (inbound)**: 50% TV-3, 50% TV-0

## 5. Logging architecture

The logging design separates research telemetry, runtime diagnostics, and safety enforcement so that no single stream has to carry every concern.

This separation is methodological and defensive at the same time: it improves analysis clarity while also reducing the chance that a debugging convenience turns into a data-handling mistake.

### Channel A: scientific telemetry

- **Goal**: statistical analysis of network density and behavioral structure
- **Storage**: names-only local JSONL surfaces under `logs/data/calamum/`
- **Constraint**: zero semantic leakage; no raw strings; strict schema discipline

## 5.1 Packet contract (current code-verified)

The current implementation does **not** expose one universal telemetry blob. It defines a small family of names-only packet shapes that share invariants but differ by responsibility.

### Contract-wide invariants

All public-facing packet families described here are governed by the following rules:

- no raw content/body/message fields are part of the allowed telemetry contract,
- names-only records are machine-parseable JSON objects,
- observer runtime and gate-clearing evidence surfaces are expected to remain fail-closed and append-only,
- observer-scoped collection/gate/evidence outputs are expected to support provenance, methodology, and process traceability,
- gate/evidence outputs must carry run-level linkage fields:
    - `run_id`
    - `posture_trigger_id`
    - `posture_trigger`
    - `security_report_ref`

### Packet family A — obfuscated feed/content sample row

Source surfaces:

- `obfuscator_lib.py::Obfuscator.obfuscate_sample(...)`
- `calamum_sampler.py`
- `calamum_observer_agent.py`

Nominal fields:

- `timestamp`
- `type`
- `author_hash`
- `content_length`
- `has_code_block`
- `tags_count`
- `mentions_count`
- derived scalar features used by current analysis surfaces:
    - `f_complexity`
    - `f_code_density`
    - `f_toxicity`
    - `f_timestamp_epoch`

Representative row:

```json
{
    "timestamp": "2026-03-24T12:00:00Z",
    "type": "post",
    "author_hash": "9d0c54f1c2a1e8ab",
    "content_length": 142,
    "has_code_block": true,
    "tags_count": 2,
    "mentions_count": 1
}
```

### Packet family B — obfuscated inbound notification row

Source surfaces:

- `obfuscator_lib.py::Obfuscator.obfuscate_notification(...)`
- `calamum_sampler.py` (canary path)
- `calamum_observer_agent.py` (canary path)

Nominal fields:

- `timestamp`
- `event_type`
- `sender_hash`
- included for message-bearing events only:
    - `content_length`
    - `has_link`

Representative row:

```json
{
    "timestamp": "2026-03-24T12:00:00Z",
    "event_type": "dm",
    "sender_hash": "ad28e10c5fd98a13",
    "content_length": 87,
    "has_link": true
}
```

Passive events such as follows do **not** synthesize absent content metrics.

### Packet family C — observer-agent runtime envelope

Source surface:

- `calamum_observer_agent.py::append_record(...)`

This family wraps the obfuscated sample/notification payload in a signed runtime envelope.

Nominal additional fields:

- `signature`
- `node_id`
- `mode`
- `kind`
- `ts`
- `run_id`
- `posture_trigger_id`
- `posture_trigger`
- `security_report_ref`

Representative row:

```json
{
    "timestamp": "2026-03-24T12:00:00Z",
    "type": "post",
    "author_hash": "9d0c54f1c2a1e8ab",
    "content_length": 142,
    "has_code_block": true,
    "tags_count": 2,
    "mentions_count": 1,
    "signature": "<hmac-sha256>",
    "node_id": "calamum-node-01",
    "mode": "WATCH",
    "kind": "obfuscated_content",
    "ts": "2026-03-24T12:00:00Z",
    "run_id": "observer-agent-20260324T120000Z",
    "posture_trigger_id": "pt-watch-20260324T120000Z",
    "posture_trigger": "isolation",
    "security_report_ref": ""
}
```

### Packet family D — baseline/resource telemetry sample

Source surface:

- `observerctl.py::_baseline_collect(...)`

Nominal fields:

- `timestamp_utc`
- `cpu_pct_now`
- `ram_pct_now`
- `stream_type`
- `sampling_profile_id`
- `mode_at_capture`
- `source_axis`
- `baseline_window_id`
- `sample_index`
- `runtime_cli_surface`
- `record_class`
- run-linkage fields

Representative row:

```json
{
    "timestamp_utc": "2026-03-24T12:00:00Z",
    "cpu_pct_now": 12.5,
    "ram_pct_now": 48.1,
    "stream_type": "resource_baseline",
    "sampling_profile_id": "resource_baseline_v1",
    "mode_at_capture": "live",
    "source_axis": "real",
    "baseline_window_id": "frame8-proof-window",
    "sample_index": 3,
    "runtime_cli_surface": "observerctl",
    "record_class": "resource_telemetry",
    "run_id": "observerctl-baseline",
    "posture_trigger_id": "pt-live-20260324T120000Z",
    "posture_trigger": "lockdown",
    "security_report_ref": "local_untracked/.../security_report.md"
}
```

### Packet family E — retained resource index row

Source surface:

- `observerctl.py::_baseline_collect(...)`

Nominal fields:

- `timestamp_utc`
- `stream_type`
- `window_id`
- `segment_path`
- `segment_records`
- `sampling_profile_id`
- `mode_at_capture`
- `source_axis`
- `run_id`
- `baseline_window_id` for baseline rows

This is the retained readback/index surface used by replay and readiness gates. The metadata parity here is part of the current contract, not decorative bookkeeping.

### Packet family F — baseline/readiness evidence packet

Source surfaces:

- `observerctl.py::_baseline_analyze(...)`
- `observerctl.py::_baseline_monitor_once(...)`
- `observerctl ops evidence pack`

These packets are expected to satisfy the project’s publication-grade evidence model with explicit:

- provenance,
- methodology, and
- process traceability.

Representative analysis packet fields include:

- `decision`
- `action`
- `sample_counts`
- `minimum_requirements`
- `baseline_ready`
- `baseline_window_id`
- `baseline_window_segment_count`
- `baseline_window_segment_resolution`
- `reason_codes`
- `provenance`
- `methodology`
- `process`
- run-linkage fields

Verification requirement: files must remain machine-parsable JSON Lines, and schema drift is treated as a validator failure.

### Channel B: runtime diagnostics

- **Goal**: debugging agent liveness, connection state, and crash behavior
- **Storage**: Docker `stdout`/`stderr` or equivalent ephemeral runtime streams
- **Typical content**:
    - application state transitions such as startup or record-count messages
    - Python tracebacks on failure
- **Privacy discipline**: credentials are redacted in memory before printing

### Channel C: safety governance

- **Goal**: safety enforcement and fail-closed auditing
- **Storage**: host-side or operator-local process logs
- **Mechanism**: the watchdog fail-signature runtime (`sentinel.py`) monitors runtime output for forbidden failure signatures and can force fail-closed termination

Current hard-stop examples include:

- `Traceback` → immediate kill
- `Permission denied` → immediate kill
- `Leaking` → immediate kill

The methodological point is straightforward: safety enforcement is not left to operator memory. The system is designed to trip loudly and stop when a core assumption is violated.

## 6. Operational reproducibility

Reproducing the experiment should not require access to the live target.

Typical workflow:

1. **Build / run**: `deployment/secure_run.ps1` or the deployment assets under `src/deployment/` start the hardened observer runtime.
2. **Select mode**: simulation and source or mode settings determine the telemetry profile under test.
3. **Validate**: tests such as `src/tests/test_container_constraints.py` verify storage and runtime guardrails.

## 7. Defense in depth

| Layer | Component | Defense Mechanism | Failure Mode |
|-------|-----------|-------------------|--------------|
| **Inner** | `obfuscator_lib.py` | Hashing, stripping, and structured reduction of content before persistence | Logic bug / import error |
| **Middle** | **Docker Runtime** | Read-only root filesystem, dropped capabilities, user namespace isolation | CVE / breakout |
| **Outer** | `sentinel.py` watchdog runtime | Fail-signature monitoring with termination semantics | **Fail-closed termination** |

This stack is intentionally more disciplined than a minimal research prototype. Secure handling is treated as a condition for trustworthy methodology, not as a separate concern to revisit later.

---

## 8. Live collection methodology

When the project transitions from simulation to live collection, it must preserve the same safety contract:

- **GET-only** network behavior
- **Names-only** persistence
- **Credentials via environment variables only**

### 8.1 Source selection

The local observer agent supports two data sources:

- `CALAMUM_MOLTBOOK_SOURCE=sim` — deterministic synthetic generator
- `CALAMUM_MOLTBOOK_SOURCE=live` — Moltbook API client, requiring `MOLTBOOK_API_KEY`

### 8.2 Canonical output streams

The project currently exposes three relevant output families.

1. **Sampler (`calamum_sampler.py`)**
    - Obfuscated feed/content samples: `logs/data/calamum/moltbook_samples_obfuscated.jsonl`
    - Inbound canary metrics: `logs/data/calamum/moltbook_canary_metrics.jsonl`

2. **Local observer agent (`calamum_observer_agent.py`)**
    - Canonical observer-runtime stream: `logs/data/calamum/observer_derived/<sim|real>/<watch|canary|live|honeypot>/moltbook_metrics.jsonl`

3. **Baseline and readiness surfaces (`observerctl.py`)**
    - Resource segments and retained index rows: `logs/data/calamum/observer_derived/<sim|real>/<mode>/resource/`
    - Publish-grade evidence and analysis packets: `logs/data/calamum/observer_derived/<sim|real>/<mode>/evidence/`

Canonical stream roles:

- sampler outputs remain available for sampling and analysis workflows,
- the `observer_derived/` family is the active canonical runtime/evidence surface for current observer-agent and `observerctl` behavior,
- both families are part of the public methodology contract and are described here by current role and current path.

### 8.3 Rate limiting and empty-backoff behavior

To avoid hammering a dead endpoint or a network-restricted environment, live collection supports:

- `CALAMUM_LIVE_BATCH_LIMIT` — cap feed fetch size (default `50`, clamped)
- `CALAMUM_LIVE_EMPTY_BACKOFF_SEC` — sleep/backoff interval when a live fetch yields no items (default `10`, clamped)

### 8.4 Failure posture

If `CALAMUM_MOLTBOOK_SOURCE=live` is selected but `MOLTBOOK_API_KEY` is absent, the observer must deny live ingest without prompting for secrets or writing unsafe partial artifacts.

For retained observer-derived artifacts, `live` input normalizes onto the `real` source axis. The canonical runtime path is therefore `observer_derived/<sim|real>/...`, not a separate `moltbook_live_metrics.jsonl` surface.

---
