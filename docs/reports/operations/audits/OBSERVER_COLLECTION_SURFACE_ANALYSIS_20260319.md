# Observer Collection Surface Analysis — 2026-03-19

Author: ORACL-Prime  
Requested by: joediggidyyy  
Scope: actual observer-collected data, retained fields, field justifications, and collection gaps  
Status: analysis artifact / on-disk report

---

## 1. Purpose

This report answers the specific question: **what data is the observer actually collecting**?

It intentionally distinguishes:

- actual collection records produced by the observer runtime
- one-shot sampler outputs
- planning / protocol / reporting surfaces such as `baseline-overnight-plan`
- operational heartbeat and governance linkage metadata

This report is written to disk to preserve full detail without compressing or diluting the findings for chat transfer.

## 1.1 2026-03-19 operator decision note

Decision agreed by joediggidyyy and ORACL-Prime:

- Use the currently collected observer data for a **preliminary baseline** now.
- Treat that preliminary baseline as limited to the fields actually present in the current canary/runtime corpus.
- Do **not** treat the current corpus as the final canonical canary baseline for the research lane.
- A fresh canary collection run is still required after development is complete and the intended collection surface is stabilized.
- That re-run should happen soon after development completion, but it is intentionally deferred until the collector/runtime contract is no longer moving.

Interpretation:

- current data remains analytically useful and should not be discarded
- missing or inconsistent feature layers should not be retroactively assumed to exist
- final baseline promotion should wait for stabilized collection semantics

---

## 2. Evidence base inspected

### Code surfaces

- `projects/calamum-moltbook-observer/src/calamum_sampler.py`
- `projects/calamum-moltbook-observer/src/calamum_observer_agent.py`
- `projects/calamum-moltbook-observer/src/obfuscator_lib.py`
- `projects/calamum-moltbook-observer/src/stage4_features.py`
- `projects/calamum-moltbook-observer/src/moltbook_client.py`
- `projects/calamum-moltbook-observer/src/analysis/schema/README.md`

### Observed output surfaces

- `projects/calamum-moltbook-observer/logs/data/calamum/moltbook_canary_metrics.jsonl`
- `projects/calamum-moltbook-observer/logs/data/calamum/moltbook_samples_obfuscated.jsonl`
- `projects/calamum-moltbook-observer/local_untracked/audit_log/ops_parameters_report.jsonl`

### Important control finding

`projects/calamum-moltbook-observer/src/observerctl.py` and related baseline packets are **not** the primary observer collection stream. They are control / assessment / wrapper surfaces around collection state.

---

## 3. Actual collection pipeline

The observed pipeline is:

1. Raw source acquisition
   - synthetic sources from `calamum_sampler.py`
   - live read-only API fetches from `moltbook_client.py`

2. Privacy gate / transformation
   - `obfuscator_lib.py`
   - strips payload text and identifiers, retains structural fields only
   - signs emitted records cryptographically

3. Runtime emission
   - `calamum_observer_agent.py`
   - writes append-only JSONL to `observer_derived/<source>/<mode>/moltbook_metrics.jsonl`

4. Separate one-shot sampler emission
   - `calamum_sampler.py` `main()`
   - writes to legacy-style outputs like `moltbook_samples_obfuscated.jsonl` and `moltbook_canary_metrics.jsonl`

5. Separate operational heartbeat
   - `calamum_observer_agent.py`
   - writes liveness records to `logs/health/calamum_observer.heartbeat.jsonl`

---

## 4. Raw source shapes before obfuscation

### 4.1 Synthetic feed samples (`simulate_moltbook_feed`)

Raw fields produced:

- `timestamp`
- `author`
- `type`
- `content`
- `tags`
- `mentions`

### 4.2 Synthetic notifications (`simulate_moltbook_notifications`)

Raw fields produced:

- `timestamp`
- `sender`
- `event_type`
- optional `content`

### 4.3 Live API feed (`MoltbookAPIClient.fetch_feed`)

The client yields raw items returned from `GET public/feed`.

Exact live payload schema is not defined in code; the observer assumes it can at least read fields compatible with:

- `timestamp`
- `author`
- `type`
- `content`
- optional `tags`
- optional `mentions`

### 4.4 Live notifications (`MoltbookAPIClient.fetch_notifications`)

The client yields raw items returned from `GET notifications`.

The observer assumes fields compatible with:

- `timestamp`
- `sender`
- `event_type`
- optional `content`

---

## 5. Privacy gate: what is retained after obfuscation

### 5.1 Content / feed records (`Obfuscator.obfuscate_sample`)

