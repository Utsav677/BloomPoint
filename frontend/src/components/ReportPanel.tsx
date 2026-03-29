"use client";

import type { CommunityReport, AnomalyEvent } from "@/lib/api";

interface ReportPanelProps {
  report: CommunityReport | null;
  loading: boolean;
  event: AnomalyEvent | null;
  onClose: () => void;
}

const PRIORITY_STYLES: Record<string, { bg: string; text: string; label: string }> = {
  immediate: { bg: "bg-[#2D1215]", text: "text-[#FCA5A5]", label: "NOW" },
  within_24h: { bg: "bg-[#27200D]", text: "text-[#FDBA74]", label: "24H" },
  within_week: { bg: "bg-[#1C1A0E]", text: "text-[#FDE68A]", label: "1WK" },
};

const LIKELIHOOD_STYLES: Record<string, { border: string; badge_bg: string; badge_text: string; bg: string }> = {
  high: { border: "border-l-[#EF4444]", badge_bg: "bg-[#2D1215]", badge_text: "text-[#FCA5A5]", bg: "bg-[#EF4444]/[0.03]" },
  medium: { border: "border-l-[#F97316]", badge_bg: "bg-[#27200D]", badge_text: "text-[#FDBA74]", bg: "bg-[#F97316]/[0.03]" },
  low: { border: "border-l-[#FBBF24]", badge_bg: "bg-[#1C1A0E]", badge_text: "text-[#FDE68A]", bg: "bg-[#FBBF24]/[0.02]" },
};

export function ReportPanel({ report, loading, event, onClose }: ReportPanelProps) {
  if (loading) {
    return (
      <div className="p-4 space-y-3">
        <div className="flex items-center gap-2">
          <div className="w-16 h-5 bg-white/[0.05] rounded animate-pulse" />
          <div className="flex-1" />
          <button onClick={onClose} className="text-tp-text-dim hover:text-tp-text-secondary text-xs">x</button>
        </div>
        {[...Array(6)].map((_, i) => (
          <div key={i} className="h-12 bg-white/[0.03] rounded-md animate-pulse" />
        ))}
        <div className="text-center text-tp-text-dim text-[10px] font-mono mt-4">
          Generating attribution report...
        </div>
      </div>
    );
  }

  if (!report || !event) return null;

  const latDir = event.lat >= 0 ? "N" : "S";
  const lonDir = event.lon >= 0 ? "E" : "W";

  return (
    <div className="p-3.5">
      {/* Header */}
      <div className="flex items-center gap-1.5 mb-2.5">
        <div className="bg-[#2D1215] text-[#FCA5A5] text-[9px] font-semibold px-2 py-0.5 rounded uppercase tracking-wider">
          {report.alert_level}
        </div>
        <div className="flex-1" />
        <span className="text-[10px] text-tp-text-muted font-mono">conf: {event.confidence.toFixed(2)}</span>
        <button onClick={onClose} className="text-tp-text-dim hover:text-tp-text-secondary text-xs ml-2">x</button>
      </div>

      <h2 className="text-[13px] text-tp-text-primary font-medium leading-tight">
        Community water quality report
      </h2>
      <p className="text-[10px] text-tp-text-dim font-mono mt-0.5 mb-3.5">
        {abs(event.lat).toFixed(2)}{latDir}, {abs(event.lon).toFixed(2)}{lonDir} · {event.date}
      </p>

      {/* Summary */}
      <SectionLabel>Summary</SectionLabel>
      <p className="text-[11px] text-tp-text-secondary leading-relaxed mb-3.5 pb-3.5 border-b border-white/[0.04]">
        {report.alert_summary}
      </p>

      {/* Probable Sources */}
      <SectionLabel>Probable sources</SectionLabel>
      <div className="space-y-1.5 mb-3.5">
        {report.probable_sources.map((src, i) => {
          const style = LIKELIHOOD_STYLES[src.likelihood] || LIKELIHOOD_STYLES.low;
          return (
            <div key={i} className={`border-l-2 ${style.border} ${style.bg} pl-2.5 pr-2 py-1.5 rounded-r-md`}>
              <div className="flex justify-between items-center">
                <span className="text-[11px] text-tp-text-primary font-medium">{src.source_name}</span>
                <span className={`text-[9px] ${style.badge_bg} ${style.badge_text} px-1.5 py-0.5 rounded`}>
                  {src.likelihood.toUpperCase()}
                </span>
              </div>
              <p className="text-[10px] text-tp-text-muted mt-0.5 leading-relaxed">{src.evidence}</p>
            </div>
          );
        })}
      </div>

      {/* Drinking Water Impact */}
      <SectionLabel>Downstream impact</SectionLabel>
      <div className="grid grid-cols-2 gap-1.5 mb-3.5">
        <MetricCard
          label="Population at risk"
          value={report.drinking_water_impact.at_risk_communities.length > 0
            ? report.drinking_water_impact.at_risk_communities[0]
            : "Unknown"}
          accent="text-tp-text-primary"
        />
        <MetricCard
          label="Time to intake"
          value={`~${Math.round(report.drinking_water_impact.estimated_arrival_hours)}h`}
          accent="text-tp-moderate"
        />
      </div>

      {/* Actions */}
      <SectionLabel>Actions</SectionLabel>
      <div className="space-y-1 mb-3">
        {report.recommended_actions.map((action, i) => {
          const style = PRIORITY_STYLES[action.priority] || PRIORITY_STYLES.within_week;
          return (
            <div key={i} className="flex gap-2 items-start">
              <span className={`text-[9px] ${style.bg} ${style.text} px-1.5 py-0.5 rounded font-mono whitespace-nowrap mt-0.5`}>
                {style.label}
              </span>
              <span className="text-[11px] text-tp-text-secondary leading-snug">{action.action}</span>
            </div>
          );
        })}
      </div>

      {/* Metadata */}
      <div className="pt-2.5 border-t border-white/[0.04] text-[9px] text-tp-text-dim font-mono leading-relaxed">
        RAG attribution · {String(report.metadata?.sources_consulted ?? "?")} sources · 3 indices<br />
        Sentinel-3 OLCI real satellite data<br />
        Gemini 2.0 Flash structured output
      </div>
    </div>
  );
}

function abs(n: number): number {
  return Math.abs(n);
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-[9px] text-tp-text-dim uppercase tracking-widest mb-1.5">
      {children}
    </div>
  );
}

function MetricCard({ label, value, accent }: { label: string; value: string; accent: string }) {
  return (
    <div className="bg-white/[0.02] border border-white/[0.05] rounded-md p-2">
      <div className="text-[9px] text-tp-text-muted">{label}</div>
      <div className={`text-lg font-medium font-mono mt-0.5 ${accent}`}>{value}</div>
    </div>
  );
}
