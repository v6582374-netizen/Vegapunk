# InternAgent 阶段性清理与架构提升报告

报告日期：2026-08-01。

对应方案：[BROWNFIELD_CLEANUP_PLAN.md](./BROWNFIELD_CLEANUP_PLAN.md)。

## 先看结论

本轮已经完成一次全量的只读审计、代码图刷新、静态扫描、架构候选整理、运行时核对和测试构建核对。

本轮没有删除任何源代码、数据、测试夹具、上游代码或用户已有产物。

本轮只新增了方案文档和本报告，并在本机全局安装了缺少的分析工具。

报告中的“候选”表示“值得确认”，不表示“已经确定可以删除”。

最适合优先确认的是可重新生成的构建产物和测试产物。

最不适合按工具结果直接删除的是研究任务数据、实验快照、上游代码、动态加载模块和模型提供商实现。

架构方面最值得先做的是拆分超大装配函数、明确 Discovery 的队列和运行边界、收敛前端的未解析别名，以及处理已经确认的一个前端循环依赖。

## 用通俗话解释本报告的词

### 什么是死代码

死代码是当前产品运行、命令行入口、测试、配置或任务流程都不再需要的一段代码。

“工具没有找到引用”只能说明静态搜索没有看到引用。

它仍然可能被配置文件、动态导入、插件注册、任务目录约定、子进程、反射或用户手工命令调用。

所以本报告把死代码工具的输出叫做“候选”，没有把它写成“确定删除”。

### 什么是复杂度

复杂度可以理解为一个文件或函数里需要同时记住的分支、状态和特殊情况数量。

复杂度高不等于代码一定错误。

复杂度高通常意味着改动更容易影响别的行为，测试和后续维护成本也更高。

本报告中的复杂度数字主要来自静态工具，适合用来找重构优先级，不适合单独用来删除文件。

### 什么是循环依赖

循环依赖是 A 依赖 B，同时 B 又依赖 A，或者经过多个文件绕一圈回到 A。

这种关系会让初始化顺序、测试替换和模块边界变得更难理解。

它通常应该通过拆出共享接口或移动职责来解决，而不是直接删除其中一个文件。

### 什么是 unresolved import

unresolved import 是分析工具无法把一条导入语句对应到实际文件或包。

它可能是真 bug，也可能只是工具不知道项目的别名配置、生成目录、运行时路径或包管理方式。

本仓库前端的 92 条 unresolved import 主要集中在没有提供 `@skills-manager/*` 别名配置的分析场景，因此不能直接当成 92 个坏文件。

### 为什么工具结果不能直接等于删除许可

本仓库同时包含产品源码、研究代码、实验任务、复制的上游项目、测试夹具、运行结果和动态运行时。

这些内容的入口不一定都能由同一个静态调用图识别。

删除前至少需要同时核对调用关系、配置入口、动态加载、测试、运行时观察和 Git 历史。

方案中规定候选至少满足五项证据中的四项，才可以进入“建议删除”阶段。

## 本轮边界和现状

本轮分析的根目录是 `/Users/shiwen/Downloads/AI-Scientist-Project/InternAgent`。

本轮没有重置、覆盖、提交或推送工作区。

报告生成前工作区检测到 64 条已修改或未跟踪项，其中包含用户已有开发改动、本轮方案文档、测试产物和工具目录。

由于这些改动的所有权不能只靠文件名安全判断，本轮没有清理它们。

以下类别被分开判断：第一方源码、上游或 vendored 代码、生成物、运行时数据、测试夹具和历史归档。

`desktop/openworker/upstream`、`third_party`、`.scratch`、`tasks/*/run_0` 和 `sci_tasks/tasks` 默认没有进入源码删除候选。

## 代码图和规模基线

本轮重新建立了独立分析图，项目名为 `InternAgentCleanup20260801`。

代码图记录了约 52,035 个节点、202,266 条边和 4,431 个文件。

图中仍包含上游代码、scratch、任务快照和实验内容，因此图中没有调用者的节点不等于可以删除。

主要语言文件数量如下：Python 1,612 个，TypeScript 497 个，YAML 282 个，Rust 151 个。

