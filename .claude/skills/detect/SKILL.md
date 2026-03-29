---
name: detect
description: Anomaly detection domain knowledge for satellite water quality monitoring. Use when implementing or debugging the detection pipeline.
user-invocable: false
---

## Anomaly Detection Domain Knowledge

### Chlorophyll-a thresholds
- Normal freshwater: 2-10 mg/m³
- Elevated (watch): 10-20 mg/m³
- Bloom (alert): 20-40 mg/m³
- Harmful algal bloom: >40 mg/m³
- WHO recreational limit: 50 mg/m³ (microcystin risk)

### Z-score interpretation
- 2σ: top 2.5% of historical values → moderate
- 3σ: top 0.1% → severe
- 4σ+: extreme outlier → critical
- Use 4-week rolling window for baseline, minimum 2 observations

### Isolation Forest settings
- contamination=0.05 (expect 5% anomaly rate in training data)
- n_estimators=100
- Features: chl_a_seasonal_residual, turbidity, sst_delta, chl_a_delta_1w, recent_heavy_rain
- Negative decision_function = anomaly

### Spatial autocorrelation
- Use BallTree with haversine metric
- Radius: 10km (converts to ~0.00157 radians for Earth radius 6371km)
- Minimum neighbors: 2 cells also flagged (z>1.5) within radius
- Single-cell spikes without neighbors are likely noise

### Weather context labels
- precipitation_7d > 50mm → "post_rainfall_runoff" (agricultural diffuse source likely)
- wind_speed > 8 m/s → "wind_driven_resuspension" (bottom sediment, not new contamination)
- Neither → "calm_conditions" (point-source discharge more likely)

### Seasonal adjustment
- Calculate week-of-year mean per grid cell from full time series
- Subtract from raw chl_a to get residual
- This prevents spring bloom false positives (normal in temperate lakes Apr-May)
