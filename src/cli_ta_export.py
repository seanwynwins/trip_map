from __future__ import annotations

import argparse
from pathlib import Path

from .ta_importer import export_trips_csv


def main() -> None:
    parser = argparse.ArgumentParser(description="Export TripAdvisor Trips to a CSV")
    parser.add_argument("--output", default="output/tripadvisor_places.csv", help="Output CSV path")
    parser.add_argument("--profile", default=None, help="Optional path for persistent browser profile")
    args = parser.parse_args()

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    export_trips_csv(output_csv=str(out), browser_profile=args.profile)


if __name__ == "__main__":
    main()
