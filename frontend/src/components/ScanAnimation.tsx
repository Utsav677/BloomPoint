"use client";

export function ScanAnimation() {
  return (
    <div className="absolute inset-0 pointer-events-none z-20 overflow-hidden">
      <div
        className="absolute top-0 bottom-0 w-1 animate-scan"
        style={{
          background: "linear-gradient(180deg, transparent 0%, #10B981 20%, #10B981 80%, transparent 100%)",
          boxShadow: "0 0 30px 10px rgba(16, 185, 129, 0.15), 0 0 60px 20px rgba(16, 185, 129, 0.05)",
        }}
      />
    </div>
  );
}
