import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        tp: {
          base: "#060D1B",
          surface: "#0B1120",
          card: "#0F172A",
          accent: "#10B981",
          critical: "#EF4444",
          severe: "#F97316",
          moderate: "#FBBF24",
          text: {
            primary: "#E2E8F0",
            secondary: "#94A3B8",
            muted: "#475569",
            dim: "#334155",
          },
        },
      },
      fontFamily: {
        mono: ["JetBrains Mono", "Fira Code", "monospace"],
      },
      animation: {
        pulse_ring: "pulse_ring 2s cubic-bezier(0, 0, 0.2, 1) infinite",
        scan: "scan 3s ease-in-out forwards",
        slide_in: "slide_in 0.3s ease-out forwards",
      },
      keyframes: {
        pulse_ring: {
          "0%": { transform: "scale(1)", opacity: "0.8" },
          "100%": { transform: "scale(2)", opacity: "0" },
        },
        scan: {
          "0%": { transform: "translateX(-100%)" },
          "100%": { transform: "translateX(100%)" },
        },
        slide_in: {
          "0%": { transform: "translateX(100%)", opacity: "0" },
          "100%": { transform: "translateX(0)", opacity: "1" },
        },
      },
    },
  },
  plugins: [],
};

export default config;
