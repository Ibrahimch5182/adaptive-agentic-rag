"use client";
import { useCallback, useEffect, useState } from "react";

export type ThemePref = "light" | "dark" | "system";

const STORAGE_KEY = "contextguard-theme";

function applyTheme(pref: ThemePref) {
  const root = document.documentElement;
  if (pref === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", pref);
}

export function useTheme() {
  const [theme, setThemeState] = useState<ThemePref>("system");

  useEffect(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY) as ThemePref | null;
      if (stored) setThemeState(stored);
    } catch {
      // localStorage unavailable — fall back to system default silently
    }
  }, []);

  const setTheme = useCallback((pref: ThemePref) => {
    setThemeState(pref);
    applyTheme(pref);
    try {
      localStorage.setItem(STORAGE_KEY, pref);
    } catch {
      // best-effort persistence only
    }
  }, []);

  return { theme, setTheme };
}
