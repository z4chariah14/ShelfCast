# Requirements Document

## Introduction

ShelfCast Stage 2 produces a chronological replay split of the Stage 1 data
foundation. Using a fixed UTC cutoff, the Split_Tool classifies each Stage 1
candidate profile — as a whole — into a training set, a held-out replay set, or
an excluded set (profiles that span the cutoff). It writes local, git-ignored
split artifacts and a report, and enforces hard-fail integrity checks that
prevent a profile's readings from being divided across sets, keep the training
and held-out profile-id sets disjoint, confirm the summary timestamps match the
underlying points, and keep the candidate-sites file free of measurement
columns.

The Stage 1 groups remain **provisional candidate profiles** inferred from
recorded position and time proximity. They are never verified fishing tows or
casts. All Stage 2 outputs and documentation use the wording "candidate
profile" and contain no tow, cast, or segment-type label.

Stage 2 is limited to producing the split artifacts. The following are
explicitly **out of scope**: any predictive or interpolation model, any map or
spatial visualization, any dashboard or UI, any deployment or hosting, any
rewrite of Stage 1 code, and any change to the Stage 1 study region. Stage 2
stops at producing the split artifacts.

## Glossary

- **Split_Tool**: The Stage 2 component that reads Stage 1 outputs, classifies
  candidate profiles against the cutoff, runs integrity checks, and writes the
  split artifacts and report.
- **Candidate_Profile**: A Stage 1 group of readings sharing a `profile_id`,
  inferred from recorded position and time proximity; a provisional grouping,
  never a verified tow or cast.
- **Cutoff**: The fixed boundary timestamp `2024-08-06T00:00:00Z` used to
  classify candidate profiles.
- **Training_Set**: Candidate profiles whose summary `end_time` is strictly
  before the Cutoff.
- **Heldout_Set**: Candidate profiles whose summary `start_time` is at or after
  the Cutoff; the hidden replay set.
- **Excluded_Set**: Candidate profiles that span the Cutoff and belong to
  neither the Training_Set nor the Heldout_Set.
- **Profile_Summary**: The Stage 1 input file `Data/processed/profile_summary.csv`
  with columns `profile_id, latitude, longitude, start_time, end_time,
  n_readings, depth_min, depth_max, depth_range, temp_min, temp_max,
  duration_seconds`.
- **Profile_Points**: The Stage 1 input file `Data/processed/profile_points.csv`
  with columns `time, latitude, longitude, depth_m, temperature_c, profile_id`.
- **Point_Row**: A single reading row from Profile_Points containing all Stage 1
  point columns, including `temperature_c` and `depth_m`.
- **Candidate_Sites**: The output file `Data/splits/candidate_sites.csv`
  containing exactly the columns `profile_id, latitude, longitude, start_time`
  for Heldout_Set candidate profiles.
- **Split_Report**: The output file `Data/splits/split_report.json` summarizing
  the split.

## Requirements

### Requirement 1: Read Stage 1 Outputs

**User Story:** As a data engineer, I want the Split_Tool to read the Stage 1
outputs, so that the replay split is derived from the established data
foundation.

#### Acceptance Criteria

1. WHEN the Split_Tool runs, THE Split_Tool SHALL read Profile_Summary from `Data/processed/profile_summary.csv` and Profile_Points from `Data/processed/profile_points.csv`.
2. THE Split_Tool SHALL interpret the `start_time`, `end_time`, and `time` values as timezone-aware UTC ISO 8601 timestamps.
3. WHERE Stage 2 constants are added to `shelfcast/config.py`, THE Split_Tool SHALL add them additively and SHALL leave all existing Stage 1 constants and all Stage 1 behavior in `shelfcast/config.py`, `shelfcast/pipeline.py`, and `Scripts/prepare_data.py` unchanged.

### Requirement 2: Whole-Profile Classification Against the Cutoff

**User Story:** As a data engineer, I want each candidate profile classified as
a whole against the cutoff, so that no profile's readings are divided across
sets.

#### Acceptance Criteria

