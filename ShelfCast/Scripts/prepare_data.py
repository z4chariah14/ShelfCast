"""ShelfCast Stage 1 command-line entry point.

Run from the project root:

    python Scripts/prepare_data.py

Lean CLI: input path, output directory, and an optional gap-minutes override.
Orchestrates the pipeline functions and exits non-zero on failure.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import timedelta

# Allow running as a script from the project root without installation.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shelfcast import pipeline  # noqa: E402
from shelfcast.config import DEFAULT_GAP  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="ShelfCast Stage 1 data pipeline"
    )
    parser.add_argument("--input", default="Data/raw/emolt.zip")
    parser.add_argument("--output", default="Data/processed")
    parser.add_argument("--gap-minutes", type=float, default=None)
    args = parser.parse_args(argv)

    gap = (
        timedelta(minutes=args.gap_minutes)
        if args.gap_minutes is not None
        else DEFAULT_GAP
    )

    try:
        raw = pipeline.load_archive(args.input)
        cleaned, counts = pipeline.clean_readings(raw)
        regional, counts["regional_count"] = pipeline.filter_region(cleaned)
        points, summary = pipeline.build_profiles(regional, gap)
        counts["retained_count"] = len(points)
        report = pipeline.build_report(
            counts, n_profiles=len(summary), gap_threshold=gap
        )
        pipeline.write_outputs(args.output, points, summary, report)
    except (FileNotFoundError, KeyError, ValueError) as exc:
        print(f"Stage 1 failed: {exc}", file=sys.stderr)
        return 1

    c = report["counts"]
    print(
        "Stage 1 complete: "
        f"input={c['input_count']} duplicates={c['duplicate_count']} "
        f"rejected={c['rejected_count']} regional={c['regional_count']} "
        f"retained={c['retained_count']} profiles={c['profile_count']}"
    )
    print(f"Outputs written to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
