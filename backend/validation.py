"""
Toxic Pulse — Validation Suite

Runs the full detection pipeline against documented real-world contamination
events to build a confusion matrix and compute accuracy metrics.

Ground truth includes TRUE POSITIVE events (confirmed blooms) and
TRUE NEGATIVE controls (same locations during clean periods).
"""

import os
import io
import json
import math
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import requests

logger = logging.getLogger("toxic_pulse.validation")

# ---------------------------------------------------------------------------
# Ground truth: documented real-world events
# ---------------------------------------------------------------------------

GROUND_TRUTH = [
    # ---- TRUE POSITIVES (blooms confirmed) ----
    {
        "name": "Lake Erie — Toledo water crisis",
        "lat": 41.65, "lon": -83.0,
        "date": "2014-08-02",
        "bloom_confirmed": True,
        "notes": "Microcystin contaminated Toledo drinking water, 500K without tap water",
    },
    {
        "name": "Lake Erie — Largest recorded bloom 5000 km²",
        "lat": 41.5, "lon": -82.8,
        "date": "2011-10-01",
        "bloom_confirmed": True,
        "notes": "Record-setting bloom covering 5,000 km² of western Lake Erie",
    },
    {
        "name": "Spencer Gulf — Karenia bloom",
        "lat": -34.5, "lon": 137.0,
        "date": "2024-09-15",
        "bloom_confirmed": True,
        "notes": "Karenia mikimotoi bloom in Spencer Gulf, South Australia",
    },
    {
        "name": "Lake Tai — Wuxi water crisis",
        "lat": 31.2, "lon": 120.2,
        "date": "2007-08-01",
        "bloom_confirmed": True,
        "notes": "2 million people lost tap water due to massive cyanobacteria bloom",
    },
    {
        "name": "Lake Okeechobee — State of emergency",
        "lat": 26.95, "lon": -80.83,
        "date": "2018-07-15",
        "bloom_confirmed": True,
        "notes": "Florida declared state of emergency over toxic algae bloom",
    },
    {
        "name": "Chesapeake Bay — Record dead zone",
        "lat": 37.8, "lon": -76.1,
        "date": "2019-08-15",
        "bloom_confirmed": True,
        "notes": "Record-size dead zone driven by excessive nutrient runoff",
    },
    {
        "name": "Gulf of Mexico — Largest dead zone 22,720 km²",
        "lat": 29.0, "lon": -89.5,
        "date": "2017-07-15",
        "bloom_confirmed": True,
        "notes": "Largest measured dead zone in Gulf of Mexico history",
    },
    {
        "name": "Baltic Sea — Massive cyanobacteria bloom",
        "lat": 57.5, "lon": 19.5,
        "date": "2019-07-15",
        "bloom_confirmed": True,
        "notes": "Massive cyanobacteria bloom visible from satellite across Baltic Sea",
    },
    {
        "name": "Lake Winnipeg — Algal bloom",
        "lat": 51.0, "lon": -96.8,
        "date": "2017-09-15",
        "bloom_confirmed": True,
        "notes": "Recurring algal bloom in Lake Winnipeg, phosphorus-driven",
    },
    {
        "name": "Seto Inland Sea Japan — Red tide",
        "lat": 34.3, "lon": 133.5,
        "date": "2022-08-15",
        "bloom_confirmed": True,
        "notes": "Red tide event in Seto Inland Sea affecting fisheries",
    },
    # ---- TRUE NEGATIVES (same locations, clean periods) ----
    {
        "name": "Lake Erie — Winter baseline (no bloom)",
        "lat": 41.65, "lon": -83.0,
        "date": "2014-02-15",
        "bloom_confirmed": False,
        "notes": "Winter period, ice cover, no algal activity expected",
    },
    {
        "name": "Spencer Gulf — Pre-bloom baseline",
        "lat": -34.5, "lon": 137.0,
        "date": "2023-02-15",
        "bloom_confirmed": False,
        "notes": "Before Karenia bloom started, normal conditions",
    },
    {
        "name": "Lake Tai — Winter low activity",
        "lat": 31.2, "lon": 120.2,
        "date": "2020-01-15",
        "bloom_confirmed": False,
        "notes": "Winter period, low biological activity",
    },
    {
        "name": "Lake Okeechobee — Dry season",
        "lat": 26.95, "lon": -80.83,
        "date": "2019-12-15",
        "bloom_confirmed": False,
        "notes": "Dry season, reduced nutrient loading",
    },
    {
        "name": "Chesapeake Bay — Winter baseline",
        "lat": 37.8, "lon": -76.1,
        "date": "2020-02-15",
        "bloom_confirmed": False,
        "notes": "Winter period, minimal biological activity",
    },
]

