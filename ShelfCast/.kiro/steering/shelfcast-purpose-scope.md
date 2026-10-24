# ShelfCast — Purpose and Scope

## Purpose

ShelfCast will eventually estimate coastal ocean temperature at different
depths and suggest where a new measurement would be most useful. The project
is being built in stages.

## Current stage: Stage 1 — data foundation ONLY

Stage 1 is limited to the data pipeline, its three output artifacts, the
supporting documentation, and focused tests. Stage 1 explicitly does **not**
include:

- any predictive or interpolation model
- any map or spatial visualization
- any dashboard or UI
- any deployment or hosting

Do not add those capabilities while working within Stage 1 scope.

## Data integrity rule (must hold across all stages)

The released eMOLT starter ZIP (`Data/raw/emolt.zip`) omits the `tow_id` and
`segment_type` columns that the full eMOLT source provides. Groups produced by
Stage 1 are therefore **provisional candidate profiles** inferred from recorded
position and time proximity.

- Never present these groups as verified fishing tows or casts.
- Use the wording "candidate profile" in outputs and docs, never "tow" or "cast".
- Output artifacts must not contain any tow, cast, or segment-type label.

## Study region and grouping rules (Stage 1)

- Study region: latitude 41.5-42.5 N, longitude -70.5 to -69.5.
- Group by identical recorded (latitude, longitude) and consecutive time gaps
  (default 5 minutes).
- Retain groups with at least 10 readings and at least 10 m of depth range.
- No group may span more than one hour; a reading that would exceed one hour
  starts a new group and the earlier portion is retained.
