---
name: rag-report
description: RAG attribution pipeline knowledge for generating community water quality reports. Use when implementing or debugging the attribution system.
user-invocable: false
---

## RAG Attribution Domain Knowledge

### Multi-index strategy
Three separate ChromaDB collections queried with different weights:
- permits (0.35): EPA NPDES permits, facility locations, discharge limits, violation history
- agriculture (0.30): FAO crop data, fertilizer rates, planting calendars, land use
- watershed (0.35): Tributary topology, flow directions, downstream communities, water intakes

### Query construction
Generate 4 queries per anomaly event to maximize retrieval coverage:
1. Permit-focused: "industrial discharge permits facilities near {lat} {lon} {region}"
2. Agriculture-focused: "agricultural fertilizer application crop types {region} {weather_context}"
3. Watershed-focused: "upstream tributaries watershed drainage {lat} {lon} downstream communities drinking water intakes"
4. Historical: "previous contamination events algal blooms {region} water quality incidents causes"

### LLM prompt structure
- Model: claude-sonnet-4-20250514
- Temperature: 0.2 (low for factual consistency)
- Max tokens: 2000
- Output: strict JSON matching CommunityReport schema
- Include: anomaly data (coordinates, severity, confidence, chl_a values, weather) + retrieved context

### Report JSON schema
```json
{
  "alert_level": "MODERATE|SEVERE|CRITICAL",
  "alert_summary": "string",
  "probable_sources": [{"source_name", "source_type", "likelihood", "evidence", "distance_km"}],
  "drinking_water_impact": {"at_risk_communities", "estimated_arrival_hours", "contaminant_type", "who_threshold_exceeded"},
  "recommended_actions": [{"priority": "immediate|within_24h|within_week", "action", "responsible_party"}],
  "historical_context": "string"
}
```

### Embeddings
- Model: all-MiniLM-L6-v2 (fast, good for short text chunks)
- Chunk size: 500 chars, overlap: 50
- Tag metadata: source file, region, document_type

### Deduplication
Hash first 100 chars of each retrieved chunk, skip duplicates, cap at 10 chunks for context.
