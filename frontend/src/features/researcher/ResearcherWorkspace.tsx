import { Button, Card, Flex, Space, Tag, Typography } from "antd";
import AppLink from "../../app/AppLink";
import { usePathname } from "../../app/router";

const WORKFLOWS = [
  {
    path: "/research",
    label: "Deep Research",
    eyebrow: "DR",
    description: "围绕一个研究问题收集证据，并生成带引用的报告。",
    action: "开始一次研究",
  },
  {
    path: "/discovery",
    label: "Discovery",
    eyebrow: "DS",
    description: "从研究简报进入候选方案、实验评估和论文产出流程。",
    action: "创建 Discovery",
  },
];

function WorkflowPage({ workflow }: { workflow: (typeof WORKFLOWS)[number] }) {
  const isCreate = usePathname().endsWith("/new");
  return (
    <section className="researcher-page">
      <div className="page-heading">
        <div>
          <Typography.Text className="eyebrow">RESEARCH WORKSPACE / {workflow.eyebrow}</Typography.Text>
          <Typography.Title level={1}>{workflow.label}</Typography.Title>
          <Typography.Paragraph type="secondary">{workflow.description}</Typography.Paragraph>
        </div>
        <AppLink href={`${workflow.path}/new`} className="primary-link">
          {isCreate ? "返回历史记录" : workflow.action}
        </AppLink>
      </div>
      {isCreate ? (
        <Card className="research-card" bordered={false}>
          <Typography.Title level={3}>创建 {workflow.label}</Typography.Title>
          <Typography.Paragraph>
            用户侧工作流页面已经进入统一应用。下一步会把现有原型中的结构化输入、附件和运行设置接到产品 API。
          </Typography.Paragraph>
          <Tag color="gold">产品 API 接入阶段</Tag>
        </Card>
      ) : (
        <Card className="research-card" bordered={false}>
          <Flex vertical gap={16}>
            <div>
              <Typography.Text className="eyebrow">YOUR WORK</Typography.Text>
              <Typography.Title level={3} style={{ marginTop: 8 }}>
                还没有 {workflow.label} 记录
              </Typography.Title>
              <Typography.Paragraph type="secondary">
                创建一个工作后，进度、活动和结果会在这里按工作流独立呈现。
              </Typography.Paragraph>
            </div>
            <AppLink href={`${workflow.path}/new`} className="primary-link">
              {workflow.action}
            </AppLink>
          </Flex>
        </Card>
      )}
    </section>
  );
}

export default function ResearcherWorkspace() {
  const path = usePathname();
  const workflow = path.startsWith("/discovery") ? WORKFLOWS[1] : WORKFLOWS[0];
  return <WorkflowPage workflow={workflow} />;
}

export function ResearcherHome() {
  return (
    <section className="researcher-page">
      <div className="page-heading">
        <div>
          <Typography.Text className="eyebrow">VEGAPUNK / RESEARCH WORKSPACE</Typography.Text>
          <Typography.Title level={1}>研究工作台</Typography.Title>
          <Typography.Paragraph type="secondary">
            选择一个研究入口开始工作。管理员高级配置已移入受保护的后台入口。
          </Typography.Paragraph>
        </div>
      </div>
      <div className="workflow-grid">
        {WORKFLOWS.map((workflow) => (
          <Card key={workflow.path} className="workflow-card" bordered={false}>
            <Space direction="vertical" size="middle">
              <span className="workflow-mark">{workflow.eyebrow}</span>
              <Typography.Title level={3}>{workflow.label}</Typography.Title>
              <Typography.Paragraph type="secondary">{workflow.description}</Typography.Paragraph>
              <AppLink href={workflow.path} className="primary-link">
                打开工作区
              </AppLink>
            </Space>
          </Card>
        ))}
      </div>
      <Card className="admin-entry-card" bordered={false}>
        <Flex justify="space-between" align="center" gap={24} wrap>
          <div>
            <Typography.Text className="eyebrow">ADVANCED CONFIGURATION</Typography.Text>
            <Typography.Title level={4} style={{ margin: "8px 0 4px" }}>
              管理后台
            </Typography.Title>
            <Typography.Paragraph type="secondary" style={{ margin: 0 }}>
              Prompt、模型目录、全局运行参数和原始诊断能力都保留在这里。
            </Typography.Paragraph>
          </div>
          <Button type="default" href="/admin">
            验证身份后进入
          </Button>
        </Flex>
      </Card>
    </section>
  );
}
