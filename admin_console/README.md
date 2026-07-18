# Admin Console

InternAgent 的开发者管理后台（Desktop Web Console，见 ADR-0156）。
后端是 FastAPI 常驻服务，前端是 React + TypeScript + Vite + Ant Design。

## 本地开发

后端（在仓库根目录，使用 `InternAgent` conda 环境）：

```bash
python -m uvicorn admin_console.app:create_app --factory --reload --port 8000
```

前端（开发服务器会把 `/api` 代理到 `127.0.0.1:8000`）：

```bash
cd admin_console/frontend
npm install
npm run dev
```

浏览器打开 Vite 输出的地址（默认 `http://localhost:5173`）。

## 构建

```bash
cd admin_console/frontend
npm run build   # 含 tsc 类型检查，产物在 dist/
```

## 测试

```bash
python -m unittest discover tests/admin_console -v
```

测试的主接缝是 HTTP API（FastAPI TestClient），只断言外部可见行为。
