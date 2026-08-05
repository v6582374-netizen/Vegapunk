# 持续仓库审查 Agent

`.github/workflows/continuous-repository-agent.yml` 每天北京时间 00:00（GitHub cron
对应 UTC 16:00）在 GitHub-hosted runner 上启动一个长循环，并支持
`workflow_dispatch` 手动触发。每个 Job 最多工作约 5 小时 40 分钟，然后主动结束；
任务之间通过 `concurrency` 防止重叠。

GitHub 的定时任务可能因平台拥塞而延迟；公开仓库如果连续 60 天没有活动，GitHub
还可能自动停用 schedule。若 Actions 页面显示 workflow 被停用，重新启用它即可。

当前工作流使用已配置的：

- Repository secret：`DEEPSEEK_API_KEY`
- Repository variable：`LLM_BASE_URL`（当前为 `https://api.deepseek.com`）

可选地添加 `DEEPSEEK_MODEL` Repository variable；未设置时使用
`deepseek-chat`。

如需暂停定时审查，添加或修改 Repository variable
`REPOSITORY_AGENT_PAUSED=true`。需要临时强制运行时，手动触发 workflow 并勾选
`ignore_pause`；删除该变量或改为其他值即可恢复定时运行。

Agent 会在云端 runner 中循环执行五类任务：回归测试、代码质量/死代码、安全、依赖
漏洞、性能优化。每一轮运行对应工具并把当前任务的源代码片段交给 DeepSeek 复核。
只有模型给出 `STATUS: FINDINGS`，或模型服务不可用需要人工处理时，才创建或更新标题为
`[云端审查] 仓库健康问题` 的单个 Issue；同一个发现使用 fingerprint 去重，新发现以
Issue comment 追加。审查 prompt 和报告正文使用简体中文，固定的 `STATUS` 标记保留英文
以便程序解析。源代码分片会按循环轮次和 GitHub run number 轮换，
因此下一次 Job 会继续查看不同文件，而不是重复同一批文件。每次运行同时上传 30 天保留期的
`audit-report.md` artifact。

工作流权限是 `contents: read` 与 `issues: write`。Agent 只报告问题，不修改仓库
内容、不自动提交代码，也不创建 Pull Request。仓库代码和静态检查输出会发送到
`LLM_BASE_URL` 指向的模型服务；请确保这符合项目的数据使用要求。
