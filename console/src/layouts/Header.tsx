import { Layout, Space, Tooltip } from "antd";
import LanguageSwitcher from "../components/LanguageSwitcher/index";
import ThemeToggleButton from "../components/ThemeToggleButton";
import { useTranslation } from "react-i18next";
import { Button } from "@agentscope-ai/design";
import styles from "./index.module.less";
import { getDocsUrl } from "./constants";
import { Link, NavLink } from "react-router-dom";
import { Network } from "lucide-react";

const { Header: AntHeader } = Layout;

export default function Header() {
  const { t, i18n } = useTranslation();

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
      <Link
        to="/projects"
        className={styles.spiderBrand}
        aria-label="SpiderAgents home"
      >
        <span className={styles.spiderMark}>
          <Network size={23} strokeWidth={1.7} />
        </span>
        <span>
          Spider<span className={styles.brandLight}>Agents</span>
        </span>
        <span className={styles.studioBadge}>STUDIO</span>
      </Link>
      <nav className={styles.studioNavigation} aria-label="Main navigation">
        {[
          ["/projects", "Projects"],
          ["/chat", "Chat"],
          ["/cron-jobs", "Jobs"],
          ["/mcp", "Connections"],
        ].map(([path, label]) => (
          <NavLink
            key={path}
            to={path}
            className={({ isActive }) =>
              isActive ? styles.studioNavigationActive : ""
            }
          >
            {label}
          </NavLink>
        ))}
      </nav>
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