在排除大型构建缓存、图数据库、测试输出和工作树后，scc 统计到 3,473 个文件、857,667 行总文本、722,677 行代码和 44,297 的静态复杂度值。

scc 统计到 Python 1,606 个文件和 278,114 行代码，TypeScript 496 个文件和 101,446 行代码，Rust 151 个文件和 56,112 行代码。

scc 还报告了 0.31% 的 DRYness 指标。

这个 DRYness 数字受研究代码、任务快照和不同语言混合影响，只能作为后续同口径复测的基线，不能直接当成重构目标。

当前分支是 `prototype/native-desktop-discovery-preparation`。

本轮记录的 HEAD 是 `9a0df4b86a671e8c857f0d7c601b617397df7c1b`。

## 已执行的工具和工具安装

本机原本缺少部分架构和死代码分析工具，因此按用户补充的授权进行了全局安装。

本轮实际使用或准备使用的版本如下：

| 工具 | 版本 | 用途 |
| --- | --- | --- |
| `scc` | 3.7.0 | 规模、代码行数、复杂度和重复度基线 |
| `ast-grep` | 0.45.0 | 结构化搜索动态入口和机械迁移候选 |
| `ruff` | 0.16.0 | Python 未使用导入和局部变量检查 |
| `semgrep` | 1.171.0 | 安全、危险 API 和边界模式扫描 |
| `vulture` | 2.16 | Python 死代码候选 |
| `deptry` | 0.25.1 | Python 依赖声明和实际使用差异 |
| `pyright` | 1.1.411 | Python 类型风险扫描 |
| `knip` | 6.31.0 | TypeScript 和 JavaScript 未使用文件、导出和依赖 |
| `dependency-cruiser` | 18.1.0 | 前端依赖关系、循环依赖和未解析导入 |
| `eslint` | 10.8.0 | 前端增量质量门准备 |
| `typescript` | 5.5.3 | 配合 dependency-cruiser 使用 |
| `reviewdog` | `master` | 只反馈本次改动新增的问题 |

全局 TypeScript 曾为 7.0.2，本轮为兼容 dependency-cruiser 调整为 5.5.3。

Semgrep 安装时 Homebrew 出现 certifi link warning，但 Semgrep 本身已经成功安装并执行。

本轮没有修改项目的依赖清单来“迎合”这些工具。

## 静态扫描结果

### Vulture

扫描范围是 `vegapunk`、`admin_console`、`launch.py`、`launch_discovery.py`、`launch_paper.py`、`launch_qa.py`、`scripts` 和 `tests`。

Vulture 找到 43 条高置信度候选。

主要是未使用的局部变量和未使用导入，不是大批可以直接删除的模块。

代表性位置如下：

| 路径 | 工具看到的内容 | 当前判断 |
| --- | --- | --- |
| `vegapunk/experiments_utils_claude.py:655` | `final_iter` 局部变量未使用 | 先做 lint 核对 |
| `vegapunk/mas/agents/dr_agents/tools/info_processing_tools.py:35` | `retry_times` 未使用 | 先确认是否保留接口参数 |
| `vegapunk/mas/agents/dr_agents/tools/tool_integration.py:644` | `need_summary` 未使用 | 先确认工具协议字段 |
| `vegapunk/mas/agents/dr_agents/workflow/task.py:321` | `summary_type` 未使用 | 先确认任务序列化兼容性 |
| `vegapunk/mas/memory/retriever.py:204` | `return_scores` 未使用 | 先确认调用方是否通过关键字传参 |
| `vegapunk/mas/tools/utils.py:160` | `include_abstract`、`include_score` 未使用 | 先确认外部工具调用契约 |

这些候选适合在用户确认后按小批次做 lint 清理，并补跑相关测试。

### Ruff

针对 `F401` 和 `F841` 扫描得到 140 条问题。

其中 126 条被工具认为可以做安全自动修复，13 条需要 unsafe fix，其余问题需要人工判断或不适合机械修复。

高信号位置包括 `admin_console/queue.py`、`vegapunk/mas/agents/codeview_agent.py`、`vegapunk/mas/agents/generation_agent.py`、`vegapunk/mas/memory`、`vegapunk/mas/models/unified_runtime.py`、`vegapunk/mas/workflow/orchestration_agent.py`、`vegapunk/prompt_library.py`、`vegapunk/stage.py` 和 `vegapunk/vis.py`。

