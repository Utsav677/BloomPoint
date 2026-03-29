"""
Toxic Pulse — API Contract (Pydantic Models)

Shared interface between frontend and backend.
Supports arbitrary water body coordinates (no hardcoded regions).
"""

from pydantic import BaseModel
from typing import Optional


# === Request Models ===

class SearchRequest(BaseModel):
    """Search for a water body by name. Frontend geocodes to lat/lon."""
    query: str
    lat: Optional[float] = None
    lon: Optional[float] = None


class AnomalyEvent(BaseModel):
    """Sent from frontend when user clicks an anomaly point."""
    region_id: str  # cache_key (e.g. "41.65_-83.00")
    date: str
    lat: float
    lon: float
    severity: str  # "moderate" | "severe" | "critical"
    confidence: float
    chl_a_value: float
    chl_a_baseline: float
    z_score: float
    weather_context: str  # "post_rainfall_runoff" | "wind_driven_resuspension" | "calm_conditions"


# === Response Models ===

class Region(BaseModel):
    """A water body region, dynamically built from coordinates."""
    id: str  # cache_key
    name: str
    country: str
    bbox: list[float]  # [min_lon, min_lat, max_lon, max_lat]
    center: list[float]  # [lon, lat]
    description: str
    highlight_event: Optional[str] = None  # ISO date, optional for dynamic regions


class TimelinePoint(BaseModel):
    """One data point in the chlorophyll time series chart."""
    date: str
    chl_a_value: float
    chl_a_baseline: float
    z_score: float
    severity: str  # "none" | "moderate" | "severe" | "critical"
    confidence: float


class AnomalyFeature(BaseModel):
    """GeoJSON Feature properties for a detected anomaly."""
    date: str
    severity: str
    confidence: float
    chl_a: float
    baseline: float
    z_score: float
    weather_context: str
    event_id: str


class ProbableSource(BaseModel):
    """A ranked pollution source in the community report."""
    source_name: str
    source_type: str  # "industrial" | "agricultural" | "municipal" | "natural"
    likelihood: str  # "high" | "medium" | "low"
    evidence: str
    distance_km: float
    coordinates: Optional[list[float]] = None  # [lat, lon] if known


class DrinkingWaterImpact(BaseModel):
    """Downstream drinking water risk assessment."""
    at_risk_communities: list[str]
    estimated_arrival_hours: float
    contaminant_type: str  # "algal_toxins" | "nutrient_loading" | "sediment" | "chemical"
    who_threshold_exceeded: bool
    recommended_monitoring: str


class RecommendedAction(BaseModel):
    """A prioritized action item."""
    priority: str  # "immediate" | "within_24h" | "within_week"
    action: str
    responsible_party: str


class CommunityReport(BaseModel):
    """The full RAG-generated community water quality report."""
    alert_level: str  # "MODERATE" | "SEVERE" | "CRITICAL"
    alert_summary: str
    probable_sources: list[ProbableSource]
    drinking_water_impact: DrinkingWaterImpact
    recommended_actions: list[RecommendedAction]
    historical_context: str
    metadata: Optional[dict] = None


class RecentRegion(BaseModel):
    """A recently searched water body from the cache."""
    name: str
    lat: float
    lon: float
    cache_key: str
    data_points: int
    cached_at: str
