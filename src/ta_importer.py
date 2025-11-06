from __future__ import annotations

import csv
import json
import random
import re
import time
from pathlib import Path
from typing import Dict, List, Optional

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from .geocode import geocode_city_for_place


OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"
CACHE_DIR = Path(__file__).resolve().parent.parent / "cache" / "tripadvisor"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _extract_json_ld(html: str) -> List[Dict]:
    soup = BeautifulSoup(html, "lxml")
    data: List[Dict] = []
    for tag in soup.select('script[type="application/ld+json"]'):
        try:
            payload = json.loads(tag.text)
            if isinstance(payload, dict):
                data.append(payload)
            elif isinstance(payload, list):
                data.extend([p for p in payload if isinstance(p, dict)])
        except Exception:
            continue
    return data


def _extract_place_links_from_html(html: str) -> set[str]:
    """Extract place links from TripAdvisor trips page HTML."""
    import urllib.parse
    links = set()
    
    # Method 1: Extract URLs from JSON-encoded data (URL-encoded in HTML)
    # Pattern: %2FAttraction...\.html (URL-encoded forward slash)
    url_pattern = r'%2F(AttractionReview|Attraction_Review|AttractionProductReview|Restaurant_[^%]+|Hotel_[^%]+|VacationRentalReview)-[^%]+\.html'
    
    for match in re.finditer(url_pattern, html, re.IGNORECASE):
        url_path = match.group(0)
        # Decode URL encoding
        url_path = urllib.parse.unquote(url_path)
        if url_path.startswith("/"):
            full_url = "https://www.tripadvisor.com" + url_path
            links.add(full_url)
    
    # Method 2: Extract from anchor tags (fallback)
    soup = BeautifulSoup(html, "lxml")
    for a in soup.select("a[href]"):
        href = a.get("href") or ""
        if re.search(r"/(AttractionReview|Attraction_Review|AttractionProductReview|Restaurant_.*|Hotel_.*|VacationRentalReview)-", href):
            if href.startswith("/"):
                href = "https://www.tripadvisor.com" + href
            links.add(href)
    
    return links


def _parse_place(html: str) -> Dict:
    # Try JSON-LD first
    for obj in _extract_json_ld(html):
        if obj.get("@type") in {"Place", "TouristAttraction", "LocalBusiness"}:
            address = obj.get("address", {}) or {}
            return {
                "name": obj.get("name"),
                "city": address.get("addressLocality"),
                "state": address.get("addressRegion"),
                "country": address.get("addressCountry"),
            }
    # Fallback: basic heuristics from meta tags or breadcrumbs
    soup = BeautifulSoup(html, "lxml")
    breadcrumb = soup.select_one("nav[aria-label='Breadcrumbs']") or soup.select_one("ol.breadcrumbs")
    city = state = country = None
    if breadcrumb:
        parts = [a.get_text(strip=True) for a in breadcrumb.select("a")]
        # Heuristic: last few parts include city/state/country
        for part in reversed(parts[-4:]):
            if not country and re.search(r"United|Kingdom|States|Canada|China|Japan|France|Germany|Mexico|Italy|Spain", part, re.I):
                country = part
            elif not state and len(part) <= 20 and re.match(r"[A-Z]{2}$", part):
                state = part
            elif not city and len(part) <= 40:
                city = part
    return {"name": soup.title.text.strip() if soup.title else None, "city": city, "state": state, "country": country}


