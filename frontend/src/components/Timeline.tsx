"use client";

import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceArea,
  ResponsiveContainer,
} from "recharts";
import type { TimelinePoint, AnomalyEvent } from "@/lib/api";

interface TimelineProps {
  data: TimelinePoint[];
  onPointClick: (event: AnomalyEvent) => void;
  selectedDate: string | null;
  regionId: string;
  regionCenter: [number, number]; // [lon, lat]
}

const SEVERITY_COLORS: Record<string, string> = {
  critical: "#EF4444",
  severe: "#F97316",
  moderate: "#FBBF24",
  none: "#10B981",
};

// Custom dot renderer — colored by severity
function CustomDot(props: any) {
  const { cx, cy, payload } = props;
  if (!payload || payload.severity === "none") return null;

  const color = SEVERITY_COLORS[payload.severity] || "#10B981";
  return (
    <g>
      <circle cx={cx} cy={cy} r={5} fill="#060D1B" stroke={color} strokeWidth={2} />
    </g>
  );
}

export function Timeline({ data, onPointClick, selectedDate, regionId, regionCenter }: TimelineProps) {
  if (!data.length) {
    return (
      <div className="h-full flex items-center justify-center text-tp-text-dim text-xs font-mono">
        Select a region to load timeline
      </div>
    );
  }

  // Calculate normal range
  const baselines = data.map((d) => d.chl_a_baseline).filter(Boolean);
  const avgBaseline = baselines.reduce((a, b) => a + b, 0) / baselines.length || 8;
  const normalLow = Math.max(0, avgBaseline - 3);
  const normalHigh = avgBaseline + 3;

  const handleClick = (point: TimelinePoint) => {
    if (point.severity === "none") return;
    const event: AnomalyEvent = {
      region_id: regionId,
      date: point.date,
      lat: regionCenter[1],
      lon: regionCenter[0],
      severity: point.severity,
      confidence: point.confidence,
      chl_a_value: point.chl_a_value,
      chl_a_baseline: point.chl_a_baseline,
      z_score: point.z_score,
      weather_context: "calm_conditions",
    };
    onPointClick(event);
  };

  return (
    <div className="h-full px-4 py-1.5">
      <div className="flex justify-between items-center mb-1">
        <span className="text-[9px] text-tp-text-dim uppercase tracking-wider font-mono">
          Chlorophyll-a concentration (mg/m³)
        </span>
        <span className="text-[9px] text-tp-text-muted font-mono">
          {data[0]?.date} — {data[data.length - 1]?.date}
        </span>
      </div>

      <ResponsiveContainer width="100%" height="85%">
        <AreaChart data={data} onClick={(e) => e?.activePayload && handleClick(e.activePayload[0].payload)}>
          <defs>
            <linearGradient id="chlGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#10B981" stopOpacity={0.3} />
              <stop offset="100%" stopColor="#060D1B" stopOpacity={0} />
            </linearGradient>
          </defs>

          <ReferenceArea
            y1={normalLow}
            y2={normalHigh}
            fill="#10B981"
            fillOpacity={0.04}
            stroke="#10B981"
            strokeOpacity={0.08}
            strokeDasharray="3 3"
          />

          <XAxis
            dataKey="date"
            tick={{ fontSize: 9, fill: "#1E293B", fontFamily: "monospace" }}
            axisLine={{ stroke: "rgba(255,255,255,0.04)" }}
            tickLine={false}
            interval="preserveStartEnd"
          />
          <YAxis
            tick={{ fontSize: 9, fill: "#1E293B", fontFamily: "monospace" }}
            axisLine={false}
            tickLine={false}
            width={30}
          />
          <Tooltip
            contentStyle={{
              background: "#0F172A",
              border: "0.5px solid rgba(255,255,255,0.08)",
              borderRadius: 6,
              fontSize: 11,
              fontFamily: "monospace",
              color: "#E2E8F0",
            }}
            formatter={(value: number) => [`${value.toFixed(1)} mg/m³`, "Chl-a"]}
            labelFormatter={(label) => `Date: ${label}`}
          />
          <Area
            type="monotone"
            dataKey="chl_a_value"
            stroke="#10B981"
            strokeWidth={1.5}
            fill="url(#chlGradient)"
            dot={<CustomDot />}
            activeDot={{ r: 6, stroke: "#10B981", strokeWidth: 2, fill: "#060D1B" }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
