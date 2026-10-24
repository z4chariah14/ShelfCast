"""ShelfCast Stage 1 pipeline.

All processing functions live in this single module as separate, well-named
functions so the flow is easy to read while each stage stays individually
testable. Runtime code uses pandas and the standard library only -- no numpy.

Flow: load (raw) -> drop_duplicates (raw) -> coerce types -> classify/reject
-> region filter -> group -> retain -> write.
"""

from __future__ import annotations

import json
import math
import os
import zipfile
from datetime import timedelta

import pandas as pd

from shelfcast.config import (
    DEFAULT_GAP,
    LAT_MAX,
    LAT_MIN,
    LON_MAX,
    LON_MIN,
    MAX_SPAN,
    MIN_DEPTH_RANGE_M,
    MIN_READINGS,
    REQUIRED_COLUMNS,
    SOURCE_CSV_NAME,
    VALID_LAT_MAX,
    VALID_LAT_MIN,
    VALID_LON_MAX,
    VALID_LON_MIN,
)

NUMERIC_COLUMNS = ["latitude", "longitude", "depth_m", "temperature_c"]


# --------------------------------------------------------------------------
# Load (Requirement 3.1-3.4)
# --------------------------------------------------------------------------
def load_archive(zip_path: str, csv_name: str = SOURCE_CSV_NAME) -> pd.DataFrame:
    """Open the ZIP with zipfile and read csv_name with pandas as raw strings.

    Every column is read with dtype=str and NA filtering disabled
    (keep_default_na=False, na_filter=False) so the raw CSV values -- including
    any missing-value text -- are preserved verbatim for exact deduplication
    downstream. Type coercion is deferred to clean_readings.

    Raises FileNotFoundError if zip_path is absent.
    Raises KeyError if csv_name is not inside the archive.
    """
    if not os.path.exists(zip_path):
        raise FileNotFoundError(f"Raw archive not found: {zip_path}")

    with zipfile.ZipFile(zip_path) as archive:
        names = archive.namelist()
        if csv_name not in names:
            raise KeyError(
                f"{csv_name!r} not found inside archive {zip_path!r}; "
                f"members: {names}"
            )
        with archive.open(csv_name) as handle:
            df = pd.read_csv(
                handle,
                dtype=str,
                keep_default_na=False,
                na_filter=False,
            )
    return df


