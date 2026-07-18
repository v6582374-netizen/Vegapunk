import { useCallback, useEffect, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Flex,
  Form,
  Input,
  Space,
  Table,
  Tag,
  Upload,
  message,
} from "antd";
import type { UploadFile } from "antd/es/upload/interface";
import {
  createTask,
  fetchTasks,
  submitLaunch,
  type TaskSummary,
} from "./api";

export default function TaskAuthoringPanel() {
  const [tasks, setTasks] = useState<TaskSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm();

  const refresh = useCallback(() => {
    fetchTasks()
      .then(setTasks)
      .catch((cause: Error) => setError(cause.message));
  }, []);

  useEffect(refresh, [refresh]);

  const onCreate = async () => {
    const values = await form.validateFields();
    const data = new FormData();
    data.append("name", values.name);
    data.append("system", values.system);
    data.append("task_description", values.task_description);
    data.append("domain", values.domain);
    data.append("background", values.background ?? "");
    const constraints = (values.constraints ?? "")
      .split("\n")
      .map((line: string) => line.trim())
      .filter(Boolean);
    data.append("constraints", JSON.stringify(constraints));
    const file = fileList[0]?.originFileObj;
    if (file !== undefined) {
      data.append("baseline_code", file);
    }

    setSaving(true);
    try {
      const created = await createTask(data);
      message.success(
        created.path_mode === "report"
          ? `已创建 ${created.name}（无基线代码，仅报告路径）`
          : `已创建 ${created.name}（可走实验路径）`,
      );
      form.resetFields();
      setFileList([]);
      refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setSaving(false);
    }
  };

  const onEnqueue = (name: string) => {
    submitLaunch(name)
      .then(() => message.success(`${name} 已入队`))
      .catch((cause: Error) => setError(cause.message));
  };

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      {error !== null && <Alert type="error" message={error} />}

      <Card title="Task Authoring Form（表单直填，无 LLM 辅助）">
        <Form form={form} layout="vertical">
          <Form.Item
            name="name"
            label="任务名"
            rules={[
              { required: true },
              {
                pattern: /^[A-Za-z][A-Za-z0-9_-]*$/,
                message: "以字母开头，仅字母/数字/_/-",
              },
            ]}
          >
            <Input placeholder="如 AutoMyIdea" />
          </Form.Item>
          <Form.Item name="system" label="system" rules={[{ required: true }]}>
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item
            name="task_description"
            label="task_description"
            rules={[{ required: true }]}
          >
            <Input.TextArea rows={4} />
          </Form.Item>
          <Form.Item name="domain" label="domain" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="background" label="background">
            <Input.TextArea rows={4} />
          </Form.Item>
          <Form.Item
            name="constraints"
            label="constraints（每行一条）"
            extra="未上传基线代码时，该任务只能走报告路径，不能走实验路径。"
          >
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item label="基线代码（zip，可选）">
            <Upload
              accept=".zip"
              maxCount={1}
              beforeUpload={() => false}
              fileList={fileList}
              onChange={({ fileList: next }) => setFileList(next)}
            >
              <Button>选择 zip</Button>
            </Upload>
          </Form.Item>
          <Flex gap={8}>
            <Button type="primary" loading={saving} onClick={onCreate}>
              创建任务
            </Button>
          </Flex>
        </Form>
      </Card>

      <Card title="既有任务（可复用入队）">
        <Table
          rowKey="name"
          size="small"
          dataSource={tasks}
          pagination={false}
          columns={[
            { title: "名称", dataIndex: "name" },
            { title: "类型", dataIndex: "kind" },
            {
              title: "路径",
              dataIndex: "path_mode",
              render: (mode: string) => (
                <Tag color={mode === "experiment" ? "green" : "orange"}>{mode}</Tag>
              ),
            },
            {
              title: "操作",
              render: (_, task) => (
                <Button size="small" onClick={() => onEnqueue(task.name)}>
                  入队
                </Button>
              ),
            },
          ]}
        />
      </Card>
    </Space>
  );
}
