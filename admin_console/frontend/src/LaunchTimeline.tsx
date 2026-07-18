import { Button, Empty, Space, Tag, Typography } from "antd";
import type { LaunchTimeline, TimelineRun } from "./api";

export default function LaunchTimelinePanel({
  timeline,
  onOpenArtifact,
  onOpenRun,
}: {
  timeline: LaunchTimeline | null;
  onOpenArtifact: (path: string) => void;
  onOpenRun: (run: TimelineRun) => void;
}) {
  if (timeline === null) {
    return <Empty description="选择 Launch 后显示时间线" />;
  }
  if (timeline.rounds.length === 0) {
    return <Empty description="尚无 Discovery Round 产物" />;
  }

  return (
    <div>
      <Space style={{ marginBottom: 12 }}>
        <Typography.Text type="secondary">阶段</Typography.Text>
        <Tag>{timeline.stage}</Tag>
        {timeline.paper.present && timeline.paper.path !== null && (
          <Button size="small" type="link" onClick={() => onOpenArtifact(timeline.paper.path!)}>
            论文产物
          </Button>
        )}
      </Space>
      {timeline.rounds.map((round, index) => (
        <div key={round.id} style={{ marginBottom: 16 }}>
          <Typography.Title level={5} style={{ marginBottom: 8 }}>
            Round {index + 1}
            <Typography.Text type="secondary" style={{ marginLeft: 8, fontWeight: 400 }}>
              {round.path || "(root)"}
            </Typography.Text>
          </Typography.Title>
          {round.ideas_path !== null && (
            <Button size="small" type="link" onClick={() => onOpenArtifact(round.ideas_path!)}>
              ideas.json
            </Button>
          )}
          {round.ideas.map((idea) => (
            <Typography.Paragraph key={String(idea.name ?? idea.title)} style={{ marginBottom: 4 }}>
              <Typography.Text strong>{idea.name ?? idea.title}</Typography.Text>
              {idea.title !== undefined && idea.title !== idea.name && (
                <Typography.Text type="secondary"> — {idea.title}</Typography.Text>
              )}
            </Typography.Paragraph>
          ))}
          {round.candidates.map((candidate) => (
            <div
              key={candidate.path}
              style={{
                marginTop: 8,
                paddingLeft: 8,
                borderLeft: "2px solid #d9d9d9",
              }}
            >
              <Space wrap>
                <Typography.Text strong>{candidate.name}</Typography.Text>
                {candidate.method_path !== null && (
                  <Button
                    size="small"
                    type="link"
                    onClick={() => onOpenArtifact(candidate.method_path!)}
                  >
                    方法笔记
                  </Button>
                )}
              </Space>
              <div style={{ marginTop: 4 }}>
                {candidate.runs.map((run) => (
                  <Button
                    key={run.path}
                    size="small"
                    style={{ marginRight: 6, marginBottom: 6 }}
                    onClick={() => onOpenRun(run)}
                  >
                    {run.id}
                    {run.combined_score !== null && (
                      <Typography.Text type="secondary" style={{ marginLeft: 4 }}>
                        {run.combined_score.toFixed(3)}
                      </Typography.Text>
                    )}
                    <Tag
                      style={{ marginLeft: 6 }}
                      color={
                        run.outcome === "failed"
                          ? "error"
                          : run.outcome === "completed"
                            ? "success"
                            : "default"
                      }
                    >
                      {run.outcome}
                    </Tag>
                  </Button>
                ))}
              </div>
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}