本轮没有运行自动修复，因为这些目录存在动态导入、工具注册和实验兼容性风险。

### deptry

deptry 报告了 13,480 个依赖问题。

这个数字当前不可直接用于删依赖。

根目录没有统一的 `pyproject.toml`，根 `requirements.txt` 是跨任务聚合依赖表，CAMEL 内部包和各个研究任务也没有清晰的独立运行边界。

下一步应先按运行单元建立依赖清单，再处理每个单元内部的未使用依赖。

### Knip

Knip 在 active GUI `desktop/openworker/upstream/surfaces/gui` 上报告 80 个未使用文件候选、1 组未使用依赖、1 个 unresolved import、27 个未使用导出和 16 个未使用导出类型。

大量结果来自 `skills-manager-upstream` 和入口配置缺失。

这些结果暂时只能作为入口和配置补全清单，不能直接删除文件。

### dependency-cruiser

dependency-cruiser 分析了 246 个前端 source modules 和 453 条依赖边。

它报告了 92 条 unresolved imports、1 个 dynamic import 和 2 条循环依赖边。

92 条 unresolved imports 主要由 `@skills-manager/*` 别名没有被分析配置识别造成。

已确认的循环依赖涉及 `src/components/ApprovalCard.tsx` 和 `src/humanize.ts`。

这个循环依赖是架构重构候选，不是删除许可。

### ast-grep

ast-grep 发现 Python 子进程调用分布在 queue、PaperOrchestra、实验 runner 和 CAMEL toolkit 等目录。

它发现的 Python 动态 import 位于 `vegapunk/mas/agents/dr_agents/camel/utils/commons.py`、`internal_python_interpreter.py` 和 `runtime/api.py`。

它还发现 `vegapunk/mas/agents/dr_agents/runtime_camel_backend.py` 使用了 `__import__`。

前端动态 import 位于 `src/components/RightRail.tsx`、`src/tauri.ts` 和 `src/skills-manager/components/editor/raycastMonacoTheme.ts`。

这些入口说明“没有静态引用”不能作为本仓库的单一删除依据。

### Semgrep

Semgrep 找到 14 条 finding，并有 23 条规则执行错误。

主要 finding 包括多处 MD5、多处明文 HTTP、`terminal_toolkit.py:163` 的 `shell=True`、`oceanbase.py` 的 `sqlalchemy.text`、`vegapunk/mas/models/openai_model.py:119` 可能记录敏感凭据提示，以及 `vegapunk/stage.py:773` 的过宽文件权限。

这些是安全审计候选，不应混入死代码删除批次。

### Pyright

Pyright 分析了 506 个文件，报告 1,322 个 errors 和 72 个 warnings。

主要噪声来自没有项目级 Pyright 配置、运行环境无法解析部分依赖，以及 CAMEL 目录的类型边界不完整。

`admin_console/parameters.py` 和 `admin_console/queue.py` 仍有值得单独复现的真实类型风险候选。

本轮没有为了清零历史类型债务而大规模改写代码。

## 架构候选

以下内容更适合重构，而不是删除。

| 路径或模块 | 当前观察 | 建议方向 | 置信度 |
| --- | --- | --- | --- |
| `admin_console/app.py::create_app` | 函数体约 915 行，约 15 个参数，同时注册大量路由并装配多个运行时对象 | 拆出路由注册和运行时装配 seam，先保持外部入口不变 | 高 |
| `launch_discovery.py::_main` | 函数体约 567 行，同时处理 resume、任务归一化、配置、Memory、IdeaGenerator、ExperimentRunner、ReportWriter 和 PaperOrchestra handoff | 明确 CLI、queue 和 Discovery Launch 的所有权 | 高 |
| `vegapunk/mas/workflow/orchestration_agent.py` | 文件约 1,164 行，复杂度约 167，多阶段状态机和业务执行集中 | 按状态机、执行器和结果适配器拆分 | 高 |
| `vegapunk/mas/agents/generation_agent.py` | 文件约 983 行，同时负责 prompt、memory、tool loop、LLM 调用和失败 idea 过滤 | 拆出生成策略、工具循环和失败过滤边界 | 高 |
| `vegapunk/prompt_library.py` | 文件约 511 行，同时负责 catalog、读取、渲染、保存、中文镜像和同步 | 拆出存储、渲染和同步接口 | 中高 |
| `vegapunk/mas/agents/dr_agents/models`、`vegapunk/mas/models`、CAMEL provider、UnifiedModelRuntime、PaperOrchestra ResponsesRuntime | 模型入口存在重复和多套适配层 | 先画运行时拥有关系，再收敛 adapter，不先删 provider 文件 | 中 |
| Memory 体系 | `TaskMemoryLayer`、`MemoryManager`、`MemoryModule`、`IdeaGraph`、`ExperienceGenerator` 和 `OnlineMemorySaver` 职责有重叠 | 先建立术语和数据流，再决定合并或拆分 | 中 |
| `src/components/ApprovalCard.tsx` 与 `src/humanize.ts` | 已确认前端循环依赖 | 抽出纯格式化接口或移动共享类型 | 中高 |

