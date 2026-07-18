import { Button, Descriptions, Empty, Space, Tag, Typography } from "antd";
import type { ExperimentRunDetail } from "./api";

export default function ExperimentRunPanel({
  detail,
  onOpenArtifact,
}: {
  detail: ExperimentRunDetail | null;
  onOpenArtifact: (path: string) => void;
}) {
  if (detail === null) {
    return <Empty description="在时间线中选择一个 Experiment Run" />;
  }

  return (
    <div>
      <Space style={{ marginBottom: 12 }} wrap>
        <Typography.Title level={5} style={{ margin: 0 }}>
          {detail.id}
        </Typography.Title>
        <Tag
          color={
            detail.outcome === "failed"
              ? "error"
              : detail.outcome === "completed"
                ? "success"
                : "default"
          }
        >
          {detail.outcome}
        </Tag>
        <Typography.Text type="secondary">{detail.path}</Typography.Text>
      </Space>

      <Descriptions size="small" column={1} bordered style={{ marginBottom: 12 }}>
        <Descriptions.Item label="指标文件">
          {detail.metrics_path !== null ? (
            <Button type="link" size="small" onClick={() => onOpenArtifact(detail.metrics_path!)}>
              {detail.metrics_path}
            </Button>
          ) : (
            "无 final_info.json"
          )}
        </Descriptions.Item>
        <Descriptions.Item label="日志">
          {detail.log_path !== null ? (
            <Button type="link" size="small" onClick={() => onOpenArtifact(detail.log_path!)}>
              {detail.log_path}
            </Button>
          ) : (
            "无 log.txt"
          )}
          {detail.traceback_path !== null && (
            <Button type="link" size="small" onClick={() => onOpenArtifact(detail.traceback_path!)}>
              {detail.traceback_path}
            </Button>
          )}
        </Descriptions.Item>
      </Descriptions>

      {detail.metrics !== null && (
        <>
          <Typography.Text strong>指标</Typography.Text>
          <pre
            style={{
              maxHeight: 200,
              overflow: "auto",
              background: "#fafafa",
              padding: 8,
              marginTop: 4,
            }}
          >
            {JSON.stringify(detail.metrics, null, 2)}
          </pre>
        </>
      )}

      {detail.log_preview !== "" && (
        <>
          <Typography.Text strong>日志预览</Typography.Text>
          <pre
            style={{
              maxHeight: 180,
              overflow: "auto",
              background: "#fafafa",
              padding: 8,
              marginTop: 4,
            }}
          >
            {detail.log_preview}
          </pre>
        </>
      )}

      {detail.code_files.length > 0 && (
        <>
          <Typography.Text strong>代码文件</Typography.Text>
          <div style={{ marginTop: 4, marginBottom: 8 }}>
            {detail.code_files.map((file) => (
              <Button
                key={file.path}
                size="small"
                type="link"
                onClick={() => onOpenArtifact(file.path)}
              >
                {file.name}
              </Button>
            ))}
          </div>
        </>
      )}

      {detail.code_diff !== "" && (
        <>
          <Typography.Text strong>相对基线的代码变更</Typography.Text>
          <pre
            style={{
              maxHeight: 260,
              overflow: "auto",
              background: "#f6f8fa",
              padding: 8,
              marginTop: 4,
              fontSize: 12,
            }}
          >
            {detail.code_diff}
          </pre>
        </>
      )}
    </div>
  );
}
