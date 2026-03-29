"""
Toxic Pulse — Feature Engineering

Computes rolling statistics, seasonal adjustment, weather flags,
and rate-of-change features per grid cell.
"""

import pandas as pd
import numpy as np


def compute_features(grid_df: pd.DataFrame, window_weeks: int = 4) -> pd.DataFrame:
    """
    For each grid cell (grouped by lat, lon), compute:
    - chl_a_rolling_mean: 4-week rolling mean of chl_a
    - chl_a_rolling_std:  4-week rolling std of chl_a
    - chl_a_zscore:       (chl_a - rolling_mean) / rolling_std
    - chl_a_seasonal_residual: chl_a minus the mean chl_a for that
                               week-of-year across all years
    - chl_a_delta_1w:     chl_a difference from 1 week ago
    - chl_a_delta_2w:     chl_a difference from 2 weeks ago
    - recent_heavy_rain:  1 if precipitation_7d > 50, else 0
    - high_wind:          1 if wind_speed > 8, else 0

    Sorts by date, forward-fills NaN from rolling calcs,
    drops any remaining NaN rows.
    """
    df = grid_df.copy()
    df = df.sort_values("date").reset_index(drop=True)

    # week-of-year for seasonal adjustment
    df["_week_of_year"] = df["date"].dt.isocalendar().week.astype(int)

    # Seasonal mean per (lat, lon, week_of_year)
    seasonal_mean = (
        df.groupby(["lat", "lon", "_week_of_year"])["chl_a"]
        .transform("mean")
    )
    df["chl_a_seasonal_residual"] = df["chl_a"] - seasonal_mean

    # Per-cell rolling statistics
    window = window_weeks  # weeks (1 row = 1 week)

    def _cell_features(cell_df: pd.DataFrame) -> pd.DataFrame:
        cell_df = cell_df.sort_values("date").copy()

        # Trailing rolling stats (exclude current row so spikes aren't absorbed)
        shifted = cell_df["chl_a"].shift(1)
        cell_df["chl_a_rolling_mean"] = (
            shifted.rolling(window=window, min_periods=1).mean()
        )
        cell_df["chl_a_rolling_std"] = (
            shifted.rolling(window=window, min_periods=2).std()
        )

        # Z-score (avoid division by zero; floor std at 1.0 for stability)
        std = cell_df["chl_a_rolling_std"].clip(lower=1.0)
        cell_df["chl_a_zscore"] = (
            (cell_df["chl_a"] - cell_df["chl_a_rolling_mean"]) / std
        )

        # Rate of change (shift by 1 and 2 weeks within the cell)
        cell_df["chl_a_delta_1w"] = cell_df["chl_a"] - cell_df["chl_a"].shift(1)
        cell_df["chl_a_delta_2w"] = cell_df["chl_a"] - cell_df["chl_a"].shift(2)

        return cell_df

    result_parts = []
    for (lat, lon), group in df.groupby(["lat", "lon"], sort=False):
        result_parts.append(_cell_features(group))

    if not result_parts:
        return df

    out = pd.concat(result_parts, ignore_index=True)

    # Weather binary flags
    out["recent_heavy_rain"] = (out["precipitation_7d"] > 50).astype(int)
    out["high_wind"] = (out["wind_speed"] > 8).astype(int)

    # Forward-fill NaN introduced by rolling windows
    roll_cols = [
        "chl_a_rolling_mean", "chl_a_rolling_std",
        "chl_a_zscore", "chl_a_delta_1w", "chl_a_delta_2w",
    ]
    out[roll_cols] = out[roll_cols].ffill()

    # Drop any rows still containing NaN in key feature columns
    drop_if_nan = roll_cols + ["chl_a_seasonal_residual"]
    out = out.dropna(subset=drop_if_nan).reset_index(drop=True)

    # Remove helper column
    out = out.drop(columns=["_week_of_year"], errors="ignore")

    return out
