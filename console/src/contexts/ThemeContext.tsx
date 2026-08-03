import {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
  type ReactNode,
} from "react";

export type ThemeMode = "light" | "dark" | "system";
export type ResolvedTheme = "light" | "dark";
export type ThemePreset = "bailian" | "carbon";

export type BackgroundType =
  | "solid"
  | "gradient-linear"
  | "gradient-radial"
  | "pattern-dots"
  | "pattern-grid"
  | "particles";

export interface CustomThemeTokens {
  colorPrimary?: string;
  colorBgBase?: string;
  borderRadius?: number;
  fontSize?: number;
}

const STORAGE_KEY = "openspider-theme";
const PRESET_KEY = "openspider-theme-preset";
const CUSTOM_KEY = "openspider-theme-custom";
const BACKGROUND_KEY = "openspider-background-type";
const GLASS_KEY = "openspider-glassmorphism";
const ANIM_KEY = "openspider-animations";

interface ThemeContextValue {
  /** User selected preference: light / dark / system */
  themeMode: ThemeMode;
  /** Resolved final theme after applying system preference */
  isDark: boolean;
  setThemeMode: (mode: ThemeMode) => void;
  /** Convenience toggle: light ↔ dark (skips system) */
  toggleTheme: () => void;
  /** Theme preset (bailian | carbon) */
  themePreset: ThemePreset;
  setThemePreset: (preset: ThemePreset) => void;
  /** Custom design-token overrides (primary color, radius, …) */
  customTokens: CustomThemeTokens;
  setCustomTokens: (tokens: CustomThemeTokens) => void;
  /** Background style: solid / gradient / pattern / particles */
  backgroundType: BackgroundType;
  setBackgroundType: (type: BackgroundType) => void;
  /** Frosted-glass effect on header/sidebar */
  enableGlassmorphism: boolean;
  setEnableGlassmorphism: (on: boolean) => void;
  /** Master switch for decorative animations */
  enableAnimations: boolean;
  setEnableAnimations: (on: boolean) => void;
  /** Restore every appearance preference to factory defaults */
  resetAppearance: () => void;
}

const ThemeContext = createContext<ThemeContextValue>({
  themeMode: "light",
  isDark: false,
  setThemeMode: () => {},
  toggleTheme: () => {},
  themePreset: "bailian",
  setThemePreset: () => {},
  customTokens: {},
  setCustomTokens: () => {},
  backgroundType: "solid",
  setBackgroundType: () => {},
  enableGlassmorphism: false,
  setEnableGlassmorphism: () => {},
  enableAnimations: true,
  setEnableAnimations: () => {},
  resetAppearance: () => {},
});

function getInitialMode(): ThemeMode {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === "light" || stored === "dark" || stored === "system") {
      return stored;
    }
  } catch {
    // ignore storage errors
  }
  return "system";
}

function getInitialPreset(): ThemePreset {
  try {
    const stored = localStorage.getItem(PRESET_KEY);
    if (stored === "bailian" || stored === "carbon") {
      return stored;
    }
  } catch {
    // ignore storage errors
  }
  return "bailian";
}

function getInitialCustomTokens(): CustomThemeTokens {
  try {
    const stored = localStorage.getItem(CUSTOM_KEY);
    if (stored) {
      const parsed = JSON.parse(stored) as CustomThemeTokens;
      if (parsed && typeof parsed === "object") {
        return parsed;
      }
    }
  } catch {
    // ignore storage errors
  }
  return {};
}

function getInitialBackground(): BackgroundType {
  const valid: BackgroundType[] = [
    "solid",
    "gradient-linear",
    "gradient-radial",
    "pattern-dots",
    "pattern-grid",
    "particles",
  ];
  try {
    const stored = localStorage.getItem(BACKGROUND_KEY);
    if (stored && valid.includes(stored as BackgroundType)) {
      return stored as BackgroundType;
    }
  } catch {
    // ignore storage errors
  }
  return "solid";
}

function getInitialBool(key: string, fallback: boolean): boolean {
  try {
    const stored = localStorage.getItem(key);
    if (stored === "1" || stored === "true") return true;
    if (stored === "0" || stored === "false") return false;
  } catch {
    // ignore storage errors
  }
  return fallback;
}

