# Trip Map

Generate a city-boundary choropleth map showing density of visited places per city.

## Setup

```bash
# from repo root
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# if using Playwright for import, also install browsers
python -m playwright install chromium
```

## Prepare your data

Use a CSV with at least these columns: `city,state,country` and optionally `place_name,category,date,notes`.

Example file is provided at `data/visited_places.sample.csv`.

## Generate the map

```bash
python -m src.generate_map --input data/visited_places.sample.csv --output output/visited_map.html
```

Open the generated HTML in a browser. Each city polygon is shaded by how many rows in the CSV match that city.

## Import from TripAdvisor (optional)
This uses a local browser session. You will log in once and the session persists in a profile folder.

```bash
# Export your TripAdvisor Trips places to CSV
python -m src.cli_ta_export --output output/tripadvisor_places.csv --profile cache/ta_profile

# Then aggregate the CSV to city density before map generation
# You can either: (a) manually edit to keep columns city/state/country; or
# (b) simply use the exported CSV directly, the map pipeline counts rows per city.
python -m src.generate_map --input output/tripadvisor_places.csv --output output/visited_map.html
```

### Notes and considerations
- Respect TripAdvisor terms of service. This tool automates your own account in a local browser; do not share or republish scraped data.
- Boundaries are fetched from OpenStreetMap Nominatim and cached under `cache/boundaries/`.
- Geocoding fallback for place names uses Nominatim and caches under `cache/geocode/`.
- If a city's polygon looks off, delete its cache file and try again; you may refine `city,state,country` in your CSV for better matches.
- Change tile style with `--tiles` (e.g. "OpenStreetMap", "Stamen Terrain").
