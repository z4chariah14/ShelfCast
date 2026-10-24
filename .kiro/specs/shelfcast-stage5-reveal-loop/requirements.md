# Requirements Document

## Introduction

ShelfCast Stage 5 adds a controlled "reveal loop" on top of the existing Stage 4 local Streamlit viewer. After a user selects a provisional candidate profile and sees the Stage 3 predicted temperature curve, the user may press a button to reveal that one profile's hidden historical measurements. The viewer then overlays the real readings at their actual recorded depths, fits a temporary model from the original training rows plus only that profile's revealed rows, and shows the original versus updated predicted curves for the selected site and one nearby still-hidden site.

This is a historical replay, not a live or future forecast. The chronological replay split means training candidate profiles ended (end_time) strictly before the cutoff of 2024-08-06T00:00:00Z UTC, while hidden candidate profiles started (start_time) on or after that cutoff. The selected hidden profile therefore started on or after the cutoff, while the original saved model was trained only on profiles that ended before the cutoff. The reveal is strictly scoped to the single selected profile, the temporary model is never saved to disk, and no pre-reveal code path may read hidden data. Stage 5 reuses the existing `predict_temperatures` function and the saved Stage 3 artifacts unchanged. It does not expand the study region, rewrite Stages 1-3, or add uncertainty bands, next-site recommendations, or deployment.

## Glossary

- **Candidate profile**: A provisional candidate profile inferred from recorded position and time proximity, identified by `profile_id`. The starter eMOLT data omits the `tow_id` and `segment_type` columns, so these groups are not verified tows or casts. The words "tow" and "cast" may appear only inside a truthful limitation note explaining this; a candidate profile is never labeled or presented as a verified tow or cast.
- **Original saved model**: The Stage 3 model loaded from `Results/model.joblib` with metadata from `Results/model_metadata.json`. Read-only in Stage 5.
- **Reveal function**: A dedicated helper, invoked only after the reveal button press, that reads the selected profile's rows from `Data/splits/heldout_points.csv` filtered to the selected `profile_id`.
- **Temporary model**: An in-memory model fit from the original training rows (`Data/splits/train_points.csv`) plus only the selected profile's revealed rows. Never written to disk.
- **Nearby still-hidden candidate site**: A candidate profile from `Data/splits/candidate_sites.csv`, other than the selected one, that is at least 1 kilometre from the selected site (great-circle distance in kilometres) and whose recorded `start_time` is strictly after the revealed profile's final recorded measurement time (the maximum `time` among the revealed rows); among eligible candidates the nearest by kilometre distance is chosen, breaking ties by lowest profile_id. Used only for prediction comparison and never read from `heldout_points.csv`.
- **Viewer**: The local Streamlit application (`app.py`) and its helper module (`shelfcast/viewer.py`).
- **Reveal_Function**: The Stage 5 reveal helper described above (EARS system name).
- **Viewer_App**: The Stage 5 Streamlit viewer behavior (EARS system name).

## Requirements

### Requirement 1: Pre-reveal prediction display

**User Story:** As a viewer user, I want to see the existing Stage 3 prediction before any reveal, so that I have a baseline to compare against.

#### Acceptance Criteria

1. WHEN a user selects a candidate profile, THE Viewer_App SHALL display the predicted temperature curve computed by the original saved model at the standard requested depths of 5, 10, 20, 30, and 50 meters, plotting exactly one predicted value per depth.
2. THE Viewer_App SHALL compute pre-reveal predictions using the original saved model loaded from `Results/model.joblib` without retraining or modifying it.
3. WHILE no reveal action has occurred for the selected candidate profile, THE Viewer_App SHALL display only predicted temperature values and SHALL NOT display any actual measured temperature or depth value.
4. IF the original saved model cannot be loaded from `Results/model.joblib`, THEN THE Viewer_App SHALL display an error message indicating the model is unavailable and SHALL NOT display any predicted or measured value.
5. WHEN a user selects a candidate profile, THE Viewer_App SHALL compute predictions using that profile's recorded coordinates and recorded UTC start time.

### Requirement 2: Reveal trigger

**User Story:** As a viewer user, I want a reveal button, so that hidden measurements appear only when I explicitly request them.

#### Acceptance Criteria

