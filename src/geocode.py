from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional

import requests
from slugify import slugify
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

CACHE_DIR = Path(__file__).resolve().parent.parent / "cache" / "geocode"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _cache_path(q: str) -> Path:
    return CACHE_DIR / f"{slugify(q)[:200]}.json"


@retry(
    reraise=True,
    retry=retry_if_exception_type(requests.RequestException),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
)
def _nominatim(q: str) -> Dict:
    headers = {
        "User-Agent": "trip-map/1.0 (personal, contact: youremail@example.com)",
        "Accept": "application/json",
    }
    params = {
        "q": q,
        "format": "json",
        "addressdetails": 1,
        "limit": 1,
    }
    resp = requests.get("https://nominatim.openstreetmap.org/search", params=params, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data[0] if data else {}


def geocode_city_for_place(name: Optional[str], url: Optional[str] = None) -> Dict:
    q = name or url or ""
    if not q:
        return {}
    cache_path = _cache_path(q)
    if cache_path.exists():
        with cache_path.open("r", encoding="utf-8") as f:
            return json.load(f)

    data = _nominatim(q)
    address = data.get("address", {}) if data else {}
    result = {
        "city": address.get("city") or address.get("town") or address.get("village"),
        "state": address.get("state") or address.get("region") or address.get("state_district"),
        "country": address.get("country"),
    }
    with cache_path.open("w", encoding="utf-8") as f:
        json.dump(result, f)
    return result
