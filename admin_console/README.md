# Vegapunk 本地 API 后端

该 Python 模块提供 Discovery 队列、任务、Prompt Library、模型目录、运行参数和产物诊断 API。它不再托管或构建产品 Web 前端；产品 UI 统一由 Desktop App 提供。

## 本地运行

启动 API 服务：

```bash
python -m uvicorn admin_console.app:create_app --factory --reload --port 8000
```

本地服务默认只提供 API 路由：

- `/api/admin/*`：任务、队列、配置、Prompt、Provider 和产物管理 API
- `/api/workspace/*`：Discovery 工作区 API
- `/api/prompt-library/v1`：Desktop Settings 使用的 Prompt Library API

Prompt Library 当前由 Desktop App 的 Settings 页面调用。如果 Desktop sidecar 尚未集成该 API，需要在本机额外启动上述 FastAPI 服务；将 Prompt Library 迁入 Desktop sidecar 是后续工作。

本地 API 不使用认证，默认绑定方式和暴露边界应由启动器控制。

## 测试

```bash
python -m unittest discover -s tests/admin_console -t . -v
```

测试通过 HTTP 接口验证 API、队列、任务、Prompt Library 和产物行为。
