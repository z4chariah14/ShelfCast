# Requirements Document

## Introduction

ShelfCast Stage 3 delivers a fast, working first temperature predictor. A regression model is fit on the Stage 2 training candidate profiles and used to predict ocean temperature at a given location, UTC time, and set of depths. Stages 1 (data foundation) and 2 (chronological replay split) are complete and unchanged. The central constraint of Stage 3 is a strict data boundary: pre-reveal code must only read the training points and the candidate-site location table, never the hidden held-out measurements or any hidden temperature/depth values. Stage 3 adds no forecasts, uncertainty claims, measurement recommendations, maps, UI, or deployment.

## Glossary

- **Predictor**: The Stage 3 software component that fits a regression model and predicts temperature.
- **Prediction_Function**: The reusable, importable function that returns predicted temperature per requested depth.
- **Training_CLI**: The command-line script that fits the model and writes artifacts under `Results/`.
- **Prediction_CLI**: The command-line script that predicts temperatures for a chosen candidate site and time.
- **Candidate_Profile**: A provisional group of readings inferred from recorded position and time proximity. Never a verified fishing tow or cast.
- **Training_Points**: `Data/splits/train_points.csv` with columns time, latitude, longitude, depth_m, temperature_c, profile_id.
- **Candidate_Sites**: `Data/splits/candidate_sites.csv` with columns profile_id, latitude, longitude, start_time.
- **Heldout_Points**: `Data/splits/heldout_points.csv`, the hidden replay measurements.
- **Profile_Summary**: `Data/processed/profile_summary.csv`, which contains temperature/depth summary values including those of hidden profiles.
- **Feature_Set**: The exactly four model inputs: latitude, longitude, depth_m, and UTC time expressed as hours since a fixed declared reference instant.
- **Time_Reference**: A fixed, declared UTC reference instant used to convert a UTC time into hours.
- **Default_Depth_Grid**: A fixed, declared list of requested prediction levels (depths in metres at which a prediction is requested) used when the caller supplies no depths. The Default_Depth_Grid does not establish or claim the actual bottom depth at a site.
- **Model_Artifact**: The serialized fitted model file written under `Results/`.
- **Metadata_Report**: The small report file written under `Results/` describing the fitted model.

## Requirements

### Requirement 1: Fit the temperature model

**User Story:** As a developer, I want to fit a reproducible regression model from the training candidate profiles, so that I have a working first temperature predictor.

#### Acceptance Criteria

1. WHEN the model is fit, THE Predictor SHALL read feature and target values only from Training_Points and SHALL use no other data source as model input.
2. THE Predictor SHALL use exactly four model inputs in a fixed, declared order: latitude, longitude, depth_m, and a UTC time feature computed as the number of hours (floating point) from a fixed declared UTC instant (Time_Reference) to each reading's recorded UTC time.
3. THE Predictor SHALL use temperature_c as the model target.
4. THE Predictor SHALL fit an ExtraTreesRegressor configured with a fixed random_state so that two fits run on byte-identical Training_Points inputs produce models that return identical predictions for identical query inputs.
5. IF Training_Points is missing or unreadable, or any row is missing a required feature or target column, or any required feature or target value is non-numeric, THEN THE Predictor SHALL stop the fit, return an error indication naming the failure, and write no model artifact.
6. BEFORE writing any artifact, THE Predictor SHALL validate that every feature value and every target value is a finite numeric value, rejecting NaN and positive or negative infinity, and that every reading timestamp is a valid UTC timestamp.
7. IF any feature value or target value is not finite, or any reading timestamp is not a valid UTC timestamp, THEN THE Predictor SHALL stop the fit, write no artifact, and return an error indication naming the failing validation.

### Requirement 2: Reusable prediction function

**User Story:** As a developer, I want an importable prediction function, so that the prediction CLI and tests can reuse one prediction path.

#### Acceptance Criteria

