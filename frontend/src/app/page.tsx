"use client";

import { useState, useEffect, useCallback } from "react";
import { Map } from "@/components/Map";
import { Timeline } from "@/components/Timeline";
import { ReportPanel } from "@/components/ReportPanel";
import { ScanAnimation } from "@/components/ScanAnimation";
import { SearchBar } from "@/components/SearchBar";
import {
  fetchRecent,
  fetchTimeline,
  fetchAnomalies,
  fetchReport,
} from "@/lib/api";
import type {
  Region,
  RecentRegion,
  TimelinePoint,
  AnomalyEvent,
  CommunityReport,
} from "@/lib/api";
import { ValidationModal } from "@/components/ValidationModal";

export default function Dashboard() {
  const [currentRegion, setCurrentRegion] = useState<Region | null>(null);
  const [anomalies, setAnomalies] = useState<GeoJSON.FeatureCollection | null>(null);
  const [timeline, setTimeline] = useState<TimelinePoint[]>([]);
  const [selectedEvent, setSelectedEvent] = useState<AnomalyEvent | null>(null);
  const [report, setReport] = useState<CommunityReport | null>(null);
  const [reportLoading, setReportLoading] = useState(false);
  const [scanActive, setScanActive] = useState(false);
  const [recentSearches, setRecentSearches] = useState<RecentRegion[]>([]);
  const [dataLoading, setDataLoading] = useState(false);
  const [showValidation, setShowValidation] = useState(false);

  useEffect(() => {
    fetchRecent().then(setRecentSearches).catch(() => {});
  }, []);

  const loadRegion = useCallback(async (region: Region) => {
    console.log("[DASH] loadRegion:", region.name, "center:", region.center);
    setCurrentRegion(region);
    setReport(null);
    setSelectedEvent(null);
    setScanActive(true);
    setDataLoading(true);

    try {
      const lat = region.center[1];
      const lon = region.center[0];
      console.log(`[DASH] Fetching timeline + anomalies for lat=${lat}, lon=${lon}`);

      const [timelineData, anomalyData] = await Promise.all([
        fetchTimeline(lat, lon),
        fetchAnomalies(lat, lon),
      ]);

      console.log(`[DASH] Timeline: ${timelineData.length} points, Anomalies: ${anomalyData.features?.length ?? 0} features`);

      setTimeline(timelineData);
      setAnomalies(anomalyData);
    } catch (err) {
      console.error("[DASH] Failed to load region data:", err);
    } finally {
      setDataLoading(false);
      setTimeout(() => setScanActive(false), 3000);
    }

    // Refresh recent searches
    fetchRecent().then(setRecentSearches).catch(() => {});
  }, []);

  const handleEventClick = async (event: AnomalyEvent) => {
    setSelectedEvent(event);
    setReportLoading(true);
    try {
      const reportData = await fetchReport(event);
      setReport(reportData);
    } catch (err) {
      console.error("Failed to fetch report:", err);
    } finally {
      setReportLoading(false);
    }
  };

  const handleRecentClick = (recent: RecentRegion) => {
    const region: Region = {
      id: recent.cache_key,
      name: recent.name,
      country: "",
      bbox: [recent.lon - 0.5, recent.lat - 0.5, recent.lon + 0.5, recent.lat + 0.5],
      center: [recent.lon, recent.lat],
      description: `Cached data: ${recent.data_points} observations`,
    };
    loadRegion(region);
  };

  const alertCount = anomalies?.features?.length ?? 0;

  return (
    <div className="h-screen w-screen flex flex-col overflow-hidden">
      {/* Header */}
      <header className="flex items-center justify-between px-4 py-2.5 border-b border-white/[0.06] bg-white/[0.02] shrink-0">
        <div className="flex items-center gap-2.5">
          <div className="w-2 h-2 rounded-full bg-tp-accent shadow-[0_0_6px_#10B981]" />
          <span className="text-sm font-medium tracking-wider uppercase text-tp-text-primary">
            BloomPoint
          </span>
          <span className="text-xs text-tp-text-muted ml-1">
            satellite water intelligence
          </span>
        </div>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-1.5">
            <div className="w-1.5 h-1.5 rounded-full bg-tp-accent" />
            <span className="text-[11px] text-tp-accent font-mono">LIVE</span>
          </div>
          <span className="text-[11px] text-tp-text-muted font-mono">
            Sentinel-3 OLCI · Copernicus Data Space
          </span>
        </div>
      </header>

      {/* Main content */}
      <div className="flex flex-1 min-h-0">
        {/* Left sidebar: Recent searches */}
        <aside className="w-[200px] shrink-0 border-r border-white/[0.05] overflow-y-auto">
          <div className="p-2.5 space-y-1.5">
            <div className="text-[9px] uppercase tracking-[1.2px] text-tp-text-dim px-1.5 mb-1">
              Recent searches
            </div>

            {recentSearches.length === 0 && (
              <p className="text-[10px] text-tp-text-dim px-1.5 py-4">
                Search any water body to get started
              </p>
            )}

            {recentSearches.map((recent) => {
              const isSelected = currentRegion?.id === recent.cache_key;
              return (
                <button
                  key={recent.cache_key}
                  onClick={() => handleRecentClick(recent)}
                  className={`w-full text-left rounded-lg p-2.5 transition-all ${
                    isSelected
                      ? "bg-gradient-to-br from-tp-accent/10 to-tp-accent/[0.03] border border-tp-accent/30"
                      : "bg-white/[0.015] border border-white/[0.05] hover:border-white/[0.1]"
                  }`}
                >
                  <div className="flex justify-between items-center">
                    <span className={`text-xs font-medium truncate ${isSelected ? "text-tp-text-primary" : "text-tp-text-secondary"}`}>
                      {recent.name}
                    </span>
                  </div>
                  <div className="text-[10px] text-tp-text-dim mt-0.5 font-mono">
                    {recent.lat.toFixed(2)}, {recent.lon.toFixed(2)}
                  </div>
                  <div className="text-[9px] text-tp-text-dim mt-0.5">
                    {recent.data_points} data points
                  </div>
                </button>
              );
            })}
          </div>
        </aside>

        {/* Center: Map + Timeline */}
        <main className="flex-1 flex flex-col relative min-w-0">
          <div className="flex-1 relative">
            <Map
              region={currentRegion}
              anomalies={anomalies}
              onAnomalyClick={handleEventClick}
            />
            {scanActive && <ScanAnimation />}
            <SearchBar
              onRegionFound={(region) => loadRegion(region)}
              loading={dataLoading}
            />
          </div>

          {/* Bottom: Timeline */}
          <div className="h-[120px] shrink-0 border-t border-white/[0.06] bg-tp-base">
            <Timeline
              data={timeline}
              onPointClick={handleEventClick}
              selectedDate={selectedEvent?.date ?? null}
              regionId={currentRegion?.id ?? ""}
              regionCenter={
                currentRegion
                  ? [currentRegion.center[0], currentRegion.center[1]]
                  : [0, 0]
              }
            />
          </div>
        </main>

        {/* Right panel: Report (slides in) */}
        {(report || reportLoading) && (
          <aside className="w-[300px] shrink-0 border-l border-white/[0.05] animate-slide_in overflow-y-auto bg-white/[0.01]">
            <ReportPanel
              report={report}
              loading={reportLoading}
              event={selectedEvent}
              onClose={() => {
                setReport(null);
                setSelectedEvent(null);
              }}
            />
          </aside>
        )}
      </div>

      {/* Footer: Stats bar */}
      <footer className="flex justify-center items-center gap-8 py-2.5 border-t border-white/[0.04] bg-black/[0.15] shrink-0">
        {[
          { value: String(alertCount), label: "anomalies detected", color: "text-tp-accent" },
          { value: String(recentSearches.length), label: "water bodies scanned", color: "text-tp-text-primary" },
          { value: "real-time", label: "satellite data", color: "text-tp-accent" },
          { value: "$0", label: "sensors deployed", color: "text-tp-text-primary" },
        ].map((stat) => (
          <div key={stat.label} className="text-center">
            <div className={`text-lg font-medium font-mono ${stat.color}`}>
              {stat.value}
            </div>
            <div className="text-[9px] text-tp-text-dim uppercase tracking-wide">
              {stat.label}
            </div>
          </div>
        ))}
        <button
          onClick={() => setShowValidation(true)}
          className="ml-4 px-3 py-1.5 rounded-lg bg-white/[0.04] border border-white/[0.08] text-tp-text-secondary text-[11px] font-mono uppercase tracking-wider hover:bg-white/[0.08] hover:border-tp-accent/30 hover:text-tp-accent transition"
        >
          Validation
        </button>
      </footer>

      {/* Validation modal */}
      {showValidation && (
        <ValidationModal onClose={() => setShowValidation(false)} />
      )}
    </div>
  );
}
