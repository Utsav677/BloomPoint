"use client";

import { useEffect, useRef, useCallback } from "react";
import mapboxgl from "mapbox-gl";
import type { Region, AnomalyEvent } from "@/lib/api";

interface MapProps {
  region: Region | null;
  anomalies: GeoJSON.FeatureCollection | null;
  onAnomalyClick: (event: AnomalyEvent) => void;
}

const EMPTY_FC: GeoJSON.FeatureCollection = { type: "FeatureCollection", features: [] };

export function Map({ region, anomalies, onAnomalyClick }: MapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<mapboxgl.Map | null>(null);
  const regionRef = useRef<Region | null>(null);
  const styleLoadedRef = useRef(false);
  // Store pending data so we can apply it once the style loads
  const pendingAnomaliesRef = useRef<GeoJSON.FeatureCollection | null>(null);

  // Keep regionRef in sync for use in click handler
  regionRef.current = region;

  // Stable callback to apply anomaly data to the map source
  const applyAnomalies = useCallback((map: mapboxgl.Map, data: GeoJSON.FeatureCollection) => {
    const source = map.getSource("anomalies") as mapboxgl.GeoJSONSource | undefined;
    if (source) {
      source.setData(data);
      console.log("[MAP] setData called —", data.features.length, "features applied to source");
    } else {
      console.warn("[MAP] Source 'anomalies' not found — queueing for later");
      pendingAnomaliesRef.current = data;
    }
  }, []);

  useEffect(() => {
    if (!containerRef.current) return;

    mapboxgl.accessToken = process.env.NEXT_PUBLIC_MAPBOX_TOKEN || "";

    const map = new mapboxgl.Map({
      container: containerRef.current,
      style: "mapbox://styles/mapbox/satellite-v9",
      center: [0, 20],
      zoom: 3,
      attributionControl: false,
    });

    mapRef.current = map;

    const setupLayers = () => {
      styleLoadedRef.current = true;
      console.log("[MAP] Style loaded — adding anomaly source + layers");

      // Add GeoJSON source
      if (!map.getSource("anomalies")) {
        map.addSource("anomalies", {
          type: "geojson",
          data: EMPTY_FC,
        });
      }

      // Outer pulse ring — bigger and more visible
      if (!map.getLayer("anomaly-pulse")) {
        map.addLayer({
          id: "anomaly-pulse",
          type: "circle",
          source: "anomalies",
          paint: {
            "circle-radius": [
              "interpolate", ["linear"], ["zoom"],
              4, 12,
              8, 20,
              12, 28,
            ],
            "circle-color": [
              "match", ["get", "severity"],
              "critical", "#EF4444",
              "severe", "#F97316",
              "moderate", "#FBBF24",
              "#FBBF24",
            ],
            "circle-opacity": 0.18,
            "circle-stroke-width": 1.5,
            "circle-stroke-color": [
              "match", ["get", "severity"],
              "critical", "#EF4444",
              "severe", "#F97316",
              "moderate", "#FBBF24",
              "#FBBF24",
            ],
            "circle-stroke-opacity": 0.4,
          },
        });
      }

      // Inner dot — bigger with stroke for visibility on satellite imagery
      if (!map.getLayer("anomaly-dots")) {
        map.addLayer({
          id: "anomaly-dots",
          type: "circle",
          source: "anomalies",
          paint: {
            "circle-radius": [
              "interpolate", ["linear"], ["zoom"],
              4, 5,
              8, 8,
              12, 11,
            ],
            "circle-color": [
              "match", ["get", "severity"],
              "critical", "#EF4444",
              "severe", "#F97316",
              "moderate", "#FBBF24",
              "#FBBF24",
            ],
            "circle-opacity": 0.95,
            "circle-stroke-width": 2,
            "circle-stroke-color": "#ffffff",
            "circle-stroke-opacity": 0.6,
          },
        });
      }

      // Click handler
      map.on("click", "anomaly-dots", (e) => {
        if (!e.features?.[0]) return;
        const props = e.features[0].properties;
        if (!props) return;

        const coords = (e.features[0].geometry as GeoJSON.Point).coordinates;
        console.log("[MAP] Anomaly clicked:", props.date, props.severity, "at", coords);
        onAnomalyClick({
          region_id: regionRef.current?.id || "",
          date: props.date,
          lat: coords[1],
          lon: coords[0],
          severity: props.severity,
          confidence: props.confidence,
          chl_a_value: props.chl_a,
          chl_a_baseline: props.baseline,
          z_score: props.z_score,
          weather_context: props.weather_context,
        });
      });

      map.on("mouseenter", "anomaly-dots", () => {
        map.getCanvas().style.cursor = "pointer";
      });
      map.on("mouseleave", "anomaly-dots", () => {
        map.getCanvas().style.cursor = "";
      });

      // Apply any pending anomaly data that arrived before the style loaded
      if (pendingAnomaliesRef.current) {
        console.log("[MAP] Applying pending anomaly data:", pendingAnomaliesRef.current.features.length, "features");
        const source = map.getSource("anomalies") as mapboxgl.GeoJSONSource;
        if (source) {
          source.setData(pendingAnomaliesRef.current);
        }
        pendingAnomaliesRef.current = null;
      }
    };

    // Use both 'load' and 'style.load' to handle initial + any style changes
    map.on("load", setupLayers);
    map.on("style.load", () => {
      if (!styleLoadedRef.current) {
        setupLayers();
      }
    });

    return () => {
      styleLoadedRef.current = false;
      map.remove();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Update anomalies data whenever it changes
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !anomalies) return;

    console.log("[MAP] Anomalies state updated:", anomalies.features?.length ?? 0, "features");

    if (!styleLoadedRef.current) {
      console.log("[MAP] Style not loaded yet — storing as pending");
      pendingAnomaliesRef.current = anomalies;
      return;
    }

    applyAnomalies(map, anomalies);
  }, [anomalies, applyAnomalies]);

  // Fly to region and fit bounds to show anomaly points
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !region) return;

    console.log("[MAP] Flying to region:", region.name, "center:", region.center, "bbox:", region.bbox);

    // If we have anomalies, fit bounds to include all of them
    if (anomalies?.features?.length) {
      const lngs: number[] = [];
      const lats: number[] = [];
      anomalies.features.forEach((f) => {
        const coords = (f.geometry as GeoJSON.Point).coordinates;
        lngs.push(coords[0]);
        lats.push(coords[1]);
      });

      const sw: [number, number] = [Math.min(...lngs), Math.min(...lats)];
      const ne: [number, number] = [Math.max(...lngs), Math.max(...lats)];

      console.log("[MAP] Fitting bounds to anomalies: SW", sw, "NE", ne);
      map.fitBounds([sw, ne], {
        padding: 60,
        maxZoom: 11,
        duration: 2000,
      });
    } else {
      // No anomalies yet — fly to region center
      map.flyTo({
        center: [region.center[0], region.center[1]],
        zoom: 9,
        duration: 2000,
      });
    }
  }, [region, anomalies]);

  return (
    <div className="absolute inset-0">
      <div ref={containerRef} className="w-full h-full" />

      {/* Coordinate overlay */}
      {region && (
        <div className="absolute top-2 left-2 flex gap-1.5 z-10">
          <div className="bg-black/50 backdrop-blur-sm px-2 py-1 rounded text-[10px] text-tp-text-muted font-mono border border-white/[0.06]">
            {region.center[1].toFixed(2)}{region.center[1] >= 0 ? "N" : "S"} {Math.abs(region.center[0]).toFixed(2)}{region.center[0] >= 0 ? "E" : "W"}
          </div>
          <div className="bg-black/50 backdrop-blur-sm px-2 py-1 rounded text-[10px] text-tp-text-muted font-mono border border-white/[0.06]">
            300m/px
          </div>
        </div>
      )}

      {/* Sensor badge */}
      <div className="absolute top-2 right-2 bg-black/50 backdrop-blur-sm px-2 py-1 rounded text-[10px] text-tp-text-dim font-mono border border-white/[0.06] z-10">
        Sentinel-3 OLCI · Real Data
      </div>
    </div>
  );
}
