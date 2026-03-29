"use client";

import { useState } from "react";
import { jsPDF } from "jspdf";
import autoTable from "jspdf-autotable";
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

function generatePDF(report: CommunityReport, event: AnomalyEvent) {
  const doc = new jsPDF({ unit: "mm", format: "a4" });
  const pageW = doc.internal.pageSize.getWidth();
  let y = 0;

  // --- Dark header bar ---
  doc.setFillColor(6, 13, 27);
  doc.rect(0, 0, pageW, 28, "F");

  // Severity accent stripe
  const accentColors: Record<string, [number, number, number]> = {
    CRITICAL: [239, 68, 68],
    SEVERE: [249, 115, 22],
    MODERATE: [251, 191, 36],
  };
  const accent = accentColors[report.alert_level] || accentColors.MODERATE;
  doc.setFillColor(...accent);
  doc.rect(0, 28, pageW, 2, "F");

  // Header text
  doc.setTextColor(226, 232, 240);
  doc.setFont("helvetica", "bold");
  doc.setFontSize(14);
  doc.text("BLOOMPOINT", 12, 12);
  doc.setFontSize(8);
  doc.setFont("helvetica", "normal");
  doc.setTextColor(148, 163, 184);
  doc.text("Community Water Quality Report", 12, 18);

  // Alert badge on right
  doc.setFillColor(...accent);
  doc.roundedRect(pageW - 40, 7, 28, 10, 2, 2, "F");
  doc.setTextColor(255, 255, 255);
  doc.setFont("helvetica", "bold");
  doc.setFontSize(8);
  doc.text(report.alert_level, pageW - 26, 13.5, { align: "center" });

  y = 36;

  // --- Location & event info ---
  const latDir = event.lat >= 0 ? "N" : "S";
  const lonDir = event.lon >= 0 ? "E" : "W";
  const locationName = (report.metadata?.location_name as string) || "Unknown location";

  doc.setTextColor(30, 41, 59);
  doc.setFont("helvetica", "bold");
  doc.setFontSize(11);
  doc.text(locationName, 12, y);
  y += 6;

  doc.setFont("courier", "normal");
  doc.setFontSize(8);
  doc.setTextColor(100, 116, 139);
  doc.text(
    `${Math.abs(event.lat).toFixed(4)}°${latDir}, ${Math.abs(event.lon).toFixed(4)}°${lonDir}  ·  ${event.date}  ·  Confidence: ${event.confidence.toFixed(2)}`,
    12, y
  );
  y += 4;
  doc.text(
    `Chl-a: ${event.chl_a_value.toFixed(1)} mg/m³ (baseline ${event.chl_a_baseline.toFixed(1)})  ·  Z-score: ${event.z_score.toFixed(2)}`,
    12, y
  );
  y += 8;

  // --- Alert Summary ---
  doc.setDrawColor(226, 232, 240);
  doc.line(12, y, pageW - 12, y);
  y += 6;

  doc.setFont("helvetica", "bold");
  doc.setFontSize(9);
  doc.setTextColor(30, 41, 59);
  doc.text("ALERT SUMMARY", 12, y);
  y += 5;

  doc.setFont("helvetica", "normal");
  doc.setFontSize(9);
  doc.setTextColor(51, 65, 85);
  const summaryLines = doc.splitTextToSize(report.alert_summary, pageW - 24);
  doc.text(summaryLines, 12, y);
  y += summaryLines.length * 4.5 + 4;

  // --- Probable Sources Table ---
  doc.setFont("helvetica", "bold");
  doc.setFontSize(9);
  doc.setTextColor(30, 41, 59);
  doc.text("PROBABLE SOURCES", 12, y);
  y += 2;

  if (report.probable_sources.length > 0) {
    autoTable(doc, {
      startY: y,
      margin: { left: 12, right: 12 },
      head: [["Source", "Type", "Likelihood", "Distance", "Evidence"]],
      body: report.probable_sources.map((s) => [
        s.source_name,
        s.source_type,
        s.likelihood.toUpperCase(),
        s.distance_km ? `${s.distance_km} km` : "—",
        s.evidence,
      ]),
      styles: { fontSize: 7, cellPadding: 2, textColor: [51, 65, 85] },
      headStyles: { fillColor: [15, 23, 42], textColor: [226, 232, 240], fontSize: 7 },
      columnStyles: {
        0: { cellWidth: 30 },
        1: { cellWidth: 22 },
        2: { cellWidth: 18 },
        3: { cellWidth: 18 },
        4: { cellWidth: "auto" },
      },
      didParseCell: (data) => {
        if (data.section === "body" && data.column.index === 2) {
          const val = String(data.cell.raw).toLowerCase();
          if (val === "high") data.cell.styles.textColor = [239, 68, 68];
          else if (val === "medium") data.cell.styles.textColor = [249, 115, 22];
          else data.cell.styles.textColor = [251, 191, 36];
        }
      },
    });
    y = (doc as any).lastAutoTable.finalY + 6;
  }

  // --- Drinking Water Impact ---
  doc.setFont("helvetica", "bold");
  doc.setFontSize(9);
  doc.setTextColor(30, 41, 59);
  doc.text("DRINKING WATER IMPACT", 12, y);
  y += 5;

  doc.setFont("helvetica", "normal");
  doc.setFontSize(8);
  doc.setTextColor(51, 65, 85);
  const impact = report.drinking_water_impact;
  const impactLines = [
    `Communities at risk: ${impact.at_risk_communities.join(", ") || "Unknown"}`,
    `Estimated arrival: ~${Math.round(impact.estimated_arrival_hours)} hours`,
    `Contaminant type: ${impact.contaminant_type.replace(/_/g, " ")}`,
    `WHO threshold exceeded: ${impact.who_threshold_exceeded ? "YES" : "No"}`,
    `Monitoring: ${impact.recommended_monitoring}`,
  ];
  impactLines.forEach((line) => {
    const wrapped = doc.splitTextToSize(line, pageW - 24);
    doc.text(wrapped, 12, y);
    y += wrapped.length * 4 + 1;
  });
  y += 3;

  // --- Recommended Actions Table ---
  if (report.recommended_actions.length > 0) {
    doc.setFont("helvetica", "bold");
    doc.setFontSize(9);
    doc.setTextColor(30, 41, 59);
    doc.text("RECOMMENDED ACTIONS", 12, y);
    y += 2;

    autoTable(doc, {
      startY: y,
      margin: { left: 12, right: 12 },
      head: [["Priority", "Action", "Responsible Party"]],
      body: report.recommended_actions.map((a) => [
        a.priority.replace(/_/g, " ").toUpperCase(),
        a.action,
        a.responsible_party,
      ]),
      styles: { fontSize: 7, cellPadding: 2, textColor: [51, 65, 85] },
      headStyles: { fillColor: [15, 23, 42], textColor: [226, 232, 240], fontSize: 7 },
      columnStyles: {
        0: { cellWidth: 24 },
        1: { cellWidth: "auto" },
        2: { cellWidth: 35 },
      },
      didParseCell: (data) => {
        if (data.section === "body" && data.column.index === 0) {
          const val = String(data.cell.raw);
          if (val.includes("IMMEDIATE")) data.cell.styles.textColor = [239, 68, 68];
          else if (val.includes("24H")) data.cell.styles.textColor = [249, 115, 22];
        }
      },
    });
    y = (doc as any).lastAutoTable.finalY + 6;
  }

  // --- Historical Context ---
  if (report.historical_context) {
    doc.setFont("helvetica", "bold");
    doc.setFontSize(9);
    doc.setTextColor(30, 41, 59);
    doc.text("HISTORICAL CONTEXT", 12, y);
    y += 5;

    doc.setFont("helvetica", "normal");
    doc.setFontSize(8);
    doc.setTextColor(51, 65, 85);
    const histLines = doc.splitTextToSize(report.historical_context, pageW - 24);
    doc.text(histLines, 12, y);
    y += histLines.length * 4 + 6;
  }

  // --- Footer ---
  const footerY = doc.internal.pageSize.getHeight() - 10;
  doc.setDrawColor(226, 232, 240);
  doc.line(12, footerY - 4, pageW - 12, footerY - 4);
  doc.setFont("courier", "normal");
  doc.setFontSize(6.5);
  doc.setTextColor(148, 163, 184);
  doc.text(
    `Generated ${new Date().toISOString()} · BloomPoint Satellite Water Intelligence · Sentinel-3 OLCI + MODIS-Aqua`,
    12, footerY
  );

  // Save
  const safeLoc = locationName.replace(/[^a-zA-Z0-9]/g, "-").toLowerCase().slice(0, 30);
  doc.save(`bloompoint-report-${safeLoc}-${event.date}.pdf`);
}

