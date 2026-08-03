import { useTranslation } from "react-i18next";
import { useTheme, type BackgroundType } from "../../contexts/ThemeContext";
import styles from "./index.module.less";

const OPTIONS: Array<{ key: BackgroundType; labelKey: string }> = [
  { key: "solid", labelKey: "appearance.background.solid" },
  { key: "gradient-linear", labelKey: "appearance.background.gradientLinear" },
  { key: "gradient-radial", labelKey: "appearance.background.gradientRadial" },
  { key: "pattern-dots", labelKey: "appearance.background.patternDots" },
  { key: "pattern-grid", labelKey: "appearance.background.patternGrid" },
  { key: "particles", labelKey: "appearance.background.particles" },
];

export default function BackgroundPicker() {
  const { t } = useTranslation();
  const { backgroundType, setBackgroundType } = useTheme();

  return (
    <div className={styles.grid}>
      {OPTIONS.map((opt) => {
        const active = backgroundType === opt.key;
        return (
          <button
            key={opt.key}
            type="button"
            className={`${styles.item} ${active ? styles.itemActive : ""}`}
            onClick={() => setBackgroundType(opt.key)}
          >
            <span
              className={`${styles.thumb} ${styles[`thumb-${opt.key}`]}`}
            />
            <span className={styles.label}>{t(opt.labelKey)}</span>
          </button>
        );
      })}
    </div>
  );
}