1. THE Cutoff SHALL be the fixed timestamp `2024-08-06T00:00:00Z`.
2. IF a Candidate_Profile summary `end_time` is strictly before the Cutoff, THEN THE Split_Tool SHALL assign that Candidate_Profile to the Training_Set.
3. IF a Candidate_Profile summary `start_time` is at or after the Cutoff, THEN THE Split_Tool SHALL assign that Candidate_Profile to the Heldout_Set.
4. IF a Candidate_Profile summary `end_time` is at or after the Cutoff AND its `start_time` is before the Cutoff, THEN THE Split_Tool SHALL assign that Candidate_Profile to the Excluded_Set and exclude that Candidate_Profile from both the Training_Set and the Heldout_Set.
5. WHEN a Candidate_Profile summary `end_time` equals the Cutoff exactly, THE Split_Tool SHALL assign that Candidate_Profile to the Excluded_Set.
6. THE Split_Tool SHALL assign all Point_Rows of a Candidate_Profile to the single set assigned to that Candidate_Profile.

### Requirement 3: Write Training and Held-out Point Files

**User Story:** As a data engineer, I want the training and held-out point data
written to local files, so that downstream replay has the full readings for each
set.

#### Acceptance Criteria

1. WHEN classification completes without integrity failure, THE Split_Tool SHALL write `Data/splits/train_points.csv` containing every Point_Row, with all Stage 1 point columns including `temperature_c` and `depth_m`, for each Training_Set Candidate_Profile.
2. WHEN classification completes without integrity failure, THE Split_Tool SHALL write `Data/splits/heldout_points.csv` containing every Point_Row, with all Stage 1 point columns including `temperature_c` and `depth_m`, for each Heldout_Set Candidate_Profile.

### Requirement 4: Write Candidate Sites File

**User Story:** As a replay operator, I want a candidate-sites file for the
held-out profiles, so that I can query sites during replay without seeing the
hidden measurements.

#### Acceptance Criteria

1. WHEN classification completes without integrity failure, THE Split_Tool SHALL write `Data/splits/candidate_sites.csv` with exactly the columns `profile_id, latitude, longitude, start_time`.
2. THE Split_Tool SHALL include in Candidate_Sites one row for each Heldout_Set Candidate_Profile.
3. THE Candidate_Sites file SHALL exclude `end_time`, temperature columns, depth columns, and all summary measurement columns.

### Requirement 5: Write Split Report

**User Story:** As a data engineer, I want a split report, so that I can audit
the composition and provenance of the split.

#### Acceptance Criteria

1. WHEN classification completes without integrity failure, THE Split_Tool SHALL write `Data/splits/split_report.json`.
2. THE Split_Report SHALL record the Candidate_Profile count and the Point_Row count for each of the Training_Set, the Heldout_Set, and the Excluded_Set.
3. THE Split_Report SHALL record the UTC time range for each of the Training_Set, the Heldout_Set, and the Excluded_Set.
4. THE Split_Report SHALL record the list of Excluded_Set `profile_id` values with each excluded Candidate_Profile `start_time` and `end_time`.
5. THE Split_Report SHALL record the Cutoff value.

### Requirement 6: Hard-Fail Integrity Checks

**User Story:** As a data engineer, I want hard-fail integrity checks, so that
the split aborts rather than producing a compromised artifact.

#### Acceptance Criteria

1. THE Split_Tool SHALL complete all integrity checks in this requirement before writing any split file.
2. IF any `profile_id` in Profile_Summary is absent from Profile_Points, OR any `profile_id` in Profile_Points is absent from Profile_Summary, THEN THE Split_Tool SHALL exit with a non-zero status and a message stating the mismatch, without writing any artifact.
3. IF any `profile_id` appears more than once in Profile_Summary, THEN THE Split_Tool SHALL exit with a non-zero status and a message naming the duplicated `profile_id` values, without writing any artifact.
4. IF, for any `profile_id`, the Profile_Summary `start_time` does not equal the earliest Profile_Points `time` among that profile's Point_Rows, OR the Profile_Summary `end_time` does not equal the latest Profile_Points `time` among that profile's Point_Rows, THEN THE Split_Tool SHALL exit with a non-zero status and a message naming the offending `profile_id` values, without writing any artifact.
5. IF any row written to `train_points.csv` carries a `profile_id` that is not a Training_Set `profile_id`, OR any row written to `heldout_points.csv` carries a `profile_id` that is not a Heldout_Set `profile_id`, THEN THE Split_Tool SHALL exit with a non-zero status and a message naming the offending `profile_id` values, without writing any artifact.
6. IF the Training_Set `profile_id` values and the Heldout_Set `profile_id` values share any value, THEN THE Split_Tool SHALL exit with a non-zero status and a message stating the overlap, without writing any artifact.
7. IF the Candidate_Sites columns would include any column other than `profile_id`, `latitude`, `longitude`, and `start_time`, THEN THE Split_Tool SHALL exit with a non-zero status and a message stating the structural violation, without writing any artifact.
8. WHEN all integrity checks pass, THE Split_Tool SHALL write the split artifacts described in Requirements 3, 4, and 5.

