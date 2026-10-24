# Requirements Document

## Introduction

ShelfCast Stage 4 adds a single, local, read-only Streamlit app that makes the
already-trained Stage 3 predictor explorable. It loads the saved model and
metadata, shows training and candidate locations on a map, lets the user pick a
candidate profile, and charts the Stage 3 predicted temperatures at the declared
standard depths for that site and its recorded UTC start time. It reuses the
existing `predict_temperatures` function unchanged, so the app is a viewer, not a
new model.

Stages 1 (data foundation), 2 (chronological replay split), and 3 (first
temperature predictor) are complete and unchanged. Stage 4 holds the same hard
data boundary as Stage 3: pre-reveal code reads only the training points and the
candidate-site location table as observational inputs, plus the model artifacts
written under `Results/`. It never opens `Data/splits/heldout_points.csv` or the
hidden temperature/depth summary columns of `Data/processed/profile_summary.csv`.
Stage 4 adds no model retraining, no uncertainty estimates, no next-site
recommendations, no forecasts, and no deployment or hosting.

## Glossary

- **Viewer_App**: The Stage 4 Streamlit application, launched with
  `streamlit run app.py`, run locally.
- **Prediction_Function**: The existing `shelfcast.model.predict_temperatures`,
  reused unchanged.
- **Saved_Model**: The serialized fitted model at `Results/model.joblib`.
- **Model_Metadata**: The metadata JSON at `Results/model_metadata.json`.
- **Training_Points**: `Data/splits/train_points.csv` (columns time, latitude,
  longitude, depth_m, temperature_c, profile_id).
- **Candidate_Sites**: `Data/splits/candidate_sites.csv` (columns profile_id,
  latitude, longitude, start_time).
- **Candidate_Profile**: A provisional group of readings inferred from recorded
  position and time proximity. Never a verified fishing tow or cast.
- **Standard_Depths**: The existing `DEFAULT_DEPTH_GRID` from `shelfcast.config`
  — requested prediction levels in metres, not the actual bottom depth at a site.
- **Heldout_Points**: `Data/splits/heldout_points.csv`, the hidden replay data.
- **Profile_Summary**: `Data/processed/profile_summary.csv`, which carries hidden
  temperature/depth summary values.

## Requirements

### Requirement 1: Load existing artifacts and inputs

**User Story:** As a user, I want the app to load what Stage 3 already produced,
so that I explore the trained model without re-running anything.

#### Acceptance Criteria

1. WHEN the Viewer_App starts, THE Viewer_App SHALL load the Saved_Model and the
   Model_Metadata from `Results/`.
2. WHEN the Viewer_App starts, THE Viewer_App SHALL load Training_Points and
   Candidate_Sites as its only observational data inputs.
3. IF the Saved_Model or Model_Metadata is missing, THEN THE Viewer_App SHALL
   show a clear message telling the user to run the Stage 3 training script and
   SHALL NOT attempt prediction.
4. THE Viewer_App SHALL NOT retrain, refit, or otherwise modify the Saved_Model.

### Requirement 2: Map of training and candidate locations

**User Story:** As a user, I want to see where the training and candidate
locations are, so that I understand the spatial context.

#### Acceptance Criteria

1. WHEN the Viewer_App renders the map, THE Viewer_App SHALL show the recorded
   training locations and the candidate-site locations as two visually
   distinguishable layers.
2. THE Viewer_App SHALL draw the map using recorded latitude and longitude only
   and SHALL NOT display any hidden temperature or depth value.
3. THE Viewer_App SHALL label the candidate-site markers as candidate profiles,
   never as verified fishing tows or casts.

### Requirement 3: Select a candidate profile

**User Story:** As a user, I want to pick a candidate profile, so that I can see
its predicted temperature-at-depth.

#### Acceptance Criteria

1. THE Viewer_App SHALL let the user select one candidate profile by its
   `profile_id` from Candidate_Sites.
2. WHEN a candidate profile is selected, THE Viewer_App SHALL read only its
   `profile_id`, latitude, longitude, and start_time from Candidate_Sites.
