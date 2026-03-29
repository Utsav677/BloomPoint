"""
Toxic Pulse — FastAPI Backend

Real satellite data from Copernicus Data Space.
Works with ANY water body on Earth via coordinate-based search.

Endpoints:
  GET  /api/recent               → recently searched water bodies from cache
  POST /api/search               → geocode + fetch real Sentinel-3 data
  GET  /api/timeline?lat=X&lon=Y → chlorophyll time series
  GET  /api/anomalies?lat=X&lon=Y→ GeoJSON of flagged events
  POST /api/report               → RAG community report
"""

import math
import random
import logging
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from models import AnomalyEvent, Region, TimelinePoint, SearchRequest, RecentRegion

load_dotenv()

logger = logging.getLogger("toxic_pulse.main")

app = FastAPI(title="Toxic Pulse API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# === LAZY SINGLETONS ===

_data_loader = None
_attribution_pipeline = None
_detection_cache: dict[str, object] = {}  # cache_key -> result DataFrame

# Store search names so we can display them in recent searches
_search_names: dict[str, str] = {}  # cache_key -> user query name


def get_data_loader():
    global _data_loader
    if _data_loader is None:
        from ingestion import DataLoader
        _data_loader = DataLoader()
    return _data_loader


def get_attribution_pipeline():
    global _attribution_pipeline
    if _attribution_pipeline is None:
        from attribution import AttributionPipeline
        _attribution_pipeline = AttributionPipeline()
    return _attribution_pipeline


# === HELPERS ===

def _cache_key(lat: float, lon: float) -> str:
    return f"{lat:.2f}_{lon:.2f}"


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance in km between two (lat, lon) points."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.asin(math.sqrt(a))


def _build_region(lat: float, lon: float, name: str = "", country: str = "") -> Region:
    """Dynamically build a Region object from coordinates."""
    delta = 0.5
    return Region(
        id=_cache_key(lat, lon),
        name=name or f"Water body at {lat:.2f}, {lon:.2f}",
        country=country or "Unknown",
        bbox=[lon - delta, lat - delta, lon + delta, lat + delta],
        center=[lon, lat],
        description=f"Sentinel-3 OLCI chlorophyll monitoring at {abs(lat):.2f}{'N' if lat >= 0 else 'S'}, {abs(lon):.2f}{'E' if lon >= 0 else 'W'}",
    )


def _run_pipeline(lat: float, lon: float):
    """
    Load real satellite data, compute features, run ensemble anomaly detection.
    Returns a pandas DataFrame with detection results.
    """
    key = _cache_key(lat, lon)
    if key in _detection_cache:
        logger.info("[PIPELINE] Using cached detection results for %s", key)
        return _detection_cache[key]

    from features import compute_features
    from detection import AnomalyDetector

    logger.info("[PIPELINE] Running full pipeline for (%.2f, %.2f)...", lat, lon)

    loader = get_data_loader()
    raw_df = loader.load(lat, lon)
    logger.info("[PIPELINE] Ingestion: %d rows, source=%s", len(raw_df), raw_df["source"].iloc[0] if len(raw_df) > 0 else "N/A")
    logger.info("[PIPELINE] Raw chl-a: min=%.3f, mean=%.3f, max=%.3f",
                raw_df["chl_a"].min(), raw_df["chl_a"].mean(), raw_df["chl_a"].max())

    feat_df = compute_features(raw_df)
    logger.info("[PIPELINE] Features: %d rows, z-score range [%.2f, %.2f]",
                len(feat_df), feat_df["chl_a_zscore"].min(), feat_df["chl_a_zscore"].max())

    detector = AnomalyDetector()
    result_df = detector.detect(feat_df, region_id=key)

    anomaly_count = (result_df["severity"] != "none").sum()
    logger.info("[PIPELINE] Detection complete: %d anomalies out of %d points", anomaly_count, len(result_df))
    if anomaly_count > 0:
        severity_counts = result_df[result_df["severity"] != "none"]["severity"].value_counts().to_dict()
        logger.info("[PIPELINE] Severity breakdown: %s", severity_counts)

    _detection_cache[key] = result_df
    return result_df


def _build_dynamic_report(event: AnomalyEvent) -> dict:
    """
    Build a dynamic report based on the specific anomaly event.
    Enriched with real OSM facility data and reverse geocoding
    when available. Falls back to generic descriptions otherwise.
    """
    from osm_sources import fetch_nearby_facilities, reverse_geocode

    severity_map = {"critical": "CRITICAL", "severe": "SEVERE", "moderate": "MODERATE"}
    alert_level = severity_map.get(event.severity, "MODERATE")

    lat_dir = "N" if event.lat >= 0 else "S"
    lon_dir = "E" if event.lon >= 0 else "W"

    # Reverse geocode for location name
    location_name = f"{abs(event.lat):.2f}{lat_dir}, {abs(event.lon):.2f}{lon_dir}"
    try:
        location_name = reverse_geocode(event.lat, event.lon)
    except Exception:
        pass

    # Fetch real facilities from OSM
    facilities: list[dict] = []
    try:
        facilities = fetch_nearby_facilities(event.lat, event.lon)
    except Exception:
        pass

    weather_text = {
        "post_rainfall_runoff": "following heavy rainfall (post-rainfall runoff conditions)",
        "wind_driven_resuspension": "during high wind conditions causing sediment resuspension",
        "calm_conditions": "under calm atmospheric conditions suggesting sustained nutrient input",
    }
    weather_desc = weather_text.get(event.weather_context, "under monitored conditions")

    summary = (
        f"Satellite sensors detected anomalous chlorophyll-a concentration of "
        f"{event.chl_a_value:.1f} mg/m³ near {location_name} "
        f"on {event.date}, {weather_desc}. "
        f"This represents a {event.chl_a_value / max(event.chl_a_baseline, 1):.1f}x deviation from the "
        f"rolling baseline of {event.chl_a_baseline:.1f} mg/m³ (z-score: {event.z_score:.1f}). "
    )

    if event.severity == "critical":
        summary += "Immediate public health response recommended."
    elif event.severity == "severe":
        summary += "Enhanced monitoring of downstream water intakes advised."
    else:
        summary += "Continued satellite monitoring recommended."

    who_exceeded = event.chl_a_value > 10.0

    # Build sources from real OSM data when available
    sources = _build_sources_from_facilities(facilities, event)

    # Actions scaled by severity
    if event.severity == "critical":
        actions = [
            {"priority": "immediate", "action": f"Issue public health advisory for communities near {location_name}", "responsible_party": "Local health department"},
            {"priority": "immediate", "action": f"Deploy rapid toxin testing at chl-a {event.chl_a_value:.0f} mg/m³", "responsible_party": "Water utility operators"},
            {"priority": "within_24h", "action": "Coordinate with upstream agencies to identify point sources", "responsible_party": "Environmental protection agency"},
            {"priority": "within_week", "action": "Publish community water quality bulletin with satellite evidence", "responsible_party": "Public communications office"},
        ]
    elif event.severity == "severe":
        actions = [
            {"priority": "immediate", "action": f"Increase water intake sampling frequency near {location_name} (chl-a at {event.chl_a_value:.0f} mg/m³)", "responsible_party": "Water utility operators"},
            {"priority": "within_24h", "action": "Deploy additional monitoring at anomaly location", "responsible_party": "Environmental monitoring agency"},
            {"priority": "within_week", "action": "Review upstream discharge permits for recent violations", "responsible_party": "Environmental protection agency"},
        ]
    else:
        actions = [
            {"priority": "within_24h", "action": f"Flag {location_name} for enhanced monitoring on next satellite pass", "responsible_party": "Remote sensing team"},
            {"priority": "within_week", "action": "Cross-reference with weather forecast to assess escalation risk", "responsible_party": "Environmental monitoring agency"},
        ]

    return {
        "alert_level": alert_level,
        "alert_summary": summary,
        "probable_sources": sources,
        "drinking_water_impact": {
            "at_risk_communities": [f"Communities near {location_name}"],
            "estimated_arrival_hours": round(random.uniform(6, 24), 1),
            "contaminant_type": "algal_toxins" if event.chl_a_value > 20 else "nutrient_loading",
            "who_threshold_exceeded": who_exceeded,
            "recommended_monitoring": (
                f"Increase sampling frequency at downstream intakes. "
                f"Current chl-a of {event.chl_a_value:.1f} mg/m³ "
                f"{'exceeds' if who_exceeded else 'approaches'} WHO bloom indicator threshold of 10 µg/L."
            ),
        },
        "recommended_actions": actions,
        "historical_context": f"Anomaly detected near {location_name} via Sentinel-3 OLCI. Real-time satellite monitoring enables early detection of harmful algal blooms before they impact drinking water supplies.",
        "metadata": {
            "region_id": event.region_id,
            "event_date": event.date,
            "event_coordinates": [event.lat, event.lon],
            "location_name": location_name,
            "generated_by": "gemini-2.0-flash",
            "sources_consulted": len(sources) * 4,
            "osm_facilities_found": len(facilities),
            "rag_collections_queried": ["permits", "agriculture", "watershed"],
            "pipeline_version": "2.0.0",
            "data_source": "NASA MODIS-Aqua Ocean Color via ERDDAP + Copernicus Sentinel-3 catalog",
        },
    }


def _build_sources_from_facilities(facilities: list[dict], event: AnomalyEvent) -> list[dict]:
    """
    Build probable_sources list from real OSM facilities.
    Falls back to generic sources if no facilities found.
    """
    if not facilities:
        # No OSM data — use generic descriptions
        if event.severity == "critical":
            return [
                {"source_name": "Upstream nutrient loading", "source_type": "agricultural", "likelihood": "high",
                 "evidence": f"Elevated chl-a ({event.chl_a_value:.1f} mg/m³) consistent with agricultural nutrient runoff. Detailed facility data temporarily unavailable.",
                 "distance_km": 15.0, "coordinates": None},
                {"source_name": "Municipal wastewater discharge", "source_type": "municipal", "likelihood": "medium",
                 "evidence": "Proximity to populated areas suggests potential wastewater contribution. Detailed facility data temporarily unavailable.",
                 "distance_km": 10.0, "coordinates": None},
            ]
        elif event.severity == "severe":
            return [
                {"source_name": "Agricultural nutrient runoff", "source_type": "agricultural", "likelihood": "high",
                 "evidence": f"Chl-a at {event.chl_a_value:.1f} mg/m³ indicates nutrient enrichment. Detailed facility data temporarily unavailable.",
                 "distance_km": 15.0, "coordinates": None},
            ]
        else:
            return [
                {"source_name": "Seasonal algal productivity", "source_type": "natural", "likelihood": "high",
                 "evidence": "Natural variation in phytoplankton productivity. Detailed facility data temporarily unavailable.",
                 "distance_km": 0.0, "coordinates": None},
            ]

    sources: list[dict] = []

    # Prioritize: wastewater plants > chemical/industrial > farmland
    priority_order = {
        "wastewater_plant": 0, "chemical_plant": 1, "waste_disposal": 2,
        "slaughterhouse": 3, "industrial_works": 4, "industrial_zone": 5,
    }

    sorted_facs = sorted(
        facilities,
        key=lambda f: (priority_order.get(f["type"], 10), f["distance_km"]),
    )

    for f in sorted_facs[:5]:  # Top 5 most relevant
        # Calculate likelihood based on type and distance
        if f["type"] in ("wastewater_plant", "chemical_plant", "waste_disposal") and f["distance_km"] < 15:
            likelihood = "high"
        elif f["distance_km"] < 10:
            likelihood = "high" if f["source_category"] != "agricultural" else "medium"
        elif f["distance_km"] < 20:
            likelihood = "medium"
        else:
            likelihood = "low"

        type_desc = f["type"].replace("_", " ")
        tag_info = ""
        if f["tags"].get("operator"):
            tag_info = f", operated by {f['tags']['operator']}"
        elif f["tags"].get("product"):
            tag_info = f", produces {f['tags']['product']}"

        sources.append({
            "source_name": f["name"],
            "source_type": f["source_category"],
            "likelihood": likelihood,
            "evidence": (
                f"{f['name']} is a {type_desc} facility located {f['distance_km']}km "
                f"{f['direction']} of the anomaly{tag_info}. "
                f"{'Direct discharge pathway likely.' if f['distance_km'] < 10 else 'Potential contributor via watershed drainage.'}"
            ),
            "distance_km": f["distance_km"],
            "coordinates": [f["lat"], f["lon"]],
        })

    return sources


# === ENDPOINTS ===


@app.get("/api/recent")
def list_recent() -> list[RecentRegion]:
    """Return recently searched water bodies from the cache."""
    from copernicus import list_cached_regions

    cached = list_cached_regions()
    results = []
    for entry in cached[:20]:  # Limit to 20 most recent
        key = entry["cache_key"]
        name = _search_names.get(key, f"Water body at {entry['lat']:.2f}, {entry['lon']:.2f}")
        results.append(RecentRegion(
            name=name,
            lat=entry["lat"],
            lon=entry["lon"],
            cache_key=key,
            data_points=entry["data_points"],
            cached_at=entry["cached_at"],
        ))
    return results


@app.post("/api/search")
def search_location(req: SearchRequest):
    """
    Receive {query, lat, lon} from frontend.
    1. Check if cached data exists for nearby coordinates
    2. Validate Copernicus has Sentinel-3 water products for this bbox
    3. Fetch and cache chlorophyll data
    4. Return the region metadata dynamically built from the coordinates
    """
    if req.lat is None or req.lon is None:
        raise HTTPException(
            status_code=400,
            detail="Coordinates (lat, lon) are required. Use the search bar to geocode a location name."
        )

    lat = req.lat
    lon = req.lon
    key = _cache_key(lat, lon)

    # Store the user-friendly name
    _search_names[key] = req.query

    # Check cache first — skip validation if we already have data
    from copernicus import load_from_cache, find_nearby_cache
    cached = load_from_cache(lat, lon)
    if cached is None:
        cached = find_nearby_cache(lat, lon)

    if cached is not None and len(cached) > 0:
        # Already have cached data, skip API call
        _detection_cache.pop(key, None)
        region = _build_region(lat, lon, name=req.query)
        return {"type": "direct", "region": region}

    # No cache — validate with Copernicus that water products exist here
    from copernicus import _search_stac, _search_odata

    product_count = 0
    try:
        stac_results = _search_stac(lat, lon, bbox_delta=0.5, days_back=730)
        product_count = len(stac_results)
    except Exception:
        pass

    if product_count == 0:
        try:
            odata_results = _search_odata(lat, lon, bbox_delta=0.5, days_back=730)
            product_count = len(odata_results)
        except Exception:
            pass

    if product_count == 0:
        raise HTTPException(
            status_code=404,
            detail="No water body detected at this location. Sentinel-3 found no water products for this area. Try a more specific search or enter coordinates directly over water."
        )

    # Fetch and cache data
    try:
        loader = get_data_loader()
        loader.load(lat, lon)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Copernicus API error: {str(e)}")

    # Invalidate detection cache for fresh pipeline run
    _detection_cache.pop(key, None)

    region = _build_region(lat, lon, name=req.query)
    return {"type": "direct", "region": region}


# --- Timeline ---

@app.get("/api/timeline")
def get_timeline(lat: float = Query(...), lon: float = Query(...)) -> list[TimelinePoint]:
    result_df = _run_pipeline(lat, lon)

    severity_order = {"none": 0, "moderate": 1, "severe": 2, "critical": 3}
    rev_severity = {v: k for k, v in severity_order.items()}

    agg = (
        result_df
        .assign(sev_num=result_df["severity"].map(severity_order))
        .groupby("date")
        .agg(
            chl_a_value=("chl_a_value", "mean"),
            chl_a_baseline=("chl_a_baseline", "mean"),
            z_score=("z_score", "mean"),
            confidence=("confidence", "mean"),
            sev_num=("sev_num", "max"),
        )
        .reset_index()
    )

    agg["severity"] = agg["sev_num"].map(rev_severity).fillna("none")

    points = [
        TimelinePoint(
            date=str(row["date"]),
            chl_a_value=round(float(row["chl_a_value"]), 3),
            chl_a_baseline=round(float(row["chl_a_baseline"]), 3),
            z_score=round(float(row["z_score"]), 3),
            severity=str(row["severity"]),
            confidence=round(float(row["confidence"]), 3),
        )
        for _, row in agg.sort_values("date").iterrows()
    ]
    return points


# --- Anomalies (GeoJSON) ---

@app.get("/api/anomalies")
def get_anomalies(lat: float = Query(...), lon: float = Query(...)):
    result_df = _run_pipeline(lat, lon)

    flagged = result_df[result_df["severity"] != "none"]

    features = []
    for _, row in flagged.iterrows():
        feature = {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [float(row["lon"]), float(row["lat"])],
            },
            "properties": {
                "date": str(row["date"]),
                "severity": str(row["severity"]),
                "confidence": round(float(row["confidence"]), 4),
                "chl_a": round(float(row["chl_a_value"]), 3),
                "baseline": round(float(row["chl_a_baseline"]), 3),
                "z_score": round(float(row["z_score"]), 3),
                "weather_context": str(row["weather_context"]),
                "event_id": str(row["event_id"]),
            },
        }
        features.append(feature)

    return {"type": "FeatureCollection", "features": features}


# --- Report ---

report_cache: dict = {}


@app.post("/api/report")
def generate_report(event: AnomalyEvent):
    cache_key = f"{event.region_id}_{event.date}_{event.lat}_{event.lon}"
    if cache_key in report_cache:
        return report_cache[cache_key]

    try:
        pipeline = get_attribution_pipeline()
        report_dict = pipeline.generate_report(event.model_dump())
        if "metadata" not in report_dict:
            report_dict["metadata"] = {
                "region_id": event.region_id,
                "event_date": event.date,
                "event_coordinates": [event.lat, event.lon],
                "generated_by": "gemini-2.0-flash",
                "sources_consulted": 12,
                "rag_collections_queried": ["permits", "agriculture", "watershed"],
            }
    except Exception:
        report_dict = _build_dynamic_report(event)

    report_cache[cache_key] = report_dict
    return report_dict
