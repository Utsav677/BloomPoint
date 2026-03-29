"""
Toxic Pulse — NASA Ocean Color ERDDAP Client

Fetches real chlorophyll-a data from NASA's ERDDAP server.
Uses MODIS-Aqua L3 mapped 8-day composites (4km resolution).
Fallback: VIIRS-SNPP if MODIS has no data.

No authentication required. Returns actual satellite-measured
chl-a values in mg/m³.
"""

import io
import logging
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import requests

logger = logging.getLogger("toxic_pulse.nasa")

# --- ERDDAP dataset IDs ---
# MODIS-Aqua 8-day L3 NRT, 4km, 2003-present (primary — most current data)
MODIS_DATASET = "erdMH1chla8day_R2022NRT"
# MODIS-Aqua monthly NRT (fallback — wider temporal coverage per request)
MODIS_MONTHLY = "erdMH1chlamday_R2022NRT"
# VIIRS-SNPP weekly (second fallback)
VIIRS_DATASET = "nesdisVHNSQchlaWeekly"

ERDDAP_BASE = "https://coastwatch.pfeg.noaa.gov/erddap/griddap"

# Maximum days per single ERDDAP request to avoid timeouts
CHUNK_DAYS = 365


def fetch_real_chlorophyll(
    lat: float,
    lon: float,
    bbox_delta: float = 0.5,
    days_back: int = 730,
) -> pd.DataFrame:
    """
    Fetch real satellite chlorophyll-a from NASA ERDDAP.

    Tries MODIS-Aqua first, then VIIRS-SNPP.
    Returns DataFrame with columns:
        date, lat, lon, chl_a, turbidity, sst_delta,
        precipitation_7d, wind_speed, source, cloud_fraction
    Returns empty DataFrame if no data is available.
    """
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days_back)

    for dataset_id, sensor_name in [
        (MODIS_DATASET, "MODIS-Aqua-8day-NRT"),
        (MODIS_MONTHLY, "MODIS-Aqua-Monthly-NRT"),
        (VIIRS_DATASET, "VIIRS-SNPP-Weekly"),
    ]:
        logger.info(
            "  [NASA] Trying %s dataset=%s for (%.2f, %.2f)",
            sensor_name, dataset_id, lat, lon,
        )
        try:
            df = _query_erddap_chunked(
                dataset_id, lat, lon, bbox_delta, start_date, end_date,
            )
            if df is not None and len(df) > 0:
                logger.info(
                    "  [NASA] %s returned %d rows, chl-a range: %.3f - %.3f mg/m3",
                    sensor_name, len(df), df["chl_a"].min(), df["chl_a"].max(),
                )
                augmented = _augment_with_env_variables(df, sensor_name)
                return augmented
            else:
                logger.warning("  [NASA] %s returned no data", sensor_name)
        except Exception as e:
            logger.warning("  [NASA] %s failed: %s", sensor_name, e)

    logger.warning("  [NASA] All sources exhausted, no real chl-a data available")
    return pd.DataFrame()


def _query_erddap_chunked(
    dataset_id: str,
    lat: float,
    lon: float,
    bbox_delta: float,
    start_date: datetime,
    end_date: datetime,
) -> pd.DataFrame | None:
    """Query ERDDAP in yearly chunks to avoid timeouts on large ranges."""
    all_frames = []
    chunk_start = start_date

    while chunk_start < end_date:
        chunk_end = min(chunk_start + timedelta(days=CHUNK_DAYS), end_date)
        try:
            df = _query_erddap(
                dataset_id, lat, lon, bbox_delta, chunk_start, chunk_end,
            )
            if df is not None and len(df) > 0:
                all_frames.append(df)
        except Exception as e:
            logger.debug("  [NASA] Chunk %s-%s failed: %s", chunk_start.date(), chunk_end.date(), e)
        chunk_start = chunk_end + timedelta(days=1)

    if not all_frames:
        return None
    return pd.concat(all_frames, ignore_index=True)