Retained fields:

- `timestamp`
- `type`
- `content_length`
- `has_code_block`
- `author_hash`
- `tags_count`
- `mentions_count`

Dropped from retained record:

- raw `content`
- raw `author`
- literal tag values
- literal mention targets

### 5.2 Canary / inbound records (`Obfuscator.obfuscate_notification`)

Retained fields:

- `timestamp`
- `event_type`
- `sender_hash`

Conditionally retained for message-bearing events:

- `content_length`
- `has_link`

Dropped from retained record:

- raw sender
- raw content
- literal URLs

### 5.3 Signature layer (`Obfuscator.sign_record`)

Appended field:

- `signature`

Purpose:

- authenticity check
- downstream verification that a record was produced by a trusted collector with the configured signing key

---

## 6. Additional scalar features currently available

`stage4_features.py` defines the following blind scalar features:

- `f_complexity`
- `f_code_density`
- `f_toxicity`
- `f_timestamp_epoch`

These are derived from raw content and timestamp, without returning raw text.

### Important implementation finding

These Stage 4 features are added in:

- `calamum_sampler.py` sampler mode
- `calamum_sampler.py` canary mode

These Stage 4 features are **not** added by:

- `calamum_observer_agent.py` runtime daemon emission path

That means the long-running observer runtime is currently collecting **less** than the one-shot sampler path.

---

## 7. Actual emitted record families

### 7.1 One-shot sampler feed file

Observed path:

- `projects/calamum-moltbook-observer/logs/data/calamum/moltbook_samples_obfuscated.jsonl`

Observed fields include:

- `timestamp`
- `type`
- `content_length`
- `has_code_block`
- `author_hash`
- `tags_count`
- `mentions_count`
- `f_complexity`
- `f_code_density`
- `f_toxicity`
- `f_timestamp_epoch`

This is a richer blind feature record than the daemon runtime currently emits.

### 7.2 One-shot sampler canary file

Observed legacy-style path:

- `projects/calamum-moltbook-observer/logs/data/calamum/moltbook_canary_metrics.jsonl`

Observed fields include:

- `timestamp`
- `event_type`
- `sender_hash`
- optional `content_length`
- optional `has_link`
- `type` (copied from `event_type` by daemon path when present in runtime stream)
- `signature`
- `node_id`
- `mode`
- `kind`
- `ts`

### 7.3 Runtime observer-derived file

Canonical runtime path template:

- `observer_derived/<source>/<mode>/moltbook_metrics.jsonl`

Observed active lanes from audit counters include:

- `observer_derived/sim/watch/moltbook_metrics.jsonl`
- `observer_derived/sim/canary/moltbook_metrics.jsonl`
- `observer_derived/sim/live/moltbook_metrics.jsonl`
- `observer_derived/real/canary/moltbook_metrics.jsonl`

### 7.4 Runtime daemon envelope fields

The daemon appends:

- `node_id`
- `mode`
- `kind`
- `ts`
- `run_id`
- `posture_trigger_id`
- `posture_trigger`
- `security_report_ref`

Additionally for canary mode, the daemon ensures:

- `type` is copied from `event_type`

---

## 8. Field-by-field justification

### 8.1 Time and sequencing

#### `timestamp`

We need this because:

- temporal ordering is essential for anomaly and campaign analysis
- burstiness, cadence, and dwell all derive from event time
- time alignment across collection lanes depends on preserving the original event timestamp

#### `ts`

We need this because:

- it captures collector emission time separately from source event time
- it helps distinguish source latency from collector/runtime latency
- it supports troubleshooting delayed writes and transport lag

#### `f_timestamp_epoch` (when present)

We need this because:

- it makes downstream temporal feature extraction cheaper and more consistent
- it supports numeric modeling without reparsing timestamp strings
- it preserves blind-safe timing value without reintroducing content

### 8.2 Event class / structural type

#### `type`

We need this because:

- feed-side behavior differs materially between `post`, `reply`, and `repost`
- class-conditioned baselines are stronger than pooled baselines
- content interaction posture is visible even when payload text is removed

#### `event_type`

We need this because:

- `dm`, `mention`, and `follow` are behaviorally distinct inbound surfaces
- the canary hypothesis depends on tracking what kind of inbound action occurred
- different threat families may dominate different inbound event classes

#### `kind`

We need this because:

- it distinguishes content records from inbound-event records
- it prevents downstream tooling from silently mixing incompatible shapes
- it supports safer dataset unions and validators

### 8.3 Actor continuity without identity disclosure

