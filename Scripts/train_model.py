"""ShelfCast Stage 3 model-training command-line entry point.

Run from the project root:

    python Scripts/train_model.py

Fits an ExtraTreesRegressor on the Stage 2 training candidate profiles and --
only if the fit succeeds -- writes the serialized model and a small metadata
report under Results/. Reads train_points.csv as the only observational input;
never opens heldout_points.csv or profile_summary.csv. Exits non-zero on failure
with a clear message, writing no artifacts.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

# Allow running as a script from the project root without installation.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd  # noqa: E402

from shelfcast import model  # noqa: E402
from shelfcast.config import (  # noqa: E402
    METADATA_PATH,
    MODEL_PATH,
    RESULTS_DIR,
    TRAIN_POINTS_PATH,
)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="ShelfCast Stage 3 temperature-predictor training"
    )
    parser.add_argument("--train", default=TRAIN_POINTS_PATH)
    parser.add_argument("--model", default=MODEL_PATH)
    parser.add_argument("--metadata", default=METADATA_PATH)
    args = parser.parse_args(argv)

    try:
        if not os.path.exists(args.train):
            raise FileNotFoundError(f"training points not found: {args.train}")
        df = pd.read_csv(args.train)
        if len(df) == 0:
            raise ValueError(f"training points file is empty: {args.train}")

        # fit_model validates fully before fitting; no artifact is written if
        # validation or the fit raises.
        fitted = model.fit_model(df)

        n_rows = int(len(df))
        n_profiles = (
            int(df["profile_id"].nunique()) if "profile_id" in df.columns else 0
        )
        metadata = model.build_metadata(n_rows, n_profiles)

        os.makedirs(RESULTS_DIR, exist_ok=True)
        model.save_model(fitted, args.model)
        with open(args.metadata, "w", encoding="utf-8") as fh:
            json.dump(metadata, fh, indent=2)
    except (FileNotFoundError, KeyError, ValueError) as exc:
        print(f"Stage 3 training failed: {exc}", file=sys.stderr)
        return 1

    print(
        "Stage 3 training complete: "
        f"rows={n_rows} candidate_profiles={n_profiles}; "
        f"model written to {args.model}, metadata to {args.metadata}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