def _query_erddap(
    dataset_id: str,
    lat: float,
    lon: float,
    bbox_delta: float,
    start_date: datetime,
    end_date: datetime,
) -> pd.DataFrame | None:
    """
    Single ERDDAP griddap request. Returns parsed DataFrame or None.

    URL format:
    /griddap/{dataset}.csv?chlorophyll[({start}):({end})][({lat_min}):({lat_max})][({lon_min}):({lon_max})]
    """
    lat_min = lat - bbox_delta
    lat_max = lat + bbox_delta
    lon_min = lon - bbox_delta
    lon_max = lon + bbox_delta

    start_str = start_date.strftime("%Y-%m-%dT00:00:00Z")
    end_str = end_date.strftime("%Y-%m-%dT00:00:00Z")

    # ERDDAP griddap constraint expression
    # The variable name differs per dataset
    var_name = "chlorophyll"
    if "VH" in dataset_id or "nesdis" in dataset_id:
        var_name = "chlor_a"

    url = (
        f"{ERDDAP_BASE}/{dataset_id}.csv"
        f"?{var_name}"
        f"[({start_str}):({end_str})]"
        f"[({lat_min}):({lat_max})]"
        f"[({lon_min}):({lon_max})]"
    )

    logger.debug("  [NASA] ERDDAP request: %s", url[:200])

    resp = requests.get(url, timeout=90)

    if resp.status_code == 404:
        logger.debug("  [NASA] Dataset %s returned 404 — may not cover this region", dataset_id)
        return None

    if resp.status_code != 200:
        logger.warning("  [NASA] ERDDAP returned HTTP %d for %s", resp.status_code, dataset_id)
        return None

    return _parse_erddap_csv(resp.text, var_name)


def _parse_erddap_csv(csv_text: str, var_name: str = "chlorophyll") -> pd.DataFrame | None:
    """
    Parse ERDDAP CSV response.

    ERDDAP CSV has:
    - Row 0: column headers (time, latitude, longitude, chlorophyll)
    - Row 1: units (UTC, degrees_north, degrees_east, mg m-3)
    - Row 2+: data
    """
    lines = csv_text.strip().split("\n")
    if len(lines) < 3:
        return None

    # Skip the units row (row 1)
    header_line = lines[0]
    data_lines = lines[2:]  # skip header + units

    if not data_lines:
        return None

    csv_clean = header_line + "\n" + "\n".join(data_lines)

    try:
        df = pd.read_csv(io.StringIO(csv_clean))
    except Exception:
        return None

    if df.empty:
        return None

    # Normalize column names
    col_map = {}
    for col in df.columns:
        lower = col.lower().strip()
        if "time" in lower:
            col_map[col] = "date"
        elif "lat" in lower:
            col_map[col] = "lat"
        elif "lon" in lower:
            col_map[col] = "lon"
        elif lower in ("chlorophyll", "chlor_a", var_name.lower()):
            col_map[col] = "chl_a"

    df = df.rename(columns=col_map)

    required = {"date", "lat", "lon", "chl_a"}
    if not required.issubset(set(df.columns)):
        logger.warning("  [NASA] Missing columns: have %s, need %s", list(df.columns), required)
        return None

    # Parse dates
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])

    # Convert chl_a to numeric, drop NaN (land/cloud pixels)
    df["chl_a"] = pd.to_numeric(df["chl_a"], errors="coerce")
    df = df.dropna(subset=["chl_a"])

    # Filter out unrealistic values (negative or extremely high)
    df = df[(df["chl_a"] > 0) & (df["chl_a"] < 300)]

    # Round coordinates for grid consistency
    df["lat"] = df["lat"].round(4)
    df["lon"] = df["lon"].round(4)

    df = df[["date", "lat", "lon", "chl_a"]].reset_index(drop=True)

    return df if len(df) > 0 else None


def _augment_with_env_variables(df: pd.DataFrame, source: str) -> pd.DataFrame:
    """
    Add correlated environmental variables to the real chl-a data.
    Turbidity is estimated from chl-a. Other variables are modeled
    from realistic distributions (these are secondary to the core
    chl-a signal that drives detection).
    """
    df = df.copy()
    n = len(df)
    rng = np.random.RandomState(42)

    # Turbidity correlates with chl-a
    df["turbidity"] = (df["chl_a"] * 0.15 + rng.normal(0, 0.3, n)).clip(lower=0.1).round(3)

    # SST delta: random but weakly correlated with high chl-a events
    df["sst_delta"] = (rng.normal(0, 1.5, n) + (df["chl_a"] > 10).astype(float) * 0.5).round(3)

    # Precipitation: exponential distribution, occasional heavy rain
    precip = rng.exponential(12, n)
    heavy_rain_mask = rng.random(n) < 0.12
    precip[heavy_rain_mask] += rng.uniform(30, 80, heavy_rain_mask.sum())
    df["precipitation_7d"] = precip.clip(min=0).round(2)

    # Wind speed
    df["wind_speed"] = rng.normal(5, 2.5, n).clip(min=0).round(2)

    # Cloud fraction (from beta distribution)
    df["cloud_fraction"] = rng.beta(2, 5, n).clip(0, 1).round(3)

    df["source"] = source

    return df
