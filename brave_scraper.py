# scrape_via_brave.py
# Requirements:
#   pip install playwright beautifulsoup4 pandas
#   python -m playwright install
#
# Usage:
#   1) Start Brave with remote debugging (see instructions).
#   2) Log in and open Trips in that Brave window.
#   3) Run: python scrape_via_brave.py

from playwright.sync_api import sync_playwright, Error
from bs4 import BeautifulSoup
import pandas as pd
import time
from urllib.parse import urljoin

CDP_URL = "http://127.0.0.1:9222"   # must match --remote-debugging-port
BASE = "https://www.tripadvisor.com"
TRIPS_URL = "https://www.tripadvisor.com/Trips"
OUTPUT_CSV = "places.csv"

def try_click_load_more(page, timeout_ms=2000):
    # Try a few heuristics to click "Load more"/"Show more" until it disappears.
    for _ in range(8):
        try:
            # common texts: 'Load more', 'Show more', aria-labels may differ
            btn = page.query_selector("button:has-text('Load more'), button:has-text('Show more'), button[aria-label*='more']")
            if not btn:
                break
            btn.click(timeout=2000)
            page.wait_for_timeout(700)  # wait for new items to render
        except Exception:
            break

def extract_trips_index(html):
    soup = BeautifulSoup(html, "html.parser")
    anchors = soup.select('div[data-automation^="trip-card-"] a[href^="/TripDetails-"], a[href^="/TripDetails-"]')
    trips = []
    for a in anchors:
        href = a.get("href")
        title = a.get_text(strip=True)
        if href:
            trips.append({"title": title, "href": href})
    # dedupe by href
    uniq = {t['href']: t for t in trips}
    return list(uniq.values())

def extract_places_from_trip(html):
    soup = BeautifulSoup(html, "html.parser")
    out = []
    place_items = soup.select('div.HSuGR.e')
    if not place_items:
        # fallback: use the header link containers
        place_items = soup.select('[data-automation="cardHeaderTitleLink"]')
    for item in place_items:
        # item may be an <a> or a wrapper div
        item_soup = item if getattr(item, "name", "") != "a" else item.parent
        name_el = item_soup.select_one('[data-automation="trip_item_card_title"]')
        name = name_el.get_text(strip=True) if name_el else (item_soup.get_text(strip=True)[:200] if item_soup else None)
        url_el = item_soup.select_one('a[data-automation="cardHeaderTitleLink"]')
        url = url_el.get("href") if url_el else None
        city_el = item_soup.select_one('[data-automation="trip_item_label"] a')
        city = city_el.get_text(strip=True) if city_el else None
        category_el = item_soup.select_one('[data-automation="trip_item_destination"]')
        category = category_el.get_text(strip=True) if category_el else None
        if name:
            out.append({
                "place_name": name,
                "place_url": urljoin(BASE, url) if url else None,
                "place_city_text": city,
                "place_category": category
            })
    return out

def main():
    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(CDP_URL)
        except Error as e:
            print("ERROR connecting to Brave CDP. Is Brave running with --remote-debugging-port=9222 ?")
            print(e)
            return

        # Try to find an open page with Trips already loaded
        trips_page = None
        for ctx in browser.contexts:
            for pg in ctx.pages:
                try:
                    u = pg.url or ""
                except Exception:
                    u = ""
                if "/Trips" in u or "Trip" in pg.title():
                    trips_page = pg
                    break
            if trips_page:
                break

        # If no page found, open Trips in the first context
        if not trips_page:
            ctx = browser.contexts[0] if browser.contexts else browser.new_context()
            trips_page = ctx.new_page()
            trips_page.goto(TRIPS_URL)
            print("Opened Trips page. If not logged in, please log in manually in the Brave window and then press Enter here.")
            input("Press Enter to continue after log in and expanding content...")

        # Ensure content fully expanded
        try_click_load_more(trips_page)
        index_html = trips_page.content()
        trips = extract_trips_index(index_html)
        print(f"Found {len(trips)} trips (sample):", trips[:4])

        all_places = []
        for t in trips:
            href = t.get("href")
            if not href:
                continue
            url = urljoin(BASE, href)
            print("Visiting trip:", t.get("title") or href)
            # open in the same page (or a new page)
            page = trips_page.context.new_page()
            page.goto(url)
            page.wait_for_timeout(1000)
            try_click_load_more(page)
            trip_html = page.content()
            places = extract_places_from_trip(trip_html)
            for p in places:
                p["trip_title"] = t.get("title")
                p["trip_href"] = href
                all_places.append(p)
            page.close()
            time.sleep(0.6)  # polite pacing

        if all_places:
            df = pd.DataFrame(all_places)
            df.to_csv(OUTPUT_CSV, index=False)
            print(f"Saved {len(df)} places to {OUTPUT_CSV}")
        else:
            print("No places extracted. Check that Trips pages are expanded and visible in Brave.")

if __name__ == "__main__":
    main()
