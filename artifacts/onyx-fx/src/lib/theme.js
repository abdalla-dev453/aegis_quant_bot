import {
  createContext,
  createElement,
  useContext,
  useEffect,
  useState,
} from "react";

const ThemeContext = createContext(null);

export function ThemeProvider({ children }) {
  const [themeMode, setThemeMode] = useState(() => {
    const saved = window.localStorage.getItem("aegis-theme");
    return saved === "light" || saved === "dark" || saved === "system"
      ? saved
      : "system";
  });

  useEffect(() => {
    const root = document.documentElement;
    const mediaQuery = window.matchMedia("(prefers-color-scheme: light)");
    const applyTheme = () => {
      const resolvedTheme =
        themeMode === "system"
          ? mediaQuery.matches
            ? "light"
            : "dark"
          : themeMode;
      root.dataset.theme = resolvedTheme;
    };

    applyTheme();
    window.localStorage.setItem("aegis-theme", themeMode);
    if (themeMode !== "system") return undefined;
    mediaQuery.addEventListener("change", applyTheme);
    return () => mediaQuery.removeEventListener("change", applyTheme);
  }, [themeMode]);

  return createElement(
    ThemeContext.Provider,
    { value: { themeMode, setThemeMode } },
    children,
  );
}

export function useTheme() {
  const context = useContext(ThemeContext);
  if (!context) throw new Error("useTheme must be used inside ThemeProvider");
  return context;
}
