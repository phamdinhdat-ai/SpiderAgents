import { Drawer, Divider, Slider, Switch, Button } from "antd";
import { useTranslation } from "react-i18next";
import {
  useTheme,
  type ThemePreset,
  type CustomThemeTokens,
} from "../../contexts/ThemeContext";
import BackgroundPicker from "../BackgroundPicker";
import styles from "./index.module.less";
import { SPIDER_STYLES, type SpiderStyle } from "../../contexts/spiderTheme";
import SpiderScene from "../SpiderScene";

interface ThemeSettingsDrawerProps {
  open: boolean;
  onClose: () => void;
}

const PRESET_OPTIONS: Array<{ label: string; value: ThemePreset }> = [
  { label: "Bailian", value: "bailian" },
  { label: "Carbon", value: "carbon" },
];

export default function ThemeSettingsDrawer({
  open,
  onClose,
}: ThemeSettingsDrawerProps) {
  const { t } = useTranslation();
  const {
    themePreset,
    setThemePreset,
    customTokens,
    setCustomTokens,
    enableGlassmorphism,
    setEnableGlassmorphism,
    enableAnimations,
    setEnableAnimations,
    resetAppearance,
    spiderStyle,
    setSpiderStyle,
    spiderColors,
    setThemeMode,
  } = useTheme();

  const updateTokens = (patch: Partial<CustomThemeTokens>) => {
    setCustomTokens({ ...customTokens, ...patch });
  };

  return (
    <Drawer
      title={t("appearance.title")}
      placement="right"
      width="min(420px, 100vw)"
      open={open}
      onClose={onClose}
    >
      <div className={styles.spiderPreview}>
        <SpiderScene />
      </div>
      <div className={styles.section}>
        <div className={styles.sectionTitle}>
          {t("appearance.spiderStyle", "Spider identity")}
        </div>
        <p className={styles.styleHint}>
          {t(
            "appearance.spiderHint",
            "Choose your universe. Make every thread your own.",
          )}
        </p>
        <div className={styles.presetCards}>
          {(
            Object.entries(SPIDER_STYLES) as Array<
              [SpiderStyle, (typeof SPIDER_STYLES)[SpiderStyle]]
            >
          ).map(([key, option]) => (
            <button
              key={key}
              type="button"
              aria-pressed={spiderStyle === key}
              className={`${styles.presetCard} ${
                spiderStyle === key ? styles.presetCardActive : ""
              }`}
              onClick={() => {
                setSpiderStyle(key);
                setCustomTokens({
                  borderRadius: customTokens.borderRadius,
                  fontSize: customTokens.fontSize,
                });
                if (key === "symbiote") setThemeMode("dark");
              }}
              title={option.description}
            >
              <span
                className={styles.presetSwatch}
                style={{
                  background: `linear-gradient(135deg, ${option.primary} 50%, ${option.secondary} 50%)`,
                }}
              />
              <span>{option.label}</span>
            </button>
          ))}
        </div>
      </div>
      <Divider />
      {/* ── Theme preset ── */}
      <div className={styles.section}>
        <div className={styles.sectionTitle}>{t("appearance.preset")}</div>
        <div className={styles.presetCards}>
          {PRESET_OPTIONS.map((opt) => {
            const active = themePreset === opt.value;
            return (
              <button
                key={opt.value}
                type="button"
                className={`${styles.presetCard} ${
                  active ? styles.presetCardActive : ""
                }`}
                onClick={() => setThemePreset(opt.value)}
              >
                <span
                  className={`${styles.presetSwatch} ${
                    styles[`swatch-${opt.value}`]
                  }`}
                />
                <span>{opt.label}</span>
                {active && <span className={styles.check}>✓</span>}
              </button>
            );
          })}
        </div>
      </div>

      <Divider />

      {/* ── Colors ── */}
      <div className={styles.section}>
        <div className={styles.sectionTitle}>{t("appearance.colors")}</div>
        <div className={styles.colorRow}>
          <label htmlFor="spider-primary-color">
            {t("appearance.primaryColor")}
          </label>
          <input
            id="spider-primary-color"
            type="color"
            value={spiderColors?.primary || "#dc304a"}
            onChange={(e) => updateTokens({ colorPrimary: e.target.value })}
            className={styles.colorInput}
          />
        </div>
        <div className={styles.colorRow}>
          <label htmlFor="spider-secondary-color">
            {t("appearance.secondaryColor", "Secondary color")}
          </label>
          <input
            id="spider-secondary-color"
            type="color"
            value={spiderColors?.secondary || "#2878de"}
            onChange={(e) => updateTokens({ colorSecondary: e.target.value })}
            className={styles.colorInput}
          />
        </div>
        <div className={styles.colorRow}>
          <label htmlFor="spider-web-color">
            {t("appearance.webColor", "Web thread color")}
          </label>
          <input
            id="spider-web-color"
            type="color"
            value={spiderColors?.web || "#a2b4d1"}
            onChange={(e) => updateTokens({ colorWeb: e.target.value })}
            className={styles.colorInput}
          />
        </div>
        <div className={styles.colorRow}>
          <label htmlFor="spider-background-color">
            {t("appearance.bgColor")}
          </label>
          <input
            id="spider-background-color"
            type="color"
            value={spiderColors?.canvas || "#f7f8fc"}
            onChange={(e) => updateTokens({ colorBgBase: e.target.value })}
            className={styles.colorInput}
          />
        </div>
      </div>

      <Divider />

      {/* ── Sizing ── */}
      <div className={styles.section}>
        <div className={styles.sectionTitle}>{t("appearance.sizing")}</div>
        <div className={styles.sliderRow}>
          <label>{t("appearance.borderRadius")}</label>
          <Slider
            min={2}
            max={16}
            value={customTokens.borderRadius ?? 6}
            onChange={(v) => updateTokens({ borderRadius: v })}
          />
        </div>
        <div className={styles.sliderRow}>
          <label>{t("appearance.fontSize")}</label>
          <Slider
            min={12}
            max={18}
            value={customTokens.fontSize ?? 14}
            onChange={(v) => updateTokens({ fontSize: v })}
          />
        </div>
      </div>

      <Divider />

      {/* ── Background ── */}
      <div className={styles.section}>
        <div className={styles.sectionTitle}>
          {t("appearance.background.title")}
        </div>
        <BackgroundPicker />
      </div>

      <Divider />

      {/* ── Effects ── */}
      <div className={styles.section}>
        <div className={styles.sectionTitle}>{t("appearance.effects")}</div>
        <div className={styles.toggleRow}>
          <label>{t("appearance.glassmorphism")}</label>
          <Switch
            checked={enableGlassmorphism}
            onChange={setEnableGlassmorphism}
          />
        </div>
        <div className={styles.toggleRow}>
          <label>{t("appearance.animations")}</label>
          <Switch
            aria-label={t("appearance.animations")}
            checked={enableAnimations}
            onChange={setEnableAnimations}
          />
        </div>
      </div>

      <Divider />

      <Button block onClick={resetAppearance}>
        {t("appearance.resetDefaults")}
      </Button>
    </Drawer>
  );
}
