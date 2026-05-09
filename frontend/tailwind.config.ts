import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}"
  ],
  theme: {
    extend: {
      colors: {
        ink: "#020617",
        paper: "#f8fafc",
        line: "#e2e8f0",
        moss: "#0047AF",
        sage: "#eaf2ff",
        coral: "#e11d48",
        amber: "#f59e0b"
      },
      boxShadow: {
        panel: "0 22px 60px rgba(15, 23, 42, 0.08)"
      }
    }
  },
  plugins: []
};

export default config;
