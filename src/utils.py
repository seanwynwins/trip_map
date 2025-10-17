from __future__ import annotations

import pandas as pd
from typing import Tuple


def normalize_key(city: str, state: str | None, country: str | None) -> Tuple[str, str | None, str | None]:
    city_n = (city or "").strip()
    state_n = (state or "").strip() or None
    country_n = (country or "").strip() or None
    return city_n, state_n, country_n


def read_places_csv(csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    expected_cols = {"city", "state", "country"}
    missing = expected_cols - set(df.columns.str.lower())
    if missing:
        raise ValueError(f"CSV missing required columns: {missing}")
    # Normalize column names to lowercase
    df.columns = [c.lower() for c in df.columns]
    return df
