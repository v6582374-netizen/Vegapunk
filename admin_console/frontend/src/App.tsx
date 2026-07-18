import { Layout, Tabs, Typography } from "antd";
import ArtifactExplorer from "./ArtifactExplorer";
import LivePanel from "./LivePanel";
import ParametersPanel from "./ParametersPanel";
import PromptsPanel from "./PromptsPanel";
import QueuePanel from "./QueuePanel";
import TaskAuthoringPanel from "./TaskAuthoringPanel";

export default function App() {
  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Layout.Header>
        <Typography.Title level={4} style={{ color: "white", margin: 0, lineHeight: "64px" }}>
          InternAgent Admin Console
        </Typography.Title>
      </Layout.Header>
      <Layout.Content style={{ padding: 24 }}>
        <Tabs
          defaultActiveKey="queue"
          items={[
            { key: "queue", label: "运行与队列", children: <QueuePanel /> },
            { key: "live", label: "实时视图", children: <LivePanel /> },
            { key: "artifacts", label: "产物浏览", children: <ArtifactExplorer /> },
            { key: "tasks", label: "任务编写", children: <TaskAuthoringPanel /> },
            { key: "prompts", label: "Prompt Library", children: <PromptsPanel /> },
            { key: "parameters", label: "运行参数", children: <ParametersPanel /> },
          ]}
        />
      </Layout.Content>
    </Layout>
  );
}
