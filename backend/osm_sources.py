"""
Toxic Pulse — OpenStreetMap Facility Lookup

Queries the Overpass API for real industrial, agricultural, and wastewater
facilities near an anomaly point. Also provides reverse geocoding via Mapbox.
Results are cached per coordinate to avoid repeat requests.
"""

import math
import os
import time
import logging
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(dotenv_path=str(Path(__file__).parent.parent / ".env"))

logger = logging.getLogger("toxic_pulse.osm")

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

# Cache: rounded (lat, lon) -> list of facility dicts
_facility_cache: dict[str, list[dict]] = {}
# Cache: rounded (lat, lon) -> place name string
_geocode_cache: dict[str, str] = {}


def _cache_key(lat: float, lon: float) -> str:
    return f"{lat:.2f}_{lon:.2f}"


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km."""
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


def bearing_label(lat1: float, lon1: float, lat2: float, lon2: float) -> str:
    """Compass direction from point 1 to point 2."""
    dlon = math.radians(lon2 - lon1)
    y = math.sin(dlon) * math.cos(math.radians(lat2))
    x = (
        math.cos(math.radians(lat1)) * math.sin(math.radians(lat2))
        - math.sin(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.cos(dlon)
    )
    deg = (math.degrees(math.atan2(y, x)) + 360) % 360
    dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    return dirs[round(deg / 45) % 8]


def _classify_type(tags: dict) -> str:
    """Map OSM tags to a source type category."""
    if tags.get("man_made") == "wastewater_plant":
        return "wastewater_plant"
    if tags.get("amenity") == "waste_disposal":
        return "waste_disposal"
    if tags.get("industrial") == "chemical":
        return "chemical_plant"
    if tags.get("industrial") == "slaughterhouse":
        return "slaughterhouse"
    if tags.get("man_made") == "works":
        return "industrial_works"
    if tags.get("landuse") == "farmland":
        return "farmland"
    if tags.get("landuse") == "industrial":
        return "industrial_zone"
    if tags.get("craft"):
        return f"craft_{tags['craft']}"
    if tags.get("building") == "industrial":
        return "industrial_building"
    if tags.get("industrial"):
        return f"industrial_{tags['industrial']}"
    return "industrial"


def _extract_name(tags: dict) -> str:
    """Get the best available name from OSM tags."""
    for key in ("name", "name:en", "official_name", "operator"):
        if tags.get(key):
            return tags[key]
    # Fallback: use type description
    return _classify_type(tags).replace("_", " ").title()


def _get_coords(element: dict) -> tuple[float, float] | None:
    """Extract lat/lon from an Overpass element (node or way with center)."""
    if "lat" in element and "lon" in element:
        return element["lat"], element["lon"]
    if "center" in element:
        return element["center"]["lat"], element["center"]["lon"]
    return None


def _query_overpass_targeted(lat: float, lon: float, radius_m: int) -> list[dict]:
    """
    Run targeted Overpass queries in priority order. Splits into smaller
    queries to avoid timeouts in dense areas like China's Yangtze Delta.
    Returns combined list of raw Overpass elements.
    """
    # Split into separate queries by priority: high-value named targets first,
    # generic zones last (most likely to timeout due to volume)
    query_groups = [
        # Group 1: High-priority named point sources (wastewater, chemical plants)
        f"""[out:json][timeout:25];
(
  node["man_made"="wastewater_plant"](around:{radius_m},{lat},{lon});
  way["man_made"="wastewater_plant"](around:{radius_m},{lat},{lon});
  node["industrial"="chemical"](around:{radius_m},{lat},{lon});
  way["industrial"="chemical"](around:{radius_m},{lat},{lon});
  node["industrial"="slaughterhouse"](around:{radius_m},{lat},{lon});
  way["industrial"="slaughterhouse"](around:{radius_m},{lat},{lon});
  node["amenity"="waste_disposal"](around:{radius_m},{lat},{lon});
  way["amenity"="waste_disposal"](around:{radius_m},{lat},{lon});
  node["man_made"="works"](around:{radius_m},{lat},{lon});
  way["man_made"="works"](around:{radius_m},{lat},{lon});
);
out center tags;""",
        # Group 2: Any named industrial/factory features
        f"""[out:json][timeout:25];