def export_trips_csv(output_csv: str, browser_profile: Optional[str] = None, browser_executable: Optional[str] = None) -> None:
    """
    Launch a browser, navigate to user's TripAdvisor Trips, and collect places.
    Requires you to log in manually once; session persists via user-data-dir (browser_profile).
    
    Args:
        output_csv: Path to output CSV file
        browser_profile: Optional path for persistent browser profile
        browser_executable: Optional path to browser executable (e.g., Brave browser path)
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = Path(output_csv)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        launch_args = {
            "user_data_dir": browser_profile or str(CACHE_DIR / "profile"),
            "headless": False,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ],
        }
        if browser_executable:
            launch_args["executable_path"] = browser_executable
        
        browser = p.chromium.launch_persistent_context(**launch_args)
        page = browser.new_page()
        
        # Add stealth: remove webdriver property and set realistic viewport
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)
        page.set_viewport_size({"width": 1920, "height": 1080})
        
        # Set realistic user agent
        page.set_extra_http_headers({
            "Accept-Language": "en-US,en;q=0.9",
        })

        # 1) Go to Trips overview with random delay
        print("Navigating to TripAdvisor...")
        time.sleep(random.uniform(1, 3))
        page.goto("https://www.tripadvisor.com/Trips", wait_until="domcontentloaded")
        time.sleep(random.uniform(2, 4))  # Wait for page to fully load

        # If not logged in, user logs in manually; wait for trips content
        print("Waiting for page to load... If you see a CAPTCHA, please solve it manually.")
        print("Make sure you are logged in to TripAdvisor and on the Trips page.")
        print("The script will automatically extract data once the page is ready.")
        print()
        
        # Wait for page to be ready - try multiple approaches
        max_wait = 120000  # 2 minutes
        start_time = time.time()
        trips_ready = False
        
        while time.time() - start_time < max_wait:
            try:
                # Try to find trips content - wait briefly
                page.wait_for_selector("[data-test-target='tripsMainContent']", timeout=5000)
                trips_ready = True
                break
            except Exception:
                # Check if page has loaded by trying to extract links
                html = page.content()
                links = _extract_place_links_from_html(html)
                if len(links) > 0:
                    print(f"✓ Found {len(links)} place links - page is ready!")
                    trips_ready = True
                    break
                # Brief wait before checking again
                time.sleep(3)
        
        if not trips_ready:
            print("⚠️  Could not automatically detect trips content.")
            print("   Continuing anyway - make sure you're logged in and on the trips page.")
            time.sleep(2)

        # 2) Find links to places within all trips (load more as needed)
        # Scroll to load content with human-like behavior
        print("Scrolling through your trips to load all places...")
        for i in range(15):
            # Random scroll amount
            scroll_amount = random.randint(300, 800)
            page.mouse.wheel(0, scroll_amount)
            # Random delay between scrolls
            time.sleep(random.uniform(0.5, 1.5))
            # Occasionally scroll back up a bit (human behavior)
            if i % 5 == 0 and i > 0:
                page.mouse.wheel(0, -random.randint(100, 300))
                time.sleep(random.uniform(0.3, 0.8))

        # Capture place links - these anchors usually have hrefs to /AttractionReview- or /Restaurant_ etc.
        links = _extract_place_links_from_html(page.content())

        print(f"Found {len(links)} place links. Fetching details...")

        records: List[Dict] = []
        total = len(links)
        for i, url in enumerate(sorted(links), 1):
            try:
                print(f"Processing {i}/{total}: {url[:60]}...")
                p2 = browser.new_page()
                # Add stealth to new page too
                p2.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                """)
                p2.set_viewport_size({"width": 1920, "height": 1080})
                
                # Random delay before navigating
                time.sleep(random.uniform(0.5, 1.5))
                p2.goto(url, wait_until="domcontentloaded", timeout=30000)
                # Random wait after page load
                time.sleep(random.uniform(1, 2))
                html = p2.content()
                p2.close()
                
                # Random delay between pages
                if i < total:
                    time.sleep(random.uniform(0.3, 1.0))

                parsed = _parse_place(html)
                # Fallback geocoding if city missing
                if not parsed.get("city"):
                    geo = geocode_city_for_place(parsed.get("name"), url)
                    parsed.update({
                        "city": geo.get("city"),
                        "state": geo.get("state"),
                        "country": geo.get("country"),
                    })
                parsed["source_url"] = url
                records.append(parsed)
            except Exception as e:
                print(f"Failed to parse {url}: {e}")

        # Write CSV
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
        browser.close()

    print(f"Exported {len(records)} places to {out_path}")


