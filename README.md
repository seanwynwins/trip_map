TODO: improve/fix chloropleth map, automate loading

README — TripAdvisor Trips → Places → Coordinates → Map
=========================================================

Overview

Goal: extract your personal TripAdvisor “Trips” data, obtain TripAdvisor location IDs (the -d<id>- detail_id), call the TripAdvisor Content API to get latitude/longitude for each place, and produce an aggregated dataset for mapping (choropleth/heatmap).
Important notes:
Only scrape your personal/authenticated data. Respect robots.txt, rate limits and site terms. Sites like TripAdvisor detect automation; using a real browser/profile reduces blocking risk
1
.
The Content API requires HTTPS and an API key and is partner/gated — key scope/referrer/IP rules commonly cause authorization errors
10
8
.
Prerequisites

macOS (commands shown below are for macOS; adjust paths for other OSes).
Brave browser installed.
Python 3.8+ and packages:
playwright, beautifulsoup4, pandas, requests, tqdm
Install: pip install playwright beautifulsoup4 pandas requests tqdm
Install Playwright browsers: python -m playwright install
Files you’ll create/run (examples used here):
scrape_via_brave.py — initial scraper (Playwright + BeautifulSoup) that outputs places.csv
enrich_with_api.py / enrich_with_api_debug_https.py — call Content API and output places_with_coords.csv
Cache files: coords_cache.json, ta_api_cache.json
Step 1 — Start Brave with remote debugging (so the script can reuse your real logged‑in session)

Close Brave, then run in Terminal (one line):



Bash
/Applications/Brave\ Browser.app/Contents/MacOS/Brave\ Browser --remote-debugging-port=9222 --user-data-dir="/tmp/ta-profile"
What this does:
Opens a separate Brave profile (no risk to your main profile) and exposes Chrome DevTools Protocol (CDP) on port 9222. Your Python Playwright script will connect to that running Brave instance and reuse the real logged‑in session (reduces likelihood of "Access blocked")
1
.
Step 2 — Log in, open Trips, expand items

In the Brave window you just opened:
Log into TripAdvisor manually.
Navigate to https://www.tripadvisor.com/Trips.
Click any “Load more” / expand buttons so all trip cards and place items you want are visible.
Step 3 — Initial scrape: extract trip cards and place links → produce places.csv

Run your Playwright scraper that connects to the running Brave CDP instance.
Typical workflow (script: scrape_via_brave.py):
Connect to CDP at http://127.0.0.1:9222
Find/open Trips page, click “Load more” heuristically
Extract place entries (name, place_url, city text, trip title)
Save output: places.csv
If you used the example script, run:



Bash
python scrape_via_brave.py
Output: places.csv (must include a place_url column that contains TripAdvisor links like /Attraction_Review-g45926-d3619312-Reviews-...).
Step 4 — Extract TripAdvisor detail_id from place URLs

The detail_id is the digits after -d in URL (e.g. -d3619312- → 3619312).
Quick Python snippet to parse and add detail_id column:



Python
import re, pandas as pd
df = pd.read_csv("places.csv")
df["detail_id"] = df["place_url"].fillna("").astype(str).apply(lambda u: re.search(r"-d(\d+)-", u).group(1) if re.search(r"-d(\d+)-", u) else None)
df.to_csv("places_with_ids.csv", index=False)
Save places_with_ids.csv for the next step.
Step 5 — Use the TripAdvisor Content API to enrich with latitude/longitude

Endpoint: https://api.content.tripadvisor.com/api/v1/location/{locationId}/details (HTTPS required)
4
10
.
Best practice: store your API key in an environment variable (do not hardcode):



Bash
export TRIPADVISOR_API_KEY="YOUR_NEW_KEY"   # macOS / Linux
Example script behavior (enrich_with_api.py / debug variant):
Read places_with_ids.csv
For each unique detail_id, call the Content API
Prefer header auth: X-TripAdvisor-API-Key: <key>
Fallback: ?key=<key> if your account uses query param
Cache API responses to ta_api_cache.json
Extract latitude and longitude from response fields (latitude, longitude, address_obj, or nested keys) and attach them to each place
Save: places_with_coords.csv
Run (example):



