# Vegapunk Frontend

这是统一的 React、TypeScript、Vite 前端入口。

Vegapunk 以统一工作台作为唯一入口。
初版使用左侧模块导航、中央工作区和按需出现的产物预览区域。

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

## 构建和正式运行

```bash
cd frontend
npm run build
cd ..
python -m uvicorn admin_console.app:create_app --factory --port 8000
```

FastAPI 会从 `frontend/dist` 同源托管构建产物，并为工作台路径返回同一个 SPA 入口。

本地 API 当前位于 `/api/admin/*`，后续会随各工作台模块逐步收敛命名和产品接口。

## 检查

```bash
npm run build
npm run lint
npx playwright install firefox
npm run test:e2e
```
