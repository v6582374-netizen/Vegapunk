# Brownfield 巨型代码库精简与架构治理工具调研

调研日期：2026-07-30。

调研对象：适合已经运行多年、目录混杂、依赖隐式、测试覆盖不均、代码和产物持续堆积的 brownfield 仓库的工具、框架与工程 skill。

目标项目：当前 InternAgent/Vegapunk 仓库。

本报告不把 star 数当成质量证明，而是把它作为生态采用度的一个可复核信号，并结合一手文档、许可证、提交活动和 brownfield 风险做筛选。

## 结论先行

没有一个工具可以单独把巨型 brownfield 仓库“自动变干净”。

最可靠的路线是先建立事实图，再建立边界规则，再提出可回滚的删除候选，最后才执行确定性重构和 AI 辅助改动。

对 InternAgent，首选组合是 `scc + 现有 codebase-memory-mcp + Import Linter/dependency-cruiser（Python/前端边界）+ Vulture/Knip（死代码）+ ast-grep（结构化改写）+ Ruff/ESLint/Pyright（回归门）+ reviewdog（只评论新增问题）`。

Semgrep 和 CodeQL 应作为第二层的规则与跨文件语义分析工具，而不是第一天就把全部历史违规清零。

OpenTelemetry 和 Backstage 解决的是“静态图看不到的真实运行依赖”和“谁拥有这个模块”，它们不能替代静态分析，但能显著降低误删风险。

OpenRewrite、Bazel 和大型 AI agent 更适合在边界已经稳定、测试和回滚路径已经可靠之后引入。

AI 不应直接决定删除哪些文件，也不应在没有 worktree、审批、diff、测试和 artifact 记录的情况下批量改写整个仓库。

## 核验方法与边界

项目 star 数来自每个 GitHub 官方仓库页面在 2026-07-30 的公开计数。

项目活跃度来自对应默认分支的 GitHub 官方 `commits.atom` 订阅，而不是第三方排行榜或 README 徽章。

许可证以 GitHub 官方仓库页面显示的许可证或仓库根许可证文件为准。

功能描述优先引用项目自己的 README、官方文档、规范或源码。

star 数会继续变化，因此下表的数字是 2026-07-30 的快照，不应当被当作永久元数据。

“活跃”只表示在快照前约三个月内存在提交或仍有明确维护活动，不表示 API 稳定、商业版可用或适合直接写入生产仓库。

商业功能、托管服务和不同子仓库可能有与核心仓库不同的许可证，报告在风险栏中单独标出这种边界。

## 为什么 InternAgent 是典型 brownfield

当前 [architecture.md](../../architecture.md) 显示，仓库同时包含 Python 的 `vegapunk`、`admin_console`、实验和脚本目录，React/TypeScript 的 `frontend`，大量 `tasks/*` 任务树，以及 `third_party/paper_orchestra` 和 `desktop/openworker/upstream` 等继承或上游代码。

这意味着“没有引用的文件”不一定是死代码，因为入口可能来自 CLI、配置、动态导入、模型工具注册、任务目录约定、子进程、外部 runner 或浏览器请求。

运行时还会生成 `results`、日志、缓存、截图和实验产物，因此源代码、vendored 代码、生成物和运行时数据必须在分析前分层。

现有的 codebase-memory-mcp 已经提供代码图谱能力，因此新工具首先应该补齐规则、指标、运行时证据和可回滚改写，而不是再造一个没有边界的全文搜索层。

## 当前 checkout 的只读规模快照

以下数字来自 2026-07-30 对当前 checkout 执行的 `git ls-files`、`wc -l`、`du`、`git count-objects` 和现有代码图谱查询，不代表已经清理后的目标状态。

仓库当前有 2,776 个 tracked files，其中 1,610 个 Python 文件约 368,303 行，188 个 TypeScript/TSX 文件约 36,313 行。

tracked file 数量最多的顶级区域是 `tasks`（1,296）、`vegapunk`（503）、`desktop`（446）、`docs`（191）、`config`（100）、`third_party`（58）、`frontend`（57）、`tests`（51）和 `admin_console`（23）。

`tasks` 不是单纯的源码目录，其中包含 810 个 Python 文件、118 个 shell 文件、89 个 JSON 文件、83 个 Markdown 文件和 35 个 YAML 文件，说明任务实现、配置、说明和运行快照已经混在同一棵树里。

本地工作树的目录体积还包括约 3.1 GiB 的 `desktop`、约 1.4 GiB 的 `sci_tasks` 子模块、约 176 MiB 的 `.code-review-graph`、约 133 MiB 的 `.claude`、约 120 MiB 的 `tmp` 和约 33 MiB 的 `output`。

这些工作树体积不能直接等同于源码债务，但它们足以证明分析器必须先排除缓存、构建物、运行产物、子模块数据和 agent 临时目录。

当前根级 `requirements.txt` 有 384 行、383 个不同的依赖声明，而根目录没有 `pyproject.toml`，这更像跨任务的依赖总表，而不是一个可直接用于架构边界的产品运行时清单。

