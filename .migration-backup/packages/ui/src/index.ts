/**
 * @aegis-quant/ui
 * Instrument-Grade Design System Foundations and Tokens
 */

export const THEME_TOKENS = {
  colors: {
    bg: {
      canvas: "#090A0F",
      surface: "#11131A",
      surfaceElevated: "#181B24",
      surfaceHover: "#202430",
    },
    border: {
      hairline: "#232734",
      active: "#3B4254",
      focus: "#2563EB",
    },
    accent: {
      primary: "#2563EB",
      primaryHover: "#1D4ED8",
      glow: "rgba(37, 99, 235, 0.15)",
    },
    pnl: {
      profit: "#10B981",
      loss: "#F43F5E",
      neutral: "#94A3B8",
    },
  },
  typography: {
    fontUi: "Geist, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
    fontMono: "'Geist Mono', 'JetBrains Mono', monospace",
  },
  radius: {
    sm: "6px",
    md: "10px",
    lg: "14px",
  },
} as const;

export type ThemeTokens = typeof THEME_TOKENS;
