import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import {
  Button,
  Card,
  Table,
  Tag,
  Modal,
  Form,
  Input,
  Select,
  Popconfirm,
  Space,
  Spin,
} from "antd";
import { PlusOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import { adminApi, UserInfo } from "../../../api/modules/admin";
import { PageHeader } from "../../../components/PageHeader";
import { useAppMessage } from "../../../hooks/useAppMessage";

export default function UserManagementPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { message: showMsg } = useAppMessage();
  const [users, setUsers] = useState<UserInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [roleUpdating, setRoleUpdating] = useState<string | null>(null);
  const [createForm] = Form.useForm();

  const fetchUsers = useCallback(async () => {
    try {
      const res = await adminApi.listUsers();
      setUsers(res.users);
    } catch (err) {
      if (err instanceof Error && err.message === "Admin access required") {
        showMsg.warning(t("admin.notAuthorized"));
        navigate("/chat", { replace: true });
        return;
      }
      showMsg.error(t("userManagement.loadFailed"));
    } finally {
      setLoading(false);
    }
  }, [navigate, showMsg, t]);

  useEffect(() => {
    fetchUsers();
  }, [fetchUsers]);

  const handleCreateUser = async (values: {
    username: string;
    password: string;
    role: string;
  }) => {
    setCreating(true);
    try {
      await adminApi.createUser(
        values.username.trim(),
        values.password,
        values.role,
      );
      showMsg.success(t("userManagement.createSuccess"));
      setCreateModalOpen(false);
      createForm.resetFields();
      fetchUsers();
    } catch (err) {
      const msg = err instanceof Error ? err.message : t("userManagement.createFailed");
      showMsg.error(msg);
    } finally {
      setCreating(false);
    }
  };

  const handleRoleChange = async (username: string, newRole: string) => {
    setRoleUpdating(username);
    try {
      await adminApi.updateRole(username, newRole);
      showMsg.success(t("userManagement.roleChangeSuccess"));
      fetchUsers();
    } catch (err) {
      const msg = err instanceof Error ? err.message : t("userManagement.roleChangeFailed");
      showMsg.error(msg);
    } finally {
      setRoleUpdating(null);
    }
  };

  const handleDelete = async (username: string) => {
    try {
      await adminApi.deleteUser(username);
      showMsg.success(t("userManagement.deleteSuccess"));
      fetchUsers();
    } catch (err) {
      const msg = err instanceof Error ? err.message : t("userManagement.deleteFailed");
      showMsg.error(msg);
    }
  };

  if (loading) {
    return (
      <div style={{ display: "flex", justifyContent: "center", marginTop: "20vh" }}>
        <Spin tip={t("common.loading")} />
      </div>
    );
  }

  const columns = [
    {
      title: t("userManagement.username"),
      dataIndex: "username",
      key: "username",
    },
    {
      title: t("userManagement.role"),
      dataIndex: "role",
      key: "role",
      render: (role: string, record: UserInfo) => (
        <Select
          value={role}
          size="small"
          style={{ width: 100 }}
          loading={roleUpdating === record.username}
          onChange={(val: string) => handleRoleChange(record.username, val)}
          options={[
            { value: "admin", label: t("userManagement.admin") },
            { value: "user", label: t("userManagement.userRole") },
          ]}
        />
      ),
    },
    {
      title: t("userManagement.actions"),
      key: "actions",
      render: (_: unknown, record: UserInfo) => (
        <Popconfirm
          title={t("userManagement.deleteConfirm")}
          onConfirm={() => handleDelete(record.username)}
          okText={t("common.yes")}
          cancelText={t("common.no")}
        >
          <Button type="link" danger size="small">
            {t("common.delete")}
          </Button>
        </Popconfirm>
      ),
    },
  ];

  return (
    <div>
      <PageHeader
        parent={t("nav.settings")}
        current={t("nav.userManagement")}
      />
      <div style={{ padding: 24, maxWidth: 900 }}>
        <Card
          title={t("userManagement.title")}
          extra={
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => {
                createForm.resetFields();
                setCreateModalOpen(true);
              }}
            >
              {t("userManagement.createUser")}
            </Button>
          }
        >
          <Table
            columns={columns}
            dataSource={users}
            rowKey="username"
            pagination={false}
            size="small"
          />
        </Card>

        <Modal
          open={createModalOpen}
          title={t("userManagement.createUser")}
          onCancel={() => setCreateModalOpen(false)}
          onOk={() => createForm.submit()}
          confirmLoading={creating}
          destroyOnHidden
        >
          <Form
            form={createForm}
            layout="vertical"
            onFinish={handleCreateUser}
            initialValues={{ role: "user" }}
          >
            <Form.Item
              name="username"
              label={t("userManagement.username")}
              rules={[{ required: true, message: t("login.usernameRequired") }]}
            >
              <Input />
            </Form.Item>
            <Form.Item
              name="password"
              label={t("login.passwordPlaceholder")}
              rules={[{ required: true, message: t("login.passwordRequired") }]}
            >
              <Input.Password />
            </Form.Item>
            <Form.Item name="role" label={t("userManagement.role")}>
              <Select
                options={[
                  { value: "user", label: t("userManagement.userRole") },
                  { value: "admin", label: t("userManagement.admin") },
                ]}
              />
            </Form.Item>
          </Form>
        </Modal>
      </div>
    </div>
  );
}
