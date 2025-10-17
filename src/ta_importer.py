from __future__ import annotations

import csv
import json
import re
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


def export_trips_csv(output_csv: str, browser_profile: Optional[str] = None) -> None:
    """
    Launch a browser, navigate to user's TripAdvisor Trips, and collect places.
    Requires you to log in manually once; session persists via user-data-dir (browser_profile).
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = Path(output_csv)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=browser_profile or str(CACHE_DIR / "profile"),
            headless=False,
        )
        page = browser.new_page()

        # 1) Go to Trips overview
        page.goto("https://www.tripadvisor.com/Trips", wait_until="networkidle")

        # If not logged in, user logs in manually; wait for trips content
        page.wait_for_selector("[data-test-target='tripsMainContent']", timeout=120000)

        # 2) Find links to places within all trips (load more as needed)
        # Scroll to load content
        for _ in range(10):
            page.mouse.wheel(0, 2000)
            page.wait_for_timeout(500)

        # Capture place links - these anchors usually have hrefs to /AttractionReview- or /Restaurant_ etc.
        links = set()
        for a in page.query_selector_all("a[href]"):
            href = a.get_attribute("href") or ""
            if re.search(r"/(AttractionReview|Restaurant_.*|Hotel_.*|VacationRentalReview)-", href):
                if href.startswith("/"):
                    href = "https://www.tripadvisor.com" + href
                links.add(href)

        print(f"Found {len(links)} place links. Fetching details...")

        records: List[Dict] = []
        for i, url in enumerate(sorted(links)):
            try:
                p2 = browser.new_page()
                p2.goto(url, wait_until="domcontentloaded")
                p2.wait_for_timeout(1000)
                html = p2.content()
                p2.close()

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
