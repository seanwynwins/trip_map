from __future__ import annotations

import argparse
from pathlib import Path

from .ta_importer import export_trips_csv_from_existing_browser


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export TripAdvisor Trips from an existing browser session",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
This script connects to an existing browser session that you've already opened.
This avoids CAPTCHA issues since you're using your normal browser.

SETUP INSTRUCTIONS:

1. Launch your browser with remote debugging enabled:

   For Brave (macOS):
     "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser" \\
       --remote-debugging-port=9222 \\
       --user-data-dir=/tmp/brave-debug

   For Chrome (macOS):
     "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \\
       --remote-debugging-port=9222 \\
       --user-data-dir=/tmp/chrome-debug

2. In that browser:
   - Log into TripAdvisor
   - Navigate to https://www.tripadvisor.com/Trips
   - Make sure your trips are visible

3. Run this script:
   python -m src.cli_ta_export_existing --output output/tripadvisor_places.csv

Example:
  python -m src.cli_ta_export_existing --output output/places.csv --cdp-url http://localhost:9222
        """
    )
    parser.add_argument("--output", default="output/tripadvisor_places.csv", help="Output CSV path")
    parser.add_argument("--cdp-url", default="http://localhost:9222", help="Chrome DevTools Protocol URL (default: http://localhost:9222)")
    args = parser.parse_args()

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    
    export_trips_csv_from_existing_browser(
        output_csv=str(out),
        cdp_url=args.cdp_url
    )


if __name__ == "__main__":
    main()


