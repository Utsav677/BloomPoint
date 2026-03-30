# BloomPoint

**Satellite-based water contamination detection with AI-powered attribution for any water body on Earth.**

BloomPoint turns free satellite data into environmental accountability reports: it detects harmful algal blooms and pollution events from space, identifies the most probable pollution sources using real facility data, and generates actionable community water quality reports — all with zero on-the-ground sensors.

---

## How It Works

```
User searches "Lake Erie"
        |
        v
  Mapbox Geocoding (frontend)
  converts name -> coordinates
        |
        v
  POST /api/search (backend)
  validates Copernicus has
  Sentinel-3 data at those coords
        |
        v
  NASA ERDDAP + Copernicus
  fetches 2 years of real
  chlorophyll-a satellite data
        |
        v
  Feature Engineering
  rolling stats, seasonal
  adjustment, weather flags
        |
        v
  Ensemble Anomaly Detection
  Z-score (35%) + IsolationForest
  (35%) + Spatial autocorrelation (30%)
        |
        v
  Map shows anomaly dots
  Timeline shows chl-a history
  User clicks an anomaly dot
        |
        v
  OpenStreetMap Overpass API
  finds real nearby facilities
  (wastewater plants, factories,
  farms) within 25-50km
        |
        v
  ChromaDB RAG Retrieval
  queries 3 collections with
  4 query strategies (36 chunks)
        |
        v
  Gemini 2.0 Flash
  synthesizes satellite data +
  real facilities + knowledge base
  into structured JSON report
        |
        v
  Community Report panel
  with attribution, risk assessment,
  recommended actions, and PDF export
```

### The 5-Stage Detection Pipeline

| Stage | What happens | Technology |
|-------|-------------|------------|
| **1. Data Ingestion** | Fetches real chlorophyll-a measurements from NASA MODIS-Aqua (primary) or generates from Copernicus Sentinel-3 catalog metadata | NASA ERDDAP griddap API, Copernicus STAC/OData |
| **2. Feature Engineering** | Computes rolling means, standard deviations, seasonal baselines, rate of change, and weather-correlated flags | pandas, numpy |
| **3. Anomaly Detection** | Runs an ensemble of 3 detectors with weighted voting to flag bloom/pollution events | scikit-learn IsolationForest, scipy z-scores, BallTree spatial clustering |
| **4. RAG Attribution** | Retrieves relevant permit, agriculture, and watershed documents from a vector database, plus queries OpenStreetMap for real nearby facilities | ChromaDB, sentence-transformers, Overpass API, Nominatim |
| **5. Report Generation** | Synthesizes all context into a structured community report with source attribution, risk assessment, and recommended actions | Gemini 2.0 Flash via LangChain |

### What Gemini 2.0 Flash Does (Stage 5)

Gemini is the **reasoning layer** that activates only when a user clicks an anomaly dot. It does NOT detect anomalies (scikit-learn does that) or find facilities (OpenStreetMap does that). Gemini receives:

- Satellite anomaly metrics (chl-a concentration, z-score, severity, weather context)
- **Real facility names and locations** from OpenStreetMap (e.g., "Whyalla Steelworks, 23.5km NW")
- Knowledge base chunks from ChromaDB (EPA permits, WHO guidelines, watershed maps, agricultural zones, historical incidents)
- A reverse-geocoded location name (e.g., "Spencer Gulf, South Australia, Australia")

And produces a structured JSON report containing:
- **Probable sources** ranked by likelihood, citing real facility names, distances, and evidence
- **Drinking water impact** assessment with at-risk communities and estimated contaminant arrival time
- **Recommended actions** prioritized by urgency with responsible parties
- **Historical context** connecting to past events in the region

Temperature is set to 0.3 for factual consistency. The prompt strictly instructs Gemini to only reference real facilities from the provided data and never hallucinate names.

---

## Prerequisites

### Accounts (free tiers)
1. **Copernicus Data Space** — https://dataspace.copernicus.eu (satellite metadata validation)
2. **Mapbox** — https://account.mapbox.com/auth/signup (map tiles + geocoding, 50k free loads/month)
3. **Google AI Studio** — https://aistudio.google.com/apikey (Gemini API key for report generation)

### Software
- **Node.js** >= 18
- **Python** >= 3.10
- **Git**

### Verify
```bash
node --version      # >= 18
python --version    # >= 3.10
git --version
```

---

## Setup Instructions

### 1. Clone the repository

```bash
git clone https://github.com/Utsav677/BloomPoint.git
cd BloomPoint
```

### 2. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` with your keys:

```env
# Required for report generation (Gemini 2.0 Flash)
GOOGLE_API_KEY=your-google-ai-key

# Required for map tiles and geocoding
MAPBOX_ACCESS_TOKEN=pk.eyJ-your-token

# Required for satellite data validation
COPERNICUS_USER=your_email@example.com
COPERNICUS_PASSWORD=your_password

# Optional: Mapbox fallback for reverse geocoding (Nominatim is primary)
MAPBOX_ACCESS_TOKEN=pk.eyJ-your-token
```

