from __future__ import annotations

import argparse
import requests
import sys
from pathlib import Path

from .ta_importer import export_trips_csv_from_existing_browser


def check_cdp_available(cdp_url: str = "http://localhost:9222") -> bool:
    """Check if a browser with remote debugging is available."""
    try:
        response = requests.get(f"{cdp_url}/json/version", timeout=2)
        return response.status_code == 200
    except Exception:
        return False


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export TripAdvisor Trips from an existing browser session (checks for debugging automatically)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
This script connects to an existing browser session that has remote debugging enabled.

QUICK START:

1. Launch Brave with remote debugging (choose one method):

   Method A - Use the helper script:
     ./launch_brave_debug.sh

   Method B - Command line:
     "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser" \\
       --remote-debugging-port=9222 \\
       --user-data-dir=/tmp/brave-debug

   Method C - If you have a normal Brave session open:
     - Close your current Brave browser
     - Launch with the command above
     - Then log in and go to tripadvisor.com/Trips

2. In that browser:
   - Log into TripAdvisor
   - Navigate to https://www.tripadvisor.com/Trips

3. Run this script:
   python -m src.cli_ta_export_existing_smart --output output/places.csv

The script will automatically detect if debugging is enabled.
        """
    )
    parser.add_argument("--output", default="output/tripadvisor_places.csv", help="Output CSV path")
    parser.add_argument("--cdp-url", default="http://localhost:9222", help="Chrome DevTools Protocol URL")
    parser.add_argument("--skip-check", action="store_true", help="Skip checking for debugging availability")
    args = parser.parse_args()

    # Check if remote debugging is available
    if not args.skip_check:
        print("Checking for browser with remote debugging enabled...")
        if not check_cdp_available(args.cdp_url):
            print("\n❌ No browser with remote debugging found!")
            print("\n" + "="*60)
            print("SETUP REQUIRED:")
            print("="*60)
            print("\nYou need to launch Brave with remote debugging enabled.")
            print("\nOption 1: Use the helper script (in this directory):")
            print("  ./launch_brave_debug.sh")
            print("\nOption 2: Manual launch command:")
            print('  "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser" \\')
            print('    --remote-debugging-port=9222 \\')
            print('    --user-data-dir=/tmp/brave-debug')
            print("\n⚠️  IMPORTANT:")
            print("  - You CANNOT connect to a normal browser session")
            print("  - The browser MUST be launched with --remote-debugging-port")
            print("  - If you have Brave open normally, close it first")
            print("\nAfter launching with debugging:")
            print("  1. Log into TripAdvisor")
            print("  2. Navigate to https://www.tripadvisor.com/Trips")
            print("  3. Run this script again")
            print("\n" + "="*60)
            sys.exit(1)
        else:
            print("✓ Found browser with remote debugging enabled")
            print()

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    
    export_trips_csv_from_existing_browser(
        output_csv=str(out),
        cdp_url=args.cdp_url
    )


if __name__ == "__main__":
    main()



