# Schema Contract (Blind ML) - v1

This schema is a **privacy gate** for analysis tooling.

## Core rule

Records must not include raw semantic payload fields (e.g., `content`, `message`, `text`, `body`).

## Supported record types

The Calamum observer produces a union of two primary record shapes:

1) **Obfuscated content samples** (feed):
- `type` in `{post, reply, repost, unknown}`
- packet identity lift: `packet_family`, `packet_version`, `venue_id`, `entity_kind`
- optional identity helper: `source_id_hash`
- `author_hash` (sha256 truncated)
- `content_length`, `has_code_block`, `tags_count`, `mentions_count`
- additive names-only structure/risk fields:
	- `content_length_words`, `code_block_count`, `has_link`, `link_count`
	- `line_count`, `question_count`, `exclamation_count`
	- `contains_ignore_previous`, `contains_system_prompt_reference`
	- `contains_developer_message_reference`, `contains_env_var_reference`
	- `prompt_injection_score`, `matched_pattern_labels`, `matched_pattern_count`
- optional Stage-4 scalar features: `f_complexity`, `f_code_density`, `f_toxicity`, `f_timestamp_epoch`

2) **Obfuscated inbound events** (canary):
- `event_type` in `{dm, mention, follow, unknown}`
- packet identity lift: `packet_family`, `packet_version`, `venue_id`, `entity_kind`
- optional identity helper: `source_id_hash`
- `sender_hash`
- optional content metrics for message-bearing events only: `content_length`, `has_link`
- optional additive names-only structure/risk fields for message-bearing events:
	- `content_length_words`, `link_count`, `line_count`
	- `question_count`, `exclamation_count`
	- `contains_ignore_previous`, `contains_system_prompt_reference`
	- `contains_developer_message_reference`, `contains_env_var_reference`
	- `prompt_injection_score`, `matched_pattern_labels`, `matched_pattern_count`
- optional Stage-4 scalar features

The daemon-style agent may additionally add an envelope:
- `node_id`, `mode`, `kind`, `ts`

The canonical observer-agent runtime path now promotes the Stage-4 scalar features into the persisted row before signing the payload for content rows and message-bearing canary rows.

## Signatures

If `signature` is present, analysis tooling may verify it using `CALAMUM_DATA_SIGNING_KEY`.

## JSON schema file

`obfuscated_record_schema_v1.json` is a **documentation+lint anchor**. The analysis scripts implement
validation without external JSON-schema dependencies.
