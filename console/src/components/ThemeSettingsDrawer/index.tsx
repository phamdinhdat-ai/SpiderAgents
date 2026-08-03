import { Drawer, Divider, Slider, Switch, Button } from "antd";
import { useTranslation } from "react-i18next";
import {
  useTheme,
  type ThemePreset,
  type CustomThemeTokens,
} from "../../contexts/ThemeContext";
import BackgroundPicker from "../BackgroundPicker";
import styles from "./index.module.less";

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
  } = useTheme();

  const updateTokens = (patch: Partial<CustomThemeTokens>) => {
    setCustomTokens({ ...customTokens, ...patch });
  };

  return (
    <Drawer
      title={t("appearance.title")}
      placement="right"
      width={380}
      open={open}
      onClose={onClose}
    >
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
                  className={`${styles.presetSwatch} ${styles[`swatch-${opt.value}`]}`}
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
          <label>{t("appearance.primaryColor")}</label>
          <input
            type="color"
            value={customTokens.colorPrimary || "#FF7F16"}
            onChange={(e) => updateTokens({ colorPrimary: e.target.value })}
            className={styles.colorInput}
          />
        </div>
        <div className={styles.colorRow}>
          <label>{t("appearance.bgColor")}</label>
          <input
            type="color"
            value={customTokens.colorBgBase || "#f9f8f4"}
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
        <div className={styles.sectionTitle}>{t("appearance.background.title")}</div>
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
          <Switch checked={enableAnimations} onChange={setEnableAnimations} />
        </div>
      </div>

      <Divider />

      <Button block onClick={resetAppearance}>
        {t("appearance.resetDefaults")}
      </Button>
    </Drawer>
  );
}
