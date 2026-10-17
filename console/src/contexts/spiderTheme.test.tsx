import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { ThemeProvider, useTheme } from "./ThemeContext";
import { resolveSpiderColors } from "./spiderTheme";

function Appearance() {
  const theme = useTheme();
  return (
    <>
      <button onClick={() => theme.setSpiderStyle("neon")}>Neon</button>
      <button
        onClick={() =>
          theme.setCustomTokens({
            colorPrimary: "#12ab45",
            colorSecondary: "#3456ab",
            colorWeb: "#8877cc",
          })
        }
      >
        Custom colors
      </button>
      <button onClick={() => theme.setEnableAnimations(false)}>
        Stop motion
      </button>
      <button onClick={theme.resetAppearance}>Reset</button>
      <output>
        {theme.spiderStyle} / {theme.backgroundType}
      </output>
    </>
  );
}
beforeEach(() => localStorage.clear());
afterEach(cleanup);
describe("Spider appearance", () => {
  it("persists custom thread colors across a remount and resets them together", () => {
    const result = render(
      <ThemeProvider>
        <Appearance />
      </ThemeProvider>,
    );
    fireEvent.click(screen.getByText("Neon"));
    fireEvent.click(screen.getByText("Custom colors"));
    fireEvent.click(screen.getByText("Stop motion"));
    expect(
      document.documentElement.style.getPropertyValue("--spider-primary"),
    ).toBe("#12ab45");
    expect(
      document.documentElement.style.getPropertyValue("--spider-secondary"),
    ).toBe("#3456ab");
    expect(
      document.documentElement.style.getPropertyValue("--spider-web"),
    ).toBe("#8877cc");
    expect(document.documentElement).toHaveClass("animations-off");
    result.unmount();
    render(
      <ThemeProvider>
        <Appearance />
      </ThemeProvider>,
    );
    expect(screen.getByText("neon / spiderweb")).toBeInTheDocument();
    expect(
      document.documentElement.style.getPropertyValue("--spider-primary"),
    ).toBe("#12ab45");
    fireEvent.click(screen.getByText("Reset"));
    expect(screen.getByText("classic / spiderweb")).toBeInTheDocument();
    expect(localStorage.getItem("openspider-theme-custom")).toBeNull();
    expect(localStorage.getItem("openspider-spider-style")).toBeNull();
    expect(document.documentElement).not.toHaveClass("animations-off");
  });

  it("ignores invalid saved color values and chooses readable button text", () => {
    const colors = resolveSpiderColors("classic", false, {
      colorPrimary: "url(secret)",
      colorWeb: "not a color",
    });
    expect(colors.primary).toBe("#dc304a");
    expect(colors.web).toMatch(/^#[\da-f]{6}$/i);
    expect(
      resolveSpiderColors("classic", false, { colorPrimary: "#ffffff" })
        .onPrimary,
    ).toBe("#141824");
    expect(
      resolveSpiderColors("classic", false, { colorPrimary: "#000000" })
        .onPrimary,
    ).toBe("#ffffff");
  });
});
