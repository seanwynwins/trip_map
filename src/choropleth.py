from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import folium
from branca.colormap import linear
from shapely.geometry import shape, GeometryCollection
from shapely.ops import unary_union

from .boundaries import get_city_boundary
from .utils import normalize_key


@dataclass(frozen=True)
class CityKey:
    city: str
    state: str | None
    country: str | None

    def as_tuple(self) -> Tuple[str, str | None, str | None]:
        return (self.city, self.state, self.country)


def _aggregate_counts(rows: Iterable[Dict]) -> Dict[CityKey, int]:
    counts: Dict[CityKey, int] = {}
    for row in rows:
        city, state, country = normalize_key(row.get("city"), row.get("state"), row.get("country"))
        if not city:
            continue
        key = CityKey(city=city, state=state, country=country)
        counts[key] = counts.get(key, 0) + 1
    return counts


def _collect_features(counts: Dict[CityKey, int]) -> List[Dict]:
    features: List[Dict] = []
    for key, count in counts.items():
        feature = get_city_boundary(key.city, key.state, key.country)
        # attach count property
        feature = {
            **feature,
            "properties": {
                **feature.get("properties", {}),
                "count": count,
                "key": ", ".join([p for p in [key.city, key.state, key.country] if p]),
            },
        }
        features.append(feature)
    return features


def _compute_center(features: List[Dict]) -> Tuple[float, float]:
    geoms = []
    for feat in features:
        try:
            geoms.append(shape(feat["geometry"]))
        except Exception:
            continue
    if not geoms:
        return (39.8283, -98.5795)  # fallback to US centroid
    merged = unary_union(geoms) if len(geoms) > 1 else geoms[0]
    centroid = merged.centroid
    return (centroid.y, centroid.x)


def build_choropleth(rows: Iterable[Dict], tiles: str = "CartoDB positron") -> folium.Map:
    counts = _aggregate_counts(rows)
    if not counts:
        # empty map
        return folium.Map(location=[39.8283, -98.5795], zoom_start=4, tiles=tiles)

    features = _collect_features(counts)
    min_count = min(counts.values())
    max_count = max(counts.values())
    # Avoid zero-range color scale
    if min_count == max_count:
        min_count = 0
    cmap = linear.YlOrRd_09.scale(min_count, max_count)
    cmap.caption = "Visited places per city"

    center_lat, center_lng = _compute_center(features)
    fmap = folium.Map(location=[center_lat, center_lng], zoom_start=4, tiles=tiles)

    # Add features with style based on count
    def style_function(feat: Dict) -> Dict:
        count = feat.get("properties", {}).get("count", 0)
        color = cmap(count)
        return {
            "fillColor": color,
            "color": "#555555",
            "weight": 1,
            "fillOpacity": 0.7,
        }

    def highlight_function(feat: Dict) -> Dict:
        return {"weight": 2, "color": "#000000", "fillOpacity": 0.8}

    gj = folium.GeoJson(
        data={"type": "FeatureCollection", "features": features},
        name="Visited density",
        style_function=style_function,
        highlight_function=highlight_function,
        tooltip=folium.GeoJsonTooltip(fields=["key", "count"], aliases=["City", "Count"]),
    )
    gj.add_to(fmap)

    fmap.add_child(cmap)
    folium.LayerControl(collapsed=True).add_to(fmap)
    return fmap
