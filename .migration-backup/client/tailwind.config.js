/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      screens: {
        'xs': '375px',
        'sm': '640px',
        'md': '768px',
        'lg': '1024px',
        'xl': '1280px',
        '2xl': '1536px',
        'mobile': '375px',
        'tablet': '768px',
        'desktop': '1024px',
      },
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
        "mobile-cta": "0 -4px 20px rgba(0,0,0,0.3)",
      },
      spacing: {
        'safe-bottom': 'env(safe-area-inset-bottom)',
        'safe-top': 'env(safe-area-inset-top)',
      },
      animation: {
        'slide-up': 'slideUp 0.3s cubic-bezier(0.22, 1, 0.36, 1)',
        'slide-down': 'slideDown 0.3s cubic-bezier(0.22, 1, 0.36, 1)',
        'fade-in': 'fadeIn 0.2s ease-out',
        'pulse-soft': 'pulseSoft 2s ease-in-out infinite',
      },
      keyframes: {
        slideUp: {
          '0%': { transform: 'translateY(100%)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
        slideDown: {
          '0%': { transform: 'translateY(-100%)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        pulseSoft: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.6' },
        },
      },
    },
  },
  plugins: [],
};