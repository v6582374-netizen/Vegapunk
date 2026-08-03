# 将 CFD 工具集成到 AI 系统的调用架构调研

调研日期：2026-07-28。

调研范围：Ansys Fluent/PyFluent、COMSOL 官方 ChatGPT 建模流程及 API、OpenFOAM 官方命令行接口，并结合当前 InternAgent 的工具层、模型层和 Launch 产物边界给出集成建议。

## 结论先行

CFD 不应该首先被包装成一个“让模型生成任意脚本并直接执行”的工具。

更稳妥的抽象是：模型只生成一个经过单位、维度、枚举值和资源约束校验的 `SimulationPlan`，系统再把它编译成 Fluent/PyFluent、COMSOL Java API 或 OpenFOAM case 的受控执行计划。

推荐的主链路是：`自然语言 -> typed plan -> validate/diff/estimate -> approve -> asynchronous job -> progress/events -> structured results + artifacts`。

在三种工具中，PyFluent 最适合先做第一条 AI 工具链，因为它提供了 Python 对象模型、Fluent gRPC session、settings 元数据、事件和监视器、批量 RPC、文件传输以及 journal 记录。

COMSOL 官方文章证明了“LLM 生成 API 代码，然后人工检查，再在 Java Shell 或 Method Editor 中运行”的可行性，但也明确展示了 API 枚举错误、需要反馈错误信息以及缺乏空间感知等限制。

OpenFOAM 更接近受控的 case-file 和 CLI 作业执行器，不适合把任意 shell 命令暴露给模型。

对当前 InternAgent 的适配是一个架构推断：CFD 应放在工具层和实验/作业后端，不应扩展 `UnifiedModelRuntime` 的模型 capability；应复用已有 `ModelToolLoop`、工具注册、参数校验、事件记录和 launch-local artifact 机制。

## 资料核验边界

本报告优先使用厂商官方文档、官方 API reference、官方 Javadoc、官方 GitHub/文档站点和官方学习中心页面。