这些候选需要先写行为回归测试和边界规则，再做小步迁移。

## 运行时核对

当前发现的监听端口如下：

| 地址 | 进程 | 结果 | 解释 |
| --- | --- | --- | --- |
| `[::1]:1420` | Vite，PID 35489 | `/` 返回 HTTP 200 | 当前开发前端可访问 |
| `[::1]:1420` | Vite，PID 35489 | `/health` 返回 HTTP 200 和同一份 HTML | 这是 Vite fallback，不是独立后端健康接口 |
| `[::1]:5199` | E2E Vite，PID 47111 | `/` 返回 HTTP 200 | E2E 前端服务可访问 |
| `[::1]:5199` | E2E Vite，PID 47111 | `/health` 返回 HTTP 200 和同一份 HTML | 这是 Vite fallback，不是独立后端健康接口 |
| `127.0.0.1:1420` | 无 IPv4 监听 | 连接失败 | 服务只绑定在 IPv6 loopback |
| `8000`、`8765`、`5173` | 无监听 | 未发现服务 | 本轮没有启动它们 |

本轮没有终止现有进程，也没有启动用户没有要求启动的后端服务。

## 生成物和数据候选

下面的内容看起来像可以回收的产物，但仍需要用户确认用途。

| 路径 | 当前大小 | 它看起来是什么 | 证据和风险 | 建议动作 |
| --- | ---: | --- | --- | --- |
| `desktop/openworker/upstream/surfaces/gui/src-tauri/target/` | 约 9.8G | Rust/Tauri 构建缓存和产物 | 通常可以重新生成，但删除会让下一次构建重新编译 | 优先确认是否正在用于本地开发，确认后可清理 |
| `desktop/openworker/upstream/surfaces/gui/node_modules/` | 约 443M | 前端安装依赖 | 可由包管理器重新安装，但删除会影响当前本地开发速度 | 确认是否需要保留本地依赖 |
| `desktop/openworker/upstream/surfaces/gui/dist/` | 约 3.6M | 前端构建输出 | 可能是部署或验收用产物 | 先确认是否有发布或验收用途 |
| `output/` | 约 41M | Playwright 截图和测试输出 | 可能用于回归比对或问题证据 | 先归档，再决定清理 |
| `results/` | 约 9.9M | 研究运行结果 | 可能是研究结论或复现实验输入 | 不按体积删除，逐项确认 |
| `logs/` | 约 1.7M | 本地运行日志 | 日志可轮换，但可能包含问题证据 | 先保留最近一轮，确认后归档旧日志 |
| `.playwright-cli/` | 约 8.3M | 浏览器自动化工具状态和产物 | 可能包含复现所需会话信息 | 确认没有未完成的自动化会话后再清理 |
| `.claude/worktrees/` | 约 133M | Claude 或协作任务工作树 | 可能仍有未合并工作 | 必须逐个确认工作树后再处理 |
| `.code-review-graph/graph.db` | 约 336M | 代码审查或代码图数据库 | 可以重建，但当前审计仍可能需要它 | 报告确认后再决定保留或删除 |
| `sci_tasks/tasks/` | 约 1.4G | 外部研究任务数据 | 不是普通构建缓存，可能是任务输入或结果 | 明确任务所有权和备份后再处理 |

