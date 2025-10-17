from __future__ import annotations

import argparse
from pathlib import Path

from .utils import read_places_csv
from .choropleth import build_choropleth


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a city-boundary choropleth from visited places CSV")
    parser.add_argument("--input", required=True, help="Path to CSV with columns: city,state,country, ...")
    parser.add_argument("--output", default="output/visited_map.html", help="Output HTML path")
    parser.add_argument("--tiles", default="CartoDB positron", help="Folium tiles name or URL template")
    args = parser.parse_args()

    df = read_places_csv(args.input)
    fmap = build_choropleth(df.to_dict(orient="records"), tiles=args.tiles)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fmap.save(str(out_path))
    print(f"Saved map to {out_path}")


if __name__ == "__main__":
    main()
