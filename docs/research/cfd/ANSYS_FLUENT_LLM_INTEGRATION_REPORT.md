# Ansys Fluent 集成 Vegapunk 与 LLM 实验 loop 调研报告

> 调研日期：**2026-08-03**。本文优先使用 Ansys、PyAnsys/PyFluent 和 NVIDIA 官方资料，并将结论映射到当前 Vegapunk 代码与已有 CFD 调研。报告讨论的是“如何把 Fluent 作为受控实验后端接入”，不是把 Fluent 本身改造成开源软件或让模型直接执行任意命令。

> 关于“系统是否需要调用 Fluent、何时调用 Fluent”的补充决策机制，见 [2026-08-04 外部仿真调用决策机制补充报告](2026-08-04-ansys-fluent-invocation-policy.md)。

> 关于 PyFluent 客户端与 Fluent 商业许可证的边界，以及真实仿真结果如何反馈给 LLM，见 [2026-08-05 PyFluent 许可证与反馈机制调研](2026-08-05-pyfluent-license-and-feedback.md)。

## 1. 结论先行

Ansys Fluent 已经具备比普通命令行 CFD wrapper 更好的自动化基础：PyFluent 提供 gRPC 会话、Solver/Meshing session、层次化 settings API、workflow、field data、事件与 monitor、文件传输、journal、BatchOps 和参数化执行。它因此是**可被程序化封装的商业 CFD solver**。

但“有 Python API”不等于“可直接被 LLM 安全、稳定地调用”。Fluent 仍需要有效的 Ansys/Fluent 许可证、匹配的 Fluent/PyFluent 版本、网格/边界/物性等专业输入、可控的 CPU/GPU/HPC 资源，以及对收敛、守恒、单位和结果可信度的程序化检查。PyFluent 的 settings 树也不能原样暴露给模型：树很大、版本相关，且部分节点的 exposure level 可能是 beta/alpha。

对 Vegapunk 的建议是：

1. 在 `ExperimentRunner` 与外部 solver 之间增加 `FluentExecutionService`/adapter seam；不要把 Fluent 当成 `UnifiedModelRuntime` 的模型 capability。
2. 用 typed `SimulationPlan` 固定 case、设计变量、单位、资源、收敛判据和输出契约；LLM 只能修改白名单变量。
3. 由本地或远程 worker 持有 PyFluent session，异步返回 `FluentJob`；MCP/Web 只暴露窄工具、状态和 curated artifacts。
4. 第一阶段采用“一 job 一 Fluent session、一 case、一 primary metric、串行资源 lease”；稳定后再启用参数扫描和并行 design points。
5. 将 Fluent 作为 high-fidelity validation lane；未来的 PhysicsNeMo/DoMINO 作为可选 surrogate/screening lane，不能让 surrogate 结果覆盖 Fluent 验证结果。

一句话判断：**Fluent 具备“adapter-ready”基础，不具备“直接 LLM-ready”基础；Vegapunk 需要补上 schema、作业状态、资源/许可证治理、安全边界、收敛评分和可恢复 artifact 契约。**

## 2. 调研范围与官方资料基线

本报告核对的主要资料如下。稳定文档可能随 PyFluent 发布而更新，因此生产集成还需要把 package、Fluent 安装、容器镜像和本文档链接对应的版本写入 lockfile/manifest。

