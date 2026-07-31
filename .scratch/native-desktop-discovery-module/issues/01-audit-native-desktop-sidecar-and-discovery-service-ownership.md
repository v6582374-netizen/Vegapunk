# Audit Native Desktop sidecar and Discovery service ownership

Type: research
Status: closed
Assignee: research_native_desktop_sidecar
Labels: wayfinder:research
Parent: ../map.md
Blocked by: none
Blocks: 04-define-single-preparation-upload-persistence-and-error-contract.md, 05-define-conversion-formatted-input-revision-and-run-gating-contract.md, 06-map-single-active-launch-lifecycle-and-desktop-transport.md, 07-define-rightrail-adapter-and-artifact-access-contract.md

## Resolution

已完成当前 Native Desktop sidecar 与 Discovery 服务归属审计，研究笔记见 [Native Desktop Sidecar and Discovery Service Ownership](../research/01-audit-native-desktop-sidecar-and-discovery-service-ownership.md)。

结论是 Tauri 管理的唯一 `openworker-server` sidecar 承担 Native Desktop 的唯一用户可见本地服务。
Discovery 应通过 sidecar 内的 `/v1/discovery/...` facade 或 router 接入，并复用 native `SessionManager` data root、`SecretStore`、token middleware、`api.ts` transport，以及通过适配层接入的 Preparation、conversion、queue、live、artifact seams。

`admin_console.app:create_app`、未认证的 `/api/*`、repository-root 的 `results`/`tasks`/config 默认值、8000 端口和 Web-only middleware 保留为兼容或测试边界，不作为 Native Desktop 的生产进程归属。

应用退出时的 active Launch 处理、重启后的 adoption 或 Resume 语义仍由票据 06 决定。
原生数据根路径和各适配器的具体契约由票据 04 至 07 继续收敛。

## Question

Which current native desktop process-start, FastAPI app-construction, data-root, authentication, and API conventions allow the existing Discovery store, conversion service, queue, and artifact seams to run behind the native sidecar without creating a second user-visible service?
The answer must identify the real ownership and integration boundaries in the current checkout and distinguish reusable code from Web-only route or middleware assumptions.