def export_trips_csv_from_html(html_file: str, output_csv: str, use_browser: bool = False) -> None:
    """
    Extract place links from a saved TripAdvisor HTML file and export to CSV.
    
    This is useful when you manually log in and save the trips page HTML.
    
    Args:
        html_file: Path to saved HTML file from TripAdvisor trips page
        output_csv: Path to output CSV file
        use_browser: If True, use browser to fetch place details. If False, only extract links from HTML.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    html_path = Path(html_file)
    out_path = Path(output_csv)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    if not html_path.exists():
        raise FileNotFoundError(f"HTML file not found: {html_file}")
    
    print(f"Reading HTML from {html_path}...")
    html_content = html_path.read_text(encoding="utf-8")
    
    # Extract place links from HTML
    links = _extract_place_links_from_html(html_content)
    print(f"Found {len(links)} place links in HTML.")
    
    if not links:
        print("⚠️  No place links found in HTML. Make sure you saved the full trips page HTML.")
        print("   Try scrolling to load all your trips before saving the page.")
        return
    
    if not use_browser:
        # Just extract what we can from the HTML (limited, but no browser needed)
        print("⚠️  Browser mode disabled. Extracting basic info from HTML only.")
        print("   For full data extraction, use --use-browser flag (requires browser automation).")
        records: List[Dict] = []
        for url in sorted(links):
            # Try to extract basic info from URL or HTML if possible
            records.append({
                "name": None,
                "city": None,
                "state": None,
                "country": None,
                "source_url": url,
            })
        
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
        
        print(f"Exported {len(records)} place URLs to {out_path}")
        print("Note: For full place details, use --use-browser to fetch location data.")
        return
    
    # Use browser to fetch full details for each place
    print(f"Fetching details for {len(links)} places using browser...")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)
        
        records: List[Dict] = []
        total = len(links)
        for i, url in enumerate(sorted(links), 1):
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
    
    print(f"Exported {len(records)} places to {out_path}")


def export_trips_csv_from_existing_browser(output_csv: str, cdp_url: str = "http://localhost:9222") -> None:
    """
    Connect to an existing browser session and extract TripAdvisor trips.
    
    This approach requires you to:
    1. Launch your browser with remote debugging enabled
    2. Log in to TripAdvisor manually
    3. Navigate to your trips page (https://www.tripadvisor.com/Trips)
    4. Run this script to extract data
    
    Args:
        output_csv: Path to output CSV file
        cdp_url: Chrome DevTools Protocol endpoint (default: http://localhost:9222)
    
    Example browser launch commands:
        Brave (macOS):
            "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser" --remote-debugging-port=9222 --user-data-dir=/tmp/brave-debug
        
        Chrome (macOS):
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --remote-debugging-port=9222 --user-data-dir=/tmp/chrome-debug
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = Path(output_csv)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    print(f"Connecting to existing browser at {cdp_url}...")
    print("Make sure you have:")
    print("  1. Launched your browser with --remote-debugging-port=9222")
    print("  2. Logged into TripAdvisor")
    print("  3. Navigated to https://www.tripadvisor.com/Trips")
    print()
    
    with sync_playwright() as p:
        try:
            # Connect to existing browser via CDP
            browser = p.chromium.connect_over_cdp(cdp_url)
            print("✓ Connected to existing browser session")
            
            # Get all contexts (tabs)
            contexts = browser.contexts
            if not contexts:
                print("⚠️  No browser contexts found. Opening new page...")
                context = browser.new_context()
                pages = [context.new_page()]
            else:
                # Use existing pages
                pages = []
                for context in contexts:
                    pages.extend(context.pages)
            
            if not pages:
                print("⚠️  No pages found. Creating new page...")
                context = browser.new_context()
                pages = [context.new_page()]
            
            print(f"Found {len(pages)} page(s) in browser")
            
            # Try to find the trips page, or use the first page
            trips_page = None
            for page in pages:
                try:
                    url = page.url
                    if "tripadvisor.com" in url.lower() and "trips" in url.lower():
                        trips_page = page
                        print(f"✓ Found trips page: {url}")
                        break
                except Exception:
                    continue
            
            if not trips_page:
                # Use first page or navigate to trips
                trips_page = pages[0]
                current_url = trips_page.url
                print(f"Using page with URL: {current_url}")
                if "tripadvisor.com/trips" not in current_url.lower():
                    print("⚠️  Current page doesn't appear to be the trips page.")
                    print("   Please navigate to https://www.tripadvisor.com/Trips in your browser")
                    print("   Waiting for you to navigate...")
                    # Wait and check periodically
                    for _ in range(20):  # Wait up to 60 seconds
                        time.sleep(3)
                        current_url = trips_page.url
                        if "tripadvisor.com/trips" in current_url.lower():
                            print(f"✓ Found trips page: {current_url}")
                            break
                    # Refresh the page
                    trips_page.reload(wait_until="domcontentloaded")
                    time.sleep(2)
            
            # Wait for trips content to load - try to detect by extracting links
            print("Waiting for trips content...")
            max_wait = 30  # seconds
            start_time = time.time()
            trips_ready = False
            
            while time.time() - start_time < max_wait:
                try:
                    trips_page.wait_for_selector("[data-test-target='tripsMainContent']", timeout=5000)
                    trips_ready = True
                    break
                except Exception:
                    # Try to extract links to see if page is ready
                    html = trips_page.content()
                    links = _extract_place_links_from_html(html)
                    if len(links) > 0:
                        print(f"✓ Found {len(links)} place links - page is ready!")
                        trips_ready = True
                        break
                    time.sleep(2)
            
            if not trips_ready:
                print("⚠️  Could not find trips content selector. Continuing anyway...")
                print("   Current URL:", trips_page.url)
                print("   Make sure you're logged in and on the trips page.")
                time.sleep(2)
            
            # Scroll to load all content
            print("Scrolling to load all trips...")
            for i in range(20):
                trips_page.mouse.wheel(0, random.randint(300, 800))
                time.sleep(random.uniform(0.3, 0.8))
                if i % 5 == 0 and i > 0:
                    trips_page.mouse.wheel(0, -random.randint(100, 300))
                    time.sleep(0.3)
            
            time.sleep(2)  # Wait for content to settle
            
            # Extract place links
            html = trips_page.content()
            links = _extract_place_links_from_html(html)
            print(f"Found {len(links)} place links.")
            
            if not links:
                print("⚠️  No place links found. Make sure:")
                print("  - You're logged into TripAdvisor")
                print("  - You're on the trips page")
                print("  - You have saved trips with places")
                return
            
            # Fetch details for each place
            print(f"Fetching details for {len(links)} places...")
            records: List[Dict] = []
            total = len(links)
            
            # Use a new page for fetching details
            context = browser.new_context()
            detail_page = context.new_page()
            detail_page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """)
            
            for i, url in enumerate(sorted(links), 1):
                try:
                    print(f"Processing {i}/{total}: {url[:60]}...")
                    time.sleep(random.uniform(0.5, 1.5))
                    detail_page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    time.sleep(random.uniform(1, 2))
                    html = detail_page.content()
                    
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
            
            detail_page.close()
            
            # Write CSV
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
            
        except Exception as e:
            print(f"❌ Error connecting to browser: {e}")
            print("\nMake sure your browser is running with remote debugging enabled:")
            print("  Brave (macOS):")
            print('    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser" \\')
            print('      --remote-debugging-port=9222 \\')
            print('      --user-data-dir=/tmp/brave-debug')
            print("\n  Chrome (macOS):")
            print('    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \\')
            print('      --remote-debugging-port=9222 \\')
            print('      --user-data-dir=/tmp/chrome-debug')
            raise