现有代码图谱显示 20 个社区、0 条社区间边，并且图谱构建 SHA `54f4a3a` 与当前 HEAD `479f8a3` 不一致。

因此，当前图谱可以作为线索，但不能作为删除或模块拆分的事实依据，第一阶段必须刷新索引并把其输出和当前 commit 一起固化。

Git 对象库当前约 142.5 MiB，而工作树远大于这个数量级，这提示第一轮重点应放在“分析边界、运行产物和目录所有权”，而不是未经审计地重写 Git 历史。

## 第一梯队：最值得先试的工具

下表的推荐等级只针对 InternAgent 的 brownfield 精简和架构治理，不代表项目本身的综合排名。

| 工具 | 2026-07-30 快照 | 语言或生态 | 主要能力 | 对 InternAgent 的用法 | Brownfield 风险 | 推荐 |
| --- | --- | --- | --- | --- | --- | --- |
| [scc](https://github.com/boyter/scc) | 8,573 stars；MIT；最近提交 2026-07-26 | Go CLI；语言无关的源码统计 | 计算 LOC、复杂度、重复度、COCOMO/LOCOMO、Git insight 和 HTML 报告，README 还记录了 MCP 模式 | 先建立每个顶级目录的规模、复杂度和重复度基线，再用同一命令比较每轮治理后的变化 | 指标是代理变量，不能证明代码可删除；团队可能为了数字而重排代码 | A |
| [tree-sitter](https://github.com/tree-sitter/tree-sitter) | 26,473 stars；MIT；最近提交 2026-07-29 | C/JavaScript parser generator；多语言 grammar 生态 | 增量、容错的语法树解析器 | 作为结构化 inventory 和自定义图谱的底层解析层，补充现有 codebase-memory-mcp 对语法结构和文件类别的判断 | 它不是现成治理平台，没有类型、运行时或业务语义；grammar 版本和解析错误需要固定 | A（基础库） |
| [ast-grep](https://github.com/ast-grep/ast-grep) | 15,302 stars；MIT；最近提交 2026-07-29 | Rust CLI；tree-sitter 多语言语法树 | 用接近普通代码的 pattern 做 structural search、lint 和 rewrite，并支持 YAML 规则和多核执行 | 批量识别和替换旧 API、导入、工具注册模式和重复分支；先 dry-run，再按目录提交小 patch | 主要理解语法结构，不等于类型或运行时语义；动态构造和反射会漏报或误报 | A |
| [Ruff](https://github.com/astral-sh/ruff) | 48,924 stars；MIT；最近提交 2026-07-29 | Rust 工具链；Python 生态 | Python lint、format、自动修复和缓存，官方文档提供规则、配置和 monorepo 用法 | 清理未使用 import、低级坏味道和风格分歧，统一 `vegapunk`、`admin_console`、脚本和测试的最小质量门 | Python only；一次性启用全部 autofix 会造成大 diff，必须分规则、分目录、可回滚 | A |
| [Knip](https://github.com/webpro-nl/knip) | 11,852 stars；ISC；最近提交 2026-07-29 | Node/TypeScript/JavaScript | 发现未使用 dependencies、exports、files 和配置，并提供 plugin/entry-point 机制 | 对 `frontend` 先配置真实入口、Vite、测试、脚本和生成路径，输出未使用依赖和文件候选，不自动删除 | 动态 import、框架约定、代码生成和实验入口会让结果偏保守或误报；必须维护 entry points 与 whitelist | A |
| [Vulture](https://github.com/jendrikseipp/vulture) | 4,736 stars；MIT；最近提交 2026-04-30 | Python | 发现未使用函数、类、变量、不可达代码，并按 confidence 评分 | 先用最高置信度扫描 `vegapunk`、`admin_console` 和脚本，再结合测试、CLI 入口和配置引用建立白名单 | 官方 README 明确动态或隐式调用可能被误判；最近提交距快照约三个月，不能把它当唯一真相 | A（只做候选） |
| [deptry](https://github.com/fpgmaas/deptry) | 1,443 stars；MIT；最近提交 2026-07-29 | Python；pyproject/requirements 依赖生态 | 检查 direct dependency 未使用、代码使用但未声明以及依赖版本问题 | 对根 `requirements.txt`、`vegapunk`、`admin_console` 和任务子项目分层扫描，清理“装着但不用”的 Python 依赖 | 复杂 extras、动态 import、子进程和 vendored 任务会造成误报；必须按可部署单元配置扫描边界 | A-（依赖减法） |
| [dependency-cruiser](https://github.com/sverweij/dependency-cruiser) | 7,003 stars；MIT；最近提交 2026-07-28 | Node；JavaScript/TypeScript/LiveScript/CoffeeScript | 生成依赖图，并用规则检测循环、跨层依赖和禁用边 | 先画 `frontend` 的 import graph，再把 UI、API client、workspace state、运行时适配器和测试 fixture 之间的边界写成规则 | 只看静态模块依赖，不是运行时调用图；规则过多会制造噪声和豁免债务 | A |
| [Nx](https://github.com/nrwl/nx) | 29,155 stars；MIT；最近提交 2026-07-30 | TypeScript/Node；workspace/monorepo 生态 | Project graph、affected-only task、缓存和插件；官方文档支持对现有 workspace 使用 `nx init` | 如果前端已经接近 workspace，可用 project graph 和 tags 把应用、库、工具和测试边界显式化，减少全量构建 | 会引入 workspace metadata、插件和 Nx 约定；Nx Cloud 等托管能力有独立商业边界，不能把 Nx 当死代码工具 | A（条件式） |
| [Semgrep](https://github.com/semgrep/semgrep) | 16,044 stars；LGPL-2.1；最近提交 2026-07-29 | 多语言静态分析；官方 README 宣称支持 30+ languages | 通过代码 pattern 做 bug、坏味道、安全和自定义 guardrail 检查，可接 IDE、pre-commit、CI，官方文档还提供 MCP server 入口 | 为废弃 provider、越层 import、危险 shell/路径操作、任意模型工具执行和旧配置格式建立可读规则，并在 PR 只阻止新增违规 | Community/本地能力与商业平台的跨文件和 dataflow 能力不同；动态语言和复杂规则会产生噪声 | A（第二层） |
| [reviewdog](https://github.com/reviewdog/reviewdog) | 9,487 stars；MIT；最近提交 2026-07-29 | Go；任意 linter 的 review adapter | 把 linter 输出按 diff 过滤并贴到 GitHub/GitLab review | 让旧仓库先只收到“本次改动新增的问题”，避免把历史债务一次性变成不可合并的质量门 | 它本身不是 analyzer，必须和 Ruff、ESLint、Semgrep、CodeQL 等配合；评论过多会变成背景噪声 | A（渐进落地） |

## 第二梯队：高价值但需要更强边界或更高投入

| 工具 | 2026-07-30 快照 | 语言或生态 | 主要能力 | 对 InternAgent 的用法 | Brownfield 风险 | 推荐 |
| --- | --- | --- | --- | --- | --- | --- |
| [GitHub CodeQL](https://github.com/github/codeql) | 9,886 stars；MIT；最近提交 2026-07-29 | QL 查询；覆盖多种主流语言和跨函数数据流 | 把源码编译或抽取成数据库，用语义查询和 dataflow 找跨文件调用链、危险模式和边界问题 | 用于高风险工具执行、凭据流、路径穿越、子进程、HTTP handler 到 runtime 的跨文件审计 | CodeQL 仓库与 CLI/engine 的许可和发布边界并不完全相同；数据库构建和 QL 学习成本高 | A-（高风险代码） |
| [SonarQube](https://github.com/SonarSource/sonarqube) | 10,843 stars；LGPL-3.0；最近提交 2026-07-29 | Java 服务端和多语言 scanner 生态 | Continuous Inspection、规则、复杂度、漏洞和 Quality Gate，并能聚焦新引入问题 | 适合需要统一仪表板、门禁、责任人和趋势报告的团队，可作为组织级质量平台 | 自托管基础设施和规则运营成本较高；商业版能力、插件许可和版本升级需独立核验 | B |
| [OpenRewrite](https://github.com/openrewrite/rewrite) | 3,624 stars；Apache-2.0 core；最近提交 2026-07-29 | Java/Kotlin/Groovy 最成熟，并扩展到其他 parser/recipe 生态 | Fast、repeatable refactoring 和 recipe，用于框架迁移、依赖升级、安全修复和风格迁移 | 如果未来仓库引入 Java 子系统，优先用官方 recipe 做可重复迁移；当前 Python/TS 主线先不要为了它引入 Java runtime | 非 Java parser/recipe 的成熟度和跨仓库批处理许可要逐项核验；recipe 仍需 fixture、编译和测试 | B（Java 专项） |
| [jscodeshift](https://github.com/facebook/jscodeshift) | 10,026 stars；MIT；最近提交 2026-07-15 | Node；JavaScript/TypeScript codemod | 基于 recast 的 codemod runner，尽量保留格式，并支持 dry-run、统计和 fixture | 对前端 API、导入路径、React 组件 prop 和配置结构做一次性可审查迁移 | JS/TS only；transform 依赖 parser 和真实入口，必须先用 fixture、snapshot、类型检查和构建验证 | A-（前端迁移） |
| [ESLint](https://github.com/eslint/eslint) | 27,428 stars；MIT；最近提交 2026-07-29 | Node/JavaScript/TypeScript 规则生态 | 可插拔 AST rule、配置和自动修复 | 把禁止跨层 import、禁止旧 API、复杂度上限和命名约定编码成只针对新增代码的规则 | ESLint 只能证明规则被满足，不能自动证明架构正确；配置和 rule sprawl 需要有 owner | A |
| [typescript-eslint](https://github.com/typescript-eslint/typescript-eslint) | 16,326 stars；MIT；最近提交 2026-07-29 | TypeScript compiler API + ESLint | 提供 TypeScript parser、typed lint 和规则生态 | 在 `frontend` 中补充类型感知的未使用、危险 any、API 边界和复杂度检查 | type-aware lint 成本更高，并与 TypeScript/ESLint 版本耦合；需要缓存和分层执行 | A- |
| [Import Linter](https://github.com/seddonym/import-linter) | 1,115 stars；BSD-2-Clause；最近提交 2026-07-03 | Python；import contract 生态 | 官方 README 将其定义为对 Python architecture 做 lint，并用 contracts 约束模块 import | 这是当前 Python 主线最贴合的边界回归工具，可把 `vegapunk`、`admin_console`、工具层和 runtime 的允许方向固化成测试 | 只看静态 import；动态 import、插件和配置入口必须进入 contracts 或 whitelist；star 数较低但问题匹配度高 | A |
| [Pyright](https://github.com/microsoft/pyright) | 15,556 stars；MIT；最近提交 2026-07-29 | TypeScript 实现的 Python type checker；VS Code/CLI 生态 | 官方 README 将其定位为面向大型代码库的高性能、全功能 Python 静态类型检查器 | 在删除和重构前逐步补齐函数、配置 DTO、tool schema 和 API 边界的类型约束，降低“静态图看似无引用但运行时形状依赖”的风险 | 类型检查不是 dead-code 检测；strictness 需要分目录提升，第三方类型缺失会制造噪声 | A-（安全网） |
| [mypy](https://github.com/python/mypy) | 20,555 stars；MIT；最近提交 2026-07-30 | Python；类型注解和 mypyc 生态 | 官方 README 将其定位为 Python static type checker，并支持渐进式类型标注 | 如果已有代码更接近 mypy 配置或需要更广的插件生态，可作为 Pyright 的替代或分层补充 | 不能直接证明模块可删除；Pyright 和 mypy 同时全量启用会产生重复成本，应先选一个主检查器 | B（择一） |
| [ArchUnit](https://github.com/TNG/ArchUnit) | 3,786 stars；Apache-2.0；最近提交 2026-07-28 | Java bytecode；JUnit 生态 | 在测试中检查 package、class、layer、slice、cycles 和命名规则 | 当前仓库没有 Java 主线时不应引入；若未来 PaperOrchestra 或服务拆成 Java，适合作为“架构即测试”模板 | Java only；错误的规则会把错误架构永久化，且不能覆盖 Python/TS 运行时边界 | C（未来专项） |
| [Bazel](https://github.com/bazelbuild/bazel) | 25,654 stars；Apache-2.0；最近提交 2026-07-30 | 多语言 hermetic build；monorepo 生态 | 显式依赖、增量 build/test、query 和 remote cache | 只有在仓库长期需要可查询的构建图、跨语言增量构建和严格可复现后，才考虑把部分稳定子树迁入 | BUILD 文件和 rule 维护成本很高；迁移会改变开发工作流，不能作为第一阶段清理手段 | C（长期基础设施） |
| [Renovate](https://github.com/renovatebot/renovate) | 22,127 stars；AGPL-3.0-only；最近提交 2026-07-30 | Node；90+ package managers | 扫描 manifest/lockfile、打开依赖升级 PR，并支持分组、节奏和 merge confidence | 让依赖“持续变旧”停止增长，优先分组非破坏性 patch/minor 更新，单独处理 major 和跨运行时升级 | PR/lockfile churn、私有 registry 凭据和 AGPL 合规需要治理；必须有 CI 和并发限制 | A- |
| [Dependabot Core](https://github.com/dependabot/dependabot-core) | 5,704 stars；MIT；最近提交 2026-07-29 | Ruby；多语言 manifest/lockfile | 解析依赖文件并生成可审查升级 PR | 如果希望使用 GitHub 原生依赖更新而不是自托管 Renovate，可作为较窄的替代 | 自托管执行不可信包管理代码时需要隔离；功能和策略编排通常比 Renovate 窄 | B |
| [OSV-Scanner](https://github.com/google/osv-scanner) | 10,706 stars；Apache-2.0；最近提交 2026-07-30 | Go；OSV 数据库和多语言 lockfile | 扫描依赖、容器和源码，提供 guided remediation 与部分 call analysis | 先给依赖删除和升级候选加漏洞严重度，避免为了“变少”而保留已知高风险依赖 | 它偏安全而不是架构简化；升级仍需 API 兼容性、运行时和实验结果验证 | A-（依赖层） |
| [OpenGrok](https://github.com/oracle/opengrok) | 4,898 stars；CDDL-1.0；最近提交 2026-06-25 | Java 服务；多语言文本索引和 cross-reference | 建立源码索引、定义和引用导航，适合超大仓库的人类检索 | 当现有图谱无法覆盖 vendored 或生成代码时，提供只读全文/交叉引用入口，帮助人工核对候选删除 | CDDL 和第三方依赖通知需审查；它偏搜索和导航，不提供边界规则或死代码证明 | B-（检索层） |
| [Zoekt](https://github.com/sourcegraph/zoekt) | 1,797 stars；Apache-2.0；最近提交 2026-07-29 | Go；trigram/full-text code search | 面向大量仓库的快速代码搜索索引 | 适合把 vendored、历史分支和生成物隔离到只读搜索索引，支持删除前的字符串和调用点复核 | star 数低于主流候选，产品化和权限集成需要自行承担；全文命中仍不等于语义引用 | B-（特殊检索） |

## 第三梯队：运行时证据、模块所有权和 AI 执行层

| 工具 | 2026-07-30 快照 | 语言或生态 | 主要能力 | 对 InternAgent 的用法 | Brownfield 风险 | 推荐 |
| --- | --- | --- | --- | --- | --- | --- |
| [OpenTelemetry Collector](https://github.com/open-telemetry/opentelemetry-collector) | 7,313 stars；Apache-2.0；最近提交 2026-07-29 | Go Collector；多语言 SDK/自动 instrumentation 生态 | 接收、处理和导出 traces、metrics、logs，并通过组件形成可观测管道 | 给模型请求、工具调用、Discovery/实验 launch、HTTP route、队列和 artifact 生命周期加稳定 span/metric，形成“实际被走过的依赖”证据 | 采集过多高基数属性会增加成本并泄露 prompt/secret；必须先定义脱敏和 cardinality 预算 | B |
| [Backstage](https://github.com/backstage/backstage) | 33,978 stars；Apache-2.0；最近提交 2026-07-29 | TypeScript/React/Node；软件目录和开发者门户 | Software Catalog、组件元数据、ownership、系统和依赖关系 | 把 `vegapunk`、`frontend`、Discovery、PaperOrchestra、OpenWorker 和任务族登记成可拥有组件，给每个边界绑定 owner、文档和质量门 | 引入平台和 catalog 运营成本；目录是人为声明，必须与构建图、CODEOWNERS 和运行时证据定期校验 | B（组织层） |
| [Joern](https://github.com/joernio/joern) | 3,366 stars；Apache-2.0；最近提交 2026-07-29 | Scala；Code Property Graph，多语言前端 | 把 AST、CFG、PDG 等信息合并成可查询的 code property graph | 对跨函数、跨文件和安全敏感路径做深度查询，尤其是 tool execution、subprocess、文件写入和 provider credential 流 | 学习成本、索引成本和语言前端覆盖需要评估；它是分析平台，不是删除按钮 | B-（高风险专项） |
| [Aider](https://github.com/Aider-AI/aider) | 47,795 stars；Apache-2.0；最近提交 2026-05-22 | Python；多语言 LLM coding CLI | README 和文档强调 repo map、Git、自动 lint/test 以及多语言编辑 | 在已经写好 issue、边界规则和测试的前提下，让模型执行小步、可审查的重构任务 | 最近提交明显慢于其他候选；模型编辑仍非确定，必须使用 worktree、最小 diff 和独立测试 | B-（执行助手） |
| [OpenHands](https://github.com/All-Hands-AI/OpenHands) | 82,555 stars；MIT；最近提交 2026-07-30 | Python/TypeScript；agent runtime、CLI、self-hosted/cloud backend | 运行可调用工具的 coding agent，并支持任务自动化和多种执行后端 | 可把“扫描结果 -> issue -> 小 patch -> 测试 -> 报告”串成受限流水线，但只能操作隔离 worktree 和明确文件范围 | 官方文档警告无 sandbox 时 agent 可能拥有完整文件系统权限；agent 仍可能误解动态入口，不能直接授予整个仓库写权限 | C（受限自动化） |
| [obra/superpowers](https://github.com/obra/superpowers) | 263,425 stars；MIT；最近提交 2026-07-28 | Agent skill/workflow；与多种 coding agent 配合 | 以 skills、流程和检查清单约束代理完成任务 | 可借鉴“先计划、先测试、分小步、检查 diff”的流程层，并与 InternAgent 的 code-review、codebase-design skill 对齐 | 它是流程和提示层，不会产生真实依赖图或删除证明；复制 skill 前仍需审查脚本、许可证和执行边界 | B-（流程层） |
| [GitHub Awesome Copilot](https://github.com/github/awesome-copilot) | 37,214 stars；MIT；最近提交 2026-07-30 | GitHub 官方社区 instructions/agents/skills 集合 | 提供可复用的 coding instructions、agents 和 skills 示例 | 可作为“架构审查、变更说明、迁移前检查”的 prompt 参考库，但只复制经过审查的流程，不自动引入其全部内容 | 社区内容质量和适用性不均；skill 可能触发工具或代码执行，必须固定版本并做权限审计 | C（参考库） |

## 对 InternAgent 的推荐组合

### 组合 A：两周内建立真实基线

第一步是把源码、vendored、生成物、缓存、实验运行目录和测试 fixture 分成明确的分析集合。

对每个集合运行 [scc](https://github.com/boyter/scc)，记录文件数、LOC、复杂度、重复度和 Git 活跃度，但不把指标直接当成删除理由。

复用现有 codebase-memory-mcp 的图谱，把 `vegapunk`、`admin_console`、`frontend`、`tasks`、`third_party` 和 `desktop/openworker/upstream` 分别标记为 first-party、integration、vendored、generated 或 runtime data。

对前端先生成 [dependency-cruiser](https://github.com/sverweij/dependency-cruiser) 图，对 Python 先用现有图谱和静态 import 扫描建立同等视图。

把所有高风险动态入口登记出来，包括 CLI dispatch、配置加载、动态 import、工具注册、子进程 runner、任务目录约定、Vite API proxy 和 browser route。

这一阶段的成功标准是“知道代码和依赖在哪里”，不是“删除了多少行”。

### 组合 B：先做候选清理，不做自动删除

对 Python 使用 [Vulture](https://github.com/jendrikseipp/vulture) 的高置信度模式，并对动态入口建立 whitelist。

对 TypeScript/JavaScript 使用 [Knip](https://knip.dev/) 的真实 entry points 和 plugins 配置，并把生成代码、测试、Vite、脚本和任务入口纳入配置。

对 Python 使用 [Ruff](https://docs.astral.sh/ruff/) 的未使用 import 和低风险规则，并选择 [Pyright](https://microsoft.github.io/pyright/) 或 [mypy](https://mypy.readthedocs.io/) 作为类型安全网，对 TypeScript 使用 [ESLint](https://eslint.org/docs/latest/) 与 [typescript-eslint](https://typescript-eslint.io/) 的类型感知规则。

每个删除候选至少需要静态引用检查、配置/入口检查、测试或 smoke run、最近运行时 trace 和 Git history 五类证据中的四类。

候选清单应写入带 owner、evidence、confidence、first_seen、last_seen 和 waiver_until 字段的机器可读文件，而不是只贴在聊天记录里。

### 组合 C：用确定性工具执行小步迁移

对同构的导入、调用和配置迁移优先使用 [ast-grep](https://ast-grep.github.io/) 的结构化规则，并为每条规则保存 before/after fixture。

对 React/TypeScript 语法保真迁移使用 [jscodeshift](https://jscodeshift.com/)，让 transform、fixture、类型检查和构建成为同一个变更单元。

对 Python 需要保留 comments 和 whitespace 的复杂迁移，再评估 [LibCST](https://libcst.readthedocs.io/)；它的仓库许可是多来源组合，复制或 vendoring 前必须逐文件审查。

只有在引入 Java 子系统时才把 [OpenRewrite](https://docs.openrewrite.org/) 提升到核心工具，并固定 recipe、版本和编译验证。

不要让 AI 自己生成任意 shell、Python 或 Java 来完成批量重构；让 AI 生成候选规则和 patch 计划，再由确定性工具和测试执行。

### 组合 D：把质量门设置为“只阻止新增问题”

用 [Semgrep](https://semgrep.dev/docs/) 编码高价值规则，例如旧 provider API、跨层 import、未经审批的 subprocess、任意文件路径、secret 进入日志和工具注册缺少 schema。

用 [CodeQL](https://codeql.github.com/docs/) 专门查询跨函数和跨文件的高风险路径，而不是重复做简单 lint。

用 [reviewdog](https://github.com/reviewdog/reviewdog) 把 Ruff、ESLint、Semgrep 和其他 analyzer 的输出按 diff 过滤到 PR review。

用 [SonarQube](https://docs.sonarsource.com/sonarqube/) 只有在需要统一质量仪表板、长期趋势和组织级 Quality Gate 时才值得承担运营成本。

历史问题先记录为 baseline 或 waiver，新改动不得新增同类问题。

### 组合 E：用运行时证据确认静态候选

给模型请求、工具调用、Deep Research、Discovery launch、实验 runner、HTTP API、队列和 artifact 访问补齐 [OpenTelemetry](https://opentelemetry.io/docs/collector/) 的低基数 span 和 metric。

不要把 prompt、API key、完整文件内容或高基数 session 数据无差别写入 trace。

当静态分析认为某模块“可能没用”时，至少经过一个覆盖真实入口的观察窗口，再与测试、配置和 Git history 交叉核对。

将模块 owner、边界、质量门和运行时组件逐步登记到 [Backstage Software Catalog](https://backstage.io/docs/features/software-catalog/)，但把 catalog 看成声明，不是事实源。

## 推荐的六阶段落地顺序

### 阶段 0：冻结分析边界

定义 `source`、`vendored`、`generated`、`runtime-data`、`fixture` 和 `archive` 六种类别。

把 `third_party`、`desktop/openworker/upstream`、`results`、缓存和临时目录默认排除出删除候选，但仍允许只读搜索和许可证审计。

建立一次全仓库 baseline，保存工具版本、配置、commit SHA、输出 artifact 和运行时间。

### 阶段 1：建立图和入口目录

使用 codebase-memory-mcp、tree-sitter、dependency-cruiser 和必要的全文索引，建立“文件 - 符号 - import - route - CLI - 配置 - artifact”的可追踪关系。

把动态入口和外部约定列成显式 registry。

为每个顶级模块指定 owner 和允许依赖方向。

### 阶段 2：生成删除候选

运行 Vulture、Knip、Ruff、ESLint、依赖扫描和 scc 差异报告。

把候选分为“确定死代码”“高置信度但需人工确认”“只可观察不可删除”三类。

先删除未使用依赖、无引用导出和重复配置，再处理业务函数和任务目录。

### 阶段 3：锁定边界规则

将已经确认的边界写成 Import Linter、dependency-cruiser、ESLint、Semgrep、测试或 CI rule。

规则只阻止新违规，旧违规用 baseline 和 owner 管理。

每条规则都需要一个正例、一个反例和一个明确的豁免机制。

### 阶段 4：执行可回滚迁移

用 ast-grep、jscodeshift、Ruff autofix 或 OpenRewrite recipe 做机械迁移。

每个 patch 只改变一个模式或一个模块，包含 fixture、类型检查、构建、E2E/smoke 和回滚说明。

严禁让一个大模型会话同时进行发现、架构决策、删除和合并。

### 阶段 5：运行时确认和持续治理

使用 OpenTelemetry 观察真实入口和模块调用，使用 Renovate/Dependabot/OSV-Scanner 控制依赖老化和安全风险。

用 reviewdog 把治理变成增量反馈，并按季度重建 baseline 和 dead-code candidate。

只有在稳定子树已经有清晰依赖图和可复现构建后，才评估 Nx、Bazel 或更重的构建图迁移。

## 不建议直接采用的误区

不要把一个 star 很高的 AI coding agent 当成架构治理器。

AI agent 可以执行已经定义好的 issue，但不能替代 owner、依赖图、运行时证据和删除批准。

不要一次性启用所有 lint、complexity、security 和 architecture rule。

brownfield 仓库首先需要 diff-only 和 baseline 模式，否则质量门会阻断所有工作并促使团队关闭工具。

不要因为静态图没有引用就删除动态注册、配置驱动、插件发现、CLI 入口、实验任务和 vendored adapter。

不要为了获得一个漂亮的 project graph 就立即迁移到 Bazel 或大型 monorepo 平台。

构建系统迁移应该由可量化的增量构建、可复现性或跨语言边界收益驱动，而不是由“代码很多”单独驱动。

不要把 OpenGrok、Zoekt 或全文搜索结果当成语义依赖证明。

不要把 Continue 当前仓库作为本报告的优先推荐，因为官方 README 已把它标记为不再积极维护或只读状态；高 star 不足以抵消维护信号。

## 最终建议排序

如果只能先做三件事，先做 `scc 基线 + dependency-cruiser/现有图谱 + Vulture/Knip 候选清单`。

如果只能再加两件事，加 `ast-grep 确定性迁移 + Semgrep/reviewdog 增量门禁`。

如果删除误报成本很高，再加 OpenTelemetry 运行时证据和 Backstage owner 目录。

如果未来出现稳定的 Java 子系统，再引入 OpenRewrite 和 ArchUnit。

如果未来出现跨语言、超大规模、可复现构建瓶颈，再评估 Nx 或 Bazel，而不是现在就迁移。

如果要使用 AI，优先把 Aider/OpenHands/Cline 放在隔离 worktree 中执行“一个 issue、一个规则、一个 patch、一次验证”，不要给它们整个 brownfield 仓库的无审批写权限。

## 一手来源索引

- [scc 官方仓库](https://github.com/boyter/scc)；[scc commits.atom](https://github.com/boyter/scc/commits/master.atom)。
- [tree-sitter 官方仓库](https://github.com/tree-sitter/tree-sitter)；[官方文档](https://tree-sitter.github.io/tree-sitter/)；[commits.atom](https://github.com/tree-sitter/tree-sitter/commits/master.atom)。
- [ast-grep 官方仓库](https://github.com/ast-grep/ast-grep)；[官方文档](https://ast-grep.github.io/)；[commits.atom](https://github.com/ast-grep/ast-grep/commits/main.atom)。
- [Ruff 官方仓库](https://github.com/astral-sh/ruff)；[官方文档](https://docs.astral.sh/ruff/)；[commits.atom](https://github.com/astral-sh/ruff/commits/main.atom)。
- [Knip 官方仓库](https://github.com/webpro-nl/knip)；[官方文档](https://knip.dev/)；[commits.atom](https://github.com/webpro-nl/knip/commits/main.atom)。
- [Vulture 官方仓库](https://github.com/jendrikseipp/vulture)；[README](https://github.com/jendrikseipp/vulture#readme)；[commits.atom](https://github.com/jendrikseipp/vulture/commits/main.atom)。
- [dependency-cruiser 官方仓库](https://github.com/sverweij/dependency-cruiser)；[官方文档目录](https://github.com/sverweij/dependency-cruiser/tree/main/doc)；[commits.atom](https://github.com/sverweij/dependency-cruiser/commits/main.atom)。
- [deptry 官方仓库](https://github.com/fpgmaas/deptry)；[官方文档](https://deptry.com/)；[commits.atom](https://github.com/fpgmaas/deptry/commits/main.atom)。
- [Nx 官方仓库](https://github.com/nrwl/nx)；[官方文档](https://nx.dev/docs)；[commits.atom](https://github.com/nrwl/nx/commits/master.atom)。
- [Semgrep 官方仓库](https://github.com/semgrep/semgrep)；[官方文档](https://semgrep.dev/docs/)；[commits.atom](https://github.com/semgrep/semgrep/commits/develop.atom)。
- [reviewdog 官方仓库](https://github.com/reviewdog/reviewdog)；[commits.atom](https://github.com/reviewdog/reviewdog/commits/master.atom)。
- [CodeQL 官方仓库](https://github.com/github/codeql)；[官方文档](https://codeql.github.com/docs/)；[commits.atom](https://github.com/github/codeql/commits/main.atom)。
- [SonarQube 官方仓库](https://github.com/SonarSource/sonarqube)；[官方文档](https://docs.sonarsource.com/sonarqube/)；[commits.atom](https://github.com/SonarSource/sonarqube/commits/master.atom)。
- [OpenRewrite 官方仓库](https://github.com/openrewrite/rewrite)；[官方文档](https://docs.openrewrite.org/)；[commits.atom](https://github.com/openrewrite/rewrite/commits/main.atom)。
- [jscodeshift 官方仓库](https://github.com/facebook/jscodeshift)；[官方文档](https://jscodeshift.com/)；[commits.atom](https://github.com/facebook/jscodeshift/commits/main.atom)。
- [ESLint 官方仓库](https://github.com/eslint/eslint)；[官方文档](https://eslint.org/docs/latest/)；[commits.atom](https://github.com/eslint/eslint/commits/main.atom)。
- [typescript-eslint 官方仓库](https://github.com/typescript-eslint/typescript-eslint)；[官方文档](https://typescript-eslint.io/)；[commits.atom](https://github.com/typescript-eslint/typescript-eslint/commits/main.atom)。
- [Import Linter 官方仓库](https://github.com/seddonym/import-linter)；[官方文档](https://import-linter.readthedocs.io/)；[commits.atom](https://github.com/seddonym/import-linter/commits/main.atom)。
- [Pyright 官方仓库](https://github.com/microsoft/pyright)；[MIT 许可证](https://github.com/microsoft/pyright/blob/main/LICENSE.txt)；[官方文档](https://microsoft.github.io/pyright/)；[commits.atom](https://github.com/microsoft/pyright/commits/main.atom)。
- [mypy 官方仓库](https://github.com/python/mypy)；[MIT 许可证](https://github.com/python/mypy/blob/master/LICENSE)；[官方文档](https://mypy.readthedocs.io/)；[commits.atom](https://github.com/python/mypy/commits/master.atom)。
- [ArchUnit 官方仓库](https://github.com/TNG/ArchUnit)；[官方文档](https://www.archunit.org/)；[commits.atom](https://github.com/TNG/ArchUnit/commits/main.atom)。
- [Bazel 官方仓库](https://github.com/bazelbuild/bazel)；[官方文档](https://bazel.build/)；[commits.atom](https://github.com/bazelbuild/bazel/commits/master.atom)。
- [Renovate 官方仓库](https://github.com/renovatebot/renovate)；[官方文档](https://docs.renovatebot.com/)；[commits.atom](https://github.com/renovatebot/renovate/commits/main.atom)。
- [Dependabot Core 官方仓库](https://github.com/dependabot/dependabot-core)；[commits.atom](https://github.com/dependabot/dependabot-core/commits/main.atom)。
- [OSV-Scanner 官方仓库](https://github.com/google/osv-scanner)；[官方文档](https://google.github.io/osv-scanner/)；[commits.atom](https://github.com/google/osv-scanner/commits/main.atom)。
- [OpenGrok 官方仓库](https://github.com/oracle/opengrok)；[CDDL-1.0 许可证文件](https://github.com/oracle/opengrok/blob/master/LICENSE.txt)；[commits.atom](https://github.com/oracle/opengrok/commits/master.atom)。
- [Zoekt 官方仓库](https://github.com/sourcegraph/zoekt)；[commits.atom](https://github.com/sourcegraph/zoekt/commits/main.atom)。
- [OpenTelemetry Collector 官方仓库](https://github.com/open-telemetry/opentelemetry-collector)；[Collector 文档](https://opentelemetry.io/docs/collector/)；[commits.atom](https://github.com/open-telemetry/opentelemetry-collector/commits/main.atom)。
- [Backstage 官方仓库](https://github.com/backstage/backstage)；[Software Catalog 文档](https://backstage.io/docs/features/software-catalog/)；[commits.atom](https://github.com/backstage/backstage/commits/master.atom)。
- [Joern 官方仓库](https://github.com/joernio/joern)；[官方文档](https://docs.joern.io/)；[commits.atom](https://github.com/joernio/joern/commits/master.atom)。
- [Aider 官方仓库](https://github.com/Aider-AI/aider)；[官方文档](https://aider.chat/docs/)；[commits.atom](https://github.com/Aider-AI/aider/commits/main.atom)。
- [OpenHands 官方仓库](https://github.com/All-Hands-AI/OpenHands)；[官方文档](https://docs.openhands.dev/)；[commits.atom](https://github.com/All-Hands-AI/OpenHands/commits/main.atom)。
- [Superpowers 官方仓库](https://github.com/obra/superpowers)；[commits.atom](https://github.com/obra/superpowers/commits/main.atom)。
- [GitHub Awesome Copilot 官方仓库](https://github.com/github/awesome-copilot)；[commits.atom](https://github.com/github/awesome-copilot/commits/main.atom)。
- [InternAgent 当前架构](../../architecture.md)。