The frontend also needs the Mapbox token. Create `frontend/.env.local`:

```env
NEXT_PUBLIC_MAPBOX_TOKEN=pk.eyJ-your-token
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### 3. Install backend dependencies

```bash
cd backend
python -m venv venv

# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate

pip install -r requirements.txt
cd ..
```

### 4. Seed the knowledge base

This embeds curated environmental documents into ChromaDB for the RAG pipeline:

```bash
cd backend
python seed_db.py
cd ..
```

You should see output like:
```
=== Toxic Pulse — ChromaDB Seeder ===

Found 5 document(s) in ../data/docs:
  agricultural_zones.md
  epa_permits.md
  historical_incidents.md
  watershed_maps.md
  who_guidelines.md

Seeding complete. X chunks upserted across 3 collections.

=== Collection Summary ===
  permits        :   XX documents
  agriculture    :   XX documents
  watershed      :   XX documents
```

### 5. Install frontend dependencies

```bash
cd frontend
npm install
cd ..
```

### 6. Run the application

Open two terminals:

**Terminal 1 — Backend:**
```bash
cd backend
venv\Scripts\activate          # or source venv/bin/activate
uvicorn main:app --reload --port 8000
```

**Terminal 2 — Frontend:**
```bash
cd frontend
npm run dev
```

Open http://localhost:3000 in your browser.

---

## Usage

1. **Search any water body** — Type a location name (e.g., "Lake Erie", "Spencer Gulf", "Mekong Delta") in the search bar at the top of the map. The system geocodes it via Mapbox and fetches 2 years of real satellite chlorophyll data from NASA.

2. **View anomalies on the map** — Detected bloom/pollution events appear as colored dots on the satellite map:
   - Yellow = moderate anomaly
   - Orange = severe anomaly
   - Red = critical anomaly

3. **Explore the timeline** — The bottom chart shows chlorophyll-a concentration over time. Colored spikes indicate anomaly events. Click any spike to generate a report.

4. **Click an anomaly dot** — Triggers the full RAG attribution pipeline:
   - Queries OpenStreetMap for real nearby industrial, agricultural, and wastewater facilities
   - Retrieves relevant documents from the ChromaDB knowledge base
   - Sends everything to Gemini 2.0 Flash for structured report generation
   - Displays the Community Water Quality Report in the right panel

5. **Export the report** — Use the "PDF" button to download a professional PDF report, or "Copy" to copy the report as formatted text to your clipboard.

6. **Recent searches** — Previously searched water bodies appear in the left sidebar with cached data for instant reload.

---

## Project Structure

```
BloomPoint/
├── .env.example                       Environment variable template
├── CLAUDE.md                          Project context for Claude Code
├── README.md                          You are here
│
├── backend/
│   ├── requirements.txt               Python dependencies
│   ├── main.py                        FastAPI app, routes, fallback report builder
│   ├── models.py                      Pydantic schemas (shared API contract)
│   ├── ingestion.py                   Data loading and normalization
│   ├── copernicus.py                  Copernicus STAC/OData + NASA ERDDAP integration
│   ├── nasa_ocean_color.py            NASA ERDDAP griddap client for real chl-a data
│   ├── features.py                    Feature engineering (rolling stats, baselines)
│   ├── detection.py                   Ensemble anomaly detection
│   ├── attribution.py                 RAG pipeline + Gemini report generation
│   ├── osm_sources.py                 OpenStreetMap facility lookup + geocoding
│   └── seed_db.py                     ChromaDB knowledge base seeder
│
├── frontend/
│   ├── package.json                   Node.js dependencies
│   ├── next.config.mjs                Next.js configuration
│   ├── tailwind.config.ts             Tailwind CSS theme (dark mode, custom palette)
│   └── src/
│       ├── app/
│       │   ├── layout.tsx             Root layout (dark theme, JetBrains Mono font)
│       │   ├── page.tsx               Main dashboard page
│       │   └── globals.css            Global styles + custom animations
│       ├── components/
│       │   ├── Map.tsx                Mapbox GL satellite map with anomaly dots
│       │   ├── Timeline.tsx           Recharts chlorophyll time series chart
│       │   ├── ReportPanel.tsx        Community report panel + PDF export
│       │   ├── SearchBar.tsx          Location search with Mapbox geocoding
│       │   └── ScanAnimation.tsx      Satellite scan loading animation
│       └── lib/
│           └── api.ts                 API client with TypeScript types
│
└── data/
    ├── docs/                          RAG knowledge base (markdown)
    │   ├── epa_permits.md             EPA discharge permits and violations
    │   ├── agricultural_zones.md      Agricultural land use and runoff data
    │   ├── who_guidelines.md          WHO drinking water quality guidelines
    │   ├── watershed_maps.md          Watershed boundaries and flow data
    │   └── historical_incidents.md    Past water contamination events
    └── chroma_db/                     Persisted ChromaDB vector store (auto-generated)
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/search` | Geocode + validate + fetch satellite data for a location |
| `GET` | `/api/timeline?lat=X&lon=Y` | Chlorophyll-a time series with anomaly flags |
| `GET` | `/api/anomalies?lat=X&lon=Y` | GeoJSON FeatureCollection of detected anomalies |
| `POST` | `/api/report` | Generate RAG community report for an anomaly event |
| `GET` | `/api/recent` | List recently searched water bodies from cache |

### Example: Search for a water body

```bash
curl -X POST http://localhost:8000/api/search \
  -H "Content-Type: application/json" \
  -d '{"query": "Lake Erie", "lat": 41.65, "lon": -83.0}'
