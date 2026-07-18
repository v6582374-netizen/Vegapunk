import { useCallback, useEffect, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Flex,
  Layout,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import {
  cancelQueued,
  fetchLaunches,
  fetchQueue,
  fetchTasks,
  submitLaunch,
  type LaunchSummary,
  type QueueEntry,
} from "./api";

const stateColors: Record<string, string> = {
  queued: "blue",
  running: "processing",
  completed: "green",
  failed: "red",
  cancelled: "default",
  interrupted: "orange",
  unknown: "default",
};

function StateTag({ state }: { state: string }) {
  return <Tag color={stateColors[state] ?? "default"}>{state}</Tag>;
}

const launchColumns: ColumnsType<LaunchSummary> = [
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
    render: (state: string) => <StateTag state={state} />,
  },
];

export default function App() {
  const [launches, setLaunches] = useState<LaunchSummary[]>([]);
  const [queue, setQueue] = useState<QueueEntry[]>([]);
  const [tasks, setTasks] = useState<string[]>([]);
  const [selectedTask, setSelectedTask] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(() => {
    Promise.all([fetchLaunches(), fetchQueue()])
      .then(([launchList, queueList]) => {
        setLaunches(launchList);
        setQueue(queueList);
        setError(null);
      })
      .catch((cause: Error) => setError(cause.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    fetchTasks().then(setTasks).catch((cause: Error) => setError(cause.message));
    refresh();
    const timer = setInterval(refresh, 2000);
    return () => clearInterval(timer);
  }, [refresh]);

  const onSubmit = () => {
    if (selectedTask === null) return;
    submitLaunch(selectedTask)
      .then(refresh)
      .catch((cause: Error) => setError(cause.message));
  };

  const onCancel = (queueId: string) => {
    cancelQueued(queueId)
      .then(refresh)
      .catch((cause: Error) => setError(cause.message));
  };

  const queueColumns: ColumnsType<QueueEntry> = [
    { title: "队列 ID", dataIndex: "queue_id", key: "queue_id" },
    { title: "任务", dataIndex: "task", key: "task" },
    { title: "提交时间", dataIndex: "submitted_at", key: "submitted_at" },
    { title: "Launch", dataIndex: "launch_id", key: "launch_id" },
    {
      title: "状态",
      dataIndex: "state",
      key: "state",
      render: (state: string) => <StateTag state={state} />,
    },
    {
      title: "操作",
      key: "actions",
      render: (_, entry) =>
        entry.state === "queued" ? (
          <Button danger size="small" onClick={() => onCancel(entry.queue_id)}>
            取消
          </Button>
        ) : null,
    },
  ];

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Layout.Header>
        <Typography.Title level={4} style={{ color: "white", margin: 0, lineHeight: "64px" }}>
          InternAgent Admin Console
        </Typography.Title>
      </Layout.Header>
      <Layout.Content style={{ padding: 24 }}>
        <Space direction="vertical" size="large" style={{ width: "100%" }}>
          {error !== null && <Alert type="error" message={error} />}

          <Card title="提交 Discovery Launch">
            <Flex gap={12}>
              <Select
                style={{ width: 320 }}
                placeholder="选择任务"
                options={tasks.map((task) => ({ value: task, label: task }))}
                value={selectedTask}
                onChange={setSelectedTask}
              />
              <Button type="primary" disabled={selectedTask === null} onClick={onSubmit}>
                入队
              </Button>
            </Flex>
          </Card>

          <Card title="Launch Queue（全局串行，同时至多一个运行）">
            <Table
              rowKey="queue_id"
              columns={queueColumns}
              dataSource={queue}
              pagination={false}
              size="small"
            />
          </Card>

          <Card title="历史 Discovery Launches">
            <Table
              rowKey="id"
              columns={launchColumns}
              dataSource={launches}
              loading={loading}
              pagination={false}
              size="small"
            />
          </Card>
        </Space>
      </Layout.Content>
    </Layout>
  );
}
