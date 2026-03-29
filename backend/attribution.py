"""
Toxic Pulse — RAG Attribution Pipeline

Multi-index retriever across permits, agriculture, watershed ChromaDB collections.
Generates structured CommunityReport JSON via Gemini 2.0 Flash.
"""

import json
import logging
import re
import os
from pathlib import Path

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
from langchain_google_genai import ChatGoogleGenerativeAI
from dotenv import load_dotenv

from osm_sources import fetch_nearby_facilities, reverse_geocode, format_facilities_for_prompt

logger = logging.getLogger("toxic_pulse.attribution")


_REPORT_PROMPT = """\
You are an environmental analyst. Given satellite-detected water quality anomaly data, \
retrieved knowledge base documents, and REAL nearby facility data from OpenStreetMap, \
generate a structured community water quality report.

ANOMALY EVENT:
- Region: {region_id}
- Location name: {location_name}
- Date: {date}
- Coordinates: {lat}, {lon}
- Severity: {severity}
- Chlorophyll-a: {chl_a_value} mg/m³ (baseline: {chl_a_baseline})
- Z-score: {z_score}
- Weather: {weather_context}

NEARBY FACILITIES (from OpenStreetMap — these are REAL places):
{facilities}

KNOWLEDGE BASE CONTEXT:
{context}

IMPORTANT INSTRUCTIONS:
- Use the REAL facility names from the OpenStreetMap data above in your probable_sources.
- Do NOT invent or hallucinate facility names. Only reference facilities from the provided data.
- Calculate likelihood based on: facility type (wastewater plants and chemical plants = higher \
risk than farmland), distance (closer = higher likelihood), and direction relative to \
water flow.
- For agricultural sources, reference the actual farmland areas listed above.
- Include the facility's actual distance and coordinates in your response.
- Use the location name ("{location_name}") in your alert_summary and community references.

Generate a JSON response with this exact structure:
{{
  "alert_level": "MODERATE" or "SEVERE" or "CRITICAL",
  "alert_summary": "2-3 sentence summary for community members, mentioning {location_name}",
  "probable_sources": [
    {{
      "source_name": "Actual facility name from OSM data above",
      "source_type": "industrial" or "agricultural" or "municipal" or "natural",
      "likelihood": "high" or "medium" or "low",
      "evidence": "Why this specific facility is a probable source, citing distance and type",
      "distance_km": 0.0,
      "coordinates": [lat, lon] or null
    }}
  ],
  "drinking_water_impact": {{
    "at_risk_communities": ["real community names near {location_name}"],
    "estimated_arrival_hours": 0.0,
    "contaminant_type": "algal_toxins" or "nutrient_loading" or "sediment" or "chemical",
    "who_threshold_exceeded": true/false,
    "recommended_monitoring": "..."
  }},
  "recommended_actions": [
    {{
      "priority": "immediate" or "within_24h" or "within_week",
      "action": "...",
      "responsible_party": "..."
    }}
  ],
  "historical_context": "1-2 sentences connecting to past events in the {location_name} region"
}}

Map severity to alert_level: moderate->MODERATE, severe->SEVERE, critical->CRITICAL.
Return ONLY valid JSON, no markdown formatting.\
"""