1. WHEN a candidate profile is selected, THE Viewer_App SHALL display a "Reveal actual measurements" control in an unpressed state.
2. WHEN the user presses the control, THE Viewer_App SHALL invoke the Reveal_Function exactly once for the selected profile_id and SHALL read only the rows of `Data/splits/heldout_points.csv` whose profile_id equals the selected profile_id.
3. WHILE the control has not been pressed for the selected candidate profile, THE Viewer_App SHALL NOT invoke the Reveal_Function and SHALL NOT open `Data/splits/heldout_points.csv`.
4. WHEN the selected candidate profile changes, THE Viewer_App SHALL reset the control to the unpressed state before the next display completes.
5. IF the reveal fails, THEN THE Viewer_App SHALL display an error message indicating the reveal could not be completed and SHALL preserve the existing pre-reveal predictions without modification.

### Requirement 3: Reveal function data access

**User Story:** As a project maintainer, I want hidden data read only by the dedicated reveal function, so that hidden measurements stay protected until an explicit reveal.

#### Acceptance Criteria

1. WHEN the user has pressed the "Reveal actual measurements" control and the Reveal_Function is invoked with a selected `profile_id`, THE Reveal_Function SHALL open `Data/splits/heldout_points.csv`, read only the rows whose `profile_id` equals the selected `profile_id`, and return, use, store, or show only the `time`, `latitude`, `longitude`, `depth_m`, and `temperature_c` values for those selected rows.
2. THE Reveal_Function SHALL NOT return, store, use for fitting, or make available for display any row whose `profile_id` differs from the selected `profile_id`.
3. WHILE the "Reveal actual measurements" control has not been pressed for the selected profile, THE Reveal_Function SHALL NOT open `Data/splits/heldout_points.csv`.
4. IF the selected `profile_id` is absent from `Data/splits/heldout_points.csv`, THEN THE Reveal_Function SHALL return no result rows, SHALL return an error indication that names the missing `profile_id`, and SHALL leave any previously revealed state unchanged.
5. THE Reveal_Function SHALL be the only code path permitted to open `Data/splits/heldout_points.csv`, and SHALL open it only after the explicit "Reveal actual measurements" click.
6. THE Viewer_App startup, pre-reveal prediction, map rendering, cache, and site-selection code paths SHALL read only `Data/splits/train_points.csv` and `Data/splits/candidate_sites.csv` as observational inputs and SHALL NOT open `Data/splits/heldout_points.csv`.
7. THE Viewer_App and Reveal_Function SHALL NOT read the hidden temperature or depth summary columns of `Data/processed/profile_summary.csv`.
8. IF `Data/splits/heldout_points.csv` does not exist when a reveal is requested, THEN THE Reveal_Function SHALL raise a file-not-found error, THE Viewer_App SHALL display a descriptive message directing the user to produce the Stage 2 split (for example, run `Scripts/split_replay.py`), and THE Viewer_App SHALL preserve the pre-reveal predictions without modifying the saved model.

### Requirement 4: Overlay actual measurements at recorded depths

**User Story:** As a viewer user, I want revealed readings shown at their true recorded depths, so that the display does not misrepresent where measurements were taken.

#### Acceptance Criteria

1. WHEN the Reveal_Function returns revealed rows, THE Viewer_App SHALL overlay each actual temperature_c reading at its actual recorded depth_m value without rounding, re-binning, or snapping.
2. WHEN overlaying actual measurements, THE Viewer_App SHALL render them with at least one visual attribute that differs from the predicted curves.
3. THE Viewer_App SHALL NOT reposition any actual measured temperature onto the standard requested depths of 5, 10, 20, 30, and 50 meters.
4. IF the Reveal_Function returns zero rows for the selected profile, THEN THE Viewer_App SHALL display a message indicating no actual measurements are available for the selected profile and SHALL NOT overlay any actual measurement.

### Requirement 5: Temporary model update

**User Story:** As a viewer user, I want a temporary updated model after reveal, so that I can see how the one revealed profile changes the prediction.

#### Acceptance Criteria

1. WHEN revealed rows are available for the selected profile, THE Viewer_App SHALL fit a temporary model from the original training rows of `Data/splits/train_points.csv` combined with only the selected profile's revealed rows, using the columns time, latitude, longitude, depth_m, and temperature_c.
2. WHEN a temporary model has been fit for the selected profile, THE Viewer_App SHALL display the original saved model predicted curve and the temporary model predicted curve together at the standard requested depths of 5, 10, 20, 30, and 50 meters for the selected profile's recorded coordinates and recorded UTC start time.
3. THE Viewer_App SHALL retain the temporary model in memory only and SHALL NOT write it to `Results/model.joblib` or any other file.
4. IF the temporary fit fails, THEN THE Viewer_App SHALL display an error message indicating the temporary model could not be fit and SHALL NOT modify or write the original saved model.

### Requirement 6: Nearby still-hidden site comparison

