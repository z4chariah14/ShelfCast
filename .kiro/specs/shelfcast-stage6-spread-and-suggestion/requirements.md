# Requirements Document

## Introduction

ShelfCast Stage 6 adds two exploratory capabilities on top of the existing Stage 5 reveal-loop viewer: a five-model **spread** and a single **suggested next measurement**. The spread fits five reproducible versions of the existing ExtraTrees temperature model by resampling whole training candidate profiles (never individual readings) and shows, at a selected site, the range of their predicted temperature curves. The suggestion picks one eligible historical candidate location from `candidate_sites.csv` using the five models' disagreement at the 5 m and 10 m requested prediction levels, and presents it as a profile to test with a plain-language reason.

Stage 6 preserves everything from Stages 1-5. It keeps the existing Stage 3 prediction and the Stage 5 reveal charts; it reuses `fit_model` and `predict_temperatures` unchanged; it keeps the study region, the chronological replay split, the "provisional candidate profile" wording, the historical-replay framing, and the unknown-bottom-depth caveat. Stage 6 explicitly does NOT add deployment, forecasts, uncertainty or confidence intervals, oxygen, weather, or any new research model. The five-model spread is an exploratory measure, not a calibrated confidence interval; the suggestion is a profile to test, never an optimal site or an operational boat route.

The reveal loop still holds the single, narrow post-reveal data exception from Stage 5. Before any reveal, Stage 6 reads only the training points (`Data/splits/train_points.csv`), the candidate-site coordinates/times (`Data/splits/candidate_sites.csv`), and the existing model artifacts under `Results/`. Only `shelfcast/reveal.py`, after the explicit "Reveal actual measurements" click, may open `Data/splits/heldout_points.csv`, and only for the one selected profile's rows. No other hidden profile value may enter any fit, score, chart, or cache. The temporary and updated models are held in memory only and never overwrite `Results/model.joblib`.

## Glossary

- **Candidate profile**: A provisional candidate profile inferred from recorded position and time proximity, identified by `profile_id`. The starter eMOLT data omits the `tow_id` and `segment_type` columns, so these groups are not verified tows or casts. The words "tow" and "cast" may appear only inside a truthful limitation note explaining this; a candidate profile is never labeled or presented as a verified tow or cast.
- **Original saved model**: The Stage 3 model loaded from `Results/model.joblib`. Read-only in Stage 6.
- **Spread models**: Exactly five reproducible ExtraTrees models, each fit via the unchanged `fit_model` on a bootstrap resample of **whole training candidate profiles** (profile-level resampling), using fixed, declared per-model seeds so the five models are reproducible run to run.
- **Spread**: At a selected site and its recorded UTC start time, the range (minimum to maximum across the five spread models) of predicted temperature at each requested prediction level. An exploratory measure, not a calibrated confidence interval.
- **Disagreement score**: For a candidate site, a non-negative number summarizing how much the five spread models disagree at the 5 m and 10 m requested prediction levels (the spread width at those two levels). Higher means the five models disagree more.
- **Suggestion**: One eligible candidate profile chosen by highest disagreement score, presented as a profile to test with its score and a plain-language reason. Never an optimal site or an operational boat route.
- **Eligible candidate (pre-reveal)**: A candidate profile from `candidate_sites.csv`, other than the selected site, at least 1 km from the selected site (great-circle distance in kilometres), whose recorded `start_time` is strictly after the selected site's recorded `start_time`.
- **Eligible candidate (post-reveal)**: As above, except the `start_time` must be strictly after the revealed profile's final recorded measurement time (the maximum `time` among the revealed rows) instead of after the selected site's start time.
- **Updated spread models**: After a reveal, five spread models each fit from the original training rows plus **only** the one selected revealed profile's rows (every updated model includes that revealed profile), held in memory only.
- **Spread_Engine**: The Stage 6 pure helper module (`shelfcast/spread.py`) that fits spread models, computes the spread, scores candidates, and chooses the suggestion (EARS system name).
- **Viewer_App**: The Stage 5/6 Streamlit viewer behavior (`app.py`) (EARS system name).

## Requirements

### Requirement 1: Five reproducible profile-level spread models

**User Story:** As a viewer user, I want five reproducible versions of the temperature model built by resampling whole candidate profiles, so that I can see how much the model's prediction depends on which profiles it saw.

#### Acceptance Criteria

