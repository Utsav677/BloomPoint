# Toxic Pulse

Satellite-based water contamination detection with RAG-powered attribution for low-income regions.

Turns free Sentinel-3 satellite data into environmental accountability reports naming probable pollution sources, estimating downstream drinking water impact, and recommending immediate actions — with zero on-the-ground sensors.

---

## Prerequisites (install before starting the clock)

### Accounts to create (free, 5 min each)
1. **Copernicus Data Space** — https://dataspace.copernicus.eu (satellite data)
2. **Mapbox** — https://account.mapbox.com/auth/signup (map tiles, 50k free loads)
3. **Anthropic API key** — https://console.anthropic.com (for RAG report generation)

### Software requirements
- **Node.js** >= 18 (for Next.js frontend + MCP servers)
- **Python** >= 3.10 (for FastAPI backend)
- **Claude Code** — `npm install -g @anthropic-ai/claude-code`
- **Git**
- **tmux** (recommended, for swarm mode split panes)

### Verify everything works
```bash
node --version          # >= 18
python3 --version       # >= 3.10
claude --version        # latest
git --version
tmux -V                 # optional but recommended
```

---

## Step-by-Step: Empty Folder to Running MVP

### Step 0: Clone or unzip this scaffold
```bash
# If you unzipped this folder:
cd toxic-pulse

# Initialize git
git init
git add .
git commit -m "initial scaffold"
```

### Step 1: Set environment variables
```bash
# Create .env in project root
cp .env.example .env

# Edit with your keys:
# ANTHROPIC_API_KEY=sk-ant-...
# MAPBOX_ACCESS_TOKEN=pk.ey...
# COPERNICUS_USER=your_email
# COPERNICUS_PASSWORD=your_password
```

### Step 2: Install MCP servers
```bash
# Core productivity MCPs
claude mcp add github -- npx -y @modelcontextprotocol/server-github
claude mcp add sequential-thinking -- npx -y @modelcontextprotocol/server-sequential-thinking
claude mcp add context7 -- npx -y @upstash/context7-mcp@latest
claude mcp add memory -- npx -y @modelcontextprotocol/server-memory
```

### Step 3: Install backend dependencies
```bash
cd backend
python3 -m venv venv
source venv/bin/activate    # Windows: venv\Scripts\activate
pip install -r requirements.txt
cd ..
```

### Step 4: Install frontend dependencies
```bash
cd frontend
npm install
cd ..
```

### Step 5: Enable swarm mode and launch Claude Code
```bash
# Start a tmux session (recommended for agent teams)
tmux new-session -s toxic-pulse

# Enable agent teams
export CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1

# Launch Claude Code from the project root
claude
```

### Step 6: Kick off the agent team
Paste this prompt into Claude Code:

```
Read CLAUDE.md for full project context. I'm building Toxic Pulse for a
hackathon in 12 hours. Create an agent team with these specialists:

1. "data-agent" — Owns /data. Downloads sample Sentinel-3 chlorophyll
   CSVs for Lake Erie, Lake Victoria, and Mekong Delta. Curates the RAG
   document corpus (EPA permits, agricultural data, WHO guidelines,
   watershed maps, historical incidents). Embeds everything into ChromaDB.
   This agent finishes first and gets dismissed.

2. "pipeline-agent" — Owns /backend. Builds FastAPI with anomaly
   detection (Z-score + IsolationForest + spatial clustering ensemble),
   RAG attribution pipeline (LangChain + ChromaDB multi-index), and all
   API endpoints. Never touches frontend code.

3. "frontend-agent" — Owns /frontend. Builds the Next.js dashboard with
   Mapbox GL satellite map, Recharts chlorophyll timeline, slide-in
   report panel, and region selector. Dark theme, emerald accent.
   Never touches backend code.

Start with data-agent, then pipeline-agent and frontend-agent in parallel.
The API contract is defined in backend/models.py — both agents build to
that interface.
```

### Step 7: Run the app
```bash
# Terminal 1: Backend
cd backend
source venv/bin/activate
uvicorn main:app --reload --port 8000

# Terminal 2: Frontend
cd frontend
npm run dev
# Opens at http://localhost:3000
```

### Step 8: Pre-cache demo reports
```bash
# Hit the warmup endpoint to pre-generate reports for demo scenarios
curl -X POST http://localhost:8000/api/warmup
```