function resolveIsDark(mode: ThemeMode): boolean {
  if (mode === "dark") return true;
  if (mode === "light") return false;
  // system
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false;
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [themeMode, setThemeModeState] = useState<ThemeMode>(getInitialMode);
  const [isDark, setIsDark] = useState<boolean>(() =>
    resolveIsDark(getInitialMode()),
  );
  const [themePreset, setThemePresetState] = useState<ThemePreset>(
    getInitialPreset,
  );
  const [customTokens, setCustomTokensState] = useState<CustomThemeTokens>(
    getInitialCustomTokens,
  );
  const [backgroundType, setBackgroundTypeState] =
    useState<BackgroundType>(getInitialBackground);
  const [enableGlassmorphism, setEnableGlassmorphismState] = useState<boolean>(
    () => getInitialBool(GLASS_KEY, false),
  );
  const [enableAnimations, setEnableAnimationsState] = useState<boolean>(() =>
    getInitialBool(ANIM_KEY, true),
  );

  // Apply dark/light class to <html> element for global CSS variable overrides
  useEffect(() => {
    const html = document.documentElement;
    if (isDark) {
      html.classList.add("dark-mode");
    } else {
      html.classList.remove("dark-mode");
    }
  }, [isDark]);

  // Apply background type class to <html> for global background CSS
  useEffect(() => {
    const html = document.documentElement;
    const valid: BackgroundType[] = [
      "solid",
      "gradient-linear",
      "gradient-radial",
      "pattern-dots",
      "pattern-grid",
      "particles",
    ];
    valid.forEach((t) => html.classList.remove(`bg-${t}`));
    html.classList.add(`bg-${backgroundType}`);
  }, [backgroundType]);

  // Enable/disable decorative animations globally
  useEffect(() => {
    const html = document.documentElement;
    html.classList.toggle("animations-off", !enableAnimations);
  }, [enableAnimations]);

  // Listen to system theme changes when mode is "system"
  useEffect(() => {
    if (themeMode !== "system") return;

    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = (e: MediaQueryListEvent) => {
      setIsDark(e.matches);
    };
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, [themeMode]);

  const setThemeMode = useCallback((mode: ThemeMode) => {
    setThemeModeState(mode);
    setIsDark(resolveIsDark(mode));
    try {
      localStorage.setItem(STORAGE_KEY, mode);
    } catch {
      // ignore
    }
  }, []);

  const toggleTheme = useCallback(() => {
    setThemeMode(isDark ? "light" : "dark");
  }, [isDark, setThemeMode]);

  const setThemePreset = useCallback((preset: ThemePreset) => {
    setThemePresetState(preset);
    try {
      localStorage.setItem(PRESET_KEY, preset);
    } catch {
      // ignore
    }
  }, []);

  const setCustomTokens = useCallback((tokens: CustomThemeTokens) => {
    setCustomTokensState(tokens);
    try {
      localStorage.setItem(CUSTOM_KEY, JSON.stringify(tokens));
    } catch {
      // ignore
    }
  }, []);

  const setBackgroundType = useCallback((type: BackgroundType) => {
    setBackgroundTypeState(type);
    try {
      localStorage.setItem(BACKGROUND_KEY, type);
    } catch {
      // ignore
    }
  }, []);

  const setEnableGlassmorphism = useCallback((on: boolean) => {
    setEnableGlassmorphismState(on);
    try {
      localStorage.setItem(GLASS_KEY, on ? "1" : "0");
    } catch {
      // ignore
    }
  }, []);

  const setEnableAnimations = useCallback((on: boolean) => {
    setEnableAnimationsState(on);
    try {
      localStorage.setItem(ANIM_KEY, on ? "1" : "0");
    } catch {
      // ignore
    }
  }, []);

  const resetAppearance = useCallback(() => {
    setThemeModeState("system");
    setIsDark(resolveIsDark("system"));
    setThemePresetState("bailian");
    setCustomTokensState({});
    setBackgroundTypeState("solid");
    setEnableGlassmorphismState(false);
    setEnableAnimationsState(true);
    try {
      localStorage.removeItem(STORAGE_KEY);
      localStorage.removeItem(PRESET_KEY);
      localStorage.removeItem(CUSTOM_KEY);
      localStorage.removeItem(BACKGROUND_KEY);
      localStorage.removeItem(GLASS_KEY);
      localStorage.removeItem(ANIM_KEY);
    } catch {
      // ignore
    }
  }, []);

  return (
    <ThemeContext.Provider
      value={{
        themeMode,
        isDark,
        setThemeMode,
        toggleTheme,
        themePreset,
        setThemePreset,
        customTokens,
        setCustomTokens,
        backgroundType,
        setBackgroundType,
        enableGlassmorphism,
        setEnableGlassmorphism,
        enableAnimations,
        setEnableAnimations,
        resetAppearance,
      }}
    >
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme(): ThemeContextValue {
  return useContext(ThemeContext);
}
