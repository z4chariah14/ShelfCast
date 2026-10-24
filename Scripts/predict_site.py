"""ShelfCast Stage 3 candidate-site prediction command-line entry point.

Run from the project root:

    python Scripts/predict_site.py --profile-id 4

Looks up a candidate site's recorded location and start time from
candidate_sites.csv (the only observational input it opens), loads the saved
model from Results/, predicts temperature at the requested prediction levels,
and emits a structured JSON object to stdout. Never opens heldout_points.csv or
profile_summary.csv. Exits non-zero with a clear message on failure.

Requested depths are REQUESTED PREDICTION LEVELS only; they are not the actual
bottom depth of a candidate profile or site. Groups are provisional candidate
profiles inferred from recorded position and time proximity, not verified
fishing tows or casts.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys

# Allow running as a script from the project root without installation.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shelfcast import model  # noqa: E402
from shelfcast.config import (  # noqa: E402
    CANDIDATE_SITES_PATH,
    DEFAULT_DEPTH_GRID,
    MODEL_PATH,
)


def _validate_depths(depths) -> None:
    invalid = [
        d
        for d in depths
        if not math.isfinite(d) or d <= 0.0
    ]
    if len(depths) == 0 or invalid:
        raise ValueError(
            "supplied depths must be a non-empty list of finite numbers "
            f"greater than 0 metres; invalid: {invalid if invalid else 'empty'}"
        )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="ShelfCast Stage 3 candidate-site temperature prediction"
    )
    parser.add_argument("--profile-id", type=int, required=True)
    parser.add_argument(
        "--depths",
        type=float,
        nargs="+",
        default=None,
        help="requested prediction levels in metres (finite, > 0); "
        "omit to use the default depth grid",
    )
    parser.add_argument("--model", default=MODEL_PATH)
    parser.add_argument("--sites", default=CANDIDATE_SITES_PATH)
    args = parser.parse_args(argv)

    try:
        if args.depths is None:
            depths = list(DEFAULT_DEPTH_GRID)
        else:
            _validate_depths(args.depths)
            depths = list(args.depths)

        if not os.path.exists(args.model):
            raise FileNotFoundError(
                f"model artifact not found: {args.model} "
                "(run Scripts/train_model.py first)"
            )
        fitted = model.load_model(args.model)

        # Raises KeyError (not found) or ValueError (ambiguous) as needed.
        site = model.lookup_candidate_site(args.profile_id, args.sites)

        temps = model.predict_temperatures(
            fitted,
            site["latitude"],
            site["longitude"],
            site["start_time"],
            depths,
        )
    except KeyError as exc:
        print(f"Stage 3 prediction failed: {exc}", file=sys.stderr)
        return 1
    except (FileNotFoundError, ValueError) as exc:
        print(f"Stage 3 prediction failed: {exc}", file=sys.stderr)
        return 1

    output = {
        "profile_id": args.profile_id,
        "utc_time": site["start_time"].isoformat(),
        "predictions": [
            {"depth_m": float(d), "temperature_c": float(t)}
            for d, t in zip(depths, temps)
        ],
    }
    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
