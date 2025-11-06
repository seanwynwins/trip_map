#!/usr/bin/env python3
"""
ta_enrich_api.py

Reads places.csv -> extracts TripAdvisor detail_id (from -dNNNNNN- in place_url) or uses existing detail_id,
calls the TripAdvisor Content API for each unique id, prints status + response snippets as it goes,
caches raw API responses in ta_api_cache.json, extracts latitude/longitude (if present),
and writes places_with_coords.csv.

Usage:
  export TRIPADVISOR_API_KEY="CF4F92A62EB34F94AAFD1FAE19CB6B8C"   # recommended
  python ta_enrich_api.py

Requirements:
  pip install requests pandas tqdm
"""

import os
import re
import time
import json
from pathlib import Path
from typing import Optional, Tuple

import requests
import pandas as pd
from tqdm import tqdm

# ---------- Config ----------
API_KEY = os.environ.get("TRIPADVISOR_API_KEY") or ""    # prefer environment variable
INPUT_CSV = "places.csv"
OUTPUT_CSV = "places_with_coords.csv"
CACHE_PATH = Path("ta_api_cache.json")
BASE_API = "https://api.content.tripadvisor.com/api/v1/location/{locationId}/details"
RATE_SLEEP = 0.5            # seconds between calls (tweak if you hit rate limits)
MAX_RETRIES = 3
# ----------------------------

def load_cache() -> dict:
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def save_cache(cache: dict):
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")

def parse_detail_id(url_or_str: str) -> Optional[str]:
    if not isinstance(url_or_str, str):
        return None
    # if it's already just digits, return it
    if re.fullmatch(r"\d+", url_or_str.strip()):
        return url_or_str.strip()
    # find -d123456- pattern
    m = re.search(r"-d(\d+)-", url_or_str)
    if m:
        return m.group(1)
    # fallback: maybe a query param or /location/NNN pattern
    m2 = re.search(r"/location/(\d+)", url_or_str)
    if m2:
        return m2.group(1)
    return None

def call_ta_api_query(location_id: str, api_key: str, language: str="en", currency: str="USD") -> Tuple[Optional[int], str]:
    url = BASE_API.format(locationId=location_id)
    params = {"key": api_key, "language": language, "currency": currency}
    headers = {"Accept": "application/json"}
    session = requests.Session()
    backoff = 1.0
    for attempt in range(1, MAX_RETRIES+1):
        try:
            r = session.get(url, params=params, headers=headers, timeout=15)
            return r.status_code, r.text
        except requests.RequestException as e:
            time.sleep(backoff)
            backoff *= 2
    return None, "request-exception"

def extract_latlon_from_json(payload: dict) -> Tuple[Optional[float], Optional[float]]:
    if not payload or not isinstance(payload, dict):
        return None, None
    # common direct fields
    for lat_key, lon_key in (("latitude","longitude"), ("lat","lng"), ("lat","lon")):
        if lat_key in payload and lon_key in payload:
            try:
                return float(payload[lat_key]), float(payload[lon_key])
            except Exception:
                pass
    # address_obj nested
    addr = payload.get("address_obj")
    if isinstance(addr, dict):
        if "latitude" in addr and "longitude" in addr:
            try:
                return float(addr["latitude"]), float(addr["longitude"])
            except Exception:
                pass
    # shallow recursive search helper
    def find_coords(o):
        if isinstance(o, dict):
            if "latitude" in o and "longitude" in o:
                return o["latitude"], o["longitude"]
            for v in o.values():
                r = find_coords(v)
                if r:
                    return r
        elif isinstance(o, list):
            for v in o:
                r = find_coords(v)
                if r:
                    return r
        return None
    res = find_coords(payload)
    if res:
        try:
            return float(res[0]), float(res[1])
        except Exception:
            pass
    return None, None

def main():
    if not API_KEY:
        raise SystemExit("Set TRIPADVISOR_API_KEY environment variable with your API key before running.")

    if not Path(INPUT_CSV).exists():
        raise SystemExit(f"Input CSV not found: {INPUT_CSV}")

    print("Loading input CSV:", INPUT_CSV)
    df = pd.read_csv(INPUT_CSV, dtype=str).fillna("")
    # ensure we have a detail_id column
    if "detail_id" not in df.columns:
        df["detail_id"] = df["place_url"].apply(parse_detail_id)

    # build unique list
    ids = sorted(set([x for x in df["detail_id"].tolist() if x]))
    print(f"Found {len(ids)} unique detail_id(s) to query.")

    cache = load_cache()

    for lid in tqdm(ids, desc="Calling Content API"):
        lid = str(lid)
        if lid in cache and cache[lid].get("checked_at"):
            entry = cache[lid]
            print(f"[cached] id={lid} status={entry.get('status')} lat={entry.get('lat')} lon={entry.get('lon')}")
            continue

        status, text = call_ta_api_query(lid, API_KEY)
        print("\n---")
        print(f"ID: {lid}  HTTP status: {status}")
        snippet = (text or "")[:2000]
        # Print a readable snippet: truncated and single-line
        print("Response snippet:", snippet.replace("\n"," ")[:1200])

        parsed = None
        lat = lon = None
        try:
            parsed = json.loads(text) if text else None
        except Exception as e:
            print("Failed to parse JSON:", e)

        if parsed:
            # try to extract lat/lon from top-level or common wrappers
            lat, lon = extract_latlon_from_json(parsed)
            if lat is None and lon is None:
                for key in ("data","location","result"):
                    if isinstance(parsed.get(key), dict):
                        lat, lon = extract_latlon_from_json(parsed.get(key))
                        if lat is not None:
                            break

        # store raw body and lat/lon in cache
        cache[lid] = {
            "status": status,
            "raw": (text or "")[:10000],   # keep limited raw text
            "lat": lat,
            "lon": lon,
            "checked_at": time.time()
        }
        save_cache(cache)
        print(f"Extracted lat,lon: {lat},{lon}")
        time.sleep(RATE_SLEEP)

    # attach coords to dataframe rows
    lats = []
    lons = []
    for _, row in df.iterrows():
        lid = str(row.get("detail_id") or "")
        entry = cache.get(lid, {})
        lats.append(entry.get("lat"))
        lons.append(entry.get("lon"))

    df["latitude"] = lats
    df["longitude"] = lons
    df.to_csv(OUTPUT_CSV, index=False)
    print("\nSaved enriched CSV:", OUTPUT_CSV)
    print("Cache saved to:", CACHE_PATH)

if __name__ == "__main__":
    main()