# ---------------------------------------------------------------------------
# NASA ERDDAP fetch for a custom date window (historical)
# ---------------------------------------------------------------------------

ERDDAP_BASE = "https://coastwatch.pfeg.noaa.gov/erddap/griddap"

# Datasets in priority order
_DATASETS = [
    ("erdMH1chla8day_R2022NRT", "chlorophyll", "MODIS-Aqua-8day-NRT"),
    ("erdMH1chlamday_R2022NRT", "chlorophyll", "MODIS-Aqua-Monthly-NRT"),
    ("nesdisVHNSQchlaWeekly", "chlor_a", "VIIRS-SNPP-Weekly"),
]

# Validation data cache directory
_CACHE_DIR = Path(__file__).parent / ".validation_cache"


def _cache_path(event: dict) -> Path:
    """Return cache file path for a validation event."""
    safe_name = event["name"].replace(" ", "_").replace("/", "_").replace("—", "-")
    return _CACHE_DIR / f"{safe_name}.csv"


def _fetch_erddap_window(
    lat: float, lon: float,
    center_date: datetime,
    window_days: int = 60,
    bbox_delta: float = 0.5,
) -> pd.DataFrame:
    """
    Fetch chl-a from NASA ERDDAP for a specific date window
    around a historical event.
    """
    start = center_date - timedelta(days=window_days)
    end = center_date + timedelta(days=window_days)

    start_str = start.strftime("%Y-%m-%dT00:00:00Z")
    end_str = end.strftime("%Y-%m-%dT00:00:00Z")

    lat_min, lat_max = lat - bbox_delta, lat + bbox_delta
    lon_min, lon_max = lon - bbox_delta, lon + bbox_delta

    for dataset_id, var_name, sensor_name in _DATASETS:
        url = (
            f"{ERDDAP_BASE}/{dataset_id}.csv"
            f"?{var_name}"
            f"[({start_str}):({end_str})]"
            f"[({lat_min}):({lat_max})]"
            f"[({lon_min}):({lon_max})]"
        )
        logger.info("  [VAL] Trying %s for %s around %s", sensor_name, f"({lat},{lon})", center_date.date())

        try:
            resp = requests.get(url, timeout=120)
            if resp.status_code != 200:
                logger.debug("  [VAL] %s returned HTTP %d", sensor_name, resp.status_code)
                continue

            df = _parse_csv(resp.text, var_name)
            if df is not None and len(df) > 0:
                logger.info("  [VAL] %s returned %d rows", sensor_name, len(df))
                return _augment(df, sensor_name)
        except Exception as e:
            logger.warning("  [VAL] %s failed: %s", sensor_name, e)

    return pd.DataFrame()


def _parse_csv(csv_text: str, var_name: str) -> pd.DataFrame | None:
    """Parse ERDDAP CSV (skip units row)."""
    lines = csv_text.strip().split("\n")
    if len(lines) < 3:
        return None

    csv_clean = lines[0] + "\n" + "\n".join(lines[2:])
    try:
        df = pd.read_csv(io.StringIO(csv_clean))
    except Exception:
        return None

    if df.empty:
        return None

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
    if not {"date", "lat", "lon", "chl_a"}.issubset(df.columns):
        return None

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])
    df["chl_a"] = pd.to_numeric(df["chl_a"], errors="coerce")
    df = df.dropna(subset=["chl_a"])
    df = df[(df["chl_a"] > 0) & (df["chl_a"] < 300)]
    df["lat"] = df["lat"].round(4)
    df["lon"] = df["lon"].round(4)

    return df[["date", "lat", "lon", "chl_a"]].reset_index(drop=True)


