---
name: frontend-dash
description: Dashboard design specification for the Toxic Pulse monitoring interface. Use when building or styling frontend components.
user-invocable: false
---

## Dashboard Design Spec

### Visual identity
Scientific monitoring aesthetic. Think mission control, not SaaS dashboard. Dark backgrounds, monospace data readouts, pulsing alert indicators, satellite imagery as the hero visual. The map IS the product.

### Critical visual details
- Anomaly points on map: concentric circles with CSS pulse animation. Inner dot solid, outer ring semi-transparent, outermost ring animating scale 1→1.5 with opacity fade
- Report panel: slide-in from right, 300px width, subtle backdrop blur on the overlay edge
- Timeline: area chart, NOT line chart. The filled area under the line creates visual weight
- Region cards: selected state has left border glow in emerald, subtle background shift
- Monospace everything numeric: coordinates, values, timestamps, confidence scores
- Severity badge colors match map point colors exactly (red/orange/yellow)

### Mapbox specifics
- Import: `mapbox-gl` and `mapbox-gl/dist/mapbox-gl.css`
- Use `mapboxgl.Map` with `style: 'mapbox://styles/mapbox/satellite-v9'`
- Add GeoJSON source from `/api/anomalies/{region_id}` response
- Circle layer with data-driven paint properties keyed on severity
- Popup on click showing anomaly details
- `flyTo` animation on region switch

### Recharts specifics
- Use `AreaChart`, `Area`, `XAxis`, `YAxis`, `Tooltip`, `ReferenceLine`, `ReferenceArea`
- ReferenceArea for the "normal range" band (y1=baseline-1std, y2=baseline+1std)
- Custom dot renderer that returns colored circles based on severity
- onClick handler on dots that triggers report fetch

### State management
- `selectedRegion`: string (region_id)
- `anomalies`: GeoJSON FeatureCollection
- `timeline`: array of {date, chl_a, baseline, severity}
- `selectedEvent`: anomaly event object or null
- `report`: CommunityReport object or null
- `reportLoading`: boolean
- `scanActive`: boolean

### API calls (lib/api.ts)
All typed to match backend Pydantic models:
- `fetchRegions()` → Region[]
- `fetchTimeline(regionId)` → TimelinePoint[]
- `fetchAnomalies(regionId)` → GeoJSON
- `fetchReport(event)` → CommunityReport
- `warmupCache()` → void