function formatReportAsText(report: CommunityReport, event: AnomalyEvent): string {
  const latDir = event.lat >= 0 ? "N" : "S";
  const lonDir = event.lon >= 0 ? "E" : "W";
  const locationName = (report.metadata?.location_name as string) || "Unknown location";

  let text = `BLOOMPOINT — Community Water Quality Report\n`;
  text += `${"=".repeat(50)}\n\n`;
  text += `Alert Level: ${report.alert_level}\n`;
  text += `Location: ${locationName}\n`;
  text += `Coordinates: ${Math.abs(event.lat).toFixed(4)}°${latDir}, ${Math.abs(event.lon).toFixed(4)}°${lonDir}\n`;
  text += `Date: ${event.date}\n`;
  text += `Chl-a: ${event.chl_a_value.toFixed(1)} mg/m³ (baseline ${event.chl_a_baseline.toFixed(1)})\n`;
  text += `Z-score: ${event.z_score.toFixed(2)} · Confidence: ${event.confidence.toFixed(2)}\n\n`;

  text += `SUMMARY\n${"-".repeat(30)}\n${report.alert_summary}\n\n`;

  text += `PROBABLE SOURCES\n${"-".repeat(30)}\n`;
  report.probable_sources.forEach((s, i) => {
    text += `${i + 1}. ${s.source_name} (${s.source_type}, ${s.likelihood})\n`;
    text += `   Distance: ${s.distance_km ? s.distance_km + " km" : "unknown"}\n`;
    text += `   ${s.evidence}\n\n`;
  });

  text += `DRINKING WATER IMPACT\n${"-".repeat(30)}\n`;
  const impact = report.drinking_water_impact;
  text += `Communities at risk: ${impact.at_risk_communities.join(", ") || "Unknown"}\n`;
  text += `Estimated arrival: ~${Math.round(impact.estimated_arrival_hours)} hours\n`;
  text += `Contaminant: ${impact.contaminant_type.replace(/_/g, " ")}\n`;
  text += `WHO threshold exceeded: ${impact.who_threshold_exceeded ? "YES" : "No"}\n\n`;

  text += `RECOMMENDED ACTIONS\n${"-".repeat(30)}\n`;
  report.recommended_actions.forEach((a) => {
    text += `[${a.priority.replace(/_/g, " ").toUpperCase()}] ${a.action}\n`;
    text += `  Responsible: ${a.responsible_party}\n\n`;
  });

  if (report.historical_context) {
    text += `HISTORICAL CONTEXT\n${"-".repeat(30)}\n${report.historical_context}\n`;
  }

  return text;
}

export function ReportPanel({ report, loading, event, onClose }: ReportPanelProps) {
  const [copied, setCopied] = useState(false);

  const handleExportPDF = () => {
    if (report && event) generatePDF(report, event);
  };

  const handleCopy = async () => {
    if (!report || !event) return;
    try {
      await navigator.clipboard.writeText(formatReportAsText(report, event));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback for older browsers
      const ta = document.createElement("textarea");
      ta.value = formatReportAsText(report, event);
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

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
        <button
          onClick={handleExportPDF}
          className="text-[9px] font-mono text-tp-accent border border-tp-accent/30 hover:border-tp-accent/60 hover:bg-tp-accent/10 px-2 py-0.5 rounded transition-all ml-2"
          title="Export PDF"
        >
          ↓ PDF
        </button>
        <button
          onClick={handleCopy}
          className="text-[9px] font-mono text-tp-text-muted border border-white/[0.08] hover:border-white/20 hover:text-tp-text-secondary px-2 py-0.5 rounded transition-all"
          title="Copy to clipboard"
        >
          {copied ? "✓ Copied" : "Copy"}
        </button>
        <button onClick={onClose} className="text-tp-text-dim hover:text-tp-text-secondary text-xs ml-1">x</button>
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