Bash
export TRIPADVISOR_API_KEY="YOUR_KEY"
python enrich_with_api_debug_https.py
If you see empty lat/lon, the debug script prints each response snippet and extracted lat/lon so you can diagnose. The debug script also tries header and query param auth and saves results to ta_api_cache.json.
Step 6 — Common API auth issues & how you debugged/fixed them

Observed responses:
"User is not authorized to access this resource with an explicit deny" — common when key is restricted by IP/referrer or not enabled for the resource
2
3
.
{"message":"Unauthorized"} — indicates the key was accepted by allowlisting but the key is still not authenticated for the endpoint (wrong auth method, scope not enabled, or using wrong IP/referrer)
3
.
Things to check and actions:
Ensure requests are over HTTPS (Content API requires it)
4
.
Confirm the public IP used by your client matches the CIDR you allowlisted in TripAdvisor Management Centre:
Check your public IP: curl https://ifconfig.me or curl https://ipinfo.io/ip.
If allowlisting a single IP, use CIDR /32 (e.g., 194.242.49.46/32)
6
.
Try header auth first:
Header method:
curl -i -H "Accept: application/json" -H "X-TripAdvisor-API-Key: YOUR_KEY" "https://api.content.tripadvisor.com/api/v1/location/3619312/details"
Query param fallback:
curl -i -G "https://api.content.tripadvisor.com/api/v1/location/3619312/details" --data-urlencode "key=YOUR_KEY" -H "Accept: application/json"
Compare the working browser network request (DevTools → Network) to your curl request:
Inspect request headers (Referer, Origin, Cookie, Any custom headers).
Reproduce the same headers in curl for debugging (redact sensitive headers before sharing).
If the browser request works but API key requests fail, the browser may be calling an internal endpoint or relying on session cookies — the Content API is partner‑gated and the key might need specific enablement
7
5
.
If issues persist, contact TripAdvisor Management Centre / partner support for key scope/quota/enablement — Community posts show these errors often require account-level fixes
7
2
.
Step 7 — If API access fails: fallbacks

Use your authenticated Brave session and scrape each place page to extract JSON‑LD / inline coordinates (script enrich_places.py that connects to Brave CDP and extracts coords).
Use geocoding fallback (Nominatim or Google) on place name + city (less accurate but works when API/page coords are missing).
Step 8 — Produce map / choropleth heatmap

Aggregate by normalized city (use ta_city from the Content API address_obj or parse city text).
Example approach:
Group by city/state: counts = df.groupby(['ta_city','ta_state']).size()
Use folium or geopandas + a city centroid dataset to create a choropleth or point heatmap.
I can provide a small notebook or script that reads places_with_coords.csv and produces a Folium map (heatmap or aggregated choropleth).
Security & housekeeping (critical)

You published an API key earlier; rotate/regenerate the key now in TripAdvisor Management Centre and use the new key only in environment variables or a secure secrets manager.
Keep auth.json, session cookies and cache files private (do not commit to public repos).
Use small delays between calls and cache API results to avoid repeated calls / rate limits.
Files you should now have (examples)

places.csv — initial scrape results (place_name, place_url, place_city_text, trip_title)
places_with_ids.csv — same + detail_id
ta_api_cache.json — cached Content API responses
places_with_coords.csv — final enriched file with latitude and longitude
scripts: scrape_via_brave.py, enrich_with_api_debug_https.py, optional enrich_places.py (scrape per place to parse coords)
Troubleshooting checklist (quick)

If CDP connection fails: re-run Brave with --remote-debugging-port=9222 and confirm no other process uses port 9222.
If scraper extracts zero trips: ensure you logged in to the same Brave session and expanded “Load more”.
If API returns explicit deny / unauthorized:
Confirm allowlisted IP/CIDR matches your public IP (use /32 for single IP)
6
.
Try header vs query param auth; check headers required in Management Centre docs
4
.
Compare browser request headers to curl and reproduce them for debugging.
If still failing, contact TripAdvisor support / Management Centre for key enablement (partner gating is common)
7
2
.
If lat/lon are missing in API response: inspect the full JSON payload (debug script prints snippets) — some location types might not include coordinates; fallback to page scrape or geocoding.