1. WHEN the Prediction_Function is called with a latitude, a longitude, a UTC time, and a non-empty ordered list of depths in meters, THE Prediction_Function SHALL return a list of predicted temperature values whose length and order correspond one-to-one with the requested depths.
2. THE Prediction_Function SHALL return a finite numeric temperature, excluding NaN and positive or negative infinity, for every requested depth.
3. WHEN the Prediction_Function is called, THE Prediction_Function SHALL build for each requested depth the fixed four-feature row consisting of latitude, longitude, depth in meters, and hours elapsed since the fixed Time_Reference computed from the provided UTC time.
4. IF the Prediction_Function is called with an empty list of depths, THEN THE Prediction_Function SHALL return an empty list of predicted temperatures and SHALL NOT invoke the fitted model.
5. IF the Prediction_Function is called with a non-empty depths list containing any value that is not a finite number greater than 0 metres, THEN THE Prediction_Function SHALL return an error indication reporting the invalid depths and SHALL NOT invoke the fitted model.
6. THE Prediction_Function SHALL be importable from the shelfcast package and SHALL be reused by the Prediction_CLI.

### Requirement 3: Training CLI

**User Story:** As a developer, I want a training command, so that I can produce and persist the fitted model and its metadata.

#### Acceptance Criteria

1. WHEN the Training_CLI runs, THE Training_CLI SHALL fit the model using only Training_Points, using a recorded deterministic seed so that two runs on identical Training_Points produce an identical Model_Artifact.
2. WHEN the Training_CLI completes the fit without error, THE Training_CLI SHALL write the Model_Artifact as a serialized model file under `Results/`.
3. WHEN the Training_CLI completes the fit without error, THE Training_CLI SHALL write the Metadata_Report as a JSON file under `Results/` containing the Feature_Set, the Time_Reference, the recorded deterministic seed, the training row count, the training Candidate_Profile count, and a note stating that groups are provisional candidate profiles inferred from recorded position and time proximity and are not verified fishing tows or casts.
4. IF Training_Points is missing, unreadable, or contains zero rows, THEN THE Training_CLI SHALL write neither the Model_Artifact nor the Metadata_Report, print a message indicating the cause of failure, and exit with a non-zero status.
5. WHEN the Training_CLI finishes writing both the Model_Artifact and the Metadata_Report, THE Training_CLI SHALL print a message indicating success and exit with a zero status.

### Requirement 4: Prediction CLI

**User Story:** As a developer, I want a prediction command for a candidate site, so that I can obtain predicted temperatures at depth for a chosen site and time.

#### Acceptance Criteria

1. WHEN the Prediction_CLI is given a profile_id that matches exactly one row in Candidate_Sites, THE Prediction_CLI SHALL read the latitude, longitude, and start_time for that Candidate_Profile from Candidate_Sites.
2. WHERE the caller supplies no depths, THE Prediction_CLI SHALL use the Default_Depth_Grid, a fixed declared list of requested prediction levels expressed as positive depths in metres.
3. WHERE the caller supplies a non-empty list of depths in which every depth is a finite number greater than 0 metres, THE Prediction_CLI SHALL use the supplied depths instead of the Default_Depth_Grid.
4. WHEN the Prediction_CLI selects a depth list, THE Prediction_CLI SHALL output exactly one predicted temperature per depth, in the same order as the selected depth list, by calling the Prediction_Function with the site latitude, longitude, and the site start_time interpreted as the UTC prediction time.
5. IF the given profile_id matches no row in Candidate_Sites, THEN THE Prediction_CLI SHALL produce no predicted temperatures and SHALL return an error indication reporting that the profile_id was not found.
6. IF the caller supplies a depths list that is empty or contains any value that is not a finite number greater than 0 metres, THEN THE Prediction_CLI SHALL produce no predicted temperatures and SHALL return an error indication reporting the invalid depths.
7. WHEN the Prediction_CLI produces predictions, THE Prediction_CLI SHALL emit a structured JSON object containing the profile_id, the UTC prediction time, and an ordered list of depth/temperature pairs in the same order as the selected depth list.
8. IF the given profile_id matches more than one row in Candidate_Sites, THEN THE Prediction_CLI SHALL produce no predicted temperatures and SHALL return an error indication reporting that the profile_id is ambiguous because it matches multiple rows.
9. THE Prediction_CLI SHALL treat requested depths as requested prediction levels only and SHALL NOT present them as the actual bottom depth of a Candidate_Profile or site.