用户提供的 [Ansys Fluent Developer Portal](https://developer.ansys.com/docs/fluent) 在本次环境中返回 Cloudflare HTTP 403，因此无法读取其页面正文。

Ansys 相关事实主要由可访问的 [PyFluent 官方文档首页](https://fluent.docs.pyansys.com/version/stable/)、[用户指南](https://fluent.docs.pyansys.com/version/stable/user_guide/user_guide_contents.html) 和 [API reference](https://fluent.docs.pyansys.com/version/stable/api/api_contents.html) 核验。

PyFluent 首页在本次核验时显示文档版本 0.40.2，API reference 说明对应 Ansys Fluent 2026 R1，并声明对较旧 Ansys 版本保持较强向后兼容性。

版本号会随官方站点更新，因此产品实现仍应在运行时记录 Fluent、PyFluent 和 adapter 版本。

## CFD 对 AI 来说难在哪里

CFD 调用不是一个单次函数调用，而是一个带状态、资源、长时间运行和大文件结果的工作流。

典型流程至少包含几何导入、网格生成、物理模型、材料、边界条件、求解器、初始化、迭代或瞬态推进、收敛判断、后处理和结果导出。

这些步骤之间存在动态依赖，例如网格区域名称会影响边界条件，物理模型会改变可用设置，求解器状态会改变可用命令和结果字段。

因此，模型需要的是“可发现、可验证、可观测的状态机”，而不是一串没有约束的代码文本。

## 一手资料中的 Fluent/PyFluent 能力

### 安装、授权与版本

[PyFluent 安装文档](https://fluent.docs.pyansys.com/version/stable/getting_started/installation.html)说明 PyFluent 支持 Python 3.10 至 3.14，并可通过 `pip install ansys-fluent-core` 安装。

同一文档要求受益于完整能力时必须有已授权的 Ansys Fluent 安装，并使用例如 `AWP_ROOT252` 的环境变量定位 Fluent。

当前 PyFluent 版本不再支持 2024 R2 之前的 Fluent 版本，这是官方安装文档对当前发布线的说明。

这意味着 CFD adapter 不能把“安装 Python 包”当作部署完成，还必须检查 Fluent 可执行文件、许可证、版本、并行能力和运行节点。

### Session 与启动方式

[Launching and connecting to Fluent](https://fluent.docs.pyansys.com/version/stable/user_guide/session/launching_ansys_fluent.html)说明 `launch_fluent()` 可以在后台启动 Fluent 并启动 Fluent gRPC server。

已有 Fluent session 可以通过 `connect_to_fluent()`，或使用 server-info 文件中的 IP、端口和密码连接。

官方文档还提供本地安装、Docker/Podman container、PIM、Windows/Linux/WSL 跨主机连接以及 Slurm、UGE、SGE、LSF、PBS 等调度环境的用法。

启动参数包括 solution、meshing、pure meshing 和 pre/post 模式，以及精度、二维或三维、处理器数量和分布式并行参数。

PyFluent [FluentConnection API](https://fluent.docs.pyansys.com/version/stable/api/fluent_connection.html)支持 health check、cleanup-on-exit、远程主机许可、TLS 证书目录和连接生命周期管理。

该 API 将 `insecure_mode=True`描述为不推荐的无 TLS 连接方式，因此生产部署不应把默认安全边界降级为裸 gRPC。

### Settings API 是最适合做 typed tool 的部分

[Using PyFluent sessions](https://fluent.docs.pyansys.com/version/stable/user_guide/session/session.html)说明 session 暴露 `settings`、`fields`、`events`、`tui` 和 workflow 等子对象。

[Solver settings objects](https://fluent.docs.pyansys.com/version/stable/user_guide/solver_settings/solver_settings_contents.html)说明 settings 是一个层次化对象树，包含 Group、NamedObject 和 ListObject。

对象可以通过调用读取 state，也可以通过赋值、`get_state()` 和 `set_state()` 修改 state。

许多设置项提供 `allowed_values()`、`min()`、`max()`、`is_active()` 和 `is_read_only()` 等元数据，因此服务端可以在执行前校验枚举、范围、动态激活状态和只读状态。

settings 对象还有 stable、beta、alpha 三种 exposure level，默认只暴露 stable 项，并且 exposure 设置只在当前 session 生效。

这组元数据应成为 `SimulationPlan` 的编译和验证依据，而不是让模型猜测 Fluent 的 TUI 名称。

官方示例中的求解动作是 `solver_session.settings.solution.run_calculation.iterate(iter_count=100)`，说明“动作”也可以作为受控方法暴露，而不必开放任意 Scheme 代码。

### Meshing 与 solver 是两个有状态阶段

[Meshing workflow](https://fluent.docs.pyansys.com/version/stable/user_guide/meshing/new_meshing_workflows.html)提供 watertight、fault-tolerant、二维和自定义 workflow，并支持导入 CAD、设置尺寸控制、生成表面和体网格、更新边界、添加边界层等任务。

普通 `Meshing` session 可以通过 `switch_to_solver()`切换到 solver，切换后原 meshing session 不再可用，官方文档也说明没有从 solution mode 切回 meshing mode 的方法。

`PureMeshing`不包含切换到 solver 的能力，适合只做网格的最小化服务或容器镜像。

这意味着 adapter 需要显式建模阶段和 session ownership，不能假设一个长连接可以任意往返切换所有模式。

### 结果字段与写入边界

[Choosing between field data and solution variable data APIs](https://fluent.docs.pyansys.com/version/stable/user_guide/fields/field_vs_svars_data.html)把结果访问分为两个不同接口。

`field_data`是按 surface 组织的后处理接口，支持标量、向量、pathlines、网格几何和 connectivity，主要用于读取和可视化。

`solution_variable_data`是按 zone 组织的 solver 数组接口，支持读取和写入内部 SVAR，适合高级初始化或直接修改求解变量。

`field_data`通常是只读的，而 `solution_variable_data`可以写入，因此后者应默认列为高风险操作并需要更严格的审批或专用工具。

### 事件、监视器、日志和批量 RPC

[Observing events](https://fluent.docs.pyansys.com/version/stable/user_guide/events.html)说明 session 的 `events`可以订阅 CASE_LOADED、SOLUTION_INITIALIZED、DATA_LOADED 和 ITERATION_ENDED 等事件。

官方特别提醒事件 callback 要保持轻量，否则会阻塞事件处理并影响 gRPC 通信。

[Using monitors](https://fluent.docs.pyansys.com/version/stable/user_guide/monitors.html)支持读取收敛、残差和 solution variable 的动态监视器数据，并注册 callback 做表格或可视化更新。

[Logging](https://fluent.docs.pyansys.com/version/stable/user_guide/log.html)说明 PyFluent 使用 Python 标准 logging，并支持 DEBUG 级别和写入文件。

[Services API](https://fluent.docs.pyansys.com/version/stable/api/services/services_contents.html)列出了 SettingsService、FieldDataService、FieldDataStreaming、EventsService、MonitorsService、HealthCheckService、TranscriptService、Reduction、SchemeEval 和 BatchOps 等 gRPC service。

同一页的 `BatchOps`示例说明多个非查询操作可以在 `with pyfluent.BatchOps(session)`块结束时通过一次 gRPC call 执行，适合将一批经过校验的设置变化合并提交。

BatchOps 中依赖尚未创建对象的查询可能失败，因此编译器仍需按阶段排序并在必要位置拆分批次。

### 文件传输、journal 与参数扫描

[File transfer](https://fluent.docs.pyansys.com/version/stable/user_guide/file_transfer.html)提供 PIM、container 和 standalone 等文件传输策略，使 `read_case()`、`write_case()`等文件 API 在远程、容器和本地环境中保持一致。

[Journaling](https://fluent.docs.pyansys.com/version/stable/user_guide/journal.html)可以记录 PyFluent settings、meshing/solver workflow、preferences 和 Python TUI command，并在 Fluent、PyFluent 和 Fluent Web UI 生态之间回放。

Journal 记录会修改状态的 commands，但不记录查询，因此它适合采集专家操作并形成可审查 recipe，不是完整的状态快照。

[PyFluent parametric API](https://fluent.docs.pyansys.com/version/stable/api/parametric.html)提供本地 parametric study、design points、输入参数、输出参数和 `run_in_fluent(num_servers)`，适合把参数扫描封装为受控任务，而不是让模型逐点循环调用 solver。

## 一手资料中的 COMSOL 路线

### 官方 ChatGPT 文章展示的是“生成代码后检查再运行”

[COMSOL 使用 ChatGPT 辅助建模](https://www.comsol.com/support/learning-center/article/modeling-with-chatgpt-86731)说明 COMSOL 提供基于 Java 的 COMSOL API，ChatGPT 可以生成用于 COMSOL 模型方法的 Java 代码。

官方示例先给 ChatGPT 一个约束提示，约定 `model`、`app`和 `public void execute()`等上下文，再逐步请求创建几何、物理场、网格、材料、study 和 plot。

示例工作流是：自然语言请求 -> 复制 Java 代码到 Application Builder 的 Method Editor -> 运行方法 -> 在 Model Builder 和图形窗口中检查结果。

官方文章明确展示了模型可能生成错误的 API 枚举，例如把 `axistype`写成无效的 `custom`，需要把实际错误反馈给 ChatGPT 或人工修正。

文章还指出 LLM 对“左边”“前面”等空间提示缺乏可靠空间感知，因此边界条件的空间选择不能仅依赖自然语言。

文章中的 `clearModel(model)`示例会删除模型中除 Application Builder 特征外的其他模型特征，官方提醒应谨慎使用以免造成工作损失。

文章末尾把当前能力定位为适合基本建模、Java API 编写和调试帮助，但不足以替代高级建模判断。

### COMSOL Java API 的官方结构

[COMSOL 6.4 Application Programming Guide](https://www.comsol.com/documentation/ApplicationProgrammingGuide.pdf)的目录包含 Method Editor、Record Code、Model Methods、Java Shell、Data Viewer 和 Chatbot Window 等章节。

该指南介绍的 Method Editor 用 Java 11 语法编写模型方法和应用方法，并直接访问 model object 与 application object。

[COMSOL Java API overview](https://doc.comsol.com/6.4/doc/com.comsol.help.comsol/api/)是官方 Javadoc 入口。

[Model Javadoc](https://doc.comsol.com/6.4/doc/com.comsol.help.comsol/api/com/comsol/model/Model.html)显示 `Model`对象提供 component、geometry、mesh、physics、material、study、solver、result、history、save 等模型实体和生命周期访问。

[ModelUtil Javadoc](https://doc.comsol.com/6.4/doc/com.comsol.help.comsol/api/com/comsol/model/util/ModelUtil.html)提供 create、createUnique、load、save、connect、disconnect、remove、clear、license 检查和进度日志等模型生命周期能力。

这使 COMSOL 也可以做成受控 executor，但执行边界应是白名单 Java method 或编译后的操作，而不是将任意 Java 源码直接交给生产 worker。

### COMSOL 的其他官方自动化接口

[LiveLink for MATLAB](https://www.comsol.com/livelink-for-matlab)官方页面说明 MATLAB 可以通过 COMSOL API 控制几何、网格、物理场、参数化研究、求解器和后处理，并提取数值数据和图形。

本次调研确认到的 COMSOL 官方自动化主线是 Java API 和 LiveLink for MATLAB，因此不应把第三方 Python 包当作官方 Python API 对外承诺。

[COMSOL Model Manager database API Javadoc](https://doc.comsol.com/6.4/doc/com.comsol.help.comsol/api/com/comsol/api/database/package-summary.html)说明可以读取、搜索和保存 repository、branch 中的模型和数据文件版本，并可通过 `ModelUtil.load()`加载 model location URI。

Model Manager API 适合为 CFD 模型、case、数据和 recipe 提供版本身份，但仍需要按 COMSOL 许可证、数据库权限和服务器认证部署。

## OpenFOAM 作为对照

[OpenFOAM Foundation User Guide v14](https://doc.cfd.direct/openfoam/user-guide-v14/)把 OpenFOAM 描述为一组 applications 和 C++ libraries，典型用法是由命令行启动 solver 和网格工具。

[Running applications](https://doc.cfd.direct/openfoam/user-guide-v14/running-applications)说明应用从 terminal 执行，读取和写入 case directory，并支持 `-case`、`-parallel`、`-solver`和日志重定向等参数。

[Case file structure](https://doc.cfd.direct/openfoam/user-guide-v14/case-file-structure)把 case 组织为 `constant`、`system`和时间目录，分别承载网格/物性、控制字典和字段/结果。

[Parallel execution](https://doc.cfd.direct/openfoam/user-guide-v14/running-applications-parallel)说明通过 domain decomposition、`decomposePar`、processor 目录和 MPI 运行并行任务。

[Post-processing CLI](https://doc.cfd.direct/openfoam/user-guide-v14/post-processing-cli)支持 function object、sampling、monitoring 和 `foamPostProcess`。

[Mesh conversion](https://doc.cfd.direct/openfoam/user-guide-v14/mesh-conversion)说明 `fluentMeshToFoam`可以读取 Fluent ASCII mesh，但边界条件不能直接一一对应，且多材料、embedded interfaces 和 refinement trees 等场景存在限制，转换后必须人工检查。

OpenFOAM 的 AI adapter 应生成受 schema 约束的 case 文件和 argv 列表，然后在固定 case 目录中运行白名单命令并解析日志，不应暴露通用 shell。

## 推荐的 AI 调用抽象

### 1. 用 SimulationPlan 代替任意代码

建议模型输出一个有版本号的 typed 计划，而不是 Python、Java、Scheme 或 shell 文本。

示例最小结构如下：

```json
{
  "schema_version": "cfd.simulation_plan.v1",
  "engine": "fluent",
  "mode": "steady",
  "geometry": {
    "source_artifact_id": "cad_123",
    "dimension": 3,
    "unit": "mm"
  },
  "mesh": {
    "workflow": "watertight",
    "global_size": {"value": 0.5, "unit": "mm"},
    "boundary_layers": {"count": 8, "first_layer": {"value": 0.02, "unit": "mm"}}
  },
  "physics": {
    "model": "k-omega-sst",
    "energy": true,
    "material": "air"
  },
  "boundary_conditions": [
    {"zone": "inlet", "type": "velocity-inlet", "velocity": {"value": 10, "unit": "m/s"}},
    {"zone": "outlet", "type": "pressure-outlet", "pressure": {"value": 0, "unit": "Pa"}}
  ],
  "solver": {"precision": "double", "processors": 4, "max_iterations": 500},
  "outputs": ["residuals", "pressure_drop", "velocity_contour", "case", "data"]
}
```

计划 schema 应表达物理量单位、维度、可选枚举、目标 zone/surface、资源预算、输出类型和是否允许覆盖已有模型。

计划不应允许任意文件路径、任意环境变量、任意进程参数或任意代码片段。

### 2. 两阶段执行

第一阶段是 `plan -> validate -> diff -> estimate`，只读取能力和现有状态，不启动高成本计算。

第二阶段是 `approve -> execute -> observe -> finalize`，由受控 worker 执行并持续发出状态事件。

低风险的只读检查可以自动批准，写入 SVAR、覆盖 case、删除模型、启用远程连接、申请大量核时或大规模参数扫描应进入显式批准策略。

COMSOL 官方文章的复制代码、运行方法、检查模型链路正好说明了这种“生成与执行分离”的必要性。

### 3. 工具面应小而稳定

推荐首批工具保持在以下粒度：

| 工具 | 作用 | 默认权限 |
| --- | --- | --- |
| `cfd.inspect_capabilities` | 返回引擎版本、模式、可用模型、单位、枚举和资源上限 | 只读 |
| `cfd.inspect_case` | 返回 zone、surface、mesh、已有结果和当前状态 | 只读 |
| `cfd.validate_plan` | 校验 schema、单位、维度、allowed values、范围和依赖 | 只读 |
| `cfd.preview_changes` | 返回设置 diff、预计资源、将覆盖的 artifact 和风险 | 只读 |
| `cfd.submit_job` | 创建异步 CFD job | 需批准 |
| `cfd.get_status` | 获取状态、阶段、迭代、残差和错误摘要 | 只读 |
| `cfd.cancel_job` | 请求安全停止并记录停止原因 | 需策略 |
| `cfd.read_results` | 按白名单读取标量、向量、监视器和汇总量 | 只读 |
| `cfd.export_artifacts` | 生成 case/data/mesh/log/plot/table 的 artifact manifest | 只读或需策略 |
| `cfd.replay_recipe` | 回放经过审核的 PyFluent journal、COMSOL method 或模板 case | 需批准 |

原始 Fluent TUI、Scheme、COMSOL 任意 Java 和 OpenFOAM 任意 shell 可以保留给开发者调试面，但不应进入默认模型工具列表。

### 4. 执行器按厂商做 adapter

Fluent adapter 应把 `SimulationPlan`编译成 PyFluent settings/workflow 调用，并使用 `allowed_values()`、`min()`、`max()`和`is_active()`做二次校验。

Fluent adapter 应复用长期 session，使用 BatchOps 合并连续设置，用 events/monitors/transcript 推送进度，用 file transfer 管理远程和容器文件。

COMSOL adapter 应优先执行预定义 Java methods 或由 Record Code 产生、经审核的 method 模板，并在运行前做 model tree、实体选择和清理动作检查。

OpenFOAM adapter 应把计划渲染为固定模板下的 `constant`、`system`和初始时间目录，使用固定 argv、固定 case root 和日志解析器。

### 5. 结果必须是结构化摘要加 artifact manifest

模型不应直接接收整个网格或所有 field 数组作为上下文。

建议返回：job 状态、solver 版本、计划摘要、收敛判断、关键标量、监视器曲线摘要、错误和警告、artifact manifest 以及 provenance。

manifest 至少应记录 artifact id、kind、路径或对象存储 key、媒体类型、大小、SHA-256、生成阶段、引擎版本、case/mesh/plan 版本和可见性。

大字段、网格和原始日志按需下载或由专用可视化接口读取。

### 6. 状态机与可观测性

建议 job 状态为 `created -> validating -> waiting_approval -> queued -> launching -> meshing -> configuring -> solving -> postprocessing -> completed`，并允许 `failed`、`cancel_requested`、`cancelled`和`interrupted`终态。

每次计划变更、工具调用、引擎命令摘要、事件、资源分配、artifact 产生和错误都应写入可重放的审计事件，但不能写入 API key、许可证密钥或完整敏感输入。

长任务必须异步提交，前端通过持久化 timeline 和 bounded activity stream 观察，不应把 HTTP 请求一直阻塞到 solver 结束。

## 当前 InternAgent 的适配建议

本节是基于仓库文档和代码图谱的架构推断，不是 Ansys 或 COMSOL 官方承诺。

### 放置边界

[`architecture.md`](../../architecture.md#模型工具记忆基础设施)将 `UnifiedModelRuntime`放在模型层，将工具注册、MCP 和检索放在独立工具层，并把实验执行与 `results/<task>/<launch_id>`产物放在执行层。

[`docs/adr/0141-use-typed-capability-operations-in-one-runtime.md`](../adr/0141-use-typed-capability-operations-in-one-runtime.md)把 Unified Model Runtime 的 typed capability 限定为文本、图像和 embedding 等模型推理操作。

因此 CFD 不应作为 `UnifiedModelRuntime` 的新模型 capability，而应作为工具层的 `CfdTool` 加上实验/作业后端的 `CfdJobRunner`。

### 应复用的现有 seam

[`LOOP_ARCHITECTURE.md`](../../LOOP_ARCHITECTURE.md#15-关键源码索引)列出 `vegapunk/mas/agents/tool_loop.py::ModelToolLoop.run`作为模型工具循环入口。

当前 `ModelToolLoop.run`已经负责发送带 tools 的模型请求、执行 function tool call、把工具错误作为模型可见证据，并通过 `record_research_event`记录工具输入和输出。

CFD 工具应复用这个循环和现有 Tool Registry，但在实际执行前增加独立的 `SimulationPlan` schema、引擎能力快照、资源策略和路径 allowlist。

[`architecture.md`](../../architecture.md#模型工具记忆基础设施)中的 `get_related_tools(query, tools)`是按 prompt 相似度筛选相关工具的发现机制。

它不能承担 CFD 的安全边界，因为相似度筛选可能遗漏工具、返回过多工具，也不负责单位、权限、资源和高风险动作校验。

CFD adapter 应在工具注册时带有稳定的 engine、operation、risk、required_capabilities 和 input schema，并由服务端 allowlist 决定是否可执行。

### 产物与产品边界

[`LOOP_ARCHITECTURE.md`](../../LOOP_ARCHITECTURE.md#42-配置快照)说明一个 Discovery Launch 会在 `results/<task_name>/<timestamp>_launch/`内保存本次运行的输入和配置边界。

[`docs/adr/0089-describe-progress-with-artifacts-and-checkpoints.md`](../adr/0089-describe-progress-with-artifacts-and-checkpoints.md)把持久化的 Native Discovery Artifacts、检查点和生成结果视为权威进度材料。

因此 CFD job 应在对应 launch-local 的实验或作业目录中写入 plan snapshot、capability snapshot、job events、solver log 摘要、metrics、plots、case/data 和 replay recipe。

对浏览器产品，只应暴露经过筛选的 CFD artifact manifest，而不是让用户通过任意路径读取整个 launch 目录。

这与 [`docs/research/end-user-frontend-v1-api-contract.md`](end-user-frontend-v1-api-contract.md#results-and-artifacts)中“复用 launch 内部投影，但只向产品暴露 Curated Research Artifact”的边界一致。

### 推荐的 V1 实现顺序

1. 先建立 `SimulationPlan v1`、能力快照和 `CfdJob`状态模型，不接任意代码执行。
2. 先实现 Fluent/PyFluent adapter，因为其 typed settings、events、monitors、BatchOps 和 file transfer 能直接映射到计划执行器。
3. 用 fake Fluent session 或录制的 PyFluent journal 做单元和集成测试，再在拥有许可证的 worker 上做小型 smoke run。
4. 为 `inspect_case`、`validate_plan`、`preview_changes`、`submit_job`、`get_status`、`read_results`和`export_artifacts`建立最小工具集。
5. 把 job 生命周期和事件接入现有 launch queue/timeline，而不是为 CFD 再造一套前端历史和 artifact 树。
6. 在有稳定 Fluent recipe 后，再添加 COMSOL Java method adapter 和 OpenFOAM template adapter。

## 限制、授权与部署注意事项

### Fluent/PyFluent

必须核验 Fluent 商业许可证、并行许可证、目标版本和 worker 上的 `AWP_ROOT*`配置。

远程连接必须限制 host、port、证书和服务账号，生产环境默认使用 TLS，不能把 PyFluent 的 insecure mode 当成便利开关。

container 和远程文件必须通过官方 file-transfer strategy 或受控挂载目录处理，不能让模型指定任意本地或远端路径。

要限制每个 job 的处理器数、最大迭代、最大 wall time、内存、并发 session 和参数点数量，因为 license token 和计算资源是外部约束。

事件 callback 必须轻量，重计算应移到独立 worker 或事件循环任务。

### COMSOL

Java API 执行具有文件、模型清理、许可证和服务器连接风险，不能把 ChatGPT 生成的原始 Java 直接视为可信代码。

必须检查实体 tag、selection、空间边界、单位和几何维度，并在高风险 method 运行前展示 diff 和批准界面。

`clearModel`等清理操作需要单独的显式确认，并应优先在副本模型上运行。

如果使用 Model Manager，还要处理数据库 alias、repository/branch 权限、服务器密码和模型版本冲突。

### OpenFOAM

OpenFOAM 的 case 字典和 CLI 参数必须由模板、枚举和数值范围生成，模型不得注入任意 shell、管道、重定向或环境变量。

mesh 转换和边界映射不能只依据命令成功返回，必须在 job 中记录转换警告并做 zone、单位和边界条件检查。

## 已验证事实、推断和未验证事项

| 类型 | 结论 |
| --- | --- |
| 已验证事实 | PyFluent 官方文档提供 gRPC session、settings 元数据、meshing workflow、field data、events、monitors、BatchOps、file transfer、journal 和参数化能力。 |
| 已验证事实 | COMSOL 官方文章展示 Java API 代码生成、Method Editor 执行、错误反馈和空间感知限制。 |
| 已验证事实 | COMSOL 6.4 官方 Javadoc 提供 Model/ModelUtil 生命周期和模型树访问，Model Manager API 提供模型与数据版本访问。 |
| 已验证事实 | OpenFOAM 官方用户指南以 case directory、CLI application、MPI 并行和后处理命令为主要自动化接口。 |
| 架构推断 | InternAgent 应把 CFD 放在工具层和实验/作业后端，而不是 UnifiedModelRuntime。 |
| 架构推断 | ModelToolLoop、工具注册、事件记录和 launch-local artifact 是 CFD 复用现有系统的主要 seam。 |
| 架构推断 | `get_related_tools`只能做发现，不应作为 CFD 的权限、安全、schema 或资源边界。 |
| 未验证事项 | 本次环境无法读取 Ansys Developer Portal 正文，不能据此确认其额外的 Fluent 平台 API 或商业条款。 |
| 未验证事项 | 本报告没有把第三方 COMSOL Python 项目、社区 wrapper 或未经官方确认的 REST endpoint 当作官方接口。 |

## 来源索引

- [Ansys Fluent Developer Portal](https://developer.ansys.com/docs/fluent)（本次访问被 Cloudflare 403 阻断）。
- [PyFluent 官方文档首页](https://fluent.docs.pyansys.com/version/stable/)。
- [PyFluent 安装](https://fluent.docs.pyansys.com/version/stable/getting_started/installation.html)。
- [PyFluent session 启动和连接](https://fluent.docs.pyansys.com/version/stable/user_guide/session/launching_ansys_fluent.html)。
- [PyFluent session](https://fluent.docs.pyansys.com/version/stable/user_guide/session/session.html)。
- [PyFluent solver settings](https://fluent.docs.pyansys.com/version/stable/user_guide/solver_settings/solver_settings_contents.html)。
- [PyFluent meshing workflow](https://fluent.docs.pyansys.com/version/stable/user_guide/meshing/new_meshing_workflows.html)。
- [PyFluent field data 和 solution variable data](https://fluent.docs.pyansys.com/version/stable/user_guide/fields/field_vs_svars_data.html)。
- [PyFluent events](https://fluent.docs.pyansys.com/version/stable/user_guide/events.html)。
- [PyFluent monitors](https://fluent.docs.pyansys.com/version/stable/user_guide/monitors.html)。
- [PyFluent services 和 BatchOps](https://fluent.docs.pyansys.com/version/stable/api/services/services_contents.html)。
- [PyFluent file transfer](https://fluent.docs.pyansys.com/version/stable/user_guide/file_transfer.html)。
- [PyFluent journaling](https://fluent.docs.pyansys.com/version/stable/user_guide/journal.html)。
- [PyFluent FluentConnection](https://fluent.docs.pyansys.com/version/stable/api/fluent_connection.html)。
- [PyFluent parametric API](https://fluent.docs.pyansys.com/version/stable/api/parametric.html)。
- [COMSOL 使用 ChatGPT 辅助建模](https://www.comsol.com/support/learning-center/article/modeling-with-chatgpt-86731)。
- [COMSOL Application Programming Guide](https://www.comsol.com/documentation/ApplicationProgrammingGuide.pdf)。
- [COMSOL Java API overview](https://doc.comsol.com/6.4/doc/com.comsol.help.comsol/api/)。
- [COMSOL Model Javadoc](https://doc.comsol.com/6.4/doc/com.comsol.help.comsol/api/com/comsol/model/Model.html)。
- [COMSOL ModelUtil Javadoc](https://doc.comsol.com/6.4/doc/com.comsol.help.comsol/api/com/comsol/model/util/ModelUtil.html)。
- [COMSOL LiveLink for MATLAB](https://www.comsol.com/livelink-for-matlab)。
- [COMSOL Model Manager database API](https://doc.comsol.com/6.4/doc/com.comsol.help.comsol/api/com/comsol/api/database/package-summary.html)。
- [OpenFOAM Foundation User Guide v14](https://doc.cfd.direct/openfoam/user-guide-v14/)。
- [OpenFOAM running applications](https://doc.cfd.direct/openfoam/user-guide-v14/running-applications)。
- [OpenFOAM case file structure](https://doc.cfd.direct/openfoam/user-guide-v14/case-file-structure)。
- [OpenFOAM parallel execution](https://doc.cfd.direct/openfoam/user-guide-v14/running-applications-parallel)。
- [OpenFOAM post-processing CLI](https://doc.cfd.direct/openfoam/user-guide-v14/post-processing-cli)。
- [OpenFOAM mesh conversion](https://doc.cfd.direct/openfoam/user-guide-v14/mesh-conversion)。
