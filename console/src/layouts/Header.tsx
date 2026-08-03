import { Layout, Space, Tooltip } from "antd";
import LanguageSwitcher from "../components/LanguageSwitcher/index";
import ThemeToggleButton from "../components/ThemeToggleButton";
import { useTranslation } from "react-i18next";
import { Button } from "@agentscope-ai/design";
import styles from "./index.module.less";
import { getDocsUrl } from "./constants";
import { useTheme } from "../contexts/ThemeContext";

const { Header: AntHeader } = Layout;

export default function Header() {
  const { t, i18n } = useTranslation();
  const { isDark } = useTheme();

  const handleNavClick = (url: string) => {
    if (url) {
      const pywebview = (window as any).pywebview;
      if (pywebview?.api) {
        pywebview.api.open_external_link(url);
      } else {
        window.open(url, "_blank");
      }
    }
  };

  return (
    <AntHeader className={styles.header}>
      <div className={styles.logoWrapper}>
        <img
          src={isDark ? "/logo-dark.svg" : "/logo-light.svg"}
          alt="OpenSpider"
          className={styles.logoImg}
        />
        <div className={styles.logoDivider} />
      </div>
      <Space size="middle">
        <Tooltip title={t("header.docs")}>
          <Button
            type="text"
            onClick={() => handleNavClick(getDocsUrl(i18n.language))}
          >
            {t("header.docs")}
          </Button>
        </Tooltip>
        <div className={styles.headerDivider} />
        <LanguageSwitcher />
        <ThemeToggleButton />
      </Space>
    </AntHeader>
  );
}
