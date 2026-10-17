export type SpiderStyle = "classic" | "symbiote" | "neon" | "studio";

export const SPIDER_STYLES: Record<
  SpiderStyle,
  { label: string; primary: string; secondary: string; description: string }
> = {
  classic: {
    label: "Spider-Verse",
    primary: "#dc304a",
    secondary: "#2878de",
    description: "Crimson threads. Electric blue connections.",
  },
  symbiote: {
    label: "Symbiote",
    primary: "#ed4058",
    secondary: "#8997ad",
    description: "Dark graphite with a sharp crimson pulse.",
  },
  neon: {
    label: "Neon Web",
    primary: "#a36bea",
    secondary: "#21bcb9",
    description: "Violet energy and luminous cyan threads.",
  },
  studio: {
    label: "Spider Studio",
    primary: "#cf6a43",
    secondary: "#738e65",
    description: "Warm copper and calm, organic connections.",
  },
};

export interface SpiderColorInput {
  colorPrimary?: string;
  colorSecondary?: string;
  colorWeb?: string;
  colorBgBase?: string;
}

const hex = (value: string | undefined, fallback: string) =>
  value && /^#[\da-f]{6}$/i.test(value) ? value : fallback;

export function resolveSpiderColors(
  style: SpiderStyle,
  dark: boolean,
  custom: SpiderColorInput = {},
) {
  const preset = SPIDER_STYLES[style];
  const canvas = hex(custom.colorBgBase, dark ? "#111722" : "#f7f8fc");
  const primary = hex(custom.colorPrimary, preset.primary);
  const channels = primary
    .slice(1)
    .match(/.{2}/g)!
    .map((value) => parseInt(value, 16) / 255);
  const luminance = channels
    .map((value) =>
      value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4,
    )
    .reduce(
      (sum, value, index) => sum + value * [0.2126, 0.7152, 0.0722][index],
      0,
    );
  return {
    primary,
    secondary: hex(custom.colorSecondary, preset.secondary),
    web: hex(custom.colorWeb, dark ? "#526785" : "#a2b4d1"),
    canvas,
    surface: dark ? "#1a2230" : "#ffffff",
    ink: dark ? "#e7edf8" : "#202b40",
    muted: dark ? "#a3b0c7" : "#63718b",
    line: dark ? "#303e54" : "#dce3ef",
    onPrimary: luminance > 0.179 ? "#141824" : "#ffffff",
  };
}

export type SpiderColors = ReturnType<typeof resolveSpiderColors>;
