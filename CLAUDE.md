# Toxic Pulse — Project Context

## What this is
Hackathon project: satellite-based water contamination detection system. Detects chlorophyll anomalies in Sentinel-3/MODIS data, attributes them to probable pollution sources via RAG, and generates Community Reports for low-income regions. The demo shows the 2014 Toledo water crisis detected 18 hours before the city shut down water for 500K people.

## Architecture
- **Frontend**: Next.js 14 + TypeScript + Tailwind + Mapbox GL JS + Recharts in `/frontend`
- **Backend**: FastAPI + LangChain + ChromaDB + scikit-learn in `/backend`
- **Data**: Pre-downloaded Sentinel-3 chlorophyll CSVs + curated RAG documents in `/data`
- **LLM**: Gemini 2.0 Flash via LangChain (NOT Anthropic API)

## User Flow (IMPORTANT)
The user experience is:
1. User enters ANY location (a body of water OR a land location) via a search bar
2. If it's a known water body → run the detection pipeline directly
3. If it's land or ambiguous → use KNN (haversine distance) to find the 3 closest monitored water bodies, present them to the user, and let them pick one (human-in-the-loop)
4. Selected water body loads on the map, anomalies appear, user clicks spikes to get RAG reports

The frontend needs a search/input bar at the top of the map. The backend needs:
- POST /api/search → accepts {query: string, lat?: float, lon?: float}
- Returns either {type: "direct", region: Region} or {type: "nearby", candidates: Region[]}
- Use Mapbox Geocoding API on frontend to convert text input to coordinates
- Backend KNN uses haversine distance from input coords to all monitored water body centers

## API Contract
The shared interface is defined in `backend/models.py`. Both frontend and backend agents MUST build to this contract. Do not deviate from the Pydantic schemas.

## Agent Boundaries — STRICTLY ENFORCED
- **data-agent**: ONLY touches files in `/data` and `backend/seed_db.py`
- **pipeline-agent**: ONLY touches files in `/backend`
- **frontend-agent**: ONLY touches files in `/frontend`
- NO agent may edit files outside its boundary
- NO agent may edit `CLAUDE.md`, `.claude/`, or `README.md`

## Design System
- Dark theme: background `#060D1B`, surface `#0B1120`, card `#0F172A`
- Accent: emerald `#10B981`
- Severity: critical `#EF4444`, severe `#F97316`, moderate `#FBBF24`
- Text: primary `#E2E8F0`, secondary `#94A3B8`, muted `#475569`, dim `#334155`
- Monospace for data readouts (coordinates, values, timestamps)
- All data readouts use monospace font
- Mapbox style: `mapbox://styles/mapbox/satellite-v9`

## Demo Regions
1. **Lake Erie** (USA): bbox [-83.5, 41.3, -82.5, 42.0], center [-83.0, 41.65]
   - Highlight: 2014-08-02 Toledo water crisis, chl-a 45.2 mg/m³
2. **Lake Victoria** (East Africa): bbox [31.5, -3.0, 35.0, 0.5], center [33.0, -1.0]
   - Highlight: 2023-04-15 bloom event, chl-a 28.6 mg/m³
3. **Mekong Delta** (Vietnam): bbox [105.5, 9.0, 107.0, 11.0], center [106.0, 10.0]
   - Highlight: 2023-09-20 industrial discharge, chl-a 22.1 mg/m³

## Detection Pipeline
Stage 1: Multi-source data ingestion (Sentinel-3 primary, MODIS gap-fill, ERA5 weather)
Stage 2: Feature engineering (rolling stats, seasonal adjustment, weather flags, rate of change)
Stage 3: Ensemble anomaly detection (Z-score + IsolationForest + spatial autocorrelation)
Stage 4: RAG attribution (multi-index retriever: permits, agriculture, watershed)
Stage 5: Structured report generation (Gemini 2.0 Flash, JSON output, confidence scores)

## Code Conventions
- Use Gemini API via LangChain for report generation, model: `gemini-2.0-flash`
- LangChain import: `from langchain_google_genai import ChatGoogleGenerativeAI`
- All API responses return JSON
- No hardcoded API keys, use environment variables via python-dotenv
- Backend: type hints on all functions, Pydantic models for request/response
- Frontend: TypeScript strict mode, named exports, components in individual files
- Commas instead of dashes in all user-facing text content

## Key Commands (Windows PowerShell)
```powershell
# Backend
cd backend; .\venv\Scripts\activate; uvicorn main:app --reload --port 8000

# Frontend
cd frontend; npm run dev

# Seed ChromaDB
cd backend; python seed_db.py

# Pre-cache demo reports
Invoke-RestMethod -Method POST http://localhost:8000/api/warmup
```

## When Compacting
Preserve: API contract (models.py schemas), agent boundaries, design system colors, demo region coordinates, detection pipeline stages, user flow (search bar → KNN → human-in-the-loop), Gemini as LLM (not Anthropic), and the demo script (Toledo 2014 is the hero story).
