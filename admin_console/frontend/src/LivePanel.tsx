import { useEffect, useRef, useState } from "react";
import { Card, Col, Descriptions, Empty, List, Row, Select, Typography } from "antd";
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
  const [status, setStatus] = useState<LaunchStatus | null>(null);
  const [logFile, setLogFile] = useState(LOG_FILES[0]);
  const [logLines, setLogLines] = useState<string[]>([]);
  const logBoxRef = useRef<HTMLPreElement | null>(null);

  // Follow whichever Launch is currently running.
  useEffect(() => {
    const timer = setInterval(() => {
      fetchQueue()
        .then((entries) => {
          const running = entries.find((entry) => entry.state === "running");
          setLaunchId((current) => running?.launch_id ?? current);
        })
        .catch(() => undefined);
    }, 2000);
    return () => clearInterval(timer);
  }, []);

  // Poll status (stage/rounds/artifact increments) every 2 seconds.
  useEffect(() => {
    if (launchId === null) return;
    const poll = () => {
      fetchLaunchStatus(launchId).then(setStatus).catch(() => undefined);
    };
    poll();
    const timer = setInterval(poll, 2000);
    return () => clearInterval(timer);
  }, [launchId]);

  // Stream the selected log over SSE.
  useEffect(() => {
    if (launchId === null) return;
    setLogLines([]);
    const source = new EventSource(logStreamUrl(launchId, logFile));
    source.onmessage = (event) => {
      setLogLines((lines) => [...lines.slice(-2000), event.data as string]);
    };
    source.onerror = () => source.close();
    return () => source.close();
  }, [launchId, logFile]);

  useEffect(() => {
    logBoxRef.current?.scrollTo({ top: logBoxRef.current.scrollHeight });
  }, [logLines]);

  if (launchId === null) {
    return <Empty description="当前没有正在运行的 Launch；提交一个后这里会自动跟随" />;
  }

  return (
    <Row gutter={16}>
      <Col span={10}>
        <Card title={`Live Launch View：${launchId}`} size="small">
          {status !== null && (
            <Descriptions column={1} size="small">
              <Descriptions.Item label="状态">
                <StateTag state={status.state} />
              </Descriptions.Item>
              <Descriptions.Item label="Discovery Round 数">
                {status.rounds}
              </Descriptions.Item>
            </Descriptions>
          )}
          <List
            size="small"
            header="最新产物（自动刷新）"
            dataSource={status?.recent_artifacts ?? []}
            style={{ maxHeight: "50vh", overflow: "auto" }}
            renderItem={(artifact) => (
              <List.Item>
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
          title="日志流（SSE）"
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
  );
}
