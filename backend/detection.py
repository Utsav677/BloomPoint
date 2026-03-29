"""
Toxic Pulse — Ensemble Anomaly Detection

Three methods: Z-score, IsolationForest, Spatial Autocorrelation
Weighted vote → severity + confidence
"""

import pandas as pd
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import BallTree


class AnomalyDetector:
    """
    Ensemble anomaly detector combining:
    1. Z-score baseline (statistical)
    2. IsolationForest (multivariate ML)
    3. Spatial autocorrelation (geographic clustering)

    Requires feature-engineered DataFrame from features.py.
    """

    # Ensemble weights
    W_ZSCORE = 0.35
    W_ISO    = 0.35
    W_SPATIAL = 0.30

    # Decision threshold for flagging a point as anomalous
    ENSEMBLE_THRESHOLD = 0.65

    def __init__(self):
        self.isolation_forest = IsolationForest(
            contamination=0.05,
            n_estimators=100,
            random_state=42,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect(self, features_df: pd.DataFrame, region_id: str = "unknown") -> pd.DataFrame:
        """
        Run all 3 methods, ensemble vote, classify severity.

        Returns DataFrame with columns:
            date, lat, lon, severity, confidence,
            chl_a_value, chl_a_baseline, z_score,
            weather_context, event_id
        """
        df = features_df.copy().reset_index(drop=True)

        # ---- Method 1: Z-score ----
        z = df["chl_a_zscore"].fillna(0)
        zscore_flag = (z.abs() > 2).astype(float)

        # ---- Method 2: IsolationForest ----
        iso_features = [
            "chl_a_seasonal_residual", "turbidity", "sst_delta",
            "chl_a_delta_1w", "recent_heavy_rain",
        ]
        # Only use columns that exist
        iso_features = [c for c in iso_features if c in df.columns]
        iso_matrix = df[iso_features].fillna(0).values
        iso_preds = self.isolation_forest.fit_predict(iso_matrix)
        # -1 → anomaly (1.0), +1 → normal (0.0)
        iso_flag = (iso_preds == -1).astype(float)

        # ---- Method 3: Spatial autocorrelation ----
        spatial_flag = self._spatial_clustering(df, z.values)

        # ---- Ensemble voting ----
        weighted_sum = (
            self.W_ZSCORE  * zscore_flag +
            self.W_ISO     * iso_flag +
            self.W_SPATIAL * spatial_flag
        )

        is_anomaly = weighted_sum >= self.ENSEMBLE_THRESHOLD

        # ---- Severity from Z-score magnitude ----
        def _severity(row_z, row_anomaly):
            if not row_anomaly:
                return "none"
            az = abs(row_z)
            if az > 4:
                return "critical"
            if az > 3:
                return "severe"
            return "moderate"

        severities = [
            _severity(z.iloc[i], is_anomaly.iloc[i])
            for i in range(len(df))
        ]

        # Confidence: continuous 0-1, capped at 1.0
        confidence = np.minimum(weighted_sum.values / 1.0, 1.0)

        # ---- Weather context ----
        weather_contexts = df.apply(self._weather_label, axis=1)

        # ---- Build result DataFrame ----
        result = pd.DataFrame({
            "date":            df["date"].dt.strftime("%Y-%m-%d"),
            "lat":             df["lat"],
            "lon":             df["lon"],
            "severity":        severities,
            "confidence":      confidence.tolist(),
            "chl_a_value":     df["chl_a"],
            "chl_a_baseline":  df["chl_a_rolling_mean"],
            "z_score":         z.values,
            "weather_context": weather_contexts.values,
        })

        # event_id: region_id_date_lat_lon
        result["event_id"] = (
            region_id + "_" +
            result["date"] + "_" +
            result["lat"].round(4).astype(str) + "_" +
            result["lon"].round(4).astype(str)
        )

        return result

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _spatial_clustering(
        self,
        df: pd.DataFrame,
        z_scores: np.ndarray,
        radius_km: float = 10,
        min_neighbors: int = 2,
    ) -> np.ndarray:
        """
        For each point, flag as spatial anomaly if:
        - Its own Z-score > 2 AND
        - At least `min_neighbors` points within `radius_km` also have Z-score > 1.5
        """
        n = len(df)
        if n == 0:
            return np.zeros(n, dtype=float)

        # Convert lat/lon degrees → radians for haversine BallTree
        coords_rad = np.radians(df[["lat", "lon"]].values)
        radius_rad = radius_km / 6371.0  # Earth radius in km

        tree = BallTree(coords_rad, metric="haversine")

        spatial_flag = np.zeros(n, dtype=float)
        for i in range(n):
            if abs(z_scores[i]) <= 2:
                continue  # own Z-score not high enough
            # Indices of neighbors within radius (includes self)
            indices = tree.query_radius(coords_rad[i:i+1], r=radius_rad)[0]
            # Exclude self
            neighbors = [j for j in indices if j != i]
            high_z_neighbors = sum(1 for j in neighbors if abs(z_scores[j]) > 1.5)
            if high_z_neighbors >= min_neighbors:
                spatial_flag[i] = 1.0

        return spatial_flag

    def _weather_label(self, row) -> str:
        if row.get("recent_heavy_rain", 0):
            return "post_rainfall_runoff"
        if row.get("high_wind", 0):
            return "wind_driven_resuspension"
        return "calm_conditions"
