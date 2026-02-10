# Labels (Synthetic Only)

This project uses a **Threat Vector** taxonomy referenced in `DATA_METHODOLOGY.md`.

## `tv_id`

When (and only when) building **synthetic/dreaming** datasets, records may include:

- `tv_id` in `{ "TV-0", "TV-1", "TV-2", "TV-3" }`

Suggested supervised target mapping:

- $y = 1$ iff `tv_id == "TV-3"`

## Important

- Live/canary datasets must not be auto-labeled without an explicit, reviewed labeling policy.
