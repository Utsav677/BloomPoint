"use client";

import { useState, useRef, useEffect } from "react";
import { searchLocation } from "@/lib/api";
import type { Region } from "@/lib/api";

interface SearchBarProps {
  onRegionFound: (region: Region) => void;
  loading?: boolean;
}

interface GeoResult {
  /** First part of the place name (before first comma) */
  title: string;
  /** Everything after the first comma — region, country context */
  context: string;
  /** Full place_name from Mapbox */
  place_name: string;
  center: [number, number]; // [lon, lat]
  isWater: boolean;
}

const WATER_KEYWORDS = [
  "lake", "river", "bay", "gulf", "sea", "ocean",
  "reservoir", "pond", "creek", "strait", "delta", "marsh", "lagoon",
  "estuary", "canal", "harbor", "harbour", "inlet", "cove", "sound",
  "fjord", "dam", "basin", "waterway", "falls", "spring", "stream",
  "wetland", "swamp", "coast", "shore", "beach", "port", "channel",
  "loch", "lac", "lago", "rio", "meer",
];

function isWaterFeature(placeName: string): boolean {
  const lower = placeName.toLowerCase();
  return WATER_KEYWORDS.some((kw) => lower.includes(kw));
}

function splitPlaceName(placeName: string): { title: string; context: string } {
  const idx = placeName.indexOf(",");
  if (idx === -1) return { title: placeName, context: "" };
  return { title: placeName.slice(0, idx).trim(), context: placeName.slice(idx + 1).trim() };
}

/** Parse "47.5, -87.5" or "47.5 -87.5" or "-34.5, 137.0" as lat/lon. */
function parseCoords(input: string): { lat: number; lon: number } | null {
  const cleaned = input.trim().replace(/[°NSEW]/gi, "");
  const match = cleaned.match(/^(-?\d+\.?\d*)[,\s]+(-?\d+\.?\d*)$/);
  if (!match) return null;
  const a = parseFloat(match[1]);
  const b = parseFloat(match[2]);
  if (isNaN(a) || isNaN(b)) return null;
  if (Math.abs(a) <= 90 && Math.abs(b) <= 180) return { lat: a, lon: b };
  if (Math.abs(b) <= 90 && Math.abs(a) <= 180) return { lat: b, lon: a };
  return null;
}