1. THE Spread_Engine SHALL fit exactly five spread models, each by calling the unchanged `fit_model` on a bootstrap resample drawn at the granularity of **whole training candidate profiles** (profile ids), never individual readings.
2. WHEN building each resample, THE Spread_Engine SHALL sample candidate profile ids with replacement and include every reading of each sampled profile, so that no reading of an unsampled profile and no partial profile enters that resample.
3. THE Spread_Engine SHALL use fixed, declared per-model random seeds so that re-running the fit on the same training rows produces the five same models and the same predictions.
4. THE Spread_Engine SHALL read feature and target values only from the training rows passed to it (the Stage 2 training candidate profiles) and SHALL NOT read any hidden heldout value.
5. IF the training rows contain fewer than two distinct candidate profile ids, THEN THE Spread_Engine SHALL raise a descriptive error and SHALL NOT fit the spread models.
6. THE Spread_Engine SHALL NOT write any spread model to disk and SHALL NOT overwrite `Results/model.joblib`.

### Requirement 2: Spread display at a selected site

**User Story:** As a viewer user, I want to see the range of the five models' predicted curves at the selected site, so that I can gauge where they agree or disagree.

#### Acceptance Criteria

1. WHEN a candidate profile is selected, THE Viewer_App SHALL display, at the standard requested prediction levels of 5, 10, 20, 30, and 50 meters and the site's recorded coordinates and recorded UTC start time, the minimum-to-maximum range of predicted temperature across the five spread models.
2. THE Viewer_App SHALL continue to display the existing Stage 3 prediction (from the original saved model) together with the spread range.
3. WHEN a reveal has occurred for the selected profile, THE Viewer_App SHALL continue to display the Stage 5 reveal charts (actual measurements at their true recorded depths, and the original versus temporary updated predicted curves).
4. THE Viewer_App SHALL label the spread as "spread across five models — an exploratory measure, not a calibrated confidence interval."
5. THE Viewer_App SHALL compute each spread curve with the unchanged `predict_temperatures` and SHALL NOT present the spread as a forecast, uncertainty band, or confidence interval.

### Requirement 3: Disagreement score at 5 m and 10 m

**User Story:** As a viewer user, I want a disagreement score at shallow levels, so that the suggestion favors sites where the models most disagree.

#### Acceptance Criteria

1. THE Spread_Engine SHALL compute a candidate's disagreement score from the five spread models' predicted temperatures at the requested prediction levels of 5 meters and 10 meters only, using that candidate's recorded coordinates and recorded UTC start time.
2. THE Spread_Engine SHALL define the disagreement score as a non-negative number that increases when the five models' predictions at 5 m and 10 m are more spread out (for example, the sum of the max-minus-min spread at 5 m and at 10 m).
3. THE Spread_Engine SHALL compute scores using predictions only and SHALL NOT read any candidate's hidden `temperature_c` or `depth_m` from `heldout_points.csv`.
4. THE Spread_Engine SHALL compute scores reproducibly, so the same spread models and the same candidate coordinates/times produce the same score.

### Requirement 4: Candidate eligibility for the suggestion

**User Story:** As a viewer user, I want the suggestion drawn only from eligible historical candidates, so that it respects the replay timeline and avoids the site I am already looking at.

#### Acceptance Criteria

1. THE Spread_Engine SHALL consider as suggestion candidates only profiles from `candidate_sites.csv`, excluding the selected site and excluding any candidate within 1 kilometre of the selected site (great-circle distance in kilometres).
2. WHILE no reveal has occurred for the selected profile, THE Spread_Engine SHALL include a candidate only if its recorded `start_time` is strictly after the selected site's recorded `start_time`.
3. WHEN a reveal has occurred for the selected profile, THE Spread_Engine SHALL include a candidate only if its recorded `start_time` is strictly after the revealed profile's final recorded measurement time (the maximum `time` among the revealed rows).
4. THE Spread_Engine SHALL read only the candidate-site columns `profile_id, latitude, longitude, start_time` when applying eligibility and SHALL NOT open `heldout_points.csv` for eligibility.

### Requirement 5: Choosing and presenting the suggestion

**User Story:** As a viewer user, I want one clearly explained suggested profile to test, so that I understand why it was chosen without mistaking it for an optimal site or a route.

#### Acceptance Criteria