`tasks/*/run_0` 下的大量实验快照和基线文件也没有进入自动删除范围。

它们的体积和目录名字不能证明它们是死数据。

## 代码清理候选的分组

### 可以优先确认的低风险候选

构建缓存、明确可重建的依赖目录、过期的 Playwright 输出和已经确认没有用途的旧日志属于这一组。

这一组仍然需要确认是否有未发布构建、验收截图、复现证据或当前会话依赖。

### 需要人工核对的历史或实验产物

`results`、`sci_tasks/tasks`、`tasks/*/run_0`、`.scratch` 和 `.claude/worktrees` 属于这一组。

确认重点是“谁还在用、是否需要复现、是否有备份、是否能从外部来源恢复”。

### 可能的代码 lint 清理

Vulture 的 43 条候选和 Ruff 的 F401/F841 候选可以作为第一批小补丁。

每批只处理一个模块或一种 lint 模式，并在修改前后运行相关单测、smoke 或 E2E。

工具注册参数、动态导入参数和兼容旧任务的字段不能只按“变量没有被本文件读取”删除。

### 架构重构候选

`create_app`、`_main`、`orchestration_agent.py`、`generation_agent.py` 和 `prompt_library.py` 应进入重构计划，而不是进入删除清单。

前端 `ApprovalCard.tsx` 与 `humanize.ts` 的循环依赖适合先建立边界测试，再抽出共享接口。

### 明确暂不删除

上游 OpenWorker 代码、`third_party` 代码、CAMEL provider 和模型适配器、动态加载模块、研究任务输入、实验快照、测试夹具和没有明确所有权的工作树暂不删除。

没有充分运行时证据的“无引用”节点也暂不删除。

## 测试、构建和质量门结果

根目录 `pytest -q` 通过，结果为 214 passed、6 warnings 和 45 个 subtests passed。

OpenWorker upstream tests 通过，结果为 946 passed 和 1 skipped。

GUI production build 通过，共转换 2,181 个模块。

GUI Vitest 通过，结果为 15 个文件和 78 个测试通过。

Skills Manager tests 通过，结果为 251 个测试通过。

GUI Playwright E2E 通过，结果为 157 个测试通过。

GUI 仍有 `api.ts` 同时 dynamic import 和 static import 的警告，以及多个超过 500KB 的 bundle chunk。

Skills Manager provenance 校验提示 stale，建议命令是 `npm run skills-manager:verify -- --write`。

本轮没有执行这个 `--write` 命令，也没有修改该生成物，因为它会改变用户工作区并且不是本轮清理必需动作。

## 建议的确认顺序

1. 先确认 `src-tauri/target`、`node_modules`、`dist`、旧测试输出和旧日志是否可以重新生成或归档。
2. 再逐个确认 `.claude/worktrees`、`results`、`sci_tasks/tasks` 和 `tasks/*/run_0` 的所有权与备份状态。
3. 用户确认后，再单独建立一个只包含已确认产物的清理补丁，不混入源码重构。
4. 对 Vulture 和 Ruff 候选先做最小 lint 清理，并逐批运行对应测试。
5. 对循环依赖和大函数建立重构计划，先加边界测试，再拆分接口。
6. 最后重新生成代码图、规模基线和运行时核对，比较变化而不是只看删除了多少文件。

## 需要用户确认的问题

请确认以下内容是否可以进入下一轮删除或归档清单：

1. `desktop/openworker/upstream/surfaces/gui/src-tauri/target/` 是否可以清理并在需要时重新构建。
2. `desktop/openworker/upstream/surfaces/gui/node_modules/` 是否只作为本机缓存保留。
3. `desktop/openworker/upstream/surfaces/gui/dist/` 是否还有发布、验收或分享用途。
4. `output/`、`logs/` 和 `.playwright-cli/` 是否需要保留最近一轮证据。
5. `.claude/worktrees/` 中是否还有需要保留或合并的工作树。
6. `results/`、`sci_tasks/tasks/` 和 `tasks/*/run_0` 是否有研究复现或历史归档要求。
7. 是否授权下一轮只处理已经确认的生成物，不触碰任何源代码、实验数据和上游代码。

在得到确认前，本报告中的候选都保持原状。
