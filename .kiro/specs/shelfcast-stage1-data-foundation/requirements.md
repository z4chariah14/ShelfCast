# Requirements Document

## Introduction

ShelfCast Stage 1 establishes the data foundation for the ShelfCast project. Stage 1 ingests the local eMOLT dataset, cleans and validates it, selects the study region, and groups nearby readings into provisional candidate profiles. The outputs are a cleaned point dataset, a candidate-profile summary, and a processing report, produced by a lean command-line pipeline written in Python using pandas and the standard library.

This document covers Stage 1 data foundation ONLY. It does not include any predictive model, map, dashboard, or deployment capability.

A central integrity constraint governs this stage: the released starter ZIP (`Data/raw/emolt.zip`) omits the `tow_id` and `segment_type` columns, even though the full eMOLT source includes both. Stage 1 does not use those columns. Because the starter data lacks `tow_id` and `segment_type`, groups of readings produced by Stage 1 are provisional candidate profiles inferred from recorded position and time proximity. Stage 1 must not present these groups as verified fishing tows or casts.

## Glossary

- **ShelfCast_Pipeline**: The Stage 1 data-processing software that loads, cleans, filters, and groups eMOLT readings and writes output artifacts.
- **Config_Module**: The Python module `shelfcast/config.py` that holds named constants for Stage 1.
- **CLI_Entry**: The command-line entry script `Scripts/prepare_data.py` that invokes the ShelfCast_Pipeline.
- **Raw_Archive**: The input ZIP file `Data/raw/emolt.zip` containing `data.csv`. The Raw_Archive is the released starter ZIP and omits the `tow_id` and `segment_type` columns that the full eMOLT source provides.
- **Source_CSV**: The file `data.csv` inside the Raw_Archive, with columns `time`, `latitude`, `longitude`, `depth_m`, `temperature_c`.
- **Reading**: A single parsed row from the Source_CSV containing a UTC timestamp, latitude, longitude, depth in meters, and temperature in degrees Celsius.
- **Study_Region**: The geographic bounds latitude 41.5 to 42.5 inclusive and longitude -70.5 to -69.5 inclusive.
- **Candidate_Profile**: A provisional group of Readings that share the same recorded latitude and longitude and whose consecutive timestamps differ by no more than the Gap_Threshold, that satisfies the retention rules. A Candidate_Profile is inferred and is not a verified fishing tow or cast.
- **Profile_Id**: A unique identifier assigned by the ShelfCast_Pipeline to each retained Candidate_Profile.
- **Gap_Threshold**: The maximum allowed time difference between consecutive Readings within a Candidate_Profile. Default value is 5 minutes.
- **Min_Readings**: The minimum number of Readings a Candidate_Profile must contain to be retained. Value is 10 (constant MIN_READINGS).
- **Min_Depth_Range_M**: The minimum difference between the maximum and minimum depth in meters within a Candidate_Profile for retention. Value is 10 (constant MIN_DEPTH_RANGE_M).
- **Max_Span**: The maximum allowed time difference between the earliest and latest Reading within a Candidate_Profile. Value is 1 hour (constant MAX_SPAN).
- **Output_Directory**: The directory `Data/processed/` where output artifacts are written.
- **Profile_Points_File**: The output file `profile_points.csv` containing every retained Reading with its Profile_Id.
- **Profile_Summary_File**: The output file `profile_summary.csv` containing one row per Candidate_Profile.
- **Stage1_Report_File**: The output file `stage1_report.json` containing processing counts and grouping rules.

## Requirements

### Requirement 1: Centralized Configuration

**User Story:** As a data engineer, I want Stage 1 constants and configuration centralized in one module, so that study parameters are explicit and consistently applied across the pipeline.

#### Acceptance Criteria

1. THE Config_Module SHALL define the Study_Region bounds as latitude 41.5 to 42.5 and longitude -70.5 to -69.5 as named constants.
2. THE Config_Module SHALL define Min_Readings with value 10 as a named constant MIN_READINGS.
3. THE Config_Module SHALL define Min_Depth_Range_M with value 10 as a named constant MIN_DEPTH_RANGE_M.
4. THE Config_Module SHALL define Max_Span with value 1 hour as a named constant MAX_SPAN.
5. THE Config_Module SHALL define the default Gap_Threshold with value 5 minutes as a named constant.
6. THE ShelfCast_Pipeline SHALL read Study_Region, Min_Readings, Min_Depth_Range_M, Max_Span, and the default Gap_Threshold from the Config_Module.

### Requirement 2: Lean Command-Line Entry