1. WHEN at least one eligible candidate exists, THE Spread_Engine SHALL choose the eligible candidate with the highest disagreement score, breaking ties by lowest `profile_id`.
2. WHEN a suggestion has been chosen, THE Viewer_App SHALL display the suggested candidate profile id, its disagreement score, and a plain-language reason stating that the five models disagree most about temperature at 5 m and 10 m there.
3. THE Viewer_App SHALL label the suggestion as a profile to test and SHALL NOT present it as an optimal site, a best site, or an operational boat route.
4. IF no eligible candidate exists, THEN THE Viewer_App SHALL display a message that no eligible candidate is available for a suggestion and SHALL NOT display a suggested profile, score, or reason.
5. THE Viewer_App SHALL compute and present the suggestion using predictions only and SHALL NOT read or display any hidden `temperature_c` or `depth_m` value for the suggested candidate.

### Requirement 6: Post-reveal update of spread and suggestion

**User Story:** As a viewer user, I want the spread and suggestion to update after I reveal the selected profile, so that I can see how adding that one real profile changes the models' disagreement.

#### Acceptance Criteria

1. WHEN a reveal has occurred for the selected profile, THE Spread_Engine SHALL fit five updated spread models from the original training rows plus **only** the one selected revealed profile's rows, including that revealed profile in every updated model, using profile-level resampling and the same fixed per-model seeds.
2. WHEN updated spread models exist, THE Viewer_App SHALL recompute and display the spread at the selected site and the suggestion using the updated spread models.
3. THE Spread_Engine SHALL hold the updated spread models in memory only and SHALL NOT write them to disk or overwrite `Results/model.joblib`.
4. THE Spread_Engine SHALL NOT include any profile other than the training rows and the one selected revealed profile in any updated spread model fit, score, chart, or cache.

### Requirement 7: Reveal and reset isolation

**User Story:** As a viewer user, I want selection changes and Reset replay to clear all updated spread/suggestion state, so that I never see stale updated results from a prior profile.

#### Acceptance Criteria

1. WHEN the selected candidate profile changes, THE Viewer_App SHALL discard any updated spread models and any suggestion derived from them and SHALL return to the pre-reveal spread models before the next display completes.
2. WHEN the user presses "Reset replay", THE Viewer_App SHALL discard any updated spread models and any suggestion derived from them and SHALL return to the pre-reveal spread and the pre-reveal suggestion.
3. WHILE the Streamlit application reruns, THE Viewer_App SHALL associate any updated spread models with the currently selected `profile_id` only, and SHALL NOT carry an updated spread or suggestion across a selection change.
4. THE Viewer_App SHALL NOT display any updated spread or suggestion derived from a profile other than the currently selected one.

### Requirement 8: Data boundary and scope

**User Story:** As a project maintainer, I want Stage 6 to keep the Stage 1-5 boundaries and scope, so that the viewer stays an honest historical replay within project limits.

#### Acceptance Criteria

1. THE Viewer_App pre-reveal paths and THE Spread_Engine SHALL read only `Data/splits/train_points.csv`, the `profile_id, latitude, longitude, start_time` columns of `Data/splits/candidate_sites.csv`, and the artifacts under `Results/`, and SHALL NOT open `Data/splits/heldout_points.csv` or read the hidden summary columns of `Data/processed/profile_summary.csv`.
2. THE Viewer_App SHALL open `Data/splits/heldout_points.csv` only through `shelfcast/reveal.py`, only after the explicit "Reveal actual measurements" click, and only for the one selected profile's rows; no other hidden profile value SHALL enter any spread fit, score, chart, or cache.
3. THE Spread_Engine and THE Viewer_App SHALL NOT write any Stage 6 model to disk and SHALL NOT overwrite `Results/model.joblib`.
4. THE Viewer_App SHALL display only sites with latitude in the inclusive range 41.5 to 42.5 degrees North and longitude in the inclusive range -70.5 to -69.5 degrees, and SHALL NOT expand the Stage 1 study region.
5. THE Viewer_App SHALL label Stage 6 output as a historical replay in which the selected hidden candidate profile started (`start_time`) on or after the 2024-08-06T00:00:00Z UTC cutoff while the original saved model was trained only on candidate profiles that ended (`end_time`) strictly before that cutoff.
6. THE Viewer_App SHALL label the requested prediction levels of 5, 10, 20, 30, and 50 meters as requested prediction levels and SHALL NOT present them as a claim about actual bottom depth at a site.
7. WHERE the Viewer_App displays the words "tow" or "cast", THE Viewer_App SHALL display them only inside a truthful limitation note explaining that the starter eMOLT data omits `tow_id`/`segment_type` so groups are provisional candidate profiles, not verified tows or casts.
8. THE Viewer_App SHALL NOT add any forecast, calibrated uncertainty or confidence interval, oxygen value, weather value, next-site-is-optimal claim, operational route, new research model, or deployment.