### Requirement 7: Dedicated CLI Over Testable Module

**User Story:** As a data engineer, I want a dedicated CLI over a testable
module, so that I can regenerate the split with one documented command.

#### Acceptance Criteria

1. THE Split_Tool SHALL expose its classification and artifact-writing logic in a testable module at `shelfcast/split.py`.
2. THE Split_Tool SHALL provide a command-line entry point at `Scripts/split_replay.py` that invokes the `shelfcast/split.py` module.
3. WHEN the `Scripts/split_replay.py` command runs, THE Split_Tool SHALL regenerate the split artifacts in `Data/splits/`.

### Requirement 8: Focused Tests

**User Story:** As a maintainer, I want focused tests, so that the split
behavior is verifiable.

#### Acceptance Criteria

1. THE Split_Tool test suite SHALL use pytest with only pandas and the Python standard library, and SHALL NOT use numpy.
2. THE Split_Tool test suite SHALL verify that a Candidate_Profile with `end_time` strictly before the Cutoff is classified to the Training_Set, a Candidate_Profile with `start_time` at or after the Cutoff is classified to the Heldout_Set, and a Candidate_Profile with `end_time` equal to the Cutoff is classified to the Excluded_Set.
3. THE Split_Tool test suite SHALL verify that a Candidate_Profile spanning the Cutoff is assigned to the Excluded_Set.
4. THE Split_Tool test suite SHALL verify that every Point_Row of a Candidate_Profile appears in exactly one set.
5. THE Split_Tool test suite SHALL verify that Candidate_Sites carries exactly the columns `profile_id`, `latitude`, `longitude`, and `start_time` and no `end_time`, temperature, depth, or summary measurement column.
6. THE Split_Tool test suite SHALL verify that every row in `train_points.csv` carries a Training_Set `profile_id`, that every row in `heldout_points.csv` carries a Heldout_Set `profile_id`, and that the Training_Set and Heldout_Set `profile_id` sets are disjoint.
7. THE Split_Tool test suite SHALL verify that a duplicate `profile_id` in Profile_Summary causes a non-zero exit with no artifact written.
8. THE Split_Tool test suite SHALL verify that a mismatch between a Profile_Summary `start_time` or `end_time` and the earliest or latest Profile_Points `time` for that `profile_id` causes a non-zero exit with no artifact written.

### Requirement 9: Documentation and Repository Hygiene

**User Story:** As a maintainer, I want the documentation and repository hygiene
updated, so that the split is reproducible and the data integrity rule is
preserved.

#### Acceptance Criteria

1. THE README SHALL contain a Stage 2 section with the exact command to regenerate the split.
2. THE `.gitignore` SHALL exclude `Data/splits/`.
3. THE steering file SHALL state "Stage 1 complete; Stage 2 active" while preserving the rule that Stage 1 groups are provisional candidate profiles.
4. THE Split_Tool SHALL keep the `.kiro` directory tracked in version control.

### Requirement 10: Provisional-Candidate Integrity in Outputs

**User Story:** As a project stakeholder, I want the provisional-candidate
integrity rule enforced in all outputs, so that groups are never misrepresented
as verified tows or casts.

#### Acceptance Criteria

1. THE Split_Tool SHALL refer to each Stage 1 group as a candidate profile in all outputs and documentation.
2. THE Split_Tool output artifacts SHALL exclude any tow label, cast label, and segment-type label.
