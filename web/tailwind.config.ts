import type { Config } from "tailwindcss";
export default {
  darkMode: ["class"],
  content: ["./src/**/*.{ts,tsx}"],
  theme: { extend: { colors: {
    bg: "rgb(var(--bg) / <alpha-value>)", panel: "rgb(var(--panel) / <alpha-value>)", raised: "rgb(var(--raised) / <alpha-value>)",
    line: "rgb(var(--line) / <alpha-value>)", ink: "rgb(var(--ink) / <alpha-value>)", muted: "rgb(var(--muted) / <alpha-value>)",
    brand: "rgb(var(--brand) / <alpha-value>)", ok: "rgb(var(--ok) / <alpha-value>)", warn: "rgb(var(--warn) / <alpha-value>)",
  } } },
  plugins: [],
} satisfies Config;