def _augment(df: pd.DataFrame, source: str) -> pd.DataFrame:
    """Add environmental variables (same logic as nasa_ocean_color.py)."""
    df = df.copy()
    n = len(df)
    rng = np.random.RandomState(42)

    df["turbidity"] = (df["chl_a"] * 0.15 + rng.normal(0, 0.3, n)).clip(lower=0.1).round(3)
    df["sst_delta"] = (rng.normal(0, 1.5, n) + (df["chl_a"] > 10).astype(float) * 0.5).round(3)
    precip = rng.exponential(12, n)
    heavy = rng.random(n) < 0.12
    precip[heavy] += rng.uniform(30, 80, heavy.sum())
    df["precipitation_7d"] = precip.clip(min=0).round(2)
    df["wind_speed"] = rng.normal(5, 2.5, n).clip(min=0).round(2)
    df["cloud_fraction"] = rng.beta(2, 5, n).clip(0, 1).round(3)
    df["source"] = source

    return df


# ---------------------------------------------------------------------------
# Haversine distance
# ---------------------------------------------------------------------------

def _haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


# ---------------------------------------------------------------------------
# Run validation for a single event
# ---------------------------------------------------------------------------

def _validate_event(event: dict) -> dict:
    """
    Fetch data, run full pipeline, check if system detects an anomaly
    within 30 days and 50 km of the known event.
    """
    from features import compute_features
    from detection import AnomalyDetector

    name = event["name"]
    lat, lon = event["lat"], event["lon"]
    center_date = datetime.strptime(event["date"], "%Y-%m-%d")
    expected_bloom = event["bloom_confirmed"]

    result = {
        "name": name,
        "lat": lat,
        "lon": lon,
        "date": event["date"],
        "expected": "bloom" if expected_bloom else "clean",
        "detected": False,
        "severity": "none",
        "max_z_score": 0.0,
        "max_chl_a": 0.0,
        "data_points": 0,
        "error": None,
    }

    # Check cache first
    cache_file = _cache_path(event)
    raw_df = None

    if cache_file.exists():
        logger.info("[VAL] Using cached data for: %s", name)
        try:
            raw_df = pd.read_csv(cache_file, parse_dates=["date"])
        except Exception:
            raw_df = None

    if raw_df is None or raw_df.empty:
        logger.info("[VAL] Fetching NASA data for: %s", name)
        try:
            raw_df = _fetch_erddap_window(lat, lon, center_date, window_days=60)
        except Exception as e:
            result["error"] = f"Fetch failed: {e}"
            logger.error("[VAL] Fetch failed for %s: %s", name, e)
            return result

        if raw_df.empty:
            result["error"] = "No satellite data available for this location/date"
            return result

        # Cache the raw data
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        raw_df.to_csv(cache_file, index=False)

    result["data_points"] = len(raw_df)

    # Normalize
    if not pd.api.types.is_datetime64_any_dtype(raw_df["date"]):
        raw_df["date"] = pd.to_datetime(raw_df["date"])
    numeric_cols = raw_df.select_dtypes(include="number").columns.tolist()
    raw_df[numeric_cols] = raw_df[numeric_cols].ffill()
    raw_df = raw_df.dropna(subset=numeric_cols)
    raw_df = raw_df.sort_values("date").reset_index(drop=True)

    if len(raw_df) < 5:
        result["error"] = f"Insufficient data: only {len(raw_df)} points"
        return result

    # Feature engineering
    try:
        feat_df = compute_features(raw_df)
    except Exception as e:
        result["error"] = f"Feature engineering failed: {e}"
        return result

    if feat_df.empty:
        result["error"] = "Feature engineering produced empty result"
        return result

    # Anomaly detection
    try:
        region_id = f"{lat:.2f}_{lon:.2f}"
        detector = AnomalyDetector()
        det_df = detector.detect(feat_df, region_id=region_id)
    except Exception as e:
        result["error"] = f"Detection failed: {e}"
        return result

    # Record max chl-a and z-score across all data
    result["max_chl_a"] = round(float(det_df["chl_a_value"].max()), 2)
    result["max_z_score"] = round(float(det_df["z_score"].abs().max()), 2)

    # Check for anomaly within 30 days and 50 km of the event
    anomalies = det_df[det_df["severity"] != "none"].copy()

    if anomalies.empty:
        return result

    # Filter by proximity in time and space
    event_date = pd.Timestamp(center_date)
    for _, row in anomalies.iterrows():
        row_date = pd.Timestamp(row["date"])
        days_diff = abs((row_date - event_date).days)
        dist_km = _haversine(lat, lon, float(row["lat"]), float(row["lon"]))

        if days_diff <= 30 and dist_km <= 50:
            result["detected"] = True
            # Keep the worst severity found
            sev_order = {"moderate": 1, "severe": 2, "critical": 3}
            if sev_order.get(row["severity"], 0) > sev_order.get(result["severity"], 0):
                result["severity"] = row["severity"]

    return result


