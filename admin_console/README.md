# Admin Console 后端

Admin Console 的 Python 模块提供队列、任务、Prompt、模型目录、运行参数和产物诊断能力。

统一前端位于仓库根目录的 `frontend/`，管理员页面通过 `/admin` 路由进入。

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

默认管理员账号是 `admin`，默认密码是 `admin`。

管理员 API 使用 `/api/admin/*`，旧的未认证 `/api/*` 管理员入口已移除。

## 测试

```bash
python -m unittest discover -s tests/admin_console -t . -v
```

测试通过 HTTP 接口验证认证、管理员 API、队列、任务和产物行为。