#### `author_hash`

We need this because:

- repeated behavior from the same blinded actor is analytically useful
- persistent actor continuity matters more than literal identity in this design
- it enables recurrence, concentration, and clustering analysis without PII leakage

#### `sender_hash`

We need this because:

- canary threat detection depends heavily on repeated inbound actor behavior
- stable blinded identifiers allow pattern discovery over time
- it preserves continuity while preventing direct identity retention

### 8.4 Payload-shape proxies

#### `content_length`

We need this because:

- message size is a useful behavioral signal without retaining payload text
- many campaigns show strong regularity in message-length patterns
- it provides a safe scalar proxy for communication style

#### `has_code_block`

We need this because:

- code-bearing content is structurally different from ordinary social text
- instruction attacks and exploit-like probes often correlate with code formatting
- it preserves a useful structural indicator without content exposure

#### `has_link`

We need this because:

- links are a major threat-relevant structural signal
- phishing/scanning behaviors often differ sharply from benign traffic on link presence
- it captures a strong indicator while avoiding URL retention

### 8.5 Social-shape proxies

#### `tags_count`

We need this because:

- tagging intensity is a safe interaction-structure signal
- spam, amplification, and reach-seeking behavior often show up in tag counts
- it preserves social shape while dropping literal tag values

#### `mentions_count`

We need this because:

- targeting intensity is analytically useful
- many adversarial behaviors are interaction-targeting problems rather than pure content problems
- it retains recipient-density information without exposing recipients

### 8.6 Blind scalar features

#### `f_complexity`

We need this because:

- complexity can help separate templated, repetitive, or machine-generated patterns from richer organic variance
- it supports blind ML without retaining text
- it compresses content structure into a safe scalar form

#### `f_code_density`

We need this because:

- code-heavy content is operationally distinct and often threat-relevant
- it supports separating technical payloads from ordinary narrative traffic
- it is a safer continuous feature than retaining snippets or tokens

#### `f_toxicity`

We need this because:

- the project needs a threat-focused scalar indicator for obviously suspicious phrasing families
- it preserves a coarse alerting dimension without storing the underlying phrases
- it provides a low-cost, blind-safe signal for downstream prioritization

### 8.7 Runtime and provenance envelope

#### `signature`

We need this because:

- collection authenticity matters for scholarly and operational trust
- unsigned records are harder to distinguish from tampering or rogue emitters
- it supports verifier tooling without changing the evidence payload

#### `node_id`

We need this because:

- multi-node collection requires source-attribution of the collector, not the observed actor
- it supports cross-node reconciliation and auditability
- it helps isolate collector-side faults and drift

#### `mode`

We need this because:

- watch / canary / live / honeypot posture is analytically meaningful context
- the same event class can mean different things in different operational postures
- downstream audits need to know which collection lane produced the record

---

## 9. Critical discrepancy: sampler vs daemon runtime

### Finding

The repository currently has two materially different collection shapes:

1. **one-shot sampler outputs** include Stage 4 scalar features
2. **daemon runtime outputs** do not include Stage 4 scalar features

### Why this matters

This is not a cosmetic mismatch. It means the long-running observer runtime is collecting a thinner blind feature surface than the research design implies.

### Research consequence

If the project hypothesis is that threat-relevant patterns can be discovered from obfuscated structural / temporal / behavioral signals, then the runtime collector should ideally gather the same blind scalar layer that the one-shot sampler already knows how to emit.

At present, the runtime collector preserves:

- structural metadata
- actor continuity
- timing
- signatures / envelope

But it omits a meaningful slice of the blind derived feature layer during continuous operation.

---

## 10. Collection gaps / holes

### 10.1 Missing Stage 4 feature collection in the daemon

Severity: High

Gap:

- `calamum_observer_agent.py` does not call `extract_stage4_features`
- runtime `observer_derived/.../moltbook_metrics.jsonl` is therefore thinner than sampler outputs

Impact:

- weaker blind feature corpus for long-duration analysis
- mismatch between intended schema and observed runtime reality
- reduced comparability between one-shot datasets and continuous datasets

### 10.2 No explicit interarrival or burst features retained

Severity: High

Currently retained:

- source timestamp
- emission timestamp

Not explicitly retained:

- delta since previous event
- delta since previous event by same actor
- burst counter over fixed windows
- rolling rate bucket

Impact:

- temporal behavior must be reconstructed later rather than preserved as safe derived features
- burst-pattern discovery is weaker and more expensive downstream
- if downstream compaction loses sequence fidelity, timing signal may be degraded

