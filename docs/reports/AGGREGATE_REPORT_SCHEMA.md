# Aggregate Report Schema

**Document ID**: `CALAMUM_AGGREGATE_REPORT_SCHEMA_20260324`
**Status**: Public aggregate reporting schema
**Owner**: ORACL-Prime
**Project**: Calamum Moltbook Observer
**Last updated**: 2026-03-24

## Purpose

This document defines the public-facing schema for aggregate reports in Calamum Moltbook Observer.

Aggregate reports differ from single-run reports. A single-run report describes one execution or one bounded evaluation event. An aggregate report synthesizes a **defined cohort of runs** into a publishable analytical statement.

The goal is professional competence and scholarly rigour: aggregate reports must be interpretable, reproducible in principle, methodologically legible, and explicit about scope and limitations.

When runtime lane evidence is part of the aggregate, it should receive top billing ahead of downstream audit-family rollups.

## When to use an aggregate report

Use an aggregate report when a public conclusion depends on patterns across multiple runs rather than on a single run artifact.

Typical cases include:

- reporting trends across repeated operational audits
- summarizing repeated runtime artifact checks over a defined interval
- synthesizing multiple repo-health or implementation-drift runs into a release-readiness view
- summarizing probe families across a bounded validation campaign

Do not use an aggregate report when a single run is the correct unit of interpretation.

## Aggregate report contract

Every public aggregate report should answer the following questions in order:

1. **Question** — what analytical question is being answered?
2. **Runtime evidence** — what current runtime lane posture or runtime snapshot anchors the report, when applicable?
3. **Corpus** — which run family or families were included?
4. **Window** — what time interval or campaign boundary defines the cohort?
5. **Selection rule** — how were included and excluded runs determined?
6. **Method** — how were the run outputs transformed into aggregate findings?
7. **Findings** — what did the synthesis show?
8. **Limitations** — what should the reader not over-interpret?
9. **Provenance** — where did the underlying evidence come from?

## Required document sections

| Section | Requirement | Purpose |
|---|---|---|
| Document metadata | Required | Gives the report a stable identity and citation surface |
| Runtime evidence aggregate | Required when runtime evidence is in scope | Anchors the report in current source or mode posture before broader rollups are interpreted |
| Research question | Required | States the analytical aim in one disciplined paragraph |
| Corpus definition | Required | Identifies the contributing run families and evidence surfaces |
| Inclusion and exclusion criteria | Required | Prevents silent cherry-picking |
| Time window or campaign boundary | Required | Defines the aggregation frame |
| Methods | Required | Explains transformation, grouping, normalization, and interpretation logic |
| Findings | Required | Presents the aggregate result clearly and proportionately |
| Quality controls | Required | States validation and data-quality safeguards |
| Limitations | Required | Makes uncertainty explicit |
| Provenance | Required | Lists the authoritative ledgers and evidence families used |
| Related surfaces | Required | Connects the report back to manuals, run ledger, and source-family docs |

## Required metadata fields

At the top of each aggregate report, include:

| Field | Meaning |
|---|---|
| `Document ID` | Stable identifier for the aggregate report |
| `Status` | Publication state such as Draft, Public aggregate report, or Superseded |
| `Owner` | Responsible author or reporting authority |
| `Project` | Project name |
| `Last updated` | Latest revision date |
| `Runtime observation point` | UTC timestamp of the live runtime snapshot when runtime evidence is included |
| `Runtime source surfaces` | Live command or surface names used for runtime-first reporting |
| `Aggregation window` | UTC range or named campaign |
| `Source families` | Run-family identifiers contributing evidence |
| `Primary question` | Short statement of the analytical question |

## Required machine-readable sidecar schema

Public aggregate reports should have a machine-readable sidecar when practical. The sidecar should preserve the analytical boundary without embedding raw runtime payloads.

Recommended fields:

| Field | Type | Meaning |
|---|---|---|
| `schema_version` | string | Sidecar schema version |
| `report_id` | string | Aggregate report document id |
| `title` | string | Public title |
| `runtime_observation_point` | string | UTC timestamp for the runtime snapshot when included |
| `runtime_sources` | array | Live runtime surfaces used for top-level runtime reporting |
| `aggregation_window` | object | Start, end, or named campaign boundary |
| `source_families` | array | Included run-family ids |
| `source_ledgers` | array | Authoritative ledger paths used for aggregation |
| `selection_rule` | string | Inclusion and exclusion rule |
| `runtime_metrics` | object | Runtime-lane and current posture metrics presented near the top of the report |
| `audit_metrics` | object | Audit/report-family aggregate metrics presented below the runtime headline |
| `method_summary` | string | Brief prose description of the aggregation logic |
| `limitations` | array | Short limitation statements |
| `generated_at_utc` | string | UTC generation timestamp |

## Recommended analytical metrics

The exact metrics depend on the contributing families, but the following patterns are appropriate:

| Family class | Suitable aggregate metrics |
|---|---|
| ops-report | status counts, cadence regularity, environment-profile consistency, density or freshness distributions |
| audit | pass or warn rates, finding counts by class, recurrence of policy issues, stability across time windows |
| probe | pass or review counts, continuity success rates, regression-detection rates, campaign completion rates |
| model-eval | threshold values, FPR summaries, score distribution summaries, comparison across bounded evaluation sets |

## Quality-control rules

Every public aggregate report should explicitly state whether the following controls were met:

1. **Stable cohort definition** — all included runs satisfy the same declared selection rule.
2. **Stable family semantics** — included run families use stable identifiers and interpretable evidence contracts.
3. **No silent gaps** — missing windows, failed runs, or omitted families are declared.
4. **No raw-secret leakage** — the aggregate surface contains only public-safe fields.
5. **Evidence traceability** — each aggregate claim can be traced back to authoritative family ledgers.

## Recommended narrative shape

A strong public aggregate report should read in this order:

1. a concise statement of the question
2. a bounded description of the corpus
3. the method and selection rule
4. the main findings in ranked order
5. the limitations and interpretive cautions
6. a provenance section suitable for scholarly review

## Template outline

A recommended aggregate report outline is:

1. Metadata block
2. Executive summary
3. Runtime evidence aggregate
4. Research question
5. Corpus and selection rule
6. Methods
7. Aggregate findings
8. Quality controls
9. Limitations
10. Provenance
11. Related surfaces

## Relationship to the public run ledger

The public run ledger defines **what kinds of runs exist** and which are aggregate-ready.

An aggregate report then defines:

- which families were used
- which specific ledger windows were considered
- which metrics were computed
- which claims are justified by the cohort

In short:

- [`PUBLIC_RUN_LEDGER.md`](PUBLIC_RUN_LEDGER.md) defines the reporting population
- aggregate reports define a bounded analytical sample from that population

## Related surfaces

- [`INDEX.md`](INDEX.md)
- [`PUBLIC_RUN_LEDGER.md`](PUBLIC_RUN_LEDGER.md)
- [`GENERATED_REPORT_SURFACES.md`](GENERATED_REPORT_SURFACES.md)
