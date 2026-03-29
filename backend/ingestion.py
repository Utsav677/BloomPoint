"""
Toxic Pulse — Data Ingestion

Takes arbitrary lat/lon coordinates, fetches real Sentinel-3 OLCI
chlorophyll data from Copernicus Data Space, and returns a normalized
DataFrame ready for feature engineering.

Falls back to cached CSV if API is slow or unavailable.
"""

import pandas as pd
from pathlib import Path

from copernicus import (
    fetch_chlorophyll_data,
    load_from_cache,
    find_nearby_cache,
    save_to_cache,
)


class DataLoader:
    """Loads real satellite chlorophyll data for arbitrary coordinates."""

    def load(self, lat: float, lon: float, use_cache: bool = True) -> pd.DataFrame:
        """
        Load chlorophyll data for a water body at (lat, lon).

        1. Check exact cache match
        2. Check nearby cache (within 0.1 degrees)
        3. Fetch from Copernicus Sentinel Hub Statistical API
        4. Cache the result

        Returns DataFrame with columns:
        date, lat, lon, chl_a, turbidity, sst_delta,
        precipitation_7d, wind_speed, source, cloud_fraction
        """
        if use_cache:
            # Try exact cache
            cached = load_from_cache(lat, lon)
            if cached is not None and len(cached) > 0:
                return self._normalize(cached)

            # Try nearby cache
            nearby = find_nearby_cache(lat, lon)
            if nearby is not None and len(nearby) > 0:
                return self._normalize(nearby)

        # Fetch from Copernicus catalog API
        df = fetch_chlorophyll_data(lat, lon)

        if df.empty:
            raise FileNotFoundError(
                f"No Sentinel-3 OLCI data available for coordinates ({lat}, {lon}). "
                "The location may be too far inland, or cloud cover may have blocked all observations."
            )

        # Cache for future requests
        save_to_cache(df, lat, lon)

        return self._normalize(df)

    def _normalize(self, df: pd.DataFrame) -> pd.DataFrame:
        """Forward-fill missing values, drop remaining NaN rows, sort by date."""
        df = df.copy()
        if "date" in df.columns and not pd.api.types.is_datetime64_any_dtype(df["date"]):
            df["date"] = pd.to_datetime(df["date"])

        numeric_cols = df.select_dtypes(include="number").columns.tolist()
        df[numeric_cols] = df[numeric_cols].ffill()
        df = df.dropna(subset=numeric_cols)
        df = df.sort_values("date").reset_index(drop=True)
        return df
