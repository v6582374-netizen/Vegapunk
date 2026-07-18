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

## 已交付标签页

- 运行与队列：提交 / 取消 / 优雅停止 / 强杀 / 中止后续跑
- 实时视图：阶段、Discovery Round、产物增量、SSE 日志
- 产物浏览：完整文件树与多格式查看器
- 任务编写：五字段表单 + 可选基线 zip，标注 experiment/report 路径
- Prompt Library：按阶段分组浏览/编辑；Launch 启动时整库快照
- 运行参数：Run Parameter Registry 结构化表单与服务端校验

## 测试

```bash
# 在仓库根目录，InternAgent conda 环境
python -m unittest discover -s tests/admin_console -t . -v
```

测试的主接缝是 HTTP API（FastAPI TestClient），只断言外部可见行为。
Launch 子进程命令可注入；`tests/admin_console/fake_runner.py` 是假 runner。