# --------------------------------------------------------------------------
# Clean / validate (Requirement 3.5-3.12, 4)
# --------------------------------------------------------------------------
def clean_readings(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Dedupe raw rows, coerce types, classify validity, drop invalid rows.

    Strict order (matters for accurate counts):
      1. drop_duplicates on the RAW string rows first,
      2. coerce types (time -> UTC datetime, numeric cols -> float),
      3. classify and reject invalid values,
      4. count duplicates and rejections.

    Returns (cleaned_df, counts) with input_count, duplicate_count,
    rejected_count.
    """
    input_count = len(df)

    # 1. Dedupe on raw string values (before any coercion).
    deduped = df.drop_duplicates(keep="first")
    duplicate_count = input_count - len(deduped)

    # 2. Coerce types on the deduplicated frame.
    coerced = deduped.copy()
    coerced["time"] = pd.to_datetime(
        coerced["time"], utc=True, format="ISO8601", errors="coerce"
    )
    for col in NUMERIC_COLUMNS:
        coerced[col] = pd.to_numeric(coerced[col], errors="coerce")

    # 3. Classify invalid rows. Start all-valid, then AND in each rule.
    valid = pd.Series(True, index=coerced.index)

    # Missing / unparseable -> NaT or NaN for any required column.
    for col in REQUIRED_COLUMNS:
        valid &= coerced[col].notna()

    # Non-finite numeric (NaN already excluded above; also catch +/-inf)
    # detected with pandas only, no numpy.
    for col in NUMERIC_COLUMNS:
        finite = coerced[col].map(
            lambda v: isinstance(v, (int, float)) and math.isfinite(v)
        )
        valid &= finite

    # Latitude / longitude physical bounds.
    valid &= (coerced["latitude"] >= VALID_LAT_MIN) & (
        coerced["latitude"] <= VALID_LAT_MAX
    )
    valid &= (coerced["longitude"] >= VALID_LON_MIN) & (
        coerced["longitude"] <= VALID_LON_MAX
    )

    # Negative depth is invalid.
    valid &= coerced["depth_m"] >= 0

    # Note: temperature_c is only rejected via the missing/unparseable/
    # non-finite checks above. No magnitude range is imposed.

    cleaned = coerced[valid].reset_index(drop=True)
    rejected_count = len(coerced) - len(cleaned)

    counts = {
        "input_count": input_count,
        "duplicate_count": duplicate_count,
        "rejected_count": rejected_count,
    }
    return cleaned, counts


# --------------------------------------------------------------------------
# Region filter (Requirement 5)
# --------------------------------------------------------------------------
def filter_region(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Keep rows inside the inclusive study region; return (regional_df, count)."""
    mask = (
        (df["latitude"] >= LAT_MIN)
        & (df["latitude"] <= LAT_MAX)
        & (df["longitude"] >= LON_MIN)
        & (df["longitude"] <= LON_MAX)
    )
    regional = df[mask].reset_index(drop=True)
    return regional, len(regional)


# --------------------------------------------------------------------------
# Grouping (Requirement 6)
# --------------------------------------------------------------------------
def build_profiles(
    df: pd.DataFrame, gap_threshold: timedelta
) -> tuple[pd.DataFrame, list[dict]]:
    """Group regional readings into retained provisional candidate profiles.

    Returns (points_df, summary_rows): points_df is every retained reading with
    a 'profile_id' column; summary_rows is one dict per retained profile.
    """
    retained_segments: list[pd.DataFrame] = []

    if len(df) > 0:
        # Partition by identical recorded (latitude, longitude).
        for _, partition in df.groupby(["latitude", "longitude"], sort=True):
            ordered = partition.sort_values("time").reset_index(drop=True)
            segments = _segment_partition(ordered, gap_threshold)
            for seg in segments:
                if _retain(seg):
                    retained_segments.append(seg)

    # Stable order: location, then start time.
    retained_segments.sort(
        key=lambda s: (
            s["latitude"].iloc[0],
            s["longitude"].iloc[0],
            s["time"].iloc[0],
        )
    )

    points_frames = []
    summary_rows: list[dict] = []
    for profile_id, seg in enumerate(retained_segments):
        seg = seg.copy()
        seg["profile_id"] = profile_id
        points_frames.append(seg)
        summary_rows.append(_summary_row(profile_id, seg))

    if points_frames:
        points_df = pd.concat(points_frames, ignore_index=True)
    else:
        cols = list(df.columns) + ["profile_id"]
        points_df = pd.DataFrame(columns=cols)

    return points_df, summary_rows


def _segment_partition(ordered: pd.DataFrame, gap_threshold: timedelta) -> list[pd.DataFrame]:
    """Split a time-ordered single-location partition into segments.

    Starts a new segment when the gap to the previous reading exceeds
    gap_threshold, OR when adding the next reading would make the segment span
    (earliest-to-latest) exceed MAX_SPAN. On a span split the earlier portion
    is retained and the new segment begins at the overflowing reading.
    """
    segments: list[pd.DataFrame] = []
    current_idx: list[int] = []

    for pos in range(len(ordered)):
        row_time = ordered["time"].iloc[pos]
        if not current_idx:
            current_idx = [pos]
            continue
        prev_time = ordered["time"].iloc[current_idx[-1]]
        start_time = ordered["time"].iloc[current_idx[0]]
        gap_break = (row_time - prev_time) > gap_threshold
        span_break = (row_time - start_time) > MAX_SPAN
        if gap_break or span_break:
            segments.append(ordered.iloc[current_idx].reset_index(drop=True))
            current_idx = [pos]
        else:
            current_idx.append(pos)

    if current_idx:
        segments.append(ordered.iloc[current_idx].reset_index(drop=True))

    return segments


def _retain(seg: pd.DataFrame) -> bool:
    """Apply retention rules: MIN_READINGS and MIN_DEPTH_RANGE_M."""
    if len(seg) < MIN_READINGS:
        return False
    depth_range = seg["depth_m"].max() - seg["depth_m"].min()
    return depth_range >= MIN_DEPTH_RANGE_M


def _summary_row(profile_id: int, seg: pd.DataFrame) -> dict:
    start = seg["time"].min()
    end = seg["time"].max()
    depth_min = float(seg["depth_m"].min())
    depth_max = float(seg["depth_m"].max())
    return {
        "profile_id": profile_id,
        "latitude": float(seg["latitude"].iloc[0]),
        "longitude": float(seg["longitude"].iloc[0]),
        "start_time": start.isoformat(),
        "end_time": end.isoformat(),
        "n_readings": int(len(seg)),
        "depth_min": depth_min,
        "depth_max": depth_max,
        "depth_range": depth_max - depth_min,
        "temp_min": float(seg["temperature_c"].min()),
        "temp_max": float(seg["temperature_c"].max()),
        "duration_seconds": (end - start).total_seconds(),
    }


# --------------------------------------------------------------------------
# Summary rows + report (Requirement 6.8, 6.10, 7.4, 7.5)
# --------------------------------------------------------------------------
def build_summary_rows(points_df: pd.DataFrame) -> list[dict]:
    """One summary row per profile_id, derived from a points frame."""
    rows: list[dict] = []
    if "profile_id" not in points_df.columns or len(points_df) == 0:
        return rows
    for profile_id, seg in points_df.groupby("profile_id", sort=True):
        rows.append(_summary_row(int(profile_id), seg.reset_index(drop=True)))
    return rows


def build_report(counts: dict, n_profiles: int, gap_threshold: timedelta) -> dict:
    """Assemble the stage1_report.json dict."""
    return {
        "counts": {
            "input_count": counts.get("input_count", 0),
            "duplicate_count": counts.get("duplicate_count", 0),
            "rejected_count": counts.get("rejected_count", 0),
            "regional_count": counts.get("regional_count", 0),
            "retained_count": counts.get("retained_count", 0),
            "profile_count": n_profiles,
        },
        "grouping_rules": {
            "gap_threshold_minutes": gap_threshold.total_seconds() / 60.0,
            "max_span_minutes": MAX_SPAN.total_seconds() / 60.0,
            "min_readings": MIN_READINGS,
            "min_depth_range_m": MIN_DEPTH_RANGE_M,
            "study_region": {
                "lat_min": LAT_MIN,
                "lat_max": LAT_MAX,
                "lon_min": LON_MIN,
                "lon_max": LON_MAX,
            },
        },
        "integrity_note": (
            "Groups are provisional candidate profiles inferred from recorded "
            "position and time proximity; they are NOT verified fishing tows "
            "or casts."
        ),
        "starter_zip_note": (
            "The released starter ZIP (Data/raw/emolt.zip) omits the tow_id and "
            "segment_type columns that the full eMOLT source provides. Stage 1 "
            "does not use them and omits any tow/cast/segment-type label from "
            "its outputs."
        ),
    }


# --------------------------------------------------------------------------
# Write outputs (Requirement 7.1-7.3)
# --------------------------------------------------------------------------
def write_outputs(
    out_dir: str,
    points_df: pd.DataFrame,
    summary_rows: list[dict],
    report: dict,
) -> None:
    """Create out_dir if needed, then write the three Stage 1 artifacts."""
    os.makedirs(out_dir, exist_ok=True)

    points_path = os.path.join(out_dir, "profile_points.csv")
    summary_path = os.path.join(out_dir, "profile_summary.csv")
    report_path = os.path.join(out_dir, "stage1_report.json")

    # profile_points.csv -- serialize timestamps as ISO 8601 strings.
    points_out = points_df.copy()
    if "time" in points_out.columns and len(points_out) > 0:
        points_out["time"] = points_out["time"].map(
            lambda t: t.isoformat() if pd.notna(t) else ""
        )
    points_out.to_csv(points_path, index=False)

    # profile_summary.csv -- header-only when empty.
    summary_columns = [
        "profile_id", "latitude", "longitude", "start_time", "end_time",
        "n_readings", "depth_min", "depth_max", "depth_range",
        "temp_min", "temp_max", "duration_seconds",
    ]
    summary_df = pd.DataFrame(summary_rows, columns=summary_columns)
    summary_df.to_csv(summary_path, index=False)

    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)


__all__ = [
    "load_archive",
    "clean_readings",
    "filter_region",
    "build_profiles",
    "build_summary_rows",
    "build_report",
    "write_outputs",
    "DEFAULT_GAP",
]
