#!/usr/bin/env python3
"""
city_choropleth.py
Produces a city-level choropleth HTML map from places_with_coords.csv.

Input: places_with_coords.csv (expects at least 'latitude','longitude' and ideally 'ta_city','ta_state','ta_country' or 'place_city_text')
Output: city_polygons.geojson and city_choropleth.html
"""

import time
import json
from pathlib import Path
from tqdm import tqdm

import pandas as pd
import geopandas as gpd
import osmnx as ox
import folium
from shapely.geometry import Point, mapping

# Config
INPUT_CSV = "places_with_coords.csv"   # produced earlier
OUTPUT_GEOJSON = "city_polygons.geojson"
OUTPUT_HTML = "city_choropleth.html"
OSM_SLEEP = 1.0            # seconds between OSM/Nominatim requests (be polite)
BUFFER_METERS = 10000      # fallback buffer radius for cities without polygons (10 km)

# Helper: normalize city key
def make_city_key(city, state, country):
    parts = [str(p).strip() for p in (city or "", state or "", country or "")]
    parts = [p for p in parts if p]
    return ", ".join(parts) if parts else None

def try_get_place_polygon(query):
    """
    Try to get a polygon GeoSeries for the place using OSMnx geocode.
    Returns a GeoSeries (geometry) or None.
    """
    try:
        gdf = ox.geocode_to_gdf(query)  # may return point or polygon
    except Exception as e:
        return None
    if gdf is None or gdf.empty:
        return None
    # use first geometry
    geom = gdf.geometry.iloc[0]
    return geom

def point_to_buffer_polygon(lat, lon, meters=BUFFER_METERS):
    # Create point and buffer in WebMercator (meters), then to WGS84
    p = gpd.GeoSeries([Point(lon, lat)], crs="EPSG:4326")
    p_m = p.to_crs(epsg=3857)
    buf = p_m.buffer(meters)
    buf_wgs84 = buf.to_crs(epsg=4326)
    return buf_wgs84.iloc[0]

def main():
    if not Path(INPUT_CSV).exists():
        raise SystemExit(f"Missing input CSV: {INPUT_CSV}")

    df = pd.read_csv(INPUT_CSV, dtype=str).fillna("")
    # prefer TripAdvisor fields if present
    city_col = None
    for candidate in ("ta_city", "place_city_text", "city", "ta_city_text"):
        if candidate in df.columns:
            city_col = candidate
            break

    # ensure lat/lon numeric
    if "latitude" not in df.columns or "longitude" not in df.columns:
        raise SystemExit("CSV must include 'latitude' and 'longitude' columns.")
    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")

    # Build normalized city key (city,state,country)
    def build_key(row):
        city = row.get(city_col) if city_col else ""
        state = row.get("ta_state","") if "ta_state" in row.index else row.get("state","")
        country = row.get("ta_country","") if "ta_country" in row.index else row.get("country","")
        return make_city_key(city, state, country)

    df["city_key"] = df.apply(build_key, axis=1)
    # fallback: if city_key missing, cluster by rounded coords (0.2 deg) to avoid tiny uniques
    df.loc[df["city_key"].astype(str).str.strip()=="" , "city_key"] = df[df["city_key"].astype(str).str.strip()==""].apply(
        lambda r: f"coords:{round(r['latitude'],2)},{round(r['longitude'],2)}", axis=1
    )

    # Aggregate counts by city_key and get a representative lat/lon (mean)
    agg = df.groupby("city_key").agg(
        count=("place_url", "count"),
        mean_lat=("latitude", "mean"),
        mean_lon=("longitude", "mean"),
    ).reset_index()

    print(f"Found {len(agg)} unique city keys to fetch polygons for.")

    polygons = []
    for _, row in tqdm(agg.iterrows(), total=len(agg), desc="Fetching polygons"):
        city_key = row["city_key"]
        # If city_key starts with 'coords:' it's a coordinates fallback
        if city_key.startswith("coords:"):
            lat = row["mean_lat"]
            lon = row["mean_lon"]
            geom = point_to_buffer_polygon(lat,lon)
            polygons.append({"city_key": city_key, "city_name": city_key, "count": int(row["count"]), "geometry": geom})
            continue

        # Try to use city/state/country query
        query = city_key
        geom = None
        try:
            geom = try_get_place_polygon(query)
            time.sleep(OSM_SLEEP)
        except Exception as e:
            geom = None

        if geom is None or geom.is_empty:
            # fallback to buffer around mean coordinate
            lat = row["mean_lat"]; lon = row["mean_lon"]
            geom = point_to_buffer_polygon(lat, lon)
        # Save
        polygons.append({"city_key": city_key, "city_name": city_key, "count": int(row["count"]), "geometry": geom})

    # Build GeoDataFrame
    gdf = gpd.GeoDataFrame(polygons, geometry=[p["geometry"] for p in polygons], crs="EPSG:4326")
    gdf["count"] = [p["count"] for p in polygons]
    gdf["city_key"] = [p["city_key"] for p in polygons]
    gdf["city_name"] = [p["city_name"] for p in polygons]

    # Save geojson
    gdf.to_file(OUTPUT_GEOJSON, driver="GeoJSON")
    print("Saved city polygons:", OUTPUT_GEOJSON)

    # Create choropleth map (Folium)
    center_lat = df["latitude"].mean()
    center_lon = df["longitude"].mean()
    m = folium.Map(location=[center_lat, center_lon], zoom_start=5, tiles="cartodbpositron")

    # Convert to GeoJSON object
    geojson = json.loads(gdf.to_json())

    # Prepare a lookup dict for counts keyed by city_key
    data_for_choropleth = pd.DataFrame({"city_key": gdf["city_key"], "count": gdf["count"]})

    # Add choropleth layer
    folium.Choropleth(
        geo_data=geojson,
        name="Visited cities",
        data=data_for_choropleth,
        columns=["city_key", "count"],
        key_on="feature.properties.city_key",
        fill_color="YlOrRd",
        fill_opacity=0.7,
        line_opacity=0.2,
        legend_name="Visited places count",
        highlight=True,
    ).add_to(m)

    # Add interactive tooltips (city name + count)
    folium.GeoJson(
        geojson,
        name="City polygons",
        tooltip=folium.features.GeoJsonTooltip(fields=["city_name","count"], aliases=["City","Count"], localize=True),
        style_function=lambda feature: {
            "fillOpacity": 0,
            "color": "black",
            "weight": 0.2
        }
    ).add_to(m)

    folium.LayerControl().add_to(m)
    m.save(OUTPUT_HTML)
    print("Saved interactive map:", OUTPUT_HTML)

if __name__ == "__main__":
    main()