---

## Project Structure

```
toxic-pulse/
├── README.md                          ← You are here
├── CLAUDE.md                          ← Project context for Claude Code
├── .env.example                       ← Environment variable template
├── .claude/
│   ├── settings.json                  ← Claude Code settings
│   ├── agents/                        ← Subagent definitions
│   │   ├── data-agent.md
│   │   ├── pipeline-agent.md
│   │   └── frontend-agent.md
│   ├── skills/                        ← Domain skills
│   │   ├── detect/SKILL.md            ← Anomaly detection knowledge
│   │   ├── rag-report/SKILL.md        ← RAG attribution knowledge
│   │   └── frontend-dash/SKILL.md     ← Dashboard design spec
│   └── commands/
│       └── demo-check.md              ← Pre-demo validation command
├── frontend/
│   ├── package.json
│   ├── next.config.ts
│   ├── tailwind.config.ts
│   ├── tsconfig.json
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx
│   │   │   ├── page.tsx
│   │   │   └── globals.css
│   │   ├── components/
│   │   │   ├── Map.tsx
│   │   │   ├── Timeline.tsx
│   │   │   ├── ReportPanel.tsx
│   │   │   ├── RegionSelector.tsx
│   │   │   └── ScanAnimation.tsx
│   │   └── lib/
│   │       └── api.ts
│   └── public/
├── backend/
│   ├── requirements.txt
│   ├── main.py                        ← FastAPI app + routes
│   ├── models.py                      ← Pydantic schemas (API contract)
│   ├── detection.py                   ← Anomaly detection ensemble
│   ├── features.py                    ← Feature engineering
│   ├── attribution.py                 ← RAG pipeline
│   ├── ingestion.py                   ← Data loading + normalization
│   └── seed_db.py                     ← ChromaDB seeding script
└── data/
    ├── chlorophyll/                    ← CSV data per region
    │   ├── lake_erie.csv
    │   ├── lake_victoria.csv
    │   └── mekong_delta.csv
    ├── docs/                           ← RAG knowledge base
    │   ├── epa_permits.md
    │   ├── agricultural_zones.md
    │   ├── who_guidelines.md
    │   ├── watershed_maps.md
    │   └── historical_incidents.md
    └── chroma_db/                      ← Persisted vector store
```

---

## Key GitHub Repos to Reference

| Repo | What it gives you |
|------|-------------------|
| `wekeo/learn-olci` | EUMETSAT Sentinel-3 OLCI Jupyter notebooks, chlorophyll processing in Python |
| `RAJohansen/waterquality` | 40 satellite water quality algorithms for OLCI, MODIS, Sentinel-2 |
| `shanraisshan/claude-code-best-practice` | CLAUDE.md, agents, skills, hooks patterns |
| `steipete/claude-code-mcp` | Claude Code as nested MCP server for subagent delegation |
| `wekeo/wekeo4oceans` | EUMETSAT marine case studies with OLCI, SLSTR, SRAL data |

---

## Tech Stack

| Layer | Tech |
|-------|------|
| Frontend | Next.js 14, TypeScript, Tailwind CSS, Mapbox GL JS, Recharts |
| Backend | FastAPI, Python 3.10+ |
| Anomaly Detection | scikit-learn (IsolationForest), scipy, numpy, pandas |
| RAG Pipeline | LangChain, ChromaDB, sentence-transformers, Claude Sonnet |
| Satellite Data | Copernicus Sentinel-3 OLCI, NASA MODIS-Aqua (pre-downloaded CSV) |
| Maps | Mapbox GL JS (satellite-v9 basemap) |
| Vector DB | ChromaDB (local, persistent) |
| Deployment | Vercel (frontend) + Railway (backend) |

---

## Demo Script (3 minutes)

1. **Open dashboard** — show the 3 monitored regions, explain satellite data is free
2. **Click Lake Erie** — map zooms, anomalies appear, timeline loads
3. **Click the red critical spike (Aug 2 2014)** — report panel slides in
4. **Walk through the report** — probable sources, 500K people at risk, 18h to intake
5. **Reveal** — "This is the Toledo water crisis. 500,000 people lost water for 3 days. Our system would have caught it 18 hours before the city did."
6. **Show $0 sensors deployed stat** — "Every body of water on Earth is already being imaged. The infrastructure exists. We just package the intelligence."