(
  node["industrial"]["name"](around:{radius_m},{lat},{lon});
  way["industrial"]["name"](around:{radius_m},{lat},{lon});
  way["landuse"="industrial"]["name"](around:{radius_m},{lat},{lon});
  node["building"="industrial"]["name"](around:{radius_m},{lat},{lon});
  way["building"="industrial"]["name"](around:{radius_m},{lat},{lon});
  node["craft"](around:{radius_m},{lat},{lon});
  way["craft"](around:{radius_m},{lat},{lon});
);
out center tags;""",
        # Group 3: Unnamed industrial zones (limit to nearest 20)
        f"""[out:json][timeout:15];
(
  way["landuse"="industrial"](around:{radius_m},{lat},{lon});
);
out center tags 20;""",
        # Group 4: Farmland (limit to nearest 10)
        f"""[out:json][timeout:15];
(
  way["landuse"="farmland"](around:{radius_m},{lat},{lon});
);
out center tags 10;""",
    ]

    all_elements: list[dict] = []

    for i, query in enumerate(query_groups):
        if i > 0:
            time.sleep(1)  # Brief pause between queries to avoid rate limiting

        for mirror in OVERPASS_MIRRORS:
            try:
                logger.info("[OSM] Query group %d/%d via %s (radius=%dkm)...",
                            i + 1, len(query_groups), mirror.split("//")[1].split("/")[0], radius_m // 1000)
                resp = requests.post(mirror, data={"data": query}, timeout=30)

                if resp.status_code == 429:
                    logger.warning("[OSM] Rate limited on %s, trying mirror...", mirror.split("//")[1].split("/")[0])
                    time.sleep(2)
                    continue

                resp.raise_for_status()
                data = resp.json()
                elements = data.get("elements", [])
                logger.info("[OSM] Group %d returned %d elements", i + 1, len(elements))
                all_elements.extend(elements)
                break  # Success on this mirror, move to next group
            except requests.Timeout:
                logger.warning("[OSM] Group %d timed out on %s", i + 1, mirror.split("//")[1].split("/")[0])
                continue
            except Exception as e:
                logger.warning("[OSM] Group %d failed on %s: %s", i + 1, mirror.split("//")[1].split("/")[0], e)
                continue

    return all_elements


def fetch_nearby_facilities(
    lat: float, lon: float, radius_m: int = 25000
) -> list[dict]:
    """
    Query Overpass API for industrial/agricultural/wastewater features
    within radius_m of (lat, lon).

    For water bodies, expands search radius up to 50km since the anomaly
    point may be far from shore. Uses targeted queries that avoid
    timeouts in dense urban areas.

    Returns list of dicts:
    {
        name: str,
        type: str,
        source_category: "industrial" | "agricultural" | "municipal",
        lat: float, lon: float,
        distance_km: float,
        direction: str,  # "N", "NE", etc.
        tags: dict,      # raw OSM tags of interest
    }
    Sorted by distance ascending. Limited to 30 closest.
    """
    key = _cache_key(lat, lon)
    if key in _facility_cache:
        logger.info("[OSM] Cache hit for %s (%d facilities)", key, len(_facility_cache[key]))
        return _facility_cache[key]

    # Try progressively larger radii if initial search returns nothing
    all_elements: list[dict] = []
    for attempt_radius in [radius_m, radius_m * 2]:
        all_elements = _query_overpass_targeted(lat, lon, attempt_radius)
        if all_elements:
            break
        logger.info("[OSM] No results at %dkm, expanding search radius...", attempt_radius // 1000)

    if not all_elements:
        logger.warning("[OSM] No facilities found within %dkm of (%.2f, %.2f)", radius_m * 2 // 1000, lat, lon)
        _facility_cache[key] = []
        return []

    elements = all_elements
    logger.info("[OSM] Overpass returned %d raw elements", len(elements))

    # Deduplicate by name + type (ways and nodes can overlap)
    seen: set[str] = set()
    facilities: list[dict] = []

    for el in elements:
        tags = el.get("tags", {})
        coords = _get_coords(el)
        if not coords:
            continue

        el_lat, el_lon = coords
        name = _extract_name(tags)
        ftype = _classify_type(tags)

        dedup_key = f"{name}_{ftype}_{el_lat:.3f}_{el_lon:.3f}"
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        dist = haversine(lat, lon, el_lat, el_lon)
        direction = bearing_label(lat, lon, el_lat, el_lon)

        # Categorize for the report
        if ftype in ("wastewater_plant", "waste_disposal"):
            source_cat = "municipal"
        elif ftype == "farmland":
            source_cat = "agricultural"
        else:
            source_cat = "industrial"

        # Extract interesting tags for context
        context_tags = {}
        for t in ("operator", "product", "industrial", "landuse", "man_made",
                   "amenity", "capacity", "website", "description"):
            if tags.get(t):
                context_tags[t] = tags[t]

        facilities.append({
            "name": name,
            "type": ftype,
            "source_category": source_cat,
            "lat": round(el_lat, 5),
            "lon": round(el_lon, 5),
            "distance_km": round(dist, 1),
            "direction": direction,
            "tags": context_tags,
        })

    # Sort by distance, limit to 30
    facilities.sort(key=lambda f: f["distance_km"])
    facilities = facilities[:30]

    logger.info("[OSM] Parsed %d unique facilities (closest: %s at %.1fkm)",
                len(facilities),
                facilities[0]["name"] if facilities else "none",
                facilities[0]["distance_km"] if facilities else 0)

    _facility_cache[key] = facilities
    return facilities


def reverse_geocode(lat: float, lon: float) -> str:
    """
    Reverse geocode coordinates to a human-readable place name.
    Tries OpenStreetMap Nominatim first (no auth needed), then Mapbox as fallback.
    Returns e.g. "Spencer Gulf, South Australia, Australia" or coordinates as fallback.
    """
    key = _cache_key(lat, lon)
    if key in _geocode_cache:
        return _geocode_cache[key]

    # Try Nominatim (OpenStreetMap) — free, no auth required
    try:
        url = (
            f"https://nominatim.openstreetmap.org/reverse"
            f"?lat={lat}&lon={lon}&format=json&zoom=10&addressdetails=1&accept-language=en"
        )
        resp = requests.get(url, headers={"User-Agent": "ToxicPulse/2.0"}, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        # Build place name from address components
        addr = data.get("address", {})
        parts: list[str] = []

        # Try to get water body name first
        display = data.get("display_name", "")
        name = data.get("name", "")
        if name:
            parts.append(name)

        # Add locality/region context
        for field in ("city", "town", "county", "state", "country"):
            val = addr.get(field, "")
            if val and val not in parts:
                parts.append(val)
            if len(parts) >= 3:
                break

        if parts:
            place_name = ", ".join(parts)
            logger.info("[GEO] Nominatim (%.2f, %.2f) → %s", lat, lon, place_name)
            _geocode_cache[key] = place_name
            return place_name
    except Exception as e:
        logger.debug("[GEO] Nominatim failed: %s", e)

    # Fallback: Mapbox
    token = os.getenv("MAPBOX_ACCESS_TOKEN", "")
    if token:
        try:
            url = (
                f"https://api.mapbox.com/geocoding/v5/mapbox.places/{lon},{lat}.json"
                f"?access_token={token}&limit=3"
            )
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            features = data.get("features", [])
            if features:
                place_parts: list[str] = []
                for feat in features:
                    text = feat.get("text", "")
                    if text and text not in place_parts:
                        place_parts.append(text)
                    if len(place_parts) >= 3:
                        break
                place_name = ", ".join(place_parts)
                if place_name:
                    logger.info("[GEO] Mapbox (%.2f, %.2f) → %s", lat, lon, place_name)
                    _geocode_cache[key] = place_name
                    return place_name
        except Exception as e:
            logger.debug("[GEO] Mapbox failed: %s", e)

    fallback = f"{abs(lat):.2f}{'N' if lat >= 0 else 'S'}, {abs(lon):.2f}{'E' if lon >= 0 else 'W'}"
    _geocode_cache[key] = fallback
    return fallback


def format_facilities_for_prompt(facilities: list[dict]) -> str:
    """
    Format facility list as structured text for the Gemini prompt.
    Groups by category, includes name, type, distance, direction, and key tags.
    """
    if not facilities:
        return "(No nearby facilities found in OpenStreetMap data)"

    lines = []
    for f in facilities:
        tag_str = ""
        if f["tags"]:
            tag_parts = [f'{k}="{v}"' for k, v in f["tags"].items() if k != "landuse"]
            if tag_parts:
                tag_str = f" [{', '.join(tag_parts)}]"

        lines.append(
            f"- {f['name']}: {f['type'].replace('_', ' ')}, "
            f"{f['distance_km']}km {f['direction']}{tag_str}"
        )

    return "\n".join(lines)