**User Story:** As a viewer user, I want a before/after prediction at a nearby hidden site, so that I can see the update's effect beyond the revealed profile without exposing more hidden data.

#### Acceptance Criteria

1. WHEN a temporary model has been fit, THE Viewer_App SHALL select, from `Data/splits/candidate_sites.csv` and excluding the selected profile, the candidate profile that is both at least 1 kilometre from the selected site (great-circle distance in kilometres) and has a recorded `start_time` strictly after the revealed profile's final recorded measurement time (the maximum `time` among the revealed rows), choosing the nearest such candidate by kilometre distance and breaking ties by lowest profile_id.
2. WHEN a nearby still-hidden candidate site has been selected, THE Viewer_App SHALL display the original saved model predicted curve and the temporary model predicted curve for that site at the standard requested depths of 5, 10, 20, 30, and 50 meters, using that site's recorded coordinates and recorded UTC start time.
3. WHEN a temporary model has been fit, THE Viewer_App SHALL update the nearby still-hidden candidate site's map marker so that the marker reflects the original saved model predicted temperature and then the temporary model predicted temperature at the requested prediction level of 20 meters, using a visible color or label change for that marker.
4. WHEN a temporary model has been fit, THE Viewer_App SHALL display a numeric prediction change for the nearby still-hidden candidate site at the requested prediction level of 20 meters, computed as the temporary model predicted temperature minus the original saved model predicted temperature, shown as a number.
5. THE Viewer_App SHALL compute the nearby-site map update and numeric prediction change using predictions only and SHALL NOT read any temperature_c or depth_m value for the nearby still-hidden candidate site from `Data/splits/heldout_points.csv`.
6. IF no candidate profile satisfies the eligibility rule in criterion 1, THEN THE Viewer_App SHALL display a "no eligible nearby site" message and SHALL NOT show a nearby-site comparison, map update, or numeric prediction change.

### Requirement 7: Reveal state reset

**User Story:** As a viewer user, I want reveals cleared when I change selection, so that I never see stale revealed data from a prior profile.

#### Acceptance Criteria

1. WHEN the selected candidate profile changes, THE Viewer_App SHALL discard the stored revealed values and the temporary model and SHALL return to the original saved model before the next display completes.
2. THE Viewer_App SHALL display a "Reset replay" control.
3. WHEN the user presses the "Reset replay" control, THE Viewer_App SHALL discard the stored revealed values and the temporary model, return to the original saved model, and return to the pre-reveal display before the next display completes.
4. WHILE the Streamlit application reruns, THE Viewer_App SHALL associate the stored revealed values and the temporary model with the currently selected profile_id only.
5. IF the stored revealed values do not match the currently selected profile_id, THEN THE Viewer_App SHALL discard them before any revealed value is displayed.
6. THE Viewer_App SHALL NOT reveal or display any profile other than the currently selected one across Streamlit reruns.

### Requirement 8: Scope and framing boundaries

**User Story:** As a project maintainer, I want Stage 5 framing and scope enforced, so that the viewer stays an honest historical replay within project limits.

#### Acceptance Criteria

1. WHEN the Viewer_App displays Stage 5 output, THE Viewer_App SHALL label the output as a historical replay in which the selected hidden candidate profile started (start_time) on or after the cutoff of 2024-08-06T00:00:00Z UTC while the original saved model was trained only on candidate profiles that ended (end_time) strictly before that cutoff.
2. WHEN the Viewer_App displays the standard requested depths of 5, 10, 20, 30, and 50 meters, THE Viewer_App SHALL label them as requested prediction levels and SHALL NOT present any of these depths as a claim about actual bottom depth at a site.
3. WHERE the Viewer_App displays the words "tow" or "cast", THE Viewer_App SHALL display them only inside a truthful limitation note stating that the starter eMOLT data omits the `tow_id` and `segment_type` columns so groups are provisional candidate profiles and are not verified tows or casts, and SHALL NOT label or present any candidate profile as a verified tow or cast.
4. WHILE any Stage 5 output is displayed, THE Viewer_App SHALL display the eMOLT source attribution.
5. THE Viewer_App SHALL display only sites with latitude in the inclusive range 41.5 to 42.5 degrees North and longitude in the inclusive range -70.5 to -69.5 degrees.
6. IF a site falls outside latitude 41.5 to 42.5 or longitude -70.5 to -69.5, THEN THE Viewer_App SHALL exclude that site from display.
7. THE Viewer_App SHALL NOT display uncertainty bands, confidence claims, next-site recommendations, or forecasts.
