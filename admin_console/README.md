# Vegapunk 本地工作台后端

该 Python 模块提供队列、任务、Prompt、模型目录、运行参数和产物诊断能力。

统一前端位于仓库根目录的 `frontend/`，不再区分管理员和用户侧页面。

## 本地运行

启动 FastAPI：

```bash
python -m uvicorn admin_console.app:create_app --factory --reload --port 8000
```

开发前端：

```bash
cd frontend
npm install
npm run dev
```

浏览器打开 Vite 输出的地址，默认是 `http://localhost:5173`。

开发服务器会把 `/api` 代理到 `127.0.0.1:8000`。

本地工作台不使用认证。

现有 API 使用 `/api/admin/*` 命名空间，后续会在各模块接入时收敛为产品 API。

## 测试

```bash
python -m unittest discover -s tests/admin_console -t . -v
```

测试通过 HTTP 接口验证本地 API、队列、任务和产物行为。
