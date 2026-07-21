import { Button, Layout, Space, Spin, Typography } from "antd";
import { useEffect, useState, type ReactNode } from "react";
import AppLink from "./app/AppLink";
import { navigate, usePathname } from "./app/router";
import AdminLogin from "./auth/AdminLogin";
import { fetchAdminSession, type AdminSession } from "./auth/authApi";
import AdminConsole from "./features/admin/AdminConsole";
import ResearcherWorkspace, { ResearcherHome } from "./features/researcher/ResearcherWorkspace";

function UserShell({ children }: { children: ReactNode }) {
  const path = usePathname();
  return (
    <Layout className="user-layout">
      <Layout.Header className="user-header">
        <AppLink href="/" className="user-brand">
          <span className="brand-mark">V</span>
          <span>Vegapunk</span>
        </AppLink>
        <nav className="user-nav" aria-label="产品区域">
          <AppLink href="/research" className={path.startsWith("/research") ? "active" : undefined}>
            Deep Research
          </AppLink>
          <AppLink href="/discovery" className={path.startsWith("/discovery") ? "active" : undefined}>
            Discovery
          </AppLink>
        </nav>
        <Space>
          <Typography.Text className="user-context">本地工作区</Typography.Text>
          <Button type="text" onClick={() => navigate("/admin")}>管理后台</Button>
        </Space>
      </Layout.Header>
      <Layout.Content>{children}</Layout.Content>
    </Layout>
  );
}

function AdminEntry() {
  const path = usePathname();
  const [session, setSession] = useState<AdminSession | null>(null);
  const [loading, setLoading] = useState(path !== "/admin/login");

  useEffect(() => {
    if (path === "/admin/login") return;
    setLoading(true);
    fetchAdminSession()
      .then(setSession)
      .catch(() => setSession({ authenticated: false }))
      .finally(() => setLoading(false));
  }, [path]);

  if (path === "/admin/login") {
    return <AdminLogin returnTo="/admin/queue" />;
  }
  if (loading) {
    return (
      <main className="loading-page">
        <Spin size="large" />
      </main>
    );
  }
  if (session?.authenticated !== true || session.username === undefined) {
    return <AdminLogin returnTo={path} />;
  }
  return <AdminConsole username={session.username} />;
}

export default function App() {
  const path = usePathname();
  if (path.startsWith("/admin")) {
    return <AdminEntry />;
  }
  const isResearcherWorkflow = path.startsWith("/research") || path.startsWith("/discovery");
  return <UserShell>{isResearcherWorkflow ? <ResearcherWorkspace /> : <ResearcherHome />}</UserShell>;
}
