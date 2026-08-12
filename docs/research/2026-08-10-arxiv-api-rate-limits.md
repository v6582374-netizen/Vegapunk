# arXiv API 请求容量

调研日期：2026-08-10

## 结论

arXiv 对 legacy API（明确包括 arXiv API）公开的限制不是“允许 N 个并发请求”，而是一条同时约束频率与连接数的规则：**同一控制主体下所有机器合计，每三秒最多一个请求，且同时只能使用一条连接**。因此，安全的设计上限是 1 个在途请求、平均不高于 1/3 请求每秒；不能将“外层 Agent 并发为 2”视为符合 arXiv 限制。

## 官方原文

arXiv 的 [API Terms of Use — Rate limits](https://info.arxiv.org/help/api/tou.html#rate-limits) 规定：

> “Please note that the following rate limits apply to all of the machines under your control as a whole. You should not attempt to overcome these limits by increasing the number of machines used to make requests.”

并明确规定 legacy API：

> “When using the legacy APIs (including OAI-PMH, RSS, and the arXiv API), make no more than one request every three seconds, and limit requests to a single connection at a time.”

同页还说明：

> “These limits may change in the future.”

## 对 Launch 的含义

这个约束以控制主体为边界，而不是以进程、Agent 或机器为边界。故 Launch 内所有 arXiv 搜索、分页、引文扩展与元数据请求必须共享同一个串行节流器；每次请求起点之间至少相隔三秒，并且不得存在第二个并行连接。官方规则本身没有公布任何大于 1 的并发配额。

补充：较早的 [arXiv API User's Manual](https://info.arxiv.org/help/api/user-manual.html#311-query-interface) 也写道：

> “In cases where the API needs to be called multiple times in a row, we encourage you to play nice and incorporate a 3 second delay in your code.”

条款页是更明确、具约束性的现行依据。
