import { useCallback, useEffect, useState } from "react";
import { Alert, Button, Card, Flex, Popconfirm, Select, Space, Table } from "antd";
import type { ColumnsType } from "antd/es/table";
import StateTag from "./StateTag";
import {
  cancelQueued,
  fetchLaunches,
  fetchQueue,
  fetchTasks,
  forceKill,
  gracefulStop,
  resumeLaunch,
  submitLaunch,
  type LaunchSummary,
  type QueueEntry,
  type TaskSummary,
} from "./api";

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

export default function QueuePanel() {
  const [launches, setLaunches] = useState<LaunchSummary[]>([]);
  const [queue, setQueue] = useState<QueueEntry[]>([]);
  const [tasks, setTasks] = useState<TaskSummary[]>([]);
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
      render: (_, entry) => {
        const act = (action: Promise<unknown>) =>
          action.then(refresh).catch((cause: Error) => setError(cause.message));
        if (entry.state === "queued") {
          return (
            <Button danger size="small" onClick={() => act(cancelQueued(entry.queue_id))}>
              取消
            </Button>
          );
        }
        if (entry.state === "running") {
          return (
            <Flex gap={8}>
              <Button size="small" onClick={() => act(gracefulStop(entry.queue_id))}>
                优雅停止
              </Button>
              <Popconfirm
                title="强杀会直接终止整个进程组，工作区可能不一致。确定？"
                onConfirm={() => act(forceKill(entry.queue_id))}
              >
                <Button danger size="small">
                  强杀
                </Button>
              </Popconfirm>
            </Flex>
          );
        }
        if (entry.launch_id !== null && entry.state === "aborted") {
          return (
            <Button size="small" onClick={() => act(resumeLaunch(entry.launch_id as string))}>
              续跑（用原快照）
            </Button>
          );
        }
        return null;
      },
    },
  ];

  return (
    <Space orientation="vertical" size="large" style={{ width: "100%" }}>
      {error !== null && <Alert type="error" message={error} />}

      <Card title="提交 Discovery Launch">
        <Flex gap={12} align="center">
          <Select
            style={{ width: 360 }}
            placeholder="选择任务"
            options={tasks.map((task) => ({
              value: task.name,
              label: `${task.name} [${task.path_mode}]`,
            }))}
            value={selectedTask}
            onChange={setSelectedTask}
            showSearch
          />
          <Button type="primary" disabled={selectedTask === null} onClick={onSubmit}>
            入队
          </Button>
          {selectedTask !== null &&
            tasks.find((task) => task.name === selectedTask)?.path_mode === "report" && (
              <Alert
                type="warning"
                showIcon
                message="该任务无基线代码，仅能走报告路径"
                style={{ margin: 0 }}
              />
            )}
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
  );
}
