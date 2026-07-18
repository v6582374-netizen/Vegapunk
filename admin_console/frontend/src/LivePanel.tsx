import { useEffect, useRef, useState } from "react";
import { Card, Col, Descriptions, Empty, List, Modal, Row, Select, Typography } from "antd";
import ArtifactViewer from "./ArtifactViewer";
import StateTag from "./StateTag";
import {
  fetchLaunchStatus,
  fetchQueue,
  logStreamUrl,
  type LaunchStatus,
} from "./api";

const LOG_FILES = ["runner.log", "console.log"];

export default function LivePanel() {
  const [launchId, setLaunchId] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [status, setStatus] = useState<LaunchStatus | null>(null);
  const [logFile, setLogFile] = useState(LOG_FILES[0]);
  const [logLines, setLogLines] = useState<string[]>([]);
  const [viewPath, setViewPath] = useState<string | null>(null);
  const logBoxRef = useRef<HTMLPreElement | null>(null);

  useEffect(() => {
    const timer = setInterval(() => {
      fetchQueue()
        .then((entries) => {
          const active = entries.find((entry) => entry.state === "running");
          if (active?.launch_id) {
            setLaunchId(active.launch_id);
            setRunning(true);
          } else {
            setRunning(false);
          }
        })
        .catch(() => undefined);
    }, 2000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    if (launchId === null || !running) return;
    const poll = () => {
      fetchLaunchStatus(launchId).then(setStatus).catch(() => undefined);
    };
    poll();
    const timer = setInterval(poll, 2000);
    return () => clearInterval(timer);
  }, [launchId, running]);

  useEffect(() => {
    if (launchId === null || !running) return;
    setLogLines([]);
    let source: EventSource | null = null;
    let closed = false;
    let retryTimer: number | undefined;

    const connect = () => {
      if (closed) return;
      source = new EventSource(logStreamUrl(launchId, logFile));
      source.onmessage = (event) => {
        setLogLines((lines) => [...lines.slice(-2000), event.data as string]);
      };
      source.onerror = () => {
        source?.close();
        if (!closed) {
          retryTimer = window.setTimeout(connect, 1500);
        }
      };
    };
    connect();
    return () => {
      closed = true;
      source?.close();
      if (retryTimer !== undefined) window.clearTimeout(retryTimer);
    };
  }, [launchId, logFile, running]);

  useEffect(() => {
    logBoxRef.current?.scrollTo({ top: logBoxRef.current.scrollHeight });
  }, [logLines]);

  if (!running || launchId === null) {
    return <Empty description="当前没有正在运行的 Launch；提交一个后这里会自动跟随" />;
  }

  return (
    <>
      <Row gutter={16}>
        <Col span={10}>
          <Card title={`Live Launch View：${launchId}`} size="small">
            {status !== null && (
              <Descriptions column={1} size="small">
                <Descriptions.Item label="状态">
                  <StateTag state={status.state} />
                </Descriptions.Item>
                <Descriptions.Item label="阶段">{status.stage}</Descriptions.Item>
                <Descriptions.Item label="Discovery Round 数">
                  {status.rounds}
                </Descriptions.Item>
              </Descriptions>
            )}
            <List
              size="small"
              header="最新产物（点击查看）"
              dataSource={status?.recent_artifacts ?? []}
              style={{ maxHeight: "50vh", overflow: "auto" }}
              renderItem={(artifact) => (
                <List.Item
                  style={{ cursor: "pointer" }}
                  onClick={() => setViewPath(artifact.path)}
                >
                  <Typography.Text code>{artifact.path}</Typography.Text>
                  <Typography.Text type="secondary">
                    {new Date(artifact.modified_at * 1000).toLocaleTimeString()}
                  </Typography.Text>
                </List.Item>
              )}
            />
          </Card>
        </Col>
        <Col span={14}>
          <Card
            title="日志流（SSE，断线自动重连）"
            size="small"
            extra={
              <Select
                size="small"
                value={logFile}
                onChange={setLogFile}
                options={LOG_FILES.map((file) => ({ value: file, label: file }))}
              />
            }
          >
            <pre
              ref={logBoxRef}
              style={{
                background: "#111",
                color: "#ddd",
                padding: 12,
                maxHeight: "65vh",
                overflow: "auto",
                whiteSpace: "pre-wrap",
              }}
            >
              {logLines.join("\n")}
            </pre>
          </Card>
        </Col>
      </Row>
      <Modal
        open={viewPath !== null}
        title={viewPath ?? ""}
        footer={null}
        width="80%"
        onCancel={() => setViewPath(null)}
        destroyOnHidden
      >
        {viewPath !== null && <ArtifactViewer launchId={launchId} path={viewPath} />}
      </Modal>
    </>
  );
}
