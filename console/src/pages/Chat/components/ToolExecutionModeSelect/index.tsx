import React, { useMemo } from "react";
import { Dropdown, Button, Space, Tooltip } from "antd";
import { DownOutlined } from "@ant-design/icons";
import { Shield, CheckCircle, AlertTriangle, Ban } from "lucide-react";
import { useTranslation } from "react-i18next";
import styles from "./index.module.less";

export type ToolExecutionLevel = "STRICT" | "SMART" | "AUTO" | "OFF";

interface LevelOption {
  value: ToolExecutionLevel;
  label: string;
  shortLabel: string;
  icon: React.ReactNode;
  description: string;
  color: string;
}

interface ToolExecutionModeSelectProps {
  value: ToolExecutionLevel;
  onChange: (level: ToolExecutionLevel) => void;
  disabled?: boolean;
}

/** Map level to compact display label (max 4 chars). */
const SHORT_LABELS: Record<ToolExecutionLevel, string> = {
  STRICT: "STRICT",
  SMART: "SMART",
  AUTO: "AUTO",
  OFF: "OFF",
};

export function ToolExecutionModeSelect({
  value,
  onChange,
  disabled = false,
}: ToolExecutionModeSelectProps) {
  const { t } = useTranslation();

  const levelOptions: LevelOption[] = useMemo(
    () => [
      {
        value: "STRICT",
        label: t("agentConfig.toolExecutionLevel.strict"),
        shortLabel: SHORT_LABELS["STRICT"],
        icon: <Ban size={16} />,
        description: t("agentConfig.toolExecutionLevel.strictDesc"),
        color: "#ff4d4f",
      },
      {
        value: "SMART",
        label: t("agentConfig.toolExecutionLevel.smart"),
        shortLabel: SHORT_LABELS["SMART"],
        icon: <AlertTriangle size={16} />,
        description: t("agentConfig.toolExecutionLevel.smartDesc"),
        color: "#faad14",
      },
      {
        value: "AUTO",
        label: t("agentConfig.toolExecutionLevel.auto"),
        shortLabel: SHORT_LABELS["AUTO"],
        icon: <Shield size={16} />,
        description: t("agentConfig.toolExecutionLevel.autoDesc"),
        color: "#1890ff",
      },
      {
        value: "OFF",
        label: t("agentConfig.toolExecutionLevel.off"),
        shortLabel: SHORT_LABELS["OFF"],
        icon: <CheckCircle size={16} />,
        description: t("agentConfig.toolExecutionLevel.offDesc"),
        color: "#52c41a",
      },
    ],
    [t],
  );

  const currentOption = useMemo(
    () => levelOptions.find((o) => o.value === value) ?? levelOptions[1], // default SMART
    [levelOptions, value],
  );

  const menuItems = useMemo(
    () => ({
      items: levelOptions.map((option) => ({
        key: option.value,
        label: (
          <div className={styles.menuItem}>
            <Space align="start" size={8}>
              <span style={{ color: option.color, marginTop: 2 }}>
                {option.icon}
              </span>
              <div className={styles.menuItemText}>
                <span className={styles.menuItemLabel}>{option.label}</span>
                <span className={styles.menuItemDesc}>{option.description}</span>
              </div>
            </Space>
          </div>
        ),
        onClick: () => onChange(option.value),
      })),
    }),
    [levelOptions, onChange],
  );

  return (
    <Dropdown menu={menuItems} trigger={["click"]} disabled={disabled}>
      <Tooltip title={t("agentConfig.toolExecutionLevel.title")} mouseEnterDelay={0.5}>
        <Button
          type="text"
          size="small"
          disabled={disabled}
          className={styles.triggerBtn}
          icon={
            <span style={{ color: currentOption.color }}>
              {currentOption.icon}
            </span>
          }
        >
          <span className={styles.triggerLabel}>{currentOption.shortLabel}</span>
          <DownOutlined className={styles.triggerArrow} />
        </Button>
      </Tooltip>
    </Dropdown>
  );
}

export default ToolExecutionModeSelect;
