import json
import os
from pathlib import Path
from typing import Dict, Optional

import requests
from slugify import slugify
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type


CACHE_DIR = Path(__file__).resolve().parent.parent / "cache" / "boundaries"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


class BoundaryNotFoundError(Exception):
    pass


def _cache_path(city: str, state: Optional[str], country: Optional[str]) -> Path:
    parts = [city]
    if state:
        parts.append(state)
    if country:
        parts.append(country)
    key = "__".join(parts)
    return CACHE_DIR / f"{slugify(key)}.geojson"


@retry(
    reraise=True,
    retry=retry_if_exception_type((requests.RequestException, BoundaryNotFoundError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
)
def _nominatim_lookup(city: str, state: Optional[str], country: Optional[str]) -> Dict:
    # Nominatim usage policy: provide descriptive User-Agent and origin
    headers = {
        "User-Agent": "trip-map/1.0 (personal, contact: youremail@example.com)",
        "Accept": "application/json",
    }

    query_parts = [city]
    if state:
        query_parts.append(state)
    if country:
        query_parts.append(country)
    q = ", ".join(query_parts)

    params = {
        "q": q,
        "format": "json",
        "polygon_geojson": 1,
        "addressdetails": 1,
        "limit": 5,
    }

    resp = requests.get("https://nominatim.openstreetmap.org/search", params=params, headers=headers, timeout=30)
    resp.raise_for_status()
    results = resp.json()

    # Prefer results that are administrative boundaries or cities/towns
    preferred_classes = {"boundary", "place"}
    preferred_types = {"administrative", "city", "town"}

    best: Optional[Dict] = None
    for item in results:
        if not item.get("geojson"):
            continue
        cls = item.get("class")
        typ = item.get("type")
        if cls in preferred_classes or typ in preferred_types:
            best = item
            break

    if best is None and results:
        best = results[0]

    if not best:
        raise BoundaryNotFoundError(f"No boundary found for {q}")

    feature = {
        "type": "Feature",
        "geometry": best["geojson"],
        "properties": {
            "display_name": best.get("display_name"),
            "city": city,
            "state": state,
            "country": country,
            "osm_id": best.get("osm_id"),
            "class": best.get("class"),
            "type": best.get("type"),
        },
    }
    return feature


def get_city_boundary(city: str, state: Optional[str] = None, country: Optional[str] = None, force_refresh: bool = False) -> Dict:
    """
    Returns a GeoJSON Feature for the given city/state/country.
    Caches results to disk for repeatable, offline-friendly usage.
    """
    cache_path = _cache_path(city, state, country)
    if cache_path.exists() and not force_refresh:
        with cache_path.open("r", encoding="utf-8") as f:
            return json.load(f)

    feature = _nominatim_lookup(city, state, country)

    # Normalize coordinates: ensure winding order is consistent isn't required for Folium
    with cache_path.open("w", encoding="utf-8") as f:
        json.dump(feature, f)

    return feature