# ---------------------------------------------------------------------------
# Full validation suite
# ---------------------------------------------------------------------------

_cached_results: dict | None = None


def run_validation() -> dict:
    """
    Run the full validation suite against all ground truth events.
    Returns confusion matrix, metrics, and per-event details.
    """
    global _cached_results

    logger.info("=" * 60)
    logger.info("[VAL] Starting validation suite with %d events", len(GROUND_TRUTH))
    logger.info("=" * 60)

    start_time = time.time()
    event_results = []

    for i, event in enumerate(GROUND_TRUTH):
        logger.info("[VAL] (%d/%d) Processing: %s", i + 1, len(GROUND_TRUTH), event["name"])
        result = _validate_event(event)
        event_results.append(result)
        logger.info(
            "[VAL]   → expected=%s, detected=%s, severity=%s, z=%.1f, chl=%.1f",
            result["expected"], result["detected"], result["severity"],
            result["max_z_score"], result["max_chl_a"],
        )

    elapsed = time.time() - start_time

    # Build confusion matrix
    tp = sum(1 for r in event_results if r["expected"] == "bloom" and r["detected"])
    fn = sum(1 for r in event_results if r["expected"] == "bloom" and not r["detected"])
    tn = sum(1 for r in event_results if r["expected"] == "clean" and not r["detected"])
    fp = sum(1 for r in event_results if r["expected"] == "clean" and r["detected"])

    total = tp + fn + tn + fp
    accuracy = (tp + tn) / total if total > 0 else 0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

    # Identify false negatives with explanations
    false_negatives = []
    for r in event_results:
        if r["expected"] == "bloom" and not r["detected"]:
            if r["error"]:
                explanation = f"Pipeline error: {r['error']}"
            elif r["data_points"] == 0:
                explanation = "No satellite data available for this location/date window"
            elif r["max_z_score"] < 2.0:
                explanation = (
                    f"Max z-score was {r['max_z_score']:.1f} (below threshold of 2.0). "
                    f"Max chl-a was {r['max_chl_a']:.1f} mg/m³. The bloom may have been "
                    f"too gradual for the rolling-baseline detector, or satellite coverage "
                    f"was sparse during the peak."
                )
            else:
                explanation = (
                    f"Z-score reached {r['max_z_score']:.1f} but the ensemble vote "
                    f"(z-score + IsolationForest + spatial) did not reach the 0.65 threshold. "
                    f"This can happen when the bloom is spatially isolated or the multivariate "
                    f"features don't align."
                )
            false_negatives.append({"event": r["name"], "explanation": explanation})

    # Build per-event detail list with pass/fail
    details = []
    for r in event_results:
        expected_bloom = r["expected"] == "bloom"
        detected = r["detected"]
        passed = (expected_bloom and detected) or (not expected_bloom and not detected)

        details.append({
            "name": r["name"],
            "date": r["date"],
            "lat": r["lat"],
            "lon": r["lon"],
            "expected": r["expected"],
            "detected": "yes" if detected else "no",
            "severity": r["severity"],
            "max_z_score": r["max_z_score"],
            "max_chl_a": r["max_chl_a"],
            "data_points": r["data_points"],
            "passed": passed,
            "error": r["error"],
        })

    output = {
        "confusion_matrix": {
            "true_positive": tp,
            "false_negative": fn,
            "true_negative": tn,
            "false_positive": fp,
        },
        "metrics": {
            "accuracy": round(accuracy, 4),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1_score": round(f1, 4),
        },
        "details": details,
        "false_negatives": false_negatives,
        "total_events": len(GROUND_TRUTH),
        "elapsed_seconds": round(elapsed, 1),
        "run_at": datetime.utcnow().isoformat() + "Z",
    }

    _cached_results = output
    return output


def get_cached_results() -> dict | None:
    """Return cached validation results from the last run, or None."""
    return _cached_results
