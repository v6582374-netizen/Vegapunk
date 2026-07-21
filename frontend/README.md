# Vegapunk Frontend

这是统一的 React、TypeScript、Vite 前端入口。

用户侧工作区是默认入口。

管理员页面位于受保护的 `/admin` 路由下，并保留完整的高级配置能力。

## 本地开发

先启动 FastAPI：

```bash
python -m uvicorn admin_console.app:create_app --factory --reload --port 8000
```

再启动 Vite：

```bash
cd frontend
npm install
npm run dev
```

开发服务器会把 `/api` 请求代理到 `127.0.0.1:8000`。

默认管理员账号是 `admin`，默认密码是 `admin`。

可通过 `VEGAPUNK_ADMIN_PASSWORD` 覆盖首次初始化的管理员密码。

## 构建和正式运行

```bash
cd frontend
npm run build
cd ..
python -m uvicorn admin_console.app:create_app --factory --port 8000
```

FastAPI 会从 `frontend/dist` 同源托管构建产物，并为用户侧和管理员侧路由返回同一个 SPA 入口。

管理员接口统一位于 `/api/admin/*`，登录接口位于 `/api/auth/*`。

## 检查

```bash
npm run build
npm run lint
```
