const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// === Types matching backend Pydantic models ===

export interface Region {
  id: string; // cache_key (e.g. "41.65_-83.00")
  name: string;
  country: string;
  bbox: number[];
  center: number[]; // [lon, lat]
  description: string;
  highlight_event?: string;
}

export interface TimelinePoint {
  date: string;
  chl_a_value: number;
  chl_a_baseline: number;
  z_score: number;
  severity: "none" | "moderate" | "severe" | "critical";
  confidence: number;
}

export interface AnomalyEvent {
  region_id: string;
  date: string;
  lat: number;
  lon: number;
  severity: string;
  confidence: number;
  chl_a_value: number;
  chl_a_baseline: number;
  z_score: number;
  weather_context: string;
}

export interface ProbableSource {
  source_name: string;
  source_type: string;
  likelihood: "high" | "medium" | "low";
  evidence: string;
  distance_km: number;
  coordinates?: number[];
}

export interface DrinkingWaterImpact {
  at_risk_communities: string[];
  estimated_arrival_hours: number;
  contaminant_type: string;
  who_threshold_exceeded: boolean;
  recommended_monitoring: string;
}

export interface RecommendedAction {
  priority: "immediate" | "within_24h" | "within_week";
  action: string;
  responsible_party: string;
}

export interface CommunityReport {
  alert_level: "MODERATE" | "SEVERE" | "CRITICAL";
  alert_summary: string;
  probable_sources: ProbableSource[];
  drinking_water_impact: DrinkingWaterImpact;
  recommended_actions: RecommendedAction[];
  historical_context: string;
  metadata?: Record<string, unknown>;
}

export interface RecentRegion {
  name: string;
  lat: number;
  lon: number;
  cache_key: string;
  data_points: number;
  cached_at: string;
}

export interface SearchResult {
  type: "direct";
  region: Region;
}

// === API Functions ===

export async function fetchRecent(): Promise<RecentRegion[]> {
  const res = await fetch(`${API_BASE}/api/recent`);
  if (!res.ok) throw new Error(`Failed to fetch recent: ${res.status}`);
  const data = await res.json();
  console.log("[API] /api/recent →", data.length, "entries");
  return data;
}

export async function fetchTimeline(lat: number, lon: number): Promise<TimelinePoint[]> {
  console.log(`[API] GET /api/timeline?lat=${lat}&lon=${lon}`);
  const res = await fetch(`${API_BASE}/api/timeline?lat=${lat}&lon=${lon}`);
  if (!res.ok) throw new Error(`Failed to fetch timeline: ${res.status}`);
  const data: TimelinePoint[] = await res.json();
  console.log(`[API] /api/timeline → ${data.length} points`);
  if (data.length > 0) {
    const anomalies = data.filter((p) => p.severity !== "none");
    console.log(`[API]   anomaly dates: ${anomalies.length}, severities:`, anomalies.map((p) => p.severity));
    const maxChl = Math.max(...data.map((p) => p.chl_a_value));
    console.log(`[API]   chl-a range: ${Math.min(...data.map((p) => p.chl_a_value)).toFixed(1)} - ${maxChl.toFixed(1)} mg/m³`);
  }
  return data;
}

export async function fetchAnomalies(lat: number, lon: number): Promise<GeoJSON.FeatureCollection> {
  console.log(`[API] GET /api/anomalies?lat=${lat}&lon=${lon}`);
  const res = await fetch(`${API_BASE}/api/anomalies?lat=${lat}&lon=${lon}`);
  if (!res.ok) throw new Error(`Failed to fetch anomalies: ${res.status}`);
  const data: GeoJSON.FeatureCollection = await res.json();
  console.log(`[API] /api/anomalies → ${data.features?.length ?? 0} GeoJSON features`);
  if (data.features?.length) {
    const byType: Record<string, number> = {};
    data.features.forEach((f) => {
      const sev = (f.properties as any)?.severity ?? "unknown";
      byType[sev] = (byType[sev] || 0) + 1;
    });
    console.log("[API]   severity breakdown:", byType);
    const first = data.features[0];
    console.log("[API]   first feature coords:", (first.geometry as any).coordinates, "props:", first.properties);
  }
  return data;
}

export async function fetchReport(event: AnomalyEvent): Promise<CommunityReport> {
  console.log("[API] POST /api/report", event);
  const res = await fetch(`${API_BASE}/api/report`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(event),
  });
  if (!res.ok) throw new Error(`Failed to fetch report: ${res.status}`);
  const data = await res.json();
  console.log("[API] /api/report →", data.alert_level, data.alert_summary?.slice(0, 80));
  return data;
}

export async function searchLocation(
  query: string,
  lat: number,
  lon: number
): Promise<SearchResult> {
  console.log(`[API] POST /api/search query="${query}" lat=${lat} lon=${lon}`);
  const res = await fetch(`${API_BASE}/api/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, lat, lon }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Search failed" }));
    throw new Error(err.detail || `Search failed: ${res.status}`);
  }
  const data = await res.json();
  console.log("[API] /api/search →", data.type, data.region?.name);
  return data;
}