### Requirement 5: Data boundary

**User Story:** As a maintainer, I want a hard data boundary, so that pre-reveal code cannot leak information from the hidden replay set.

#### Acceptance Criteria

1. WHILE training a model, THE Predictor SHALL open Training_Points as the only observational data file for feature and label values, and SHALL open Candidate_Sites as an observational data file only when a candidate-site lookup is needed.
2. WHILE performing prediction, THE Predictor SHALL open Candidate_Sites as the only observational data file (for candidate-site lookup), and loading the previously saved Model_Artifact and Metadata_Report from `Results/` SHALL be permitted and SHALL NOT count as an observational data input.
3. WHEN a candidate site location or time is needed, THE Predictor SHALL read from Candidate_Sites only the columns profile_id, latitude, longitude, and start_time.
4. WHILE performing training or prediction, THE Predictor SHALL NOT open Heldout_Points (Data/splits/heldout_points.csv) for reading.
5. WHILE performing training or prediction, THE Predictor SHALL NOT read the temperature or depth columns of Profile_Summary (temp_min, temp_max, depth_min, depth_max, depth_range from Data/processed/profile_summary.csv).
6. THE Predictor SHALL be covered by focused tests that assert the training path and the prediction path do not open Heldout_Points or Profile_Summary.

### Requirement 6: Reproducibility

**User Story:** As a developer, I want deterministic results, so that outputs can be trusted and compared.

#### Acceptance Criteria

1. WHEN the model is fit twice on identical Training_Points with the fixed random settings, THE Predictor SHALL produce identical models.
2. WHEN the Prediction_Function is called twice with identical inputs on identical models, THE Prediction_Function SHALL return identical predicted temperatures.

### Requirement 7: Scope boundaries

**User Story:** As a maintainer, I want Stage 3 scope held, so that the stage stays minimal and the earlier stages stay intact.

#### Acceptance Criteria

1. THE Predictor SHALL output predicted temperatures only, without forecasts, uncertainty or confidence values, or measurement-location recommendations.
2. THE Predictor SHALL operate without any map, spatial visualization, dashboard, user interface, deployment, or hosting.
3. THE Predictor SHALL leave Stage 1 and Stage 2 code, files, and outputs unchanged.
4. THE Predictor SHALL operate within the existing Stage 1 study region without expanding it.
5. WHERE a Candidate_Profile is described in any output or document, THE Predictor SHALL use the wording "candidate profile" and SHALL NOT describe the group as a verified fishing tow or cast.

### Requirement 8: Documentation and status

**User Story:** As a maintainer, I want the status documents updated, so that readers know Stage 3 is active and understand its scope.

#### Acceptance Criteria

1. THE Predictor SHALL update `.kiro/steering/shelfcast-purpose-scope.md` to state "Stage 1 and 2 complete; Stage 3 active" and SHALL describe the Stage 3 scope.
2. THE Predictor SHALL update `README.md` to state "Stage 1 and 2 complete; Stage 3 active" and SHALL describe the Stage 3 scope.

### Requirement 9: End-to-end smoke check

**User Story:** As a developer, I want one end-to-end check, so that I can confirm the predictor works and respects the data boundary.

#### Acceptance Criteria

1. WHEN the smoke check runs, THE Predictor SHALL train successfully from Training_Points.
2. WHEN the smoke check runs, THE Predictor SHALL return finite predicted temperatures for one Candidate_Site at a fixed set of depths.
3. WHEN the smoke check runs, THE Predictor SHALL confirm that Heldout_Points was not accessed during training or prediction.
