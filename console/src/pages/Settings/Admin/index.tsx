import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Card, Descriptions, Tag, Spin } from "antd";
import { useTranslation } from "react-i18next";
import { adminApi, AdminStatusResponse } from "../../../api/modules/admin";
import { authApi } from "../../../api/modules/auth";
import { PageHeader } from "../../../components/PageHeader";
import { useAppMessage } from "../../../hooks/useAppMessage";

export default function AdminSettingsPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { message } = useAppMessage();
  const [adminInfo, setAdminInfo] = useState<AdminStatusResponse | null>(null);
  const [authEnabled, setAuthEnabled] = useState(false);
  const [hasUsers, setHasUsers] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [statusRes, adminRes] = await Promise.all([
          authApi.getStatus(),
          adminApi.getAdminStatus(),
        ]);
        if (cancelled) return;
        setAuthEnabled(statusRes.enabled);
        setHasUsers(statusRes.has_users);
        setAdminInfo(adminRes);
      } catch (err) {
        if (cancelled) return;
        if (err instanceof Error && err.message === "Admin access required") {
          message.warning(t("admin.notAuthorized"));
          navigate("/chat", { replace: true });
          return;
        }
        message.error(t("admin.loadFailed"));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [navigate, message, t]);

  if (loading) {
    return (
      <div style={{ display: "flex", justifyContent: "center", marginTop: "20vh" }}>
        <Spin tip={t("common.loading")} />
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        parent={t("nav.settings")}
        current={t("nav.adminSettings")}
      />
      <div style={{ padding: 24, maxWidth: 800 }}>
        <Card title={t("admin.authConfig")} style={{ marginBottom: 24 }}>
          <Descriptions column={1} bordered size="small">
            <Descriptions.Item label={t("admin.authEnabled")}>
              <Tag color={authEnabled ? "green" : "red"}>
                {authEnabled ? t("common.enabled") : t("common.disabled")}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label={t("admin.userCount")}>
              {adminInfo ? "..." : (hasUsers ? "1+" : "0")}
            </Descriptions.Item>
            {adminInfo && (
              <>
                <Descriptions.Item label={t("admin.username")}>
                  {adminInfo.username}
                </Descriptions.Item>
                <Descriptions.Item label={t("admin.role")}>
                  <Tag color="blue">{adminInfo.role}</Tag>
                </Descriptions.Item>
              </>
            )}
          </Descriptions>
        </Card>

        <Card title={t("admin.sessions")} style={{ marginBottom: 24 }}>
          <Descriptions column={1} bordered size="small">
            <Descriptions.Item label={t("admin.activeSessions")}>
              {t("admin.sessionsComingSoon")}
            </Descriptions.Item>
          </Descriptions>
        </Card>
      </div>
    </div>
  );
}
