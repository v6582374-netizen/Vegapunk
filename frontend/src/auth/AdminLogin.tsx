import { Alert, Button, Card, Flex, Form, Input, Typography } from "antd";
import { useState } from "react";
import { navigate } from "../app/router";
import { loginAdmin } from "./authApi";

interface LoginValues {
  username: string;
  password: string;
}

export default function AdminLogin({ returnTo }: { returnTo: string }) {
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const onFinish = async (values: LoginValues) => {
    setError(null);
    setLoading(true);
    try {
      await loginAdmin(values.username, values.password);
      navigate(returnTo.startsWith("/admin/") ? returnTo : "/admin/queue");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="auth-page">
      <Card className="auth-card" bordered={false}>
        <Flex vertical gap={24}>
          <div>
            <Typography.Text className="eyebrow">VEGAPUNK / ADMIN</Typography.Text>
            <Typography.Title level={2} style={{ margin: "8px 0 4px" }}>
              管理后台
            </Typography.Title>
            <Typography.Paragraph type="secondary" style={{ margin: 0 }}>
              这是本机高级配置入口。登录后可以编辑 Prompt、模型目录和全局运行参数。
            </Typography.Paragraph>
          </div>
          {error !== null && <Alert type="error" showIcon message={error} />}
          <Form<LoginValues>
            layout="vertical"
            initialValues={{ username: "admin" }}
            onFinish={onFinish}
          >
            <Form.Item
              label="管理员账号"
              name="username"
              rules={[{ required: true, message: "请输入管理员账号" }]}
            >
              <Input autoComplete="username" />
            </Form.Item>
            <Form.Item
              label="密码"
              name="password"
              rules={[{ required: true, message: "请输入密码" }]}
            >
              <Input.Password autoComplete="current-password" autoFocus />
            </Form.Item>
            <Button type="primary" htmlType="submit" loading={loading} block>
              验证并进入
            </Button>
          </Form>
          <Button type="link" onClick={() => navigate("/")}>
            返回研究工作台
          </Button>
        </Flex>
      </Card>
    </main>
  );
}