| 资料 | 关键事实 |
| --- | --- |
| [Ansys Fluent 产品页](https://www.ansys.com/products/fluids/ansys-fluent) | Fluent 是商业通用 CFD 平台，覆盖前处理/网格、流动、传热、物种、多相、湍流等工程仿真能力。 |
| [PyFluent 安装与许可](https://fluent.docs.pyansys.com/version/stable/getting_started/installation.html) | `pip install ansys-fluent-core`；当前稳定文档列出 Python 3.10–3.14，完整使用需要有授权的 Fluent 安装/许可。 |
| [PyFluent README（固定 commit）](https://github.com/ansys/pyfluent/blob/feab8839d524e1f1d24d18fa77ccb4095778c923/README.rst) | 记录 PyFluent 与 Fluent 2024 R2 SP05、2025 R1 SP04、2025 R2 SP03、2026 R1 等版本组合；应按部署版本锁定，而不是盲跟 `main`。 |
| [启动与连接 Fluent](https://fluent.docs.pyansys.com/version/stable/user_guide/session/launching_ansys_fluent.html) / [launcher API](https://fluent.docs.pyansys.com/version/stable/api/launcher/launcher.html) | `launch_fluent` 启动 Fluent 与 gRPC server，`connect_to_fluent` 连接已有 server；支持 solver/meshing、2D/3D、单双精度、processor count、容器和 HPC 调度器。 |
| [Session 生命周期](https://fluent.docs.pyansys.com/version/stable/user_guide/session/session.html) | Solver、Meshing、PureMeshing session；支持 settings、fields、events、workflow、TUI 和退出/清理。 |
| [Solver settings](https://fluent.docs.pyansys.com/version/stable/user_guide/solver_settings/solver_settings_contents.html) / [flobject API](https://fluent.docs.pyansys.com/version/stable/api/solver/flobject.html) | Settings 是层次化 Group/NamedObject/ListObject；可查询 allowed values、min/max、read-only、active 子树、command 参数等元数据。 |
| [可用性与 semantic search](https://fluent.docs.pyansys.com/version/stable/user_guide/usability.html) | `pyfluent.search()` 支持 semantic、wildcard、whole-word、拼写修正、`api_path` 限定和多语言查询；这是辅助开发者发现 API 的能力，不是安全策略。 |
| [Meshing workflows](https://fluent.docs.pyansys.com/version/stable/user_guide/meshing/new_meshing_workflows.html) | Watertight、Fault-tolerant、2D 等 workflow 可被任务化编排，并可保存/加载 workflow。 |
| [Events](https://fluent.docs.pyansys.com/version/stable/user_guide/events.html) / [Monitors](https://fluent.docs.pyansys.com/version/stable/user_guide/monitors.html) | 可监听 case loaded、solution initialized、data loaded、iteration ended 等事件，读取/订阅收敛和 solution variable monitor。 |
| [BatchOps](https://fluent.docs.pyansys.com/version/stable/api/services/batch_ops.html) | 将多个非 getter settings 操作合并为一次 gRPC 往返；queued 对象的依赖关系需要遵守文档限制。 |
| [Journal](https://fluent.docs.pyansys.com/version/stable/user_guide/journal.html) | 记录 settings/workflow/TUI 的副作用并可回放；普通 Python 查询不自动写入 journal。 |
| [文件传输](https://fluent.docs.pyansys.com/version/stable/user_guide/file_transfer.html) | PIM、容器和 standalone strategy 统一处理 upload/download、`read_case`、`write_case`，适合远程 worker。 |
| [Field data](https://fluent.docs.pyansys.com/version/stable/user_guide/fields/field_data.html) / [Reduction](https://fluent.docs.pyansys.com/version/stable/user_guide/fields/reduction.html) | 可读取 surface/scalar/vector/pathlines 数据，并将 area/volume average、integral、force、moment、min/max 等压缩为结构化标量。 |
| [Solution variable data](https://fluent.docs.pyansys.com/version/stable/user_guide/fields/solution_data.html) / [field 与 SVAR 区别](https://fluent.docs.pyansys.com/version/stable/user_guide/fields/field_vs_svars_data.html) | solution-variable 数组读写能力更底层；默认只开放 reduction/只读 field data，SVAR 写入必须单独列入高风险白名单。 |
| [Meshing→solver 数据传递](https://fluent.docs.pyansys.com/version/stable/user_guide/transfer_data.html) | 可在不同 PyFluent session 间转移 mesh/case；适合把 meshing worker 的产物交给独立 solver worker。 |
| [Parametric API](https://fluent.docs.pyansys.com/version/stable/api/parametric.html) | `LocalParametricStudy` 可定义 design points，并通过 `run_in_fluent` 批量执行；应由 worker 管理并发与资源，而不是由 LLM 逐点循环。 |
| [容器镜像与许可证](https://fluent.docs.pyansys.com/version/stable/user_guide/make_container_image.html) | Fluent 容器需要有效 Ansys license；运行时通常通过 `ANSYSLMD_LICENSE_FILE` 提供 license server/file，容器和 GPU 能力需按版本核对。 |

本文也参考了已有的 [CFD 与 LLM 实验 loop 报告](CFD_LLM_INTEGRATION_REPORT.md) 和 [PyFluent/COMSOL/OpenFOAM 路线报告](2026-07-28-cfd-ai-integration.md)。

## 3. Ansys Fluent 到底提供什么

### 3.1 Fluent 是 solver + meshing + post-processing 平台

Fluent 不只是一个 Python 包或一组 shell 脚本，而是一个需要授权的工程仿真产品。典型工作流包含几何/网格准备、区域和边界定义、材料与模型选择、初始化、迭代/瞬态求解、监控、结果提取和可视化。不同物理模型对输入字段、边界条件、收敛判断和可接受误差的要求不同。

这使 Fluent 的自动化入口比 Antmicro `cfd-simulation-scripts` 更接近“可编程求解服务”，但也意味着 Vegapunk 不能只把一个自然语言 prompt 变成几行参数。case 模板、网格质量、单位、模型选择和后处理定义都必须由领域工程师预先审核。

### 3.2 PyFluent 的安装和版本边界

PyFluent 的核心包是 `ansys-fluent-core`。安装文档同时说明了两类路径：

- `AWP_ROOT252` 一类的环境变量用于让 PyFluent 找到对应版本的本机 Ansys 安装；具体数字应随 Fluent 版本变化。
- `ANSYSLMD_LICENSE_FILE` 用于容器/远程运行时指向 Ansys license file 或 license server；它不是 Fluent 安装路径。

因此 capability probe 不能只检查 `import ansys.fluent.core` 成功，还要验证：PyFluent 版本、Fluent executable、Fluent server/gRPC、license 可借用、processor/GPU/HPC 资源和目标 case 模板均可用。许可证不可用时，任务应在 preflight 阶段进入 `blocked`/`preflight_failed`，不要让模型自行猜测安装或 license 命令。

### 3.3 启动、连接与 session

PyFluent 可以在 worker 上启动 Fluent，也可以连接已有的 Fluent server。启动参数可表达 solver/meshing 模式、2D/3D、精度、处理器数量、容器/PIM 和 HPC scheduler；连接模式需要 server info、IP/port/password 等信息。远程连接还涉及 TLS、证书目录和 `insecure_mode` 的安全选择。

在 Vegapunk 的第一版 adapter 中，建议每个异步 job 独占一个 worker/session：

```text
validate plan
  -> stage case and inputs
  -> launch Fluent solver/meshing session
  -> read case or run approved workflow
  -> apply typed design-variable patch
  -> solve and stream monitors
  -> extract metrics and write case/data
  -> persist manifest and curated artifacts
  -> exit/cleanup session
```

不要一开始就在多个用户任务之间共享长寿命 session。共享 session 会引入 case 污染、未保存状态、残留 monitor/callback、license 占用和取消语义问题；等单 job 模型稳定后再评估 session pool。

FluentConnection 支持带 timeout 的 `exit`/强制退出和 `cleanup_on_exit`。adapter 必须把正常退出、超时、取消、强制终止和“进程退出但 case 未写完”区分为不同结果状态。

### 3.4 Settings API：比 TUI 更适合受控自动化

Solver settings API 将可配置对象组织为 Group、NamedObject、ListObject 等层次结构，并为节点暴露 active/read-only/default/allowed values/min/max 等元数据。它允许 worker 在应用计划前做 schema 校验，例如：

- 设计变量是否位于允许的 API path；
- 值是否是当前版本允许的枚举；
- 数值是否满足上下界和单位要求；
- 节点是否因当前物理模型未启用而 inactive；
- 该字段是否只读，是否需要先创建 named object。

`pyfluent.search()` 的 semantic/wildcard 搜索有助于开发者查找 API，但不能直接作为 LLM 的执行授权。生产 adapter 应在仓库中维护版本化的“变量目录”（canonical API path、单位、范围、转换规则、风险级别和 artifact 影响），模型只能引用目录中的 key。

第一版应优先使用 settings/workflow API；TUI 只作为经过审核的兼容层。任意 TUI 字符串、任意 Python 片段、任意 Scheme 调用和任意 journal 都不应直接暴露为模型工具参数。

### 3.5 Meshing workflow

PyFluent 文档提供 Watertight、Fault-tolerant、2D 等 meshing workflow，可以将导入几何、尺寸控制、表面/体网格、边界层和区域更新编排成任务。对 Vegapunk 而言，workflow 适合被固化在 case template 中，LLM 只选择经过审核的 workflow profile 和有限的网格参数。

网格生成仍是 CFD 可信性的主要风险源。adapter 至少需要在 solver 启动前保存几何 hash、单位/姿态、网格版本，并检查网格质量、区域/边界映射和规模上限；不能只凭“mesh workflow 返回成功”判断 case 可用于科学比较。

### 3.6 Events、monitors 与长作业

Events 可监听 case loaded、solution initialized、data loaded、iteration ended 等生命周期事件；Monitors 可读取残差、力、温度和其他 solution variables，并注册 callback。它们正好对应实验 loop 的中间反馈：

- `launching`/`case_loaded`：session 和输入快照已确认；
- `meshing`：网格阶段和质量摘要；
- `solving`：当前迭代、残差、关键 monitor；
- `converged`：达到计划中的收敛判据；
- `stalled`/`diverged`：进入失败或人工审批路径。

事件 callback 必须轻量；官方文档提醒 callback 运行在线程/事件循环边界中，阻塞 gRPC 或在错误线程直接操作 asyncio 会造成死锁和丢事件。worker 应把事件转成带序列号的内部事件队列，再由独立持久化器写入 launch artifact。流式 monitor 数据可能重复，按 iteration/time index 去重后才进入 metrics store。

### 3.7 BatchOps

每个 settings 操作都产生远程调用时，参数化扫描会有明显 gRPC 往返开销。BatchOps 可以将多个非 getter 操作合并发送，适合一次应用一个经过校验的 settings patch。需要注意 queued 对象不能在同一 batch 中被后续 query 依赖；adapter 应把“创建对象”和“读取结果”分成明确的 batch/阶段，避免把 API 细节暴露给模型。

### 3.8 Journaling、文件传输与 replay

Journal 能记录 settings、workflow、preferences 和 TUI 命令的副作用，方便复核和回放；普通查询、日志读取和 Python 侧计算不一定进入 journal。因此 Vegapunk 需要另建 `plan_snapshot.json`、`capability_snapshot.json`、事件日志、输入/输出 hash 和 adapter digest，journal 只能作为其中一个 replay artifact。

PIM、容器和 standalone file-transfer strategy 使 `read_case()`/`write_case()` 等 API 可在本地、容器和远程环境复用。worker 不应把任意绝对路径交给 Fluent；所有 case、几何、journal、data 和导出文件必须位于 launch-local root，并在上传前检查大小、格式、symlink 和路径逃逸。

### 3.9 参数化执行

PyFluent 的 `LocalParametricStudy` 可以定义 design points，并通过 `run_in_fluent(num_servers, ...)` 执行。它适合由后端把多个 design points 变成一个可追踪的 `FluentJob`，统一管理 license/CPU/GPU lease、失败策略、结果排序和取消。

不建议让 LLM 逐点调用 Fluent。这样会导致 tool call 次数、license 占用和部分失败状态不可控，也难以保证所有 candidate 使用同一 case/solver/mesh 快照。模型只应提交一个带上限的参数化计划。

### 3.10 结果抽取：优先 reduction，field/SVAR 分级开放

PyFluent 的 Field Data API 可以请求 surface、scalar、vector、pathlines 等数据，并以 NumPy 等结构返回；适合在需要绘图或局部诊断时按需获取。Reduction API 则直接提供 area/volume average、integral、minimum/maximum、mass average、force、moment、count 等运算，更适合作为实验 loop 的 primary metric 输入。

因此推荐三层结果权限：

1. **默认层**：只返回 reduction 标量、单位、monitor 曲线摘要和 quality gate；这部分进入 `final_info.json` 和模型上下文。
2. **诊断层**：按 selector 读取有限 surface/field 数组，生成 curated plot 或小型 NumPy artifact；由服务端限制 zone、变量、采样点、大小和媒体类型。
3. **高风险层**：solution variable data（SVAR）的底层数组读写。除非 case profile 明确声明并经过审批，否则禁止写入 SVAR；LLM 不应获得任意 zone/variable 的写权限。

这比把整个 Fluent field tree 或二进制 data 文件直接交给模型更可控，也更容易与现有 scorer 的 scalar primary metric 对接。

Meshing 和 solver 可以使用不同的 PyFluent session，再通过 `transfer_case` 传递 mesh/case。这样能够缩短 session 生命周期、隔离 meshing/solver 失败，并避免多个阶段共享同一个有状态 session；代价是需要显式记录 transfer artifact 和版本/hash。

## 4. Fluent 对 LLM 调用是否“丝滑”

### 4.1 有利条件

| 能力 | 对 LLM/实验 loop 的价值 |
| --- | --- |
| gRPC session 与显式 launch/connect | 不必让模型拼接 shell；worker 可以管理进程生命周期和远程连接。 |
| typed settings 层次树 | 可在执行前查询/校验枚举、范围、只读和 active 条件。 |
| events/monitors | 长作业可以异步反馈 iteration、残差和关键指标。 |
| journal/file transfer | 能保存回放线索，并把远程 worker 的 case/data 安全搬运到 artifact 根。 |
| BatchOps/parametric API | 可以减少 API 往返并把参数扫描作为一个受控后端作业。 |

### 4.2 仍然不能自动解决的问题

1. **许可证与部署**：没有有效 license、正确版本或 server，PyFluent 代码不能完成求解。
2. **领域输入**：settings API 不会替模型决定网格是否足够、边界条件是否物理正确、湍流/多相模型是否合适。
3. **版本漂移**：settings path、workflow 名称、exposure level 和支持的 Fluent 版本会变化，必须锁版本并做 capability snapshot。
4. **长任务资源**：solver 可能占用数小时、多个 CPU/GPU 或 HPC slot；同步工具调用会阻塞 loop，盲目并行会耗尽 license 或 oversubscribe。
5. **结果可信性**：进程退出码为 0 不代表收敛、守恒、网格质量或目标指标有效。
6. **安全**：任意 TUI/journal/Python、绝对路径和环境变量可能带来宿主机命令执行、数据外泄或 license secret 泄漏。
7. **取消/恢复**：gRPC 断线、Fluent crash、MPI/HPC 取消、部分写出的 case/data 需要可区分、可重试的状态机。
8. **大数据**：完整 field/mesh 不能直接送入模型上下文；需要 curated metrics、plot 和按需下载的 artifact manifest。

所以 Fluent 的正确定位是“有良好 API 的高保真计算后端”，不是“LLM 直接操作的工具”。

### 4.3 与 Antmicro/OpenFOAM wrapper 的差异

| 维度 | Ansys Fluent + PyFluent | Antmicro `cfd-simulation-scripts` + OpenFOAM |
| --- | --- | --- |
| 产品边界 | 商业 solver、meshing、结果和远程 API | OpenFOAM case 的 CLI pipeline/wrapper |
| 主要调用面 | gRPC session、typed settings、workflow、events、monitors、file transfer | `cfd-pre`/`cfd-post`/`cfd-utils`、当前工作目录和文本日志 |
| 输入抽象 | case/data、meshing workflow、settings 对象 | 人工准备的 `0/`、`constant/`、`system/` 和 `config.json` |
| LLM 友好度 | adapter-ready；有结构化 schema 线索，但需版本/许可治理 | worker-ready；缺少任务 ID、状态 API、schema、取消和结果契约 |
| 许可/成本 | 需要 Ansys/Fluent 商业许可，部署条款需单独核对 | 依赖开源/外部工具许可；原仓库许可状态需单独核对 |
| 适合作为 | 第一条 high-fidelity adapter lane | 后续 OpenFOAM adapter 或对照 lane |

这不是 Fluent 的数值精度排名。它只说明：若目标是让后端提供类型化、可观测、可恢复的作业接口，PyFluent 的 API seam 比只包一层 shell 更容易治理；Fluent 的商业许可和版本约束也更重。

## 5. Vegapunk 当前架构与集成位置

以下映射以当前代码为准，相关文件索引见 [CFD 与 LLM 报告的项目内证据索引](CFD_LLM_INTEGRATION_REPORT.md#18-项目内证据索引)。

### 5.1 现有入口和边界

- [`launch_discovery.py`](../../../launch_discovery.py) 负责 Discovery launch、round、resume、baseline、summary 和 PaperOrchestra handoff。
- [`vegapunk/stage.py`](../../../vegapunk/stage.py) 提供 `IdeaGenerator`、`ExperimentRunner`、workspace/资源 lease 和实验阶段编排。
- [`vegapunk/experiments_utils_codex.py`](../../../vegapunk/experiments_utils_codex.py) 的 `run_experiment` 负责实验目录、`launcher.sh`、超时、日志和 `final_info.json` 契约。
- [`vegapunk/mas/agents/tool_loop.py`](../../../vegapunk/mas/agents/tool_loop.py) 的 `ModelToolLoop.run` 将模型 tool call、工具执行、错误可见性和 research event 串起来。
- [`vegapunk/mas/agents/dr_agents/camel/toolkits/mcp_toolkit.py`](../../../vegapunk/mas/agents/dr_agents/camel/toolkits/mcp_toolkit.py) 提供 stdio/SSE MCP、JSON Schema 和动态 function wrapper。
- [`vegapunk/paper_orchestra/candidate_selection.py`](../../../vegapunk/paper_orchestra/candidate_selection.py) 依赖 primary metric、optimization direction、finite number 和 provenance 做 candidate selection。

当前 loop 的优势是已有 round-level resume、artifact 路径和模型工具循环；缺口是外部 solver 仍会被视作一次同步实验脚本，缺少 CFD-specific preflight、stage 状态、license/resource lease、monitor 事件和物理质量 gate。

### 5.2 不应放置的位置

Fluent 不应直接塞进 `UnifiedModelRuntime`。该 runtime 的职责是文本/视觉/embedding 等模型能力和 provider/model 配置，不应持有商业 solver session、license secret、MPI/HPC 资源或大体积 mesh/field。

Fluent 也不应让 LLM 直接调用 `subprocess`、TUI、journal 或任意 Python。MCP 只应暴露 `FluentExecutionService` 的窄 façade；服务端负责 schema、权限、路径、资源和结果校验。

### 5.3 推荐 seam

```text
Discovery/ExperimentRunner
        |
        | typed SimulationPlan + launch snapshot
        v
CfdExecutionService
        |
        +-- FluentAdapter (PyFluent, licensed worker)
        +-- OpenFOAMAdapter (future/Antmicro)
        +-- SurrogateAdapter (future PhysicsNeMo/DoMINO)
        |
        v
   CfdJob state/events/artifacts
        |
        +-- MCP facade for ModelToolLoop
        +-- Web/admin status + curated artifact projection
```

这个 seam 让 solver 可替换、让 LLM 只看到稳定的 job API，也让高保真、OpenFOAM 和 surrogate 结果遵循同一份 provenance 和 scorer 契约。

## 6. 推荐后端设计

### 6.1 `SimulationPlan`：LLM 不应直接生成 Fluent 命令

建议的最小计划结构如下。字段名可以在实现时调整，但语义应保持显式：

```json
{
  "engine": "ansys_fluent",
  "engine_version": "2025_R2_SP03",
  "mode": "solver",
  "case_template": "templates/duct_heat_transfer/v1",
  "geometry": {"artifact_id": "...", "sha256": "...", "unit": "m"},
  "design_variables": {
    "inlet.velocity_m_per_s": 3.0,
    "heater.power_w": 120.0
  },
  "allowed_variables_profile": "duct_heat_transfer_v1",
  "resources": {"cpu_cores": 8, "gpu": false, "wall_time_s": 3600},
  "convergence": {
    "residual_norm_max": 1e-5,
    "monitor": "outlet_temperature",
    "max_iterations": 2000
  },
  "outputs": ["primary_metric", "convergence_curve", "curated_plot", "case_data"],
  "policy": {"network": "deny", "requires_approval": true}
}
```

服务端在接受计划时补齐 `plan_id`、`case_template_digest`、`adapter_digest`、capability snapshot、license profile 和 launch id。模型不能覆盖这些系统字段。

### 6.2 `FluentJob` 状态机

推荐状态：

```text
created
 -> validating
 -> waiting_approval
 -> queued
 -> launching
 -> loading_case
 -> meshing
 -> configuring
 -> solving
 -> postprocessing
 -> scoring
 -> completed
```

任意阶段都可能转到 `failed`、`preflight_failed`、`cancel_requested`、`cancelled` 或 `interrupted`。状态事件至少包含 `job_id`、`seq`、`stage`、UTC timestamp、短 message、resource lease、solver session id（脱敏）和 artifact references。原始日志、password、license 内容和完整 field 不写进 LLM 上下文。

### 6.3 `FluentExecutionService` 的最小接口

```text
inspect_capabilities(profile) -> FluentCapabilitySnapshot
inspect_case(case_ref) -> CaseInspection
validate_plan(plan) -> ValidationReport
preview_changes(plan) -> ChangePreview
submit_job(plan) -> FluentJobRef
get_status(job_id) -> FluentJobStatus
cancel_job(job_id, reason) -> CancellationResult
read_metrics(job_id, names) -> MetricSummary
export_artifacts(job_id, selectors) -> ArtifactManifest
```

`inspect_capabilities` 只读返回 Fluent/PyFluent 版本、模式、可用 workflow、CPU/GPU/HPC、license 状态和 adapter digest；它不返回 secret。`validate_plan` 必须在启动 Fluent 前完成 schema、单位、路径、mesh/geometry 上限、资源和 policy 检查。

### 6.4 PyFluent adapter 的执行顺序

1. **Stage**：在 launch-local workspace 复制/上传 case template、geometry、journal 和 manifest；拒绝 symlink/path traversal，计算输入 hash。
2. **Preflight**：检查 PyFluent import、Fluent executable、版本兼容矩阵、license、CPU/GPU/HPC lease；使用 session/connection 状态做探针，不依赖已弃用的 `health_check` 语义。
3. **Launch/connect**：以固定 mode/dimension/precision/processor count 启动或连接 session；保存 connection properties 的非敏感摘要。
4. **Load**：调用受控 `read_case`/workflow，等待 case loaded/data loaded 事件；校验 zones、boundaries、materials 和 unit system。
5. **Configure**：把 `design_variables` 通过版本化变量目录映射到 settings API path；在一个或多个 BatchOps 中应用，并再次读取可审计摘要。禁止把模型原始字符串当作 API path。
6. **Mesh/solve**：仅运行模板允许的 workflow/solver 阶段；订阅 iteration/monitor 事件，去重后写入事件队列。达到收敛或发现发散时由后端判定，不让模型凭自然语言判断。
7. **Postprocess**：优先通过 reduction 读取白名单标量；必要时读取受限 field data，计算 primary metric、单位、收敛标志、守恒/质量 gate 和 curated plots；完整 field 放在 artifact store，SVAR 写入默认禁用。
8. **Persist**：写 case/data/journal、plan snapshot、capability snapshot、metrics、日志摘要、输入输出 hash 和 `final_info.json`/统一 manifest。
9. **Exit**：正常 `exit` 带 timeout；超时先安全取消，再按 policy 使用强制退出；清理子进程、临时目录和 license session。

### 6.5 统一评分和实验产物

Fluent 的成功不能只由 `return_code == 0` 定义。建议 `final_info.json` 至少包含：

```json
{
  "engine": "ansys_fluent",
  "engine_version": "...",
  "adapter_digest": "...",
  "plan_id": "...",
  "case_sha256": "...",
  "mesh_quality": {"valid": true},
  "converged": true,
  "primary_metric": {"name": "outlet_temperature", "value": 312.4, "unit": "K"},
  "optimization_direction": "minimize",
  "quality_gates": {"residual": true, "conservation": true},
  "artifacts": [{"id": "...", "kind": "plot", "sha256": "..."}]
}
```

只有 `converged`、质量 gate、finite primary metric 和 provenance 均通过，candidate 才能进入现有 selection。Surrogate 结果必须标记为 `prediction`，Fluent 结果标记为 `validation`，并保留两者误差，不得覆盖同名指标。

## 7. MCP 与 Web 集成方式

### 7.1 面向 `ModelToolLoop` 的 MCP 工具

第一版只需暴露以下窄工具：

| 工具 | 类型 | 说明 |
| --- | --- | --- |
| `fluent.inspect_capabilities` | 只读 | 版本、模式、资源、许可状态摘要和可用 profile。 |
| `fluent.inspect_case` | 只读 | zones/boundaries/geometry hash/已有 artifacts/缺失项。 |
| `fluent.validate_plan` | 只读 | schema、单位、范围、资源、审批和安全检查。 |
| `fluent.preview_changes` | 只读 | 将修改哪些白名单变量、预计资源和覆盖风险。 |
| `fluent.submit_job` | 写入/需审批 | 创建异步 job，返回 `job_id` 和固定 plan snapshot。 |
| `fluent.get_status` | 只读 | 当前 stage、进度、monitor 摘要、警告和短错误。 |
| `fluent.cancel_job` | 写入/需审批 | 请求安全取消，不接受任意 signal/command。 |
| `fluent.read_metrics` | 只读 | 读取白名单标量、收敛曲线摘要和 quality gates。 |
| `fluent.export_artifacts` | 只读/需策略 | 导出 curated plot、manifest 或按需 case/data。 |

`submit_job` 必须返回而不是阻塞到 solver 结束；模型随后使用 `get_status` 和 `read_metrics`。MCP server 不提供 `run_tui`、`run_journal`、`run_python`、`run_shell` 或任意文件浏览工具。

### 7.2 现有 Web sidecar 的投影

当前 Web/desktop sidecar 已有 MCP 管理和 launch/status 观察面。Fluent 不需要另一棵历史树：

- launch timeline 增加 `fluent` stage 和 `job_id`；
- API 返回 status、短 monitor 序列、质量 gate 和 artifact manifest；
- 大日志、mesh、case/data 通过按权限检查的下载/可视化接口按需取；
- 浏览器刷新、网络中断后由 `job_id` 重新读取持久化状态，不重新启动 Fluent；
- 取消、重试和 license blocked 状态在同一 timeline 中可见。

## 8. 许可证、资源和安全护栏

### 8.1 许可证和版本

- Ansys/Fluent 是商业软件，运行需要有效许可；许可 feature、token、借用策略和再分发权限取决于组织合同，不能从 PyFluent 的开源 Python 代码推断。
- PyFluent 包、Fluent 安装、容器镜像、HPC plugin 和 case template 都写入 capability snapshot；升级必须通过固定 smoke case 和 schema diff。
- 只在有 license 的 worker 上运行 solver；没有 license 时不回退到“让 LLM 安装软件”。

### 8.2 资源 lease

- 每个 job 显式申请 CPU cores、RAM、临时磁盘、GPU（如启用）和 wall time；processor count 不能默认取宿主机所有核。
- license lease 与 CPU/GPU lease 一起记录，防止两个 candidate 争用同一 Fluent feature 或 GPU。
- 第一版 `parallelism=1`，参数化 study 先限制 design point 数和总 wall time；成功后再接入 Slurm/UGE/LSF/PBS 等调度。

### 8.3 路径、网络与 secret

- case、geometry、journal、日志和 artifacts 只能位于 launch-local root；拒绝绝对路径、`..`、symlink 逃逸、未知挂载和任意容器参数。
- worker 默认禁止外网；远程 Fluent 连接只允许配置中的 host/port，TLS/证书策略显式记录。
- `ANSYSLMD_LICENSE_FILE`、NGC/API key、server password 不写入 research event、journal、日志和 model-visible output。
- 上传 STL/CAD 有大小、面数、格式、单位、姿态和几何质量上限；失败在 `validate_plan` 返回。

### 8.4 物理可信性

至少由程序检查：网格质量、区域/边界映射、单位一致性、残差和 monitor 收敛、质量守恒/能量守恒、有限值和 primary metric 方向。LLM 的文字解释只能作为叙述，不能替代这些 gate。

## 9. 分阶段路线图

### P0：授权与环境 smoke

1. 选择一个固定的、可公开复现的 Fluent case template 和 primary metric。
2. 锁定 Fluent/PyFluent/container/HPC 版本，确认 Linux/Windows worker、license、CPU/GPU 和文件传输策略。
3. 只用人工启动或最小 PyFluent script 跑通 load → configure → solve → write case/data → exit，并保存 journal、日志和 hash。

### P1：deterministic adapter（不接 LLM）

1. 实现 `FluentExecutionService` 的 `inspect_capabilities`、`inspect_case`、`validate_plan`、`submit_job`、`get_status`、`read_metrics`。
2. 只支持一个 case profile、一个 solver mode、一个 primary metric 和串行 lease。
3. 用 fake session/recorded journal 测试版本校验、settings patch、timeout、cancel、事件去重、artifact hash 和 `final_info.json`。

### P2：接入 ExperimentRunner

1. 为 CFD task 增加 manifest/registry，不再通过 prompt 文本猜任务类型。
2. 将 `FluentJob` 映射到现有 `run_N`、`final_info.json`、round summary 和 resume；增加 stage-level resume。
3. 在 selection 中强制 quality gate、primary metric direction 和 prediction/validation provenance。

### P3：MCP 与 Web 观察面

1. 用同一个 service 提供本地 stdio MCP façade。
2. 将 job status、monitor 摘要、审批、取消、重试和 artifact manifest 投影到现有 launch timeline/Web sidecar。
3. 做浏览器刷新、网络中断、worker 重启和 license blocked 的端到端测试。

### P4：参数化与 HPC

1. 接入受限 `LocalParametricStudy`/`run_in_fluent`，由 scheduler 管理 design points 和资源。
2. 在有稳定 checkpoint 后再启用多个 candidate；每个 candidate 仍独占可写 case 和 lease。
3. 测量 gRPC BatchOps、文件传输、容器和远程 HPC 的性能与失败恢复。

### P5：surrogate lane

1. 在独立 worker 接入 PhysicsNeMo-CFD/DoMINO NIM，先做 health/schema/输入边界验证。
2. surrogate 只做 candidate screening 或高保真初始化；Fluent 仍是 validation lane。
3. 保存 prediction/validation 差异，只有经 Fluent quality gate 复核的结果才进入验证记忆。

## 10. 验收标准

称为“Fluent 已嵌入实验 loop”至少需要满足：

- 不完整 case、非法单位/变量、网格/几何质量问题和超资源计划在启动 Fluent 前被拒绝；
- 相同 plan/case/adapter digest 生成可比较的 manifest；
- LLM 不可执行任意 shell/TUI/Python/journal、绝对路径、网络或 secret 参数；
- `validating`、`launching`、`meshing`、`configuring`、`solving`、`postprocessing`、`scoring` 每阶段都有持久化状态、序列号、退出码、短日志和 artifact 引用；
- events/monitors 可去重、可恢复，并能在浏览器刷新/网络中断后继续观察同一个 job；
- timeout、cancel、SIGTERM、Fluent crash、远程断线和子进程清理都有可测试行为；
- `final_info.json` 的 primary metric、direction、单位、converged、质量 gate 和 provenance 可被 scorer 机器读取；
- 并行 design points 不共享可写 case、processor/临时目录、MPI ranks、GPU 或 license lease；
- Web/LLM 只获得 curated metrics/artifacts，大 field/mesh 按需取；
- surrogate 与 Fluent 结果明确区分 prediction/validation 并保存误差；
- 许可证或运行依赖缺失时进入 `blocked/preflight_failed`，不会触发未经批准的安装/网络命令。

## 11. 最终决策建议

如果当前目标是尽快开始核心后端集成，建议先实现一个**固定 case + 单指标 + 单 worker + PyFluent session + 异步 job**的 vertical slice。它能在不改动模型 runtime 的前提下验证最关键的事实：本机/远程 license 是否可用、版本组合是否兼容、settings patch 是否稳定、monitor/事件是否可持久化、结果是否能进入现有 `final_info.json` 和 round selection。

不要先做“让 LLM 自由探索 Fluent settings 树”，也不要先做多目标并行优化。等 deterministic adapter 通过验收后，再开放变量目录、审批策略和参数扫描；surrogate 则作为独立 lane 接入。

报告结论：**Fluent 的 PyFluent API 为 Vegapunk 提供了较好的工程集成起点，但真正的 LLM-ready 能力来自 Vegapunk 自己的 typed plan、异步 job、资源/许可证治理、安全 allowlist、物理质量 gate 和 artifact provenance，而不是来自 Fluent API 本身。**

## 12. 官方来源索引

- [Ansys Fluent 产品页](https://www.ansys.com/products/fluids/ansys-fluent)
- [PyFluent 稳定文档首页](https://fluent.docs.pyansys.com/version/stable/)
- [PyFluent 安装](https://fluent.docs.pyansys.com/version/stable/getting_started/installation.html)
- [PyFluent session 启动和连接](https://fluent.docs.pyansys.com/version/stable/user_guide/session/launching_ansys_fluent.html)
- [PyFluent launcher API](https://fluent.docs.pyansys.com/version/stable/api/launcher/launcher.html)
- [PyFluent session 生命周期](https://fluent.docs.pyansys.com/version/stable/user_guide/session/session.html)
- [Solver settings 内容](https://fluent.docs.pyansys.com/version/stable/user_guide/solver_settings/solver_settings_contents.html)
- [Solver flobject API](https://fluent.docs.pyansys.com/version/stable/api/solver/flobject.html)
- [PyFluent usability/search](https://fluent.docs.pyansys.com/version/stable/user_guide/usability.html)
- [Meshing workflows](https://fluent.docs.pyansys.com/version/stable/user_guide/meshing/new_meshing_workflows.html)
- [Events](https://fluent.docs.pyansys.com/version/stable/user_guide/events.html)
- [Events streaming API](https://fluent.docs.pyansys.com/version/stable/api/streaming_services/events_streaming.html)
- [Monitors](https://fluent.docs.pyansys.com/version/stable/user_guide/monitors.html)
- [Monitor service API](https://fluent.docs.pyansys.com/version/stable/api/services/monitor.html)
- [BatchOps API](https://fluent.docs.pyansys.com/version/stable/api/services/batch_ops.html)
- [Logging](https://fluent.docs.pyansys.com/version/stable/user_guide/log.html)
- [Journaling](https://fluent.docs.pyansys.com/version/stable/user_guide/journal.html)
- [File transfer](https://fluent.docs.pyansys.com/version/stable/user_guide/file_transfer.html)
- [Field data](https://fluent.docs.pyansys.com/version/stable/user_guide/fields/field_data.html)
- [Field reductions](https://fluent.docs.pyansys.com/version/stable/user_guide/fields/reduction.html)
- [Solution variable data](https://fluent.docs.pyansys.com/version/stable/user_guide/fields/solution_data.html)
- [Field data versus solution variable data](https://fluent.docs.pyansys.com/version/stable/user_guide/fields/field_vs_svars_data.html)
- [Transfer data between meshing and solver sessions](https://fluent.docs.pyansys.com/version/stable/user_guide/transfer_data.html)
- [Parametric API](https://fluent.docs.pyansys.com/version/stable/api/parametric.html)
- [FluentConnection API](https://fluent.docs.pyansys.com/version/stable/api/fluent_connection.html)
- [Container image and license](https://fluent.docs.pyansys.com/version/stable/user_guide/make_container_image.html)
- [PyFluent README at fixed commit `feab8839d524e1f1d24d18fa77ccb4095778c923`](https://github.com/ansys/pyfluent/blob/feab8839d524e1f1d24d18fa77ccb4095778c923/README.rst)