class AttributionPipeline:
    """
    RAG pipeline that takes an anomaly event and produces a structured
    Community Report with probable source attribution.

    Uses:
    - 3 ChromaDB collections: permits, agriculture, watershed
    - 4 query strategies per event
    - Gemini 2.0 Flash structured JSON output
    """

    def __init__(self, chroma_path: str = "../data/chroma_db"):
        # Load .env from project root (one level above backend/)
        load_dotenv(dotenv_path=str(Path(__file__).parent.parent / ".env"))

        # ChromaDB
        client = chromadb.PersistentClient(path=str(Path(chroma_path)))
        self._embed_fn = SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )

        self._collections = {
            name: client.get_or_create_collection(
                name=name,
                embedding_function=self._embed_fn,
                metadata={"hnsw:space": "cosine"},
            )
            for name in ("permits", "agriculture", "watershed")
        }

        # Gemini 2.0 Flash via LangChain
        self._llm = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash",
            temperature=0.3,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_report(self, anomaly_event: dict) -> dict:
        """Generate a structured CommunityReport for a single anomaly event."""
        lat = anomaly_event.get("lat", 0.0)
        lon = anomaly_event.get("lon", 0.0)

        # Fetch real facility data from OpenStreetMap
        facilities = []
        facilities_text = "(Detailed facility data temporarily unavailable)"
        try:
            facilities = fetch_nearby_facilities(lat, lon)
            facilities_text = format_facilities_for_prompt(facilities)
            logger.info("[ATTR] Found %d real facilities near (%.2f, %.2f)", len(facilities), lat, lon)
        except Exception as e:
            logger.warning("[ATTR] OSM facility lookup failed: %s", e)

        # Reverse geocode for a human-readable location name
        location_name = "the affected area"
        try:
            location_name = reverse_geocode(lat, lon)
            logger.info("[ATTR] Location: %s", location_name)
        except Exception as e:
            logger.warning("[ATTR] Reverse geocode failed: %s", e)

        # RAG context from ChromaDB
        queries = self._build_queries(anomaly_event)
        docs = self._retrieve(queries)
        context = self._format_context(docs)

        prompt_text = _REPORT_PROMPT.format(
            region_id=anomaly_event.get("region_id", "unknown"),
            location_name=location_name,
            date=anomaly_event.get("date", "unknown"),
            lat=lat,
            lon=lon,
            severity=anomaly_event.get("severity", "unknown"),
            chl_a_value=anomaly_event.get("chl_a_value", 0.0),
            chl_a_baseline=anomaly_event.get("chl_a_baseline", 0.0),
            z_score=round(anomaly_event.get("z_score", 0.0), 2),
            weather_context=anomaly_event.get("weather_context", "calm_conditions"),
            facilities=facilities_text,
            context=context,
        )

        response = self._llm.invoke(prompt_text)
        raw = response.content if hasattr(response, "content") else str(response)

        report = self._parse_json_response(raw)

        # Inject real coordinates into probable_sources from OSM data
        report = self._enrich_sources_with_coords(report, facilities)

        # Add facility data to metadata
        if "metadata" not in report:
            report["metadata"] = {}
        report["metadata"]["osm_facilities_found"] = len(facilities)
        report["metadata"]["location_name"] = location_name

        return report

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_queries(self, event: dict) -> list[str]:
        """Generate 4 retrieval queries covering different attribution angles."""
        lat = event.get("lat", 0.0)
        lon = event.get("lon", 0.0)
        region_name = event.get("region_id", "unknown").replace("_", " ")
        weather = event.get("weather_context", "")
        date = event.get("date", "")

        return [
            f"pollution sources near {lat}, {lon} water contamination",
            f"agricultural runoff nutrient loading {weather} chlorophyll {date}",
            f"industrial discharge permits violations near {region_name}",
            f"watershed downstream communities drinking water intake {region_name}",
        ]

    @staticmethod
    def _enrich_sources_with_coords(report: dict, facilities: list[dict]) -> dict:
        """
        Match probable_sources in the report to actual OSM facilities
        and inject their real coordinates if the LLM didn't include them.
        """
        if not facilities or "probable_sources" not in report:
            return report

        # Build a lookup by lowercased name
        facility_lookup: dict[str, dict] = {}
        for f in facilities:
            facility_lookup[f["name"].lower()] = f

        for source in report["probable_sources"]:
            name = source.get("source_name", "").lower()
            if not source.get("coordinates"):
                # Try exact match first, then substring match
                matched = facility_lookup.get(name)
                if not matched:
                    for fname, fdata in facility_lookup.items():
                        if fname in name or name in fname:
                            matched = fdata
                            break
                if matched:
                    source["coordinates"] = [matched["lat"], matched["lon"]]
                    if not source.get("distance_km") or source["distance_km"] == 0:
                        source["distance_km"] = matched["distance_km"]

        return report

    def _retrieve(self, queries: list[str]) -> list[str]:
        """
        Query each of the 3 collections with each query (n_results=3).
        Deduplicate by document content. Return list of unique document strings.
        """
        seen: set[str] = set()
        unique_docs: list[str] = []

        for query in queries:
            for coll in self._collections.values():
                try:
                    results = coll.query(query_texts=[query], n_results=3)
                    for doc in (results.get("documents") or [[]])[0]:
                        if doc and doc not in seen:
                            seen.add(doc)
                            unique_docs.append(doc)
                except Exception:
                    # Collection may be empty; skip gracefully
                    continue

        return unique_docs

    def _format_context(self, docs: list[str]) -> str:
        """Join docs with separator and truncate to 8000 chars."""
        joined = "\n---\n".join(docs)
        return joined[:8000]

    @staticmethod
    def _parse_json_response(raw: str) -> dict:
        """
        Extract and parse JSON from a Gemini response.
        Handles responses wrapped in markdown code fences.
        """
        # Strip markdown code fences if present
        cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`").strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            # Try to find the first {...} block
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass

        # Fallback: return a minimal valid CommunityReport structure
        return {
            "alert_level": "MODERATE",
            "alert_summary": "Report generation encountered an error. Manual review required.",
            "probable_sources": [],
            "drinking_water_impact": {
                "at_risk_communities": [],
                "estimated_arrival_hours": 0.0,
                "contaminant_type": "algal_toxins",
                "who_threshold_exceeded": False,
                "recommended_monitoring": "Contact local water authority.",
            },
            "recommended_actions": [],
            "historical_context": "No historical context available.",
        }