```

### Example: Get anomalies

```bash
curl "http://localhost:8000/api/anomalies?lat=41.65&lon=-83.0"
```

### Example: Generate a report

```bash
curl -X POST http://localhost:8000/api/report \
  -H "Content-Type: application/json" \
  -d '{
    "region_id": "41.65_-83.00",
    "date": "2024-08-02",
    "lat": 41.65,
    "lon": -83.0,
    "severity": "critical",
    "confidence": 0.92,
    "chl_a_value": 45.2,
    "chl_a_baseline": 5.1,
    "z_score": 12.5,
    "weather_context": "post_rainfall_runoff"
  }'
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 14, TypeScript, Tailwind CSS, Mapbox GL JS, Recharts |
| Backend | FastAPI, Python 3.10+, Pydantic |
| Satellite Data | NASA MODIS-Aqua via ERDDAP (primary), Copernicus Sentinel-3 OLCI (validation) |
| Anomaly Detection | scikit-learn (IsolationForest), scipy (z-scores), BallTree (spatial) |
| RAG Pipeline | LangChain, ChromaDB, sentence-transformers (all-MiniLM-L6-v2) |
| LLM | Google Gemini 2.0 Flash via LangChain |
| Facility Data | OpenStreetMap Overpass API, Nominatim reverse geocoding |
| Maps | Mapbox GL JS (satellite-v9 basemap) |
| PDF Export | jsPDF + jspdf-autotable |

---

## Data Sources

All data sources are **free and require no paid subscriptions**:

| Source | What it provides | Access |
|--------|-----------------|--------|
| **NASA ERDDAP** | Real chlorophyll-a measurements from MODIS-Aqua satellite (4km resolution, 8-day composites, 2002-present) | Free, no auth |
| **Copernicus Data Space** | Sentinel-3 OLCI product catalog for validation | Free account |
| **OpenStreetMap** | Real facility names, locations, and types (wastewater plants, factories, farms) | Free, no auth |
| **Nominatim** | Reverse geocoding (coordinates to place names) | Free, no auth |
| **Mapbox** | Satellite map tiles, forward geocoding | Free tier (50k loads/month) |

---

## Key Design Decisions

- **No sensors required** — Uses existing satellite infrastructure that images every water body on Earth. The data already exists; BloomPoint packages the intelligence.
- **Real facility attribution** — Unlike generic "agricultural runoff" labels, BloomPoint queries OpenStreetMap for actual named facilities and their distances, giving reports that name specific sources.
- **Ensemble detection** — Three independent anomaly detectors vote to reduce false positives: statistical (z-score), machine learning (IsolationForest), and spatial (BallTree autocorrelation).
- **Works anywhere** — No pre-configured regions. Search any coordinate on Earth and the system dynamically fetches satellite data, detects anomalies, and generates reports.
- **Graceful degradation** — If Gemini is unavailable, the system falls back to rule-based report generation using real OSM facility data. If OSM fails, generic descriptions are used.

---

## Troubleshooting

### "No water body detected at this location"
The backend validates that Copernicus has Sentinel-3 water products for the searched coordinates. Try searching directly over a lake, river, or coastal area rather than inland.

### Backend returns 502 or hangs on first search
The first search for a new location takes 15-30 seconds because it fetches 2 years of satellite data from NASA ERDDAP and runs the full detection pipeline. Subsequent searches for the same location are cached and instant.

### Map shows no anomaly dots
Check the browser console for `[MAP]` logs. If anomalies are returned by the API but dots don't appear, it may be a Mapbox style loading race condition — refresh the page.

### ChromaDB errors on `/api/report`
Run `cd backend && python seed_db.py` to seed the knowledge base. The RAG pipeline requires the 3 ChromaDB collections to be populated.

### PDF export fails
Ensure `jspdf` and `jspdf-autotable` are installed: `cd frontend && npm install jspdf jspdf-autotable --legacy-peer-deps`

---

## License

MIT