3. THE Viewer_App SHALL display the selected candidate profile's recorded
   latitude, longitude, and UTC start time.

### Requirement 4: Chart predicted temperatures at standard depths

**User Story:** As a user, I want to see the predicted temperatures at the
standard depths for the selected site, so that I can read the model's output.

#### Acceptance Criteria

1. WHEN a candidate profile is selected, THE Viewer_App SHALL call the existing
   Prediction_Function with the site latitude, longitude, the site start_time as
   the UTC prediction time, and the Standard_Depths.
2. THE Viewer_App SHALL chart exactly one predicted temperature per standard
   depth, in depth order, and SHALL produce the same predicted values that the
   Stage 3 prediction CLI produces for the same profile and depths.
3. THE Viewer_App SHALL display temperature in degrees Celsius and depth in
   metres, with both units shown.
4. THE Viewer_App SHALL present the predicted temperatures as model predictions
   only, without any forecast, uncertainty, confidence, or measurement-location
   recommendation.

### Requirement 5: Context, units, and limitations

**User Story:** As a user, I want the app to state its sources and limits, so
that I do not over-trust the output.

#### Acceptance Criteria

1. THE Viewer_App SHALL display dataset source attribution for the eMOLT
   observations.
2. THE Viewer_App SHALL state that the view is a historical replay, not a live or
   future forecast.
3. THE Viewer_App SHALL state the provisional-candidate-profile limitation: groups
   are inferred from recorded position and time proximity and are not verified
   fishing tows or casts.
4. THE Viewer_App SHALL state the unknown-bottom-depth limitation: the standard
   depths are requested prediction levels only and do not establish the actual
   bottom depth at a site.

### Requirement 6: Data boundary

**User Story:** As a maintainer, I want Stage 4 to hold the Stage 3 data
boundary, so that the app cannot leak hidden replay information.

#### Acceptance Criteria

1. WHILE running, THE Viewer_App SHALL NOT open Heldout_Points
   (`Data/splits/heldout_points.csv`) for reading, directly or indirectly.
2. WHILE running, THE Viewer_App SHALL NOT read the hidden temperature or depth
   summary columns of Profile_Summary (`Data/processed/profile_summary.csv`).
3. THE Viewer_App SHALL NOT display or otherwise reveal any actual hidden
   temperature or depth value.
4. THE data boundary SHALL be covered by a focused test asserting that loading the
   app's data and running one site prediction opens neither Heldout_Points nor
   Profile_Summary.

### Requirement 7: Scope boundaries

**User Story:** As a maintainer, I want Stage 4 scope held, so that the app stays
a thin viewer and the earlier stages stay intact.

#### Acceptance Criteria

1. THE Viewer_App SHALL add no model retraining, no uncertainty estimates, no
   next-site recommendations, no forecasts, and no deployment or hosting.
2. THE Viewer_App SHALL reuse the existing Prediction_Function unchanged and SHALL
   leave Stage 1, Stage 2, and Stage 3 code, files, and outputs unchanged.
3. THE Viewer_App SHALL operate within the existing Stage 1 study region without
   expanding it.
4. WHERE a Candidate_Profile is described in any output, THE Viewer_App SHALL use
   the wording "candidate profile" and SHALL NOT describe the group as a verified
   fishing tow or cast.
5. THE Viewer_App SHALL use libraries already available in the environment
   (Streamlit, pydeck, altair) and add only the dependencies needed for the app.

### Requirement 8: Documentation and status

**User Story:** As a maintainer, I want status documents updated, so that readers
know Stage 4 is active and understand its scope.

#### Acceptance Criteria

1. THE Viewer_App SHALL update `.kiro/steering/shelfcast-purpose-scope.md` to
   state "Stages 1-3 complete; Stage 4 active" and describe the Stage 4 scope and
   data boundary, while preserving the historical stage descriptions.
2. THE Viewer_App SHALL update `README.md` to state "Stages 1-3 complete; Stage 4
   active", describe the app, and document how to launch it.
