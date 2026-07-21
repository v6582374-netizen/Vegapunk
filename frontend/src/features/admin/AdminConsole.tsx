import { Layout, Menu, Space, Typography, Button } from "antd";
import { useEffect, useMemo } from "react";
import AppLink from "../../app/AppLink";
import { navigate, usePathname } from "../../app/router";
import { logoutAdmin } from "../../auth/authApi";
import ArtifactExplorer from "./ArtifactExplorer";
import LivePanel from "./LivePanel";
import ModelCatalogPanel from "./ModelCatalogPanel";
import ParametersPanel from "./ParametersPanel";
import PromptsPanel from "./PromptsPanel";
import QueuePanel from "./QueuePanel";
import TaskAuthoringPanel from "./TaskAuthoringPanel";

const ADMIN_SECTIONS = [
  { key: "/admin/queue", label: "运行与队列" },
  { key: "/admin/live", label: "实时视图" },
  { key: "/admin/artifacts", label: "产物浏览" },
  { key: "/admin/tasks", label: "任务编写" },
  { key: "/admin/prompts", label: "Prompt Library" },
  { key: "/admin/parameters", label: "运行参数" },
  { key: "/admin/catalog", label: "模型目录" },
];

function selectedSection(path: string): string {
  return ADMIN_SECTIONS.some((section) => section.key === path)
    ? path
    : "/admin/queue";
}

function Section({ path }: { path: string }) {
  switch (path) {
    case "/admin/live":
      return <LivePanel />;
    case "/admin/artifacts":
      return <ArtifactExplorer />;
    case "/admin/tasks":
      return <TaskAuthoringPanel />;
    case "/admin/prompts":
      return <PromptsPanel />;
    case "/admin/parameters":
      return <ParametersPanel />;
    case "/admin/catalog":
      return <ModelCatalogPanel />;
    default:
      return <QueuePanel />;
  }
}

export default function AdminConsole({ username }: { username: string }) {
  const path = usePathname();
  const section = selectedSection(path);
  const menuItems = useMemo(
    () => ADMIN_SECTIONS.map(({ key, label }) => ({ key, label })),
    [],
  );

  useEffect(() => {
    if (path === "/admin" || !ADMIN_SECTIONS.some((item) => item.key === path)) {
      navigate("/admin/queue");
    }
  }, [path]);

  const onLogout = async () => {
    await logoutAdmin();
    navigate("/admin/login");
  };

  return (
    <Layout className="admin-layout">
      <Layout.Header className="admin-header">
        <Space size="large">
          <AppLink href="/" className="admin-brand">
            <span className="brand-mark">V</span>
            <span>Vegapunk</span>
          </AppLink>
          <Typography.Text className="admin-header-label">管理后台</Typography.Text>
        </Space>
        <Space>
          <Typography.Text className="admin-user">{username}</Typography.Text>
          <Button type="text" onClick={() => void onLogout()}>
            退出
          </Button>
        </Space>
      </Layout.Header>
      <Layout>
        <Layout.Sider width={232} theme="light" className="admin-sider">
          <Menu
            mode="inline"
            selectedKeys={[section]}
            items={menuItems}
            onClick={({ key }) => navigate(key)}
          />
        </Layout.Sider>
        <Layout.Content className="admin-content">
          <Section path={section} />
        </Layout.Content>
      </Layout>
    </Layout>
  );
}
