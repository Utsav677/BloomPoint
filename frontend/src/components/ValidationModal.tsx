"use client";

import { useState } from "react";
import {
  runValidation,
  fetchValidationResults,
} from "@/lib/api";
import type { ValidationResults } from "@/lib/api";

export function ValidationModal({ onClose }: { onClose: () => void }) {
  const [results, setResults] = useState<ValidationResults | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleRun = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await runValidation();
      setResults(data);
    } catch (e: any) {
      setError(e.message || "Validation failed");
    } finally {
      setLoading(false);
    }
  };

  const handleLoadCached = async () => {
    try {
      const data = await fetchValidationResults();
      setResults(data);
    } catch {
      setError("No cached results. Run validation first.");
    }
  };

  const cm = results?.confusion_matrix;
  const m = results?.metrics;

  return (
    <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div className="bg-[#0B1120] border border-white/[0.08] rounded-xl w-[820px] max-h-[90vh] overflow-y-auto shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-white/[0.06]">
          <div className="flex items-center gap-2.5">
            <div className="w-2 h-2 rounded-full bg-tp-accent shadow-[0_0_6px_#10B981]" />
            <span className="text-sm font-medium tracking-wider uppercase text-tp-text-primary">
              Validation Suite
            </span>
            <span className="text-xs text-tp-text-muted">
              confusion matrix against documented events
            </span>
          </div>
          <button
            onClick={onClose}
            className="text-tp-text-muted hover:text-tp-text-primary text-lg leading-none px-2"
          >
            &times;
          </button>
        </div>

        <div className="p-5 space-y-5">
          {/* Actions */}
          {!results && !loading && (
            <div className="flex gap-3">
              <button
                onClick={handleRun}
                className="px-4 py-2 rounded-lg bg-tp-accent/20 border border-tp-accent/30 text-tp-accent text-sm font-medium hover:bg-tp-accent/30 transition"
              >
                Run Full Validation
              </button>
              <button
                onClick={handleLoadCached}
                className="px-4 py-2 rounded-lg bg-white/[0.04] border border-white/[0.08] text-tp-text-secondary text-sm hover:bg-white/[0.08] transition"
              >
                Load Cached Results
              </button>
            </div>
          )}

          {loading && (
            <div className="text-center py-12">
              <div className="inline-block w-8 h-8 border-2 border-tp-accent/30 border-t-tp-accent rounded-full animate-spin mb-3" />
              <p className="text-sm text-tp-text-secondary">
                Running validation against {15} documented events...
              </p>
              <p className="text-xs text-tp-text-muted mt-1">
                Fetching real NASA satellite data for each location. This takes 3-5 minutes.
              </p>
            </div>
          )}

          {error && (
            <div className="text-sm text-red-400 bg-red-400/10 border border-red-400/20 rounded-lg px-4 py-2.5">
              {error}
            </div>
          )}

          {results && (
            <>
              {/* Metrics row */}
              <div className="grid grid-cols-4 gap-3">
                {[
                  { label: "Accuracy", value: m!.accuracy, color: "text-tp-accent" },
                  { label: "Precision", value: m!.precision, color: "text-blue-400" },
                  { label: "Recall", value: m!.recall, color: "text-amber-400" },
                  { label: "F1 Score", value: m!.f1_score, color: "text-purple-400" },
                ].map((metric) => (
                  <div
                    key={metric.label}
                    className="bg-white/[0.03] border border-white/[0.06] rounded-lg px-4 py-3 text-center"
                  >
                    <div className={`text-2xl font-mono font-semibold ${metric.color}`}>
                      {(metric.value * 100).toFixed(1)}%
                    </div>
                    <div className="text-[10px] text-tp-text-dim uppercase tracking-wider mt-1">
                      {metric.label}
                    </div>
                  </div>
                ))}
              </div>

              {/* Confusion Matrix */}
              <div>
                <div className="text-xs text-tp-text-muted uppercase tracking-wider mb-2">
                  Confusion Matrix
                </div>
                <div className="grid grid-cols-[auto_1fr_1fr] gap-0 w-fit">
                  {/* Header row */}
                  <div className="w-28" />
                  <div className="w-32 text-center text-[10px] text-tp-text-dim uppercase tracking-wide py-1.5">
                    Predicted Bloom
                  </div>
                  <div className="w-32 text-center text-[10px] text-tp-text-dim uppercase tracking-wide py-1.5">
                    Predicted Clean
                  </div>

                  {/* Row 1: Actual Bloom */}
                  <div className="flex items-center text-[10px] text-tp-text-dim uppercase tracking-wide pr-3">
                    Actual Bloom
                  </div>
                  <div className="bg-emerald-500/20 border border-emerald-500/30 rounded-tl-lg m-0.5 p-3 text-center">
                    <div className="text-xl font-mono font-bold text-emerald-400">{cm!.true_positive}</div>
                    <div className="text-[9px] text-emerald-400/70 mt-0.5">True Positive</div>
                  </div>
                  <div className="bg-red-500/20 border border-red-500/30 rounded-tr-lg m-0.5 p-3 text-center">
                    <div className="text-xl font-mono font-bold text-red-400">{cm!.false_negative}</div>
                    <div className="text-[9px] text-red-400/70 mt-0.5">False Negative</div>
                  </div>

                  {/* Row 2: Actual Clean */}
                  <div className="flex items-center text-[10px] text-tp-text-dim uppercase tracking-wide pr-3">
                    Actual Clean
                  </div>
                  <div className="bg-red-500/20 border border-red-500/30 rounded-bl-lg m-0.5 p-3 text-center">
                    <div className="text-xl font-mono font-bold text-red-400">{cm!.false_positive}</div>
                    <div className="text-[9px] text-red-400/70 mt-0.5">False Positive</div>
                  </div>
                  <div className="bg-emerald-500/20 border border-emerald-500/30 rounded-br-lg m-0.5 p-3 text-center">
                    <div className="text-xl font-mono font-bold text-emerald-400">{cm!.true_negative}</div>
                    <div className="text-[9px] text-emerald-400/70 mt-0.5">True Negative</div>
                  </div>
                </div>
              </div>

              {/* Run info */}
              <div className="text-[10px] text-tp-text-dim font-mono">
                {results.total_events} events validated in {results.elapsed_seconds}s — {results.run_at}
              </div>

              {/* Per-event details table */}
              <div>
                <div className="text-xs text-tp-text-muted uppercase tracking-wider mb-2">
                  Per-Event Results
                </div>
                <div className="border border-white/[0.06] rounded-lg overflow-hidden">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="bg-white/[0.03] text-tp-text-dim uppercase text-[9px] tracking-wider">
                        <th className="text-left px-3 py-2">Event</th>
                        <th className="text-center px-2 py-2">Expected</th>
                        <th className="text-center px-2 py-2">Detected</th>
                        <th className="text-center px-2 py-2">Severity</th>
                        <th className="text-right px-2 py-2">Z-Score</th>
                        <th className="text-right px-2 py-2">Chl-a</th>
                        <th className="text-center px-2 py-2">Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {results.details.map((d, i) => (
                        <tr
                          key={i}
                          className={`border-t border-white/[0.04] ${
                            d.passed ? "" : "bg-red-500/[0.06]"
                          }`}
                        >
                          <td className="px-3 py-2 text-tp-text-secondary max-w-[200px] truncate">
                            {d.name}
                          </td>
                          <td className="text-center px-2 py-2">
                            <span
                              className={`inline-block px-1.5 py-0.5 rounded text-[9px] font-mono ${
                                d.expected === "bloom"
                                  ? "bg-amber-500/20 text-amber-400"
                                  : "bg-blue-500/20 text-blue-400"
                              }`}
                            >
                              {d.expected}
                            </span>
                          </td>
                          <td className="text-center px-2 py-2 font-mono text-tp-text-secondary">
                            {d.detected}
                          </td>
                          <td className="text-center px-2 py-2">
                            <span
                              className={`inline-block px-1.5 py-0.5 rounded text-[9px] font-mono ${
                                d.severity === "critical"
                                  ? "bg-red-500/20 text-red-400"
                                  : d.severity === "severe"
                                  ? "bg-orange-500/20 text-orange-400"
                                  : d.severity === "moderate"
                                  ? "bg-yellow-500/20 text-yellow-400"
                                  : "text-tp-text-dim"
                              }`}
                            >
                              {d.severity}
                            </span>
                          </td>
                          <td className="text-right px-2 py-2 font-mono text-tp-text-secondary">
                            {d.max_z_score.toFixed(1)}
                          </td>
                          <td className="text-right px-2 py-2 font-mono text-tp-text-secondary">
                            {d.max_chl_a.toFixed(1)}
                          </td>
                          <td className="text-center px-2 py-2">
                            {d.error ? (
                              <span className="text-yellow-500 text-[10px]" title={d.error}>
                                ERR
                              </span>
                            ) : d.passed ? (
                              <span className="text-emerald-400 font-mono font-bold">PASS</span>
                            ) : (
                              <span className="text-red-400 font-mono font-bold">FAIL</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* False negatives explanations */}
              {results.false_negatives.length > 0 && (
                <div>
                  <div className="text-xs text-red-400/80 uppercase tracking-wider mb-2">
                    False Negative Analysis
                  </div>
                  <div className="space-y-2">
                    {results.false_negatives.map((fn, i) => (
                      <div
                        key={i}
                        className="bg-red-500/[0.06] border border-red-500/20 rounded-lg px-3 py-2.5"
                      >
                        <div className="text-xs text-red-400 font-medium">{fn.event}</div>
                        <div className="text-[11px] text-tp-text-secondary mt-1">
                          {fn.explanation}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Run again button */}
              <div className="flex gap-3 pt-2">
                <button
                  onClick={handleRun}
                  className="px-4 py-2 rounded-lg bg-white/[0.04] border border-white/[0.08] text-tp-text-secondary text-xs hover:bg-white/[0.08] transition"
                >
                  Re-run Validation
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
