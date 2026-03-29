"""
Toxic Pulse — Copernicus Data Space API Client

Authenticates with Copernicus, searches Sentinel-3 OLCI catalog via
OData and STAC APIs, generates chlorophyll time series from product
metadata and regional climatology, and caches results as CSV.

Uses only catalogue.dataspace.copernicus.eu endpoints (NOT Sentinel Hub).
"""

import os
import time
import math
import logging
from datetime import datetime, timedelta
from pathlib import Path

import requests
import pandas as pd
import numpy as np
from dotenv import load_dotenv

load_dotenv(dotenv_path=str(Path(__file__).parent.parent / ".env"))

logger = logging.getLogger("toxic_pulse.copernicus")

# Configure root logger so messages reach uvicorn console
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)

# --- Auth ---

_TOKEN_URL = (
    "https://identity.dataspace.copernicus.eu"
    "/auth/realms/CDSE/protocol/openid-connect/token"
)

_token_cache: dict = {"access_token": None, "expires_at": 0.0}


def _get_access_token() -> str:
    """Authenticate with Copernicus Data Space and return a bearer token."""
    now = time.time()
    if _token_cache["access_token"] and _token_cache["expires_at"] > now + 60:
        logger.info("[AUTH] Using cached Copernicus token (expires in %.0fs)", _token_cache["expires_at"] - now)
        return _token_cache["access_token"]

    user = os.getenv("COPERNICUS_USER", "")
    password = os.getenv("COPERNICUS_PASSWORD", "")
    if not user or not password:
        logger.error("[AUTH] FAIL — COPERNICUS_USER / COPERNICUS_PASSWORD not set in .env")
        raise RuntimeError("COPERNICUS_USER / COPERNICUS_PASSWORD not set in .env")

    logger.info("[AUTH] Authenticating with Copernicus Data Space as '%s'...", user)
    try:
        resp = requests.post(
            _TOKEN_URL,
            data={
                "client_id": "cdse-public",
                "username": user,
                "password": password,
                "grant_type": "password",
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        _token_cache["access_token"] = data["access_token"]
        _token_cache["expires_at"] = now + data.get("expires_in", 300)
        logger.info("[AUTH] SUCCESS — token valid for %ds", data.get("expires_in", 300))
        return data["access_token"]
    except Exception as e:
        logger.error("[AUTH] FAIL — %s", e)
        raise


# --- STAC Catalog Search ---

_STAC_URL = "https://catalogue.dataspace.copernicus.eu/stac/search"


def _search_stac(
    lat: float, lon: float, bbox_delta: float = 0.5, days_back: int = 730
) -> list[dict]:
    """
    Search Copernicus STAC catalog for Sentinel-3 products
    intersecting the bounding box around (lat, lon).

    Returns list of STAC feature dicts with datetime info.
    NOTE: This returns product METADATA only — not pixel-level chlorophyll values.
    """
    token = _get_access_token()

    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days_back)

    logger.info("[STAC] Searching Sentinel-3 products for bbox around (%.2f, %.2f), %d days back", lat, lon, days_back)

    features = []
    page = 1

    while True:
        body = {
            "collections": ["SENTINEL-3"],
            "bbox": [lon - bbox_delta, lat - bbox_delta, lon + bbox_delta, lat + bbox_delta],
            "datetime": f"{start_date.strftime('%Y-%m-%dT00:00:00Z')}/{end_date.strftime('%Y-%m-%dT23:59:59Z')}",
            "limit": 50,
            "sortby": [{"field": "datetime", "direction": "desc"}],
        }

        resp = requests.post(
            _STAC_URL,
            json=body,
            headers={"Authorization": f"Bearer {token}"},
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()

        batch = data.get("features", [])
        if not batch:
            break

        features.extend(batch)
        page += 1

        # Stop after enough products or no more pages
        if len(features) >= 200 or len(batch) < 50:
            break

    logger.info("[STAC] Found %d Sentinel-3 products (metadata only — no pixel values)", len(features))
    return features


# --- OData Catalog Search (fallback) ---

_ODATA_URL = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"


def _search_odata(
    lat: float, lon: float, bbox_delta: float = 0.5, days_back: int = 730
) -> list[dict]:
    """
    Search Copernicus OData catalog for Sentinel-3 OLCI Water Full Resolution
    products intersecting the bounding box around (lat, lon).
    """
    token = _get_access_token()

    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days_back)

    bbox_wkt = (
        f"POLYGON(({lon - bbox_delta} {lat - bbox_delta},"
        f"{lon + bbox_delta} {lat - bbox_delta},"
        f"{lon + bbox_delta} {lat + bbox_delta},"
        f"{lon - bbox_delta} {lat + bbox_delta},"
        f"{lon - bbox_delta} {lat - bbox_delta}))"
    )

    odata_filter = (
        f"Collection/Name eq 'SENTINEL-3'"
        f" and Attributes/OData.CSC.StringAttribute/any("
        f"att:att/Name eq 'productType' and att/OData.CSC.StringAttribute/Value eq 'OL_2_WFR___')"
        f" and OData.CSC.Intersects(area=geography'SRID=4326;{bbox_wkt}')"
        f" and ContentDate/Start gt {start_date.strftime('%Y-%m-%dT00:00:00.000Z')}"
    )

    logger.info("[OData] Searching Sentinel-3 OLCI WFR products for bbox around (%.2f, %.2f)", lat, lon)

    products = []

    resp = requests.get(
        _ODATA_URL,
        params={
            "$filter": odata_filter,
            "$orderby": "ContentDate/Start desc",
            "$top": 100,
        },
        headers={"Authorization": f"Bearer {token}"},
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    products = data.get("value", [])

    logger.info("[OData] Found %d products (metadata only — no pixel values)", len(products))
    return products


# --- Climatology-based chlorophyll estimation ---


def _latitude_baseline_chl(lat: float) -> float:
    """
    Approximate baseline chlorophyll-a (mg/m³) based on latitude.
    Tropical waters: higher baseline (eutrophic lakes, coastal).
    Temperate: moderate with strong seasonal signal.
    Polar: low baseline.
    """
    abs_lat = abs(lat)
    if abs_lat < 15:
        return 8.0   # tropical — high nutrient, eutrophic lakes
    elif abs_lat < 30:
        return 5.5   # subtropical
    elif abs_lat < 50:
        return 4.0   # temperate
    elif abs_lat < 65:
        return 2.5   # subpolar
    else:
        return 1.5   # polar


def _seasonal_amplitude(lat: float) -> float:
    """
    Seasonal chlorophyll amplitude factor.
    Tropics have weak seasonality; temperate has strong spring/autumn blooms.
    """
    abs_lat = abs(lat)
    if abs_lat < 15:
        return 0.15
    elif abs_lat < 30:
        return 0.3
    elif abs_lat < 50:
        return 0.5   # strong spring bloom
    else:
        return 0.35


def _seasonal_chl(lat: float, day_of_year: int) -> float:
    """
    Generate a climatological chlorophyll-a value for a given latitude and day.
    Incorporates seasonal cycle (spring bloom in temperate, bimodal in tropics).
    """
    baseline = _latitude_baseline_chl(lat)
    amplitude = _seasonal_amplitude(lat)

    # Northern hemisphere: spring bloom peaks ~day 120 (April 30)
    # Southern hemisphere: shift by 182 days
    if lat >= 0:
        phase_shift = 0
    else:
        phase_shift = 182

    adjusted_day = (day_of_year + phase_shift) % 365

    # Primary spring bloom
    spring_signal = math.exp(-((adjusted_day - 120) ** 2) / (2 * 40 ** 2))
    # Secondary autumn bloom (temperate only)
    autumn_signal = 0.4 * math.exp(-((adjusted_day - 280) ** 2) / (2 * 30 ** 2))

    seasonal_factor = 1.0 + amplitude * (spring_signal + autumn_signal)

    return baseline * seasonal_factor


def fetch_chlorophyll_data(
    lat: float, lon: float, bbox_delta: float = 0.5, days_back: int = 730
) -> pd.DataFrame:
    """
    Fetch real chlorophyll-a data for a water body at (lat, lon).

    Strategy:
    1. Try NASA ERDDAP (MODIS-Aqua / VIIRS) for real satellite chl-a values
    2. Fall back to Copernicus catalog dates + climatology model (synthetic)

    Returns a DataFrame with columns:
    date, lat, lon, chl_a, turbidity, sst_delta, precipitation_7d,
    wind_speed, source, cloud_fraction
    """
    logger.info("=" * 60)
    logger.info("[FETCH] Fetching chlorophyll data for (%.2f, %.2f), bbox_delta=%.1f, days_back=%d", lat, lon, bbox_delta, days_back)

    # --- Strategy 1: Real data from NASA ERDDAP ---
    try:
        from nasa_ocean_color import fetch_real_chlorophyll

        logger.info("[FETCH] Trying NASA ERDDAP for real satellite chl-a...")
        nasa_df = fetch_real_chlorophyll(lat, lon, bbox_delta, days_back)

        if nasa_df is not None and len(nasa_df) > 0:
            nasa_df["date"] = pd.to_datetime(nasa_df["date"])
            nasa_df = nasa_df.sort_values("date").reset_index(drop=True)
            logger.info(
                "[FETCH] SUCCESS — NASA returned %d rows of REAL chl-a data",
                len(nasa_df),
            )
            logger.info(
                "[FETCH]   chl-a: min=%.3f, mean=%.3f, max=%.3f mg/m3",
                nasa_df["chl_a"].min(), nasa_df["chl_a"].mean(), nasa_df["chl_a"].max(),
            )
            logger.info(
                "[FETCH]   date range: %s to %s",
                nasa_df["date"].min().date(), nasa_df["date"].max().date(),
            )
            logger.info(
                "[FETCH]   unique dates: %d, unique grid points: %d",
                nasa_df["date"].nunique(),
                nasa_df.groupby(["lat", "lon"]).ngroups,
            )
            return nasa_df
        else:
            logger.warning("[FETCH] NASA ERDDAP returned no data — falling back to Copernicus catalog")
    except Exception as e:
        logger.warning("[FETCH] NASA ERDDAP failed (%s) — falling back to Copernicus catalog", e)

    # --- Strategy 2: Copernicus catalog dates + climatology (SYNTHETIC) ---
    logger.warning("[FETCH] Using SYNTHETIC chlorophyll from climatology model (NOT real satellite data)")

    product_dates = set()

    try:
        stac_features = _search_stac(lat, lon, bbox_delta, days_back)
        for feat in stac_features:
            dt_str = feat.get("properties", {}).get("datetime", "")
            if dt_str:
                product_dates.add(dt_str[:10])
    except Exception as e:
        logger.warning("[FETCH] STAC search failed: %s", e)

    if len(product_dates) < 10:
        try:
            odata_products = _search_odata(lat, lon, bbox_delta, days_back)
            for prod in odata_products:
                content_date = prod.get("ContentDate", {})
                start = content_date.get("Start", "")
                if start:
                    product_dates.add(start[:10])
        except Exception as e:
            logger.warning("[FETCH] OData search failed: %s", e)

    logger.info("[FETCH] Copernicus catalog found %d unique product dates", len(product_dates))

    if not product_dates:
        logger.error("[FETCH] No data from any source for (%.2f, %.2f)", lat, lon)
        return pd.DataFrame()

    # Sort dates and aggregate to weekly
    sorted_dates = sorted(product_dates)
    weekly_dates = _aggregate_to_weekly(sorted_dates)
    logger.info("[FETCH] Aggregated to %d weekly dates", len(weekly_dates))

    if not weekly_dates:
        return pd.DataFrame()

    # Generate grid points within bbox for spatial diversity
    min_lat, max_lat = lat - bbox_delta, lat + bbox_delta
    min_lon, max_lon = lon - bbox_delta, lon + bbox_delta
    grid_lats = np.linspace(min_lat + 0.05, max_lat - 0.05, 3)
    grid_lons = np.linspace(min_lon + 0.05, max_lon - 0.05, 3)

    rng = np.random.RandomState(int(abs(lat * 1000) + abs(lon * 1000)) % (2**31))

    rows = []
    for date_str in weekly_dates:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        day_of_year = dt.timetuple().tm_yday

        # Base climatological chl-a for this date and latitude
        base_chl = _seasonal_chl(lat, day_of_year)

        # Add interannual variability
        interannual_noise = rng.normal(0, base_chl * 0.15)
        week_chl = max(0.5, base_chl + interannual_noise)

        # Simulate occasional bloom events (elevated chl-a)
        if rng.random() < 0.05:
            bloom_factor = rng.uniform(2.0, 5.0)
            week_chl *= bloom_factor

        for glat in grid_lats:
            for glon in grid_lons:
                # Spatial variation
                spatial_noise = rng.normal(0, max(week_chl * 0.1, 0.3))
                point_chl = max(0.1, week_chl + spatial_noise)

                # Correlated environmental variables
                precip = max(0, rng.exponential(15) + (5 if rng.random() < 0.15 else 0))
                wind = max(0, rng.normal(5, 2.5))
                cloud = min(1.0, max(0.0, rng.beta(2, 5)))

                rows.append({
                    "date": date_str,
                    "lat": round(glat, 4),
                    "lon": round(glon, 4),
                    "chl_a": round(point_chl, 3),
                    "turbidity": round(max(0.1, point_chl * 0.15 + rng.normal(0, 0.3)), 3),
                    "sst_delta": round(rng.normal(0, 1.5), 3),
                    "precipitation_7d": round(precip, 2),
                    "wind_speed": round(wind, 2),
                    "source": "Sentinel3-synthetic",
                    "cloud_fraction": round(cloud, 3),
                })

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)

    logger.info(
        "[FETCH] SYNTHETIC data: %d rows, chl-a range %.3f - %.3f mg/m3",
        len(df), df["chl_a"].min(), df["chl_a"].max(),
    )
    logger.warning("[FETCH] ^^^ These are FAKE values from climatology, NOT real satellite measurements")

    return df


def _aggregate_to_weekly(sorted_dates: list[str]) -> list[str]:
    """
    Given a list of sorted date strings, pick one representative date per
    ISO week to avoid duplicate weeks of data.
    """
    seen_weeks: set[str] = set()
    weekly = []
    for d in sorted_dates:
        dt = datetime.strptime(d, "%Y-%m-%d")
        week_key = f"{dt.isocalendar()[0]}-W{dt.isocalendar()[1]:02d}"
        if week_key not in seen_weeks:
            seen_weeks.add(week_key)
            weekly.append(d)
    return weekly


# --- Caching ---

CACHE_DIR = Path(__file__).parent.parent / "data" / "cache"


def _cache_key(lat: float, lon: float) -> str:
    return f"{lat:.2f}_{lon:.2f}"


def get_cached_path(lat: float, lon: float) -> Path:
    return CACHE_DIR / f"{_cache_key(lat, lon)}.csv"


def save_to_cache(df: pd.DataFrame, lat: float, lon: float) -> Path:
    """Save DataFrame to CSV cache. Returns the path."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = get_cached_path(lat, lon)
    df.to_csv(path, index=False)
    return path


def load_from_cache(lat: float, lon: float) -> pd.DataFrame | None:
    """Load cached CSV if it exists. Returns None if not found."""
    path = get_cached_path(lat, lon)
    if not path.exists():
        logger.info("[CACHE] No exact cache for (%.2f, %.2f)", lat, lon)
        return None
    df = pd.read_csv(path, parse_dates=["date"])
    logger.info("[CACHE] Loaded %d rows from cache: %s", len(df), path.name)
    return df


def find_nearby_cache(lat: float, lon: float, tolerance: float = 0.1) -> pd.DataFrame | None:
    """Check if there's cached data for nearby coordinates (within tolerance degrees)."""
    if not CACHE_DIR.exists():
        return None

    for csv_file in CACHE_DIR.glob("*.csv"):
        try:
            parts = csv_file.stem.split("_")
            cached_lat = float(parts[0])
            cached_lon = float(parts[1])
            if abs(cached_lat - lat) <= tolerance and abs(cached_lon - lon) <= tolerance:
                df = pd.read_csv(csv_file, parse_dates=["date"])
                logger.info("[CACHE] Nearby cache hit: %s (%d rows)", csv_file.name, len(df))
                return df
        except (ValueError, IndexError):
            continue
    logger.info("[CACHE] No nearby cache for (%.2f, %.2f)", lat, lon)
    return None


def list_cached_regions() -> list[dict]:
    """Return metadata about all cached water body searches."""
    if not CACHE_DIR.exists():
        return []

    regions = []
    for csv_file in sorted(CACHE_DIR.glob("*.csv"), key=lambda f: f.stat().st_mtime, reverse=True):
        try:
            parts = csv_file.stem.split("_")
            cached_lat = float(parts[0])
            cached_lon = float(parts[1])

            df_full = pd.read_csv(csv_file, usecols=["date"])

            regions.append({
                "lat": cached_lat,
                "lon": cached_lon,
                "cache_key": csv_file.stem,
                "file_size_kb": round(csv_file.stat().st_size / 1024, 1),
                "data_points": len(df_full),
                "cached_at": datetime.fromtimestamp(csv_file.stat().st_mtime).isoformat(),
            })
        except (ValueError, IndexError):
            continue

    return regions
