from __future__ import annotations

import argparse
from pathlib import Path

from .ta_importer import export_trips_csv, export_trips_csv_from_html


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export TripAdvisor Trips to a CSV",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Automated mode (requires browser automation):
  python -m src.cli_ta_export --output output/places.csv

  # From saved HTML file (no automation, manual login):
  python -m src.cli_ta_export --from-html trips_page.html --output output/places.csv

  # From HTML with browser to fetch full details:
  python -m src.cli_ta_export --from-html trips_page.html --output output/places.csv --use-browser
        """
    )
    parser.add_argument("--output", default="output/tripadvisor_places.csv", help="Output CSV path")
    parser.add_argument("--from-html", help="Path to saved HTML file from TripAdvisor trips page (manual login)")
    parser.add_argument("--use-browser", action="store_true", help="Use browser to fetch full place details (requires --from-html)")
    parser.add_argument("--profile", default=None, help="Optional path for persistent browser profile (automated mode only)")
    parser.add_argument("--browser-executable", default=None, help="Path to browser executable (automated mode only)")
    args = parser.parse_args()

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    
    if args.from_html:
        # HTML file mode - user manually logged in and saved page
        export_trips_csv_from_html(
            html_file=args.from_html,
            output_csv=str(out),
            use_browser=args.use_browser
        )
    else:
        # Automated browser mode
        export_trips_csv(
            output_csv=str(out),
            browser_profile=args.profile,
            browser_executable=args.browser_executable
        )


if __name__ == "__main__":
    main()
