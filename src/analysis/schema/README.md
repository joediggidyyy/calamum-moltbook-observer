# Schema Contract (Blind ML) - v1

This schema is a **privacy gate** for analysis tooling.

## Core rule

Records must not include raw semantic payload fields (e.g., `content`, `message`, `text`, `body`).

## Supported record types

The Calamum observer produces a union of two primary record shapes:

1) **Obfuscated content samples** (feed):
- `type` in `{post, reply, repost, unknown}`
- `author_hash` (sha256 truncated)
- `content_length`, `has_code_block`, `tags_count`, `mentions_count`
- optional Stage-4 scalar features: `f_complexity`, `f_code_density`, `f_toxicity`, `f_timestamp_epoch`

2) **Obfuscated inbound events** (canary):
- `event_type` in `{dm, mention, follow, unknown}`
- `sender_hash`
- optional content metrics for message-bearing events only: `content_length`, `has_link`
- optional Stage-4 scalar features

The daemon-style agent may additionally add an envelope:
- `node_id`, `mode`, `kind`, `ts`

## Signatures

If `signature` is present, analysis tooling may verify it using `CALAMUM_DATA_SIGNING_KEY`.

## JSON schema file

`obfuscated_record_schema_v1.json` is a **documentation+lint anchor**. The analysis scripts implement
validation without external JSON-schema dependencies.
