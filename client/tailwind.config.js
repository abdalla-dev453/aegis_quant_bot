/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        // Base surfaces
        canvas: "#0a0d14",      // page background
        surface: "#10141d",     // card background
        "surface-alt": "#151a25", // table header / nested rows
        border: "#1e2530",      // hairline borders

        // Text
        ink: "#e6e9ef",         // primary text
        "ink-dim": "#8991a3",   // secondary/labels
        "ink-faint": "#5b6272", // tertiary/timestamps

        // Signal colors
        bull: "#22d67e",        // buy / connected / positive
        "bull-dim": "#16532f",
        bear: "#ff4d5e",        // sell / negative / halt
        "bear-dim": "#4a1720",
        accent: "#4f8ff7",      // EMA200 / profit factor / info
        warn: "#f5a623",        // amber warnings / countdowns
        "warn-dim": "#4a3512",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["'JetBrains Mono'", "ui-monospace", "monospace"],
      },
      boxShadow: {
        panel: "0 1px 0 rgba(255,255,255,0.02) inset",
      },
    },
  },
  plugins: [],
};