export function SearchBar({ onRegionFound, loading: externalLoading }: SearchBarProps) {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [resultText, setResultText] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [waterResults, setWaterResults] = useState<GeoResult[]>([]);
  const [otherResults, setOtherResults] = useState<GeoResult[]>([]);
  const [showDropdown, setShowDropdown] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const isLoading = loading || externalLoading;

  // Close dropdown on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setShowDropdown(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const loadFromCoords = async (lat: number, lon: number, name: string) => {
    setShowDropdown(false);
    setLoading(true);
    setError(null);
    setResultText("Fetching satellite data from Copernicus...");

    try {
      const res = await searchLocation(name, lat, lon);
      if (res.type === "direct" && res.region) {
        setResultText(`Loaded: ${res.region.name}`);
        setError(null);
        onRegionFound(res.region);
      } else {
        setError("No satellite data available for this location");
      }
    } catch (err: any) {
      setError(err.message || "Search failed. Check connection.");
    } finally {
      setLoading(false);
    }
  };

  const selectResult = async (result: GeoResult) => {
    const [geoLon, geoLat] = result.center;
    await loadFromCoords(geoLat, geoLon, result.title);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = query.trim();
    if (!trimmed || loading) return;

    setError(null);
    setResultText(null);
    setShowDropdown(false);
    setWaterResults([]);
    setOtherResults([]);

    // Direct coordinate input — skip geocoding entirely
    const coords = parseCoords(trimmed);
    if (coords) {
      await loadFromCoords(
        coords.lat,
        coords.lon,
        `${coords.lat.toFixed(2)}, ${coords.lon.toFixed(2)}`,
      );
      return;
    }

    // Geocode via Mapbox
    setLoading(true);
    try {
      const token = process.env.NEXT_PUBLIC_MAPBOX_TOKEN || "";
      const geoRes = await fetch(
        `https://api.mapbox.com/geocoding/v5/mapbox.places/${encodeURIComponent(trimmed)}.json?access_token=${token}&limit=10&types=region,district,place,locality,poi`
      );
      const geoData = await geoRes.json();

      if (!geoData.features || geoData.features.length === 0) {
        setError("No results found. Try entering coordinates directly like: -34.5, 137.0");
        setLoading(false);
        return;
      }

      const all: GeoResult[] = geoData.features.map((f: any) => {
        const { title, context } = splitPlaceName(f.place_name);
        return {
          title,
          context,
          place_name: f.place_name,
          center: f.center as [number, number],
          isWater: isWaterFeature(f.place_name),
        };
      });

      const water = all.filter((r) => r.isWater);
      const other = all.filter((r) => !r.isWater);

      setWaterResults(water);
      setOtherResults(other);
      setShowDropdown(true);
      setLoading(false);
    } catch (err: any) {
      setError(err.message || "Geocoding failed.");
      setLoading(false);
    }
  };

  const hasResults = waterResults.length > 0 || otherResults.length > 0;

  return (
    <div className="absolute top-4 left-1/2 -translate-x-1/2 z-30 w-[460px] max-w-[calc(100%-2rem)]" ref={dropdownRef}>
      <form
        onSubmit={handleSubmit}
        className="bg-black/40 backdrop-blur-xl border border-white/[0.08] rounded-xl overflow-hidden shadow-2xl"
      >
        <div className="flex items-center px-3 py-2.5 gap-2.5">
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" className="shrink-0 text-tp-accent">
            <circle cx="6.5" cy="6.5" r="5" stroke="currentColor" strokeWidth="1.5" />
            <path d="M10.5 10.5L14 14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          </svg>

          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setShowDropdown(false);
            }}
            placeholder="Search any water body... e.g. Spencer Gulf, Lake Tai, Chesapeake Bay"
            className="flex-1 bg-transparent text-sm text-tp-text-primary placeholder:text-tp-text-dim outline-none"
            disabled={isLoading}
          />

          {isLoading && (
            <svg className="animate-spin shrink-0 text-tp-accent" width="14" height="14" viewBox="0 0 24 24" fill="none">
              <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="2" strokeOpacity="0.25" />
              <path d="M12 2a10 10 0 0 1 10 10" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            </svg>
          )}

          {!isLoading && query.trim() && (
            <button
              type="submit"
              className="shrink-0 text-[10px] font-mono text-tp-accent px-2 py-0.5 rounded border border-tp-accent/30 hover:border-tp-accent/60 transition"
            >
              GO
            </button>
          )}
        </div>
      </form>

      {/* Results dropdown */}
      {showDropdown && hasResults && (
        <div className="mt-1.5 bg-black/80 backdrop-blur-xl border border-white/[0.1] rounded-xl overflow-hidden shadow-2xl max-h-[320px] overflow-y-auto">
          {/* Water results */}
          {waterResults.length > 0 && (
            <>
              <div className="px-3 py-1.5 text-[9px] text-tp-accent uppercase tracking-wider border-b border-white/[0.06] bg-tp-accent/[0.03]">
                Water bodies
              </div>
              {waterResults.map((result, i) => (
                <ResultRow key={`w-${i}`} result={result} onSelect={selectResult} />
              ))}
            </>
          )}

          {/* Other results — shown below a divider */}
          {otherResults.length > 0 && (
            <>
              <div className="px-3 py-1.5 text-[9px] text-tp-text-dim uppercase tracking-wider border-b border-white/[0.06] border-t border-white/[0.06]">
                {waterResults.length > 0 ? "Other locations" : "Locations (no water bodies matched)"}
              </div>
              {otherResults.map((result, i) => (
                <ResultRow key={`o-${i}`} result={result} onSelect={selectResult} />
              ))}
            </>
          )}
        </div>
      )}

      {/* Status text (only when dropdown is not showing) */}
      {!showDropdown && (resultText || error) && (
        <div
          className={`mt-1.5 px-3 py-1 text-[10px] font-mono rounded-lg bg-black/40 backdrop-blur-sm border ${
            error
              ? "border-tp-critical/30 text-tp-critical"
              : "border-tp-accent/20 text-tp-accent"
          }`}
        >
          {error ?? resultText}
        </div>
      )}
    </div>
  );
}

function ResultRow({ result, onSelect }: { result: GeoResult; onSelect: (r: GeoResult) => void }) {
  return (
    <button
      onClick={() => onSelect(result)}
      className="w-full text-left px-3 py-2.5 hover:bg-white/[0.06] transition border-b border-white/[0.04] last:border-b-0"
    >
      <div className="text-[12px] text-tp-text-primary font-medium leading-tight">
        {result.title}
      </div>
      {result.context && (
        <div className="text-[11px] text-tp-text-muted mt-0.5 leading-tight">
          {result.context}
        </div>
      )}
    </button>
  );
}