**User Story:** As an operator, I want a lean command-line entry point, so that I can run Stage 1 with explicit input and output paths and an adjustable gap threshold.

#### Acceptance Criteria

1. THE CLI_Entry SHALL accept an input path argument identifying the Raw_Archive.
2. THE CLI_Entry SHALL accept an output path argument identifying the Output_Directory.
3. THE CLI_Entry SHALL accept a gap threshold argument that overrides the default Gap_Threshold.
4. WHERE the gap threshold argument is omitted, THE ShelfCast_Pipeline SHALL use the default Gap_Threshold from the Config_Module.
5. WHEN the CLI_Entry is invoked with valid input and output paths, THE ShelfCast_Pipeline SHALL execute the Stage 1 processing sequence and write the output artifacts to the Output_Directory.

### Requirement 3: Archive Loading and Parsing

**User Story:** As a data engineer, I want the raw archive loaded and parsed reliably, so that downstream steps operate on typed, validated readings.

#### Acceptance Criteria

1. WHEN the ShelfCast_Pipeline loads the Raw_Archive, THE ShelfCast_Pipeline SHALL read the Source_CSV from within the ZIP using the standard library zipfile module.
2. WHEN the ShelfCast_Pipeline reads the Source_CSV, THE ShelfCast_Pipeline SHALL parse the file using pandas.
3. WHEN the ShelfCast_Pipeline parses the `time` column, THE ShelfCast_Pipeline SHALL interpret each value as a UTC ISO 8601 timestamp with a trailing `Z` designator.
4. WHEN the ShelfCast_Pipeline parses the `latitude`, `longitude`, `depth_m`, and `temperature_c` columns, THE ShelfCast_Pipeline SHALL interpret each value as a numeric value.
5. IF a Reading cannot be parsed into a valid UTC timestamp or a valid numeric value for a required column, THEN THE ShelfCast_Pipeline SHALL exclude that Reading from further processing and count it as a rejected Reading.
6. WHEN the ShelfCast_Pipeline encounters Readings that are exact duplicates across all columns, THE ShelfCast_Pipeline SHALL retain one Reading and remove the remaining duplicate Readings.
7. IF a Reading has a required value that is missing, THEN THE ShelfCast_Pipeline SHALL treat that Reading as an invalid Reading.
8. IF a Reading has a required value that is unparseable for its column type, THEN THE ShelfCast_Pipeline SHALL treat that Reading as an invalid Reading.
9. IF a Reading has a numeric value that is non-finite as NaN or infinity, THEN THE ShelfCast_Pipeline SHALL treat that Reading as an invalid Reading.
10. IF a Reading has a latitude outside the range -90 to 90 inclusive or a longitude outside the range -180 to 180 inclusive, THEN THE ShelfCast_Pipeline SHALL treat that Reading as an invalid Reading.
11. IF a Reading has a negative depth_m value, THEN THE ShelfCast_Pipeline SHALL treat that Reading as an invalid Reading.
12. THE ShelfCast_Pipeline SHALL reject the temperature_c value of a Reading only WHERE the temperature_c value is missing, unparseable, or non-finite.

### Requirement 4: Missing and Invalid Data Reporting

**User Story:** As a data engineer, I want invalid and missing data detected and reported, so that data quality is transparent even when the current copy is clean.

#### Acceptance Criteria

1. WHEN the ShelfCast_Pipeline processes the parsed Readings, THE ShelfCast_Pipeline SHALL identify Readings that have a missing value in any required column.
2. WHEN the ShelfCast_Pipeline processes the parsed Readings, THE ShelfCast_Pipeline SHALL identify an invalid Reading as a Reading that has a required value that is missing, a required value that is unparseable, a numeric value that is non-finite as NaN or infinity, a latitude outside -90 to 90 inclusive, a longitude outside -180 to 180 inclusive, or a negative depth_m value.
3. THE ShelfCast_Pipeline SHALL reject the temperature_c value of a Reading only WHERE the temperature_c value is missing, unparseable, or non-finite.
4. IF a Reading has a missing or invalid value in any required column, THEN THE ShelfCast_Pipeline SHALL exclude that Reading from further processing.
5. THE ShelfCast_Pipeline SHALL record the count of excluded Readings in the Stage1_Report_File.

### Requirement 5: Study Region Selection

**User Story:** As a researcher, I want readings restricted to the study region, so that analysis focuses on the area of interest.

#### Acceptance Criteria

