import { useEffect, useState } from "react";
import { Alert, Layout, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { fetchLaunches, type LaunchSummary } from "./api";

const stateColors: Record<string, string> = {
  completed: "green",
  unknown: "default",
};

const columns: ColumnsType<LaunchSummary> = [
  { title: "Launch", dataIndex: "id", key: "id" },
  { title: "任务", dataIndex: "task", key: "task" },
  {
    title: "启动时间",
    dataIndex: "started_at",
    key: "started_at",
    render: (value: string) => new Date(value).toLocaleString(),
  },
  {
    title: "状态",
    dataIndex: "state",
    key: "state",
    render: (state: string) => (
      <Tag color={stateColors[state] ?? "default"}>{state}</Tag>
    ),
  },
];

export default function App() {
  const [launches, setLaunches] = useState<LaunchSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchLaunches()
      .then(setLaunches)
      .catch((cause: Error) => setError(cause.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Layout.Header>
        <Typography.Title level={4} style={{ color: "white", margin: 0, lineHeight: "64px" }}>
          InternAgent Admin Console
        </Typography.Title>
      </Layout.Header>
      <Layout.Content style={{ padding: 24 }}>
        <Typography.Title level={5}>Discovery Launches</Typography.Title>
        {error !== null && <Alert type="error" message={error} style={{ marginBottom: 16 }} />}
        <Table
          rowKey="id"
          columns={columns}
          dataSource={launches}
          loading={loading}
          pagination={false}
        />
      </Layout.Content>
    </Layout>
  );
}
