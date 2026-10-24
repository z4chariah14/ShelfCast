"""ShelfCast Stage 2 chronological-split command-line entry point.

Run from the project root:

    python Scripts/split_replay.py

Reads the Stage 1 outputs, classifies each provisional candidate profile as a
whole against the fixed cutoff, runs all integrity checks, and -- only if every
check passes -- writes the four local, git-ignored artifacts to Data/splits/.
Exits non-zero on failure with a clear message.
"""

from __future__ import annotations

import argparse
import os
import sys

# Allow running as a script from the project root without installation.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shelfcast import split  # noqa: E402
from shelfcast.config import CUTOFF, PROCESSED_DIR, SPLITS_DIR  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="ShelfCast Stage 2 chronological replay split"
    )
    parser.add_argument("--processed", default=PROCESSED_DIR)
    parser.add_argument(
        "--output", "--splits", dest="output", default=SPLITS_DIR
    )
    args = parser.parse_args(argv)

    try:
        summary_df, points_df = split.load_stage1_outputs(args.processed)
        classification = split.classify_profiles(summary_df, CUTOFF)

        labeled = points_df.merge(
            classification[["profile_id", "label"]],
            on="profile_id",
            how="left",
        )
        train_points = labeled[labeled["label"] == "train"][split.POINT_COLUMNS]
        heldout_points = labeled[labeled["label"] == "heldout"][
            split.POINT_COLUMNS
        ]

        # All integrity checks run here, before any write.
        split.check_integrity(
            summary_df, points_df, classification, train_points, heldout_points
        )

        heldout_ids = classification.loc[
            classification["label"] == "heldout", "profile_id"
        ]
        candidate_sites = split.build_candidate_sites(summary_df, heldout_ids)
        report = split.build_split_report(classification, points_df, CUTOFF)
        split.write_split_outputs(
            args.output, train_points, heldout_points, candidate_sites, report
        )
    except (FileNotFoundError, KeyError, ValueError) as exc:
        # IntegrityError subclasses ValueError, so it is caught here too.
        print(f"Stage 2 split failed: {exc}", file=sys.stderr)
        return 1

    print(
        "Stage 2 split complete: "
        f"train={report['train']['profile_count']} "
        f"heldout={report['heldout']['profile_count']} "
        f"excluded={report['excluded']['profile_count']} (profiles); "
        f"outputs written to {args.output}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