### 10.3 No interaction graph or thread topology

Severity: High

Not retained:

- thread / conversation hash
- reply-parent hash
- target hash bucket
- per-record recipient topology beyond raw counts

Impact:

- the corpus captures event structure better than relationship structure
- coordination and targeting patterns remain under-observed
- adversarial graph behavior can be missed even with strong single-record features

### 10.4 Link structure is too coarse

Severity: Medium-High

Currently retained:

- `has_link`

Not retained:

- link count
n- domain hash
- domain reuse bucket
- internal vs external classification
- scheme bucket

Impact:

- campaign-level link reuse is largely invisible
- structural URL behavior is compressed into a single boolean
- the collection surface gives up safe, high-value signal

### 10.5 No attachment / artifact metadata

Severity: Medium

Not retained:

- attachment count
- media type bucket
- attachment extension bucket
- size bucket for attached artifacts

Impact:

- non-text threat vectors are weakly represented
- the collection surface is text-event centric
- some behavioral channels may be systematically under-sampled

### 10.6 No quality or partial-record flags

Severity: Medium

Not retained:

- partial fetch indicator
- parse-quality flag
- schema version on record
- feature version on record
- source retrieval degradation flag

Impact:

- degraded records are hard to separate from genuine sparse observations
- scholarly reproducibility suffers
- downstream error analysis is harder than necessary

### 10.7 No blinded content-pattern fingerprint beyond coarse scalars

Severity: Medium

Not retained:

- normalized skeleton hash
- repeated-shape fingerprint
- locality-sensitive content-pattern signature

Impact:

- repeated templated campaigns may evade grouping if they vary exact wording
- the collection surface sees rough size and complexity but not shape reuse
- downstream pattern mining has less leverage than it could

### 10.8 Governance / provenance fields mixed into primary observation records

Severity: Medium

Currently mixed into primary record body:

- `run_id`
- `posture_trigger_id`
- `posture_trigger`
- `security_report_ref`

Impact:

- the research corpus includes operator / governance context in the same object as observed behavior
- downstream models could overfit to posture-state context rather than observed event structure
- these fields are operationally useful, but they are not first-order observational evidence

### 10.9 Live feed schema is weakly formalized in code

Severity: Medium

Gap:

- live client simply yields `data.get("items", [])`
- expected raw shape is inferred rather than contract-enforced before obfuscation

Impact:

- upstream API changes could silently thin or skew retained records
- field loss may not be obvious until downstream analysis fails or drifts
- live-collection reproducibility is weaker than ideal

---

## 11. What the observer is already doing well

The current design has strong foundations:

- raw payload text is not retained
- raw actor identifiers are not retained
- stable blinded continuity is preserved with hashes
- timing is preserved
- structural event class is preserved
- content and link presence are reduced to safe scalars
- records can be signed and verified
- collection remains append-only JSONL
- canary collection is inbound-focused rather than broad-spectrum identity analysis

This means the primary weakness is not conceptual failure. The weakness is **incomplete blind feature capture and underdeveloped relational / temporal richness**.

---

## 12. Bottom line

The observer is currently collecting a meaningful blind-safe structural corpus, but not yet the fullest version of the research corpus implied by the threat-only hypothesis.

### What it definitely collects today

- time of event
- class of event
- blinded actor continuity
- message-size proxies
- code / link presence proxies
- tag / mention count proxies
- collector authenticity and runtime envelope fields

### What it only collects sometimes

- Stage 4 scalar features (`f_complexity`, `f_code_density`, `f_toxicity`, `f_timestamp_epoch`)
  - present in one-shot sampler outputs
  - absent from the long-running daemon path

### What it does not yet collect well enough

- explicit temporal delta features
- graph / thread / relationship structure
- richer blind URL structure
- attachment/media structure
- per-record quality/version metadata
- safe repeated-pattern fingerprints

### Main conclusion

The current observer collection surface is **research-usable but incomplete**. It preserves structural evidence well enough to support early threat-pattern work, but the continuous runtime collector is still thinner than the project’s intended blind-ML collection contract.

---

## 13. Suggested next lane (not executed here)

A clean next implementation lane would separate the collection surface into three strata:

1. **Primary observation record**
   - only observed event structure and blinded actor continuity

2. **Blind derived feature layer**
   - Stage 4 scalars, temporal deltas, safe graph/shape enrichments

3. **Governance / provenance linkage layer**
   - `run_id`, posture trigger linkage, security report refs, control-plane context

That separation would preserve scholarly cleanliness while keeping operational traceability intact.
