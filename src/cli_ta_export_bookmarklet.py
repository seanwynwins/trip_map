from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path

from .ta_importer import _parse_place
from playwright.sync_api import sync_playwright
from .geocode import geocode_city_for_place


def process_bookmarklet_json(json_file: str, output_csv: str, use_browser: bool = True) -> None:
    """
    Process a JSON file exported by the bookmarklet and create a CSV.
    
    Args:
        json_file: Path to JSON file from bookmarklet
        output_csv: Path to output CSV file
        use_browser: If True, use browser to fetch place details. If False, only extract URLs.
    """
    json_path = Path(json_file)
    out_path = Path(output_csv)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    if not json_path.exists():
        raise FileNotFoundError(f"JSON file not found: {json_file}")
    
    print(f"Reading JSON from {json_path}...")
    with json_path.open('r', encoding='utf-8') as f:
        data = json.load(f)
    
    links = data.get('places', [])
    print(f"Found {len(links)} place links in JSON.")
    
    if not links:
        print("⚠️  No place links found in JSON file.")
        return
    
    if not use_browser:
        # Just save URLs without fetching details
        import csv
        with out_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["place_name", "city", "state", "country", "source_url"])
            writer.writeheader()
            for url in links:
                writer.writerow({
                    "place_name": None,
                    "city": None,
                    "state": None,
                    "country": None,
                    "source_url": url,
                })
        print(f"Exported {len(links)} place URLs to {out_path}")
        print("Note: Use --use-browser to fetch full place details.")
        return
    
    # Use browser to fetch full details
    print(f"Fetching details for {len(links)} places using browser...")
    print("This will open a browser window and visit each place page.")
    
    records = []
    total = len(links)
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)
        
        for i, url in enumerate(links, 1):
            try:
                print(f"Processing {i}/{total}: {url[:60]}...")
                time.sleep(random.uniform(0.5, 1.5))
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                time.sleep(random.uniform(1, 2))
                html = page.content()
                
                parsed = _parse_place(html)
                if not parsed.get("city"):
                    geo = geocode_city_for_place(parsed.get("name"), url)
                    parsed.update({
                        "city": geo.get("city"),
                        "state": geo.get("state"),
                        "country": geo.get("country"),
                    })
                parsed["source_url"] = url
                records.append(parsed)
                
                if i < total:
                    time.sleep(random.uniform(0.3, 1.0))
            except Exception as e:
                print(f"Failed to parse {url}: {e}")
        
        browser.close()
    
    # Write CSV
    import csv
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["place_name", "city", "state", "country", "source_url"])
        writer.writeheader()
        for r in records:
            writer.writerow({
                "place_name": r.get("name"),
                "city": r.get("city"),
                "state": r.get("state"),
                "country": r.get("country"),
                "source_url": r.get("source_url"),
            })
    
    print(f"✓ Exported {len(records)} places to {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Process JSON file exported from TripAdvisor bookmarklet",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
HOW TO USE THE BOOKMARKLET:

1. Open the file: bookmarklet.js
2. Copy the entire JavaScript code
3. In your browser (Brave/Chrome):
   - Go to Bookmarks → Bookmark Manager
   - Click "Add new bookmark"
   - Name it: "Extract TripAdvisor Places"
   - Paste the JavaScript code as the URL
   - Save

4. On TripAdvisor:
   - Log in to TripAdvisor
   - Navigate to https://www.tripadvisor.com/Trips
   - Scroll to load all your trips
   - Click the bookmarklet you just created
   - A JSON file will download automatically

5. Process the JSON file:
   python -m src.cli_ta_export_bookmarklet --input tripadvisor_places_*.json --output output/places.csv

Example:
  python -m src.cli_ta_export_bookmarklet --input tripadvisor_places_1234567890.json --output output/places.csv
        """
    )
    parser.add_argument("--input", required=True, help="Path to JSON file from bookmarklet")
    parser.add_argument("--output", default="output/tripadvisor_places.csv", help="Output CSV path")
    parser.add_argument("--no-browser", action="store_true", help="Don't use browser to fetch details (only extract URLs)")
    args = parser.parse_args()

    process_bookmarklet_json(
        json_file=args.input,
        output_csv=args.output,
        use_browser=not args.no_browser
    )


if __name__ == "__main__":
    main()

