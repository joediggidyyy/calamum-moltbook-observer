# Features (Blind ML) - v1

All features must be derived from **structural metadata** only.

## Record-level scalar features

These are expected to exist when telemetry was produced via the sampler or agent:

- `content_length` (int)
- `has_code_block` (bool)
- `tags_count` (int)
- `mentions_count` (int)
- `has_link` (bool; notifications only)
- `f_complexity` (float)
- `f_code_density` (float)
- `f_toxicity` (int; regex flags)
- `f_timestamp_epoch` (float; timestamp parsed to epoch)

## Notes

- This document is a contract for analysis outputs; it is not a promise that every field is present for every record.
- Missing values are filled with 0/false for the baseline dataset builder.
