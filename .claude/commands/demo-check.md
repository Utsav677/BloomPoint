---
name: demo-check
description: Run before demo to verify everything works end-to-end
disable-model-invocation: true
---

Run these checks and report results:

1. Verify backend is running: `curl -s http://localhost:8000/api/regions | python3 -m json.tool`
2. Verify anomaly detection: `curl -s http://localhost:8000/api/anomalies/lake_erie | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'{len(d[\"features\"])} anomalies found')"`
3. Verify timeline: `curl -s http://localhost:8000/api/timeline/lake_erie | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'{len(d)} data points')"`
4. Verify report generation: `curl -s -X POST http://localhost:8000/api/report -H 'Content-Type: application/json' -d '{"region_id":"lake_erie","date":"2014-08-02","lat":41.7,"lon":-83.3,"severity":"critical","confidence":0.94,"chl_a_value":45.2,"chl_a_baseline":8.1,"z_score":5.2,"weather_context":"post_rainfall_runoff"}' | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Report: {d.get(\"alert_level\",\"MISSING\")} — {len(d.get(\"probable_sources\",[]))} sources identified')"`
5. Verify frontend is running: `curl -s -o /dev/null -w '%{http_code}' http://localhost:3000`
6. Verify cache warmup: `curl -s -X POST http://localhost:8000/api/warmup | python3 -m json.tool`

Report pass/fail for each check. If any fail, diagnose and fix.