1. WHEN the ShelfCast_Pipeline filters Readings by region, THE ShelfCast_Pipeline SHALL retain only Readings whose latitude is within the Study_Region latitude bounds and whose longitude is within the Study_Region longitude bounds.
2. THE ShelfCast_Pipeline SHALL exclude Readings outside the Study_Region from Candidate_Profile grouping.
3. THE ShelfCast_Pipeline SHALL record the count of Readings within the Study_Region in the Stage1_Report_File.

### Requirement 6: Provisional Candidate Profile Grouping

**User Story:** As a researcher, I want nearby readings grouped into provisional candidate profiles under explicit rules, so that structure can be inferred without overstating the data.

#### Acceptance Criteria

1. WHEN the ShelfCast_Pipeline groups Readings, THE ShelfCast_Pipeline SHALL group Readings that share the same recorded latitude and the same recorded longitude.
2. WHEN the ShelfCast_Pipeline groups Readings at a shared location, THE ShelfCast_Pipeline SHALL separate the Readings into groups wherever the time difference between consecutive Readings exceeds the Gap_Threshold.
3. THE ShelfCast_Pipeline SHALL retain a group as a Candidate_Profile only WHERE the group contains at least Min_Readings Readings.
4. THE ShelfCast_Pipeline SHALL retain a group as a Candidate_Profile only WHERE the difference between the maximum depth and the minimum depth in the group is at least Min_Depth_Range_M.
5. IF adding the next Reading to a group would make the group span a time difference greater than Max_Span between its earliest and latest Reading, THEN THE ShelfCast_Pipeline SHALL start a new group beginning at that next Reading and SHALL retain the earlier portion of the group as its own candidate group.
6. THE ShelfCast_Pipeline SHALL subject every group produced by a Max_Span split to the Min_Readings and Min_Depth_Range_M retention rules.
7. WHEN the ShelfCast_Pipeline retains a Candidate_Profile, THE ShelfCast_Pipeline SHALL assign a unique Profile_Id to that Candidate_Profile.
8. THE ShelfCast_Pipeline SHALL record the grouping rules in the Stage1_Report_File.
9. THE ShelfCast_Pipeline SHALL label grouped Readings as provisional Candidate_Profiles and SHALL NOT present any Candidate_Profile as a verified fishing tow or cast.
10. THE ShelfCast_Pipeline SHALL record in the Stage1_Report_File that the Raw_Archive starter ZIP omits the `tow_id` and `segment_type` columns that the full eMOLT source provides, and SHALL omit any tow identifier, cast identifier, or segment-type label from the output artifacts.

### Requirement 7: Output Artifacts

**User Story:** As a researcher, I want cleaned points, a profile summary, and a processing report written to disk, so that Stage 1 outputs can feed later stages.

#### Acceptance Criteria

1. WHEN the ShelfCast_Pipeline completes grouping, THE ShelfCast_Pipeline SHALL write the Profile_Points_File to the Output_Directory containing every retained Reading together with its Profile_Id.
2. WHEN the ShelfCast_Pipeline completes grouping, THE ShelfCast_Pipeline SHALL write the Profile_Summary_File to the Output_Directory containing one row per Candidate_Profile.
3. WHEN the ShelfCast_Pipeline completes processing, THE ShelfCast_Pipeline SHALL write the Stage1_Report_File to the Output_Directory using the standard library json module.
4. THE Stage1_Report_File SHALL contain the input Reading count, the rejected Reading count, the regional Reading count, and the retained Reading count.
5. THE Stage1_Report_File SHALL contain the grouping rules applied during Stage 1.

### Requirement 8: Documentation, Ignore Rules, Tests, and Steering

**User Story:** As a contributor, I want project documentation, ignore rules, tests, and steering, so that the repository is reproducible and scoped correctly.

#### Acceptance Criteria

1. THE ShelfCast_Pipeline SHALL be accompanied by a README that states the exact command used to run Stage 1 and the dataset attribution.
2. THE ShelfCast_Pipeline SHALL be accompanied by a `.gitignore` that excludes generated output artifacts and the local Raw_Archive while keeping the `.kiro/` directory tracked.
3. THE ShelfCast_Pipeline SHALL be accompanied by automated tests that verify timestamp and numeric parsing behavior.
4. THE ShelfCast_Pipeline SHALL be accompanied by automated tests that verify Candidate_Profile grouping behavior.
5. THE ShelfCast_Pipeline SHALL be accompanied by a workspace steering file that states the ShelfCast purpose and the Stage 1 scope limits.
6. WHEN the Stage 1 command is executed against the local Raw_Archive, THE ShelfCast_Pipeline SHALL complete the processing sequence and write the output artifacts.
