# Ansys Fluent 集成 Vegapunk 与 LLM：外部仿真调用决策机制补充报告

> 调研日期：**2026-08-04**。本文专门回答“系统是否需要调用 Fluent、何时调用 Fluent”这两个问题。它补充 [Ansys Fluent 集成主报告](ANSYS_FLUENT_LLM_INTEGRATION_REPORT.md)，不把 Fluent 的 API 能力误当成调用策略。

## 1. 结论先行

外部仿真调用不能由 LLM 在对话中自由决定，也不能简单地把 `fluent.run` 加入现有工具列表。建议增加一个由平台代码负责的 **Simulation Invocation Controller（SIC，外部仿真调用决策控制器）**：

```text
LLM 提出仿真意图
        |
        v
SIC：相关性 / 证据等级 / 缓存 / 资源 / 许可证 / 审批 / 成本门控
        |
        +--> NO_CALL       不调用
        +--> CACHE_HIT     复用已验证结果
        +--> SURROGATE     先走快速 surrogate
        +--> FLUENT        提交高保真 Fluent job
        +--> NEEDS_APPROVAL 等待审批
        +--> BLOCKED       前置条件不满足
```

核心原则是：**LLM 可以提出“需要什么证据”，但不能拥有“启动商业仿真软件”的最终权限；ExperimentRunner 负责实验编排，SIC 负责调用决策，Fluent adapter 负责执行和结果校验。**

默认时机应是“候选方案已经落地为可校验的 `SimulationPlan`、且已经通过便宜的代码/输入检查之后”，而不是每个推理 token、每次工具调用或每个 Fluent iteration 都重新让 LLM 决策。

## 2. 为什么现有 experiment loop 不能直接承接 Fluent

当前系统已经有代码实验的 loop，但它把“实验”基本等同于“准备代码目录并运行代码”。这与需要许可证、长时间 session、网格/边界条件、收敛判据和资源 lease 的 Fluent job 不是同一种过程。

| 当前事实 | 代码证据 | 对 Fluent 集成的影响 |
| --- | --- | --- |
| 任务类型只区分 `sci` 与 `auto` | [`detect_task_type`](../../../launch_discovery.py#L38-L47) | 没有 CFD 相关性、证据等级或高保真要求字段 |
| 每个 idea 都进入实验执行 | [`ExperimentRunner.run_experiments`](../../../vegapunk/stage.py#L1173-L1239) | 现有 loop 没有“本候选是否值得启动外部 solver”的门控 |
| 后端分支是 OpenHands/Codex/iFlow | [`run_codex_experiment`](../../../vegapunk/stage.py#L899-L993)、[`_run_single_experiment`](../../../vegapunk/stage.py#L1061-L1171) | 当前边界是代码编辑/运行，不是外部仿真 job 生命周期 |
| LLM 工具调用只受迭代数和调用数限制 | [`ModelToolLoop.run`](../../../vegapunk/mas/agents/tool_loop.py#L52-L131) | 把 Fluent 工具暴露给模型后，模型仍可能重复提交昂贵 job |
| 性能按同名指标变化率求平均 | [`_calculate_experiment_performance`](../../../vegapunk/stage.py#L597-L642) | 未表达 Fluent 的收敛、守恒、网格质量和指标方向 |
| 默认允许 10 轮、最多 4 个并行实验 | [`default_config.yaml`](../../../config/default_config.yaml#L144-L160) | 不能将现有并发配置直接套到 Fluent license、CPU/MPI 和临时磁盘 |

因此，Fluent 不是一个普通 backend 名称，而是一个新的 **外部、异步、受资源和物理质量约束的实验阶段**。它需要在现有 `ExperimentRunner` 与 solver 之间增加决策和作业边界。

## 3. 决策职责：谁可以决定什么

| 角色 | 可以做的事 | 不应做的事 |
| --- | --- | --- |
| LLM | 说明候选方案是否涉及流体物理；提出期望观测量、设计变量和证据等级；建议“需要 Fluent” | 直接拼 TUI/journal/shell；覆盖许可证、资源、审批和安全策略；自行决定重跑次数 |
| Task/CFD profile | 声明该任务 `none`、`optional` 还是 `required`；声明 primary metric、单位、方向和最低证据等级 | 由自然语言临时修改硬约束 |
| SIC | 根据硬门控和预算返回调用/不调用决定；检查缓存、版本、资源、license、审批和成本 | 执行 Fluent settings 或解释数值结果 |
| Fluent adapter | 将批准的 typed plan 编译为白名单 settings/workflow；启动 session；采集 events/monitors；提取 metrics/artifacts | 判断“这次科学问题是否值得仿真”；接受任意命令和任意路径 |
| Scorer/quality gate | 检查收敛、守恒、网格质量、有限值、primary metric 和 provenance；决定结果能否进入候选选择 | 仅凭进程退出码认定物理结果有效 |
| 人工审批（可选） | 批准新 case、昂贵资源、最终发表级验证或策略升级 | 代替机器做可重复的 schema/资源检查 |

Ansys 官方资料说明 PyFluent 可以通过 session、events、monitors、文件传输和参数化 API 承载长任务；这些资料定义了“如何执行”，并没有定义 Vegapunk“什么时候应该执行”。后者必须是平台自己的策略层。[PyFluent session](https://fluent.docs.pyansys.com/version/stable/user_guide/session/session.html)、[events](https://fluent.docs.pyansys.com/version/stable/user_guide/events.html)、[monitors](https://fluent.docs.pyansys.com/version/stable/user_guide/monitors.html)、[parametric API](https://fluent.docs.pyansys.com/version/stable/api/parametric.html)

这也符合 LLM function calling 的应用边界：官方接口把模型输出定义为待应用执行的 function call，应用执行后再用 `function_call_output` 把结果送回模型；`tool_choice=auto` 只是默认的选择方式，不是业务授权。严格 JSON Schema、关闭并行 tool calls 和敏感副作用的人工审批都应由应用层设置。[Function calling](https://developers.openai.com/api/docs/guides/function-calling)、[Guardrails and human approval](https://developers.openai.com/api/docs/guides/agents/guardrails-approvals/)

## 4. 两个必须显式化的对象

### 4.1 `SimulationIntent`：模型提出的意图

它是模型的建议，不是授权令牌。模型只能引用任务 profile 中已有的变量和指标：

```json
{
  "schema_version": "vegapunk.cfd.intent.v1",
  "relevance": "required",
  "evidence_phase": "screening",
  "reason_codes": [
    "changes_inlet_boundary_condition",
    "objective_is_pressure_drop"
  ],
  "changed_variables": ["inlet.velocity_m_per_s"],
  "expected_observation": "outlet_pressure_drop_pa",
  "requested_fidelity": "high",
  "max_wait_s": 3600,
  "rationale": "..."
}
```

`relevance`、`requested_fidelity` 和 `rationale` 可以被 SIC 降级或拒绝；不能由模型把 `optional` 强行升级成 `required`。

### 4.2 `InvocationDecision`：平台给出的决定

```json
{
  "action": "FLUENT",
  "reason_codes": [
    "final_candidate",
    "high_fidelity_required",
    "plan_digest_changed"
  ],
  "policy_version": "cfd-invocation-v1",
  "plan_digest": "sha256:...",
  "case_ref": "case:...",
  "resource_estimate": {"cpu_cores": 8, "wall_time_s": 3600},
  "approval": "required",
  "cache": {"hit": false},
  "next_check": "await_quality_gate"
}
```

建议的 `action` 集合固定为 `NO_CALL`、`CACHE_HIT`、`SURROGATE`、`FLUENT`、`NEEDS_APPROVAL`、`BLOCKED`。每个决定都写入 launch artifact，记录 policy version、plan/case/adapter digest、理由码和资源估算，避免后续只剩一句“模型说应该跑 Fluent”。

## 5. 调用与否：硬门控优先，成本/信息价值其次

SIC 先执行不可被 LLM 覆盖的硬门控，再进行证据和成本判断。建议顺序如下：

1. **任务相关性门控**：任务 profile 为 `none`，或候选没有改变任何 CFD 输入、物理模型或 CFD 目标，返回 `NO_CALL`。
2. **安全与完整性门控**：case、几何、单位、变量目录、solver profile 或输出契约不完整，返回 `BLOCKED`，不启动 Fluent。
3. **能力与资源门控**：PyFluent/Fluent 版本不匹配、license 不可借用、CPU/GPU/HPC/临时磁盘不满足，返回 `BLOCKED` 或 `NEEDS_APPROVAL`。
4. **缓存门控**：canonical case、mesh、solver profile、变量 patch、adapter digest 和输出 profile 均相同，且已有结果通过 quality gate，返回 `CACHE_HIT`。
5. **证据等级门控**：任务要求最终高保真证据，或候选处于最终选择/发表级验证阶段，选择 `FLUENT`。
6. **快速筛选门控**：任务处于早期探索阶段、surrogate 可用且 profile 允许近似，选择 `SURROGATE`；surrogate 只能提供 prediction，不能替代最终 validation。
7. **信息价值门控**：如果结果会改变候选排序或验证结论，且预期信息价值高于时间、license 和资源成本，选择 `FLUENT`；否则 `NO_CALL` 或先使用 `SURROGATE`。

这里的“信息价值”可以用简单的策略阈值实现，不必一开始训练一个新的决策模型：

```text
调用价值 = 预计减少的决策不确定性
          - wall time 成本
          - license/CPU/GPU 成本
          - 失败和取消风险
```

LLM 可以提供“不确定性”和“候选排序可能改变”的解释性估计，但阈值、预算和安全约束由配置和 SIC 计算，不能让模型通过自然语言绕过。

### 5.1 触发矩阵

| 场景 | 默认动作 | 说明 |
| --- | --- | --- |
| 纯代码重构、文档、测试、与流体输入无关的想法 | `NO_CALL` | Fluent 不会增加目标证据 |
| 改变了与 Fluent 无关的代码，但 CFD plan digest 未变化 | `CACHE_HIT` 或 `NO_CALL` | 不因代码实验每次迭代而重复求解 |
| 改变入口速度、几何、材料、边界条件、网格 profile 或 solver settings | 重新评估；通常 `SURROGATE` 或 `FLUENT` | 物理输入变化使旧结果变 stale |
| 早期候选筛选，surrogate 在适用域内 | `SURROGATE` | 用于排序/初始化，不作为最终验证 |
| 候选接近决策阈值、Pareto 边界或多个候选难以区分 | `FLUENT` | 高信息价值，值得消耗高保真资源 |
| 任务声明发表级/安全关键/最终验证必须使用 Fluent | `FLUENT` | profile 的硬要求高于模型建议 |
| 通过日志显示“成功”，但没有收敛、守恒或 primary metric | `BLOCKED`/`RETRY` | 进程成功不等于物理结果有效 |
| 有相同 plan/case/adapter digest 的通过质量门结果 | `CACHE_HIT` | 结果可复用，但必须保留 provenance |
| license、版本、网格、资源或审批缺失 | `BLOCKED`/`NEEDS_APPROVAL` | 不让 LLM 猜安装、license 或 shell 命令 |

## 6. 何时调用：放在 loop 的哪个阶段

建议把外部仿真变成一个显式阶段，而不是塞进模型的每次工具循环：

```text
任务 intake
  -> 读取 task/CFD profile 与 capability snapshot（只读）
  -> LLM 生成候选与 SimulationIntent
  -> 候选代码/输入编译 + 便宜检查
  -> SIC 决定 NO_CALL / CACHE_HIT / SURROGATE / FLUENT
  -> validate/preview/approval
  -> 异步 Fluent job（events + monitors）
  -> quality gate + metrics/artifacts
  -> scorer：接受、修订、重试、拒绝或进入下一轮
```

具体时点如下：

### T0：任务 intake，只做分类，不启动 Fluent

读取 `simulation_profile`、primary metric、证据等级、预算和可用 case profile；可做 `inspect_capabilities`，但不启动 solver。能力探针只返回版本、模式、可用资源和 license 摘要，不把 secret 暴露给模型。

### T1：候选方案已物化后，才做第一次调用决策

候选必须已经生成确定的设计变量、case 引用、单位、输出指标和资源上限。此时先做 schema、几何/网格、代码编译和低成本 sanity check，再调用 SIC。不能因为 LLM 在分析阶段提到“可能需要 CFD”就立即启动 Fluent。

### T2：提交前做一次 preview/approval

SIC 返回 `FLUENT` 后，服务端仍要执行 `validate_plan` 和 `preview_changes`，展示将修改的白名单变量、预计资源、license slot、wall time 和产物。新 case、昂贵资源、模型/网格 profile 变化或发表级验证可以要求人工审批。

### T3：求解期间由 job 状态机驱动，不由 LLM 逐迭代干预

Fluent 支持 events/monitors；adapter 应把它们转为 `loading_case`、`meshing`、`solving`、`converged`、`stalled` 等持久化事件。LLM 只查询 `get_status`/`read_metrics`，不在每个 iteration 重新调用 `submit_job`。参数扫描应由后端的 parametric API/worker 作为一个受控 job 批量执行，而不是由模型逐点循环。[PyFluent events](https://fluent.docs.pyansys.com/version/stable/user_guide/events.html)、[monitors](https://fluent.docs.pyansys.com/version/stable/user_guide/monitors.html)、[parametric API](https://fluent.docs.pyansys.com/version/stable/api/parametric.html)

Fluent 的批处理文档也把“后台/批量执行、transcript/residual 输出、等待进程结束和退出码”作为独立运行模式；checkpoint 文档则提供了保存并继续、保存并退出的文件触发机制。因此 job 状态、checkpoint 和退出码都应由 adapter 管理，不能让模型把一次进程退出误解成物理成功。[Batch execution](https://ansyshelp.ansys.com/public/Views/Secured/corp/v242/en/flu_ug/flu_ug_BatchExecution.html)、[Checkpointing](https://ansyshelp.ansys.com/public/Views/Secured/corp/v242/en/flu_ug/flu_ug_checkpointing.html)

### T4：质量门之后才决定下一步

只有当收敛、守恒、网格质量、finite primary metric 和 provenance 均通过，结果才可进入 scorer。质量门失败时，下一动作应是：

- 可解释且允许的数值问题：按固定策略 `RETRY_SAME_PLAN` 或 `REPAIR_PLAN`；
- 输入/物理模型错误：回到 LLM/人工修订，但必须生成新的 plan digest；
- 结果已足够区分候选：`ACCEPT`，不再重复调用；
- 结果不影响候选排序且预算不足：`STOP_WITH_EVIDENCE_GAP`，明确记录未验证，而不是伪装成功。

### T5：后续 round 只在输入或证据状态变化时调用

以下情况才允许再次调用 Fluent：设计变量/几何/网格/solver profile 变化导致 digest 变化；上一次结果 stale/未通过 quality gate；候选进入更高证据等级；或新结果可能改变最终选择。仅仅因为进入下一轮、LLM 生成了新的解释或代码目录发生了与 CFD 无关的变化，不应触发新的 Fluent job。

## 7. baseline 与调用时机的关键取舍

现有系统把 `run_0` 作为代码实验 baseline。Fluent 集成后必须先确定 baseline 的 fidelity，否则会出现“baseline 是代码指标、candidate 是 Fluent 指标”的不可比问题。

建议在 task profile 中显式声明：

```json
{
  "simulation_profile": "fluent_required",
  "baseline_fidelity": "fluent",
  "candidate_fidelity": "fluent",
  "primary_metric": "outlet_pressure_drop_pa",
  "optimization_direction": "minimize"
}
```

三种模式的推荐行为：

| profile | baseline | 早期候选 | 最终候选 |
| --- | --- | --- | --- |
| `none` | 现有代码 baseline | 不调用 | 不调用 |
| `optional` | 代码或 surrogate baseline | surrogate/缓存优先 | Top candidate 至少一次 Fluent validation |
| `required` | Fluent baseline | 受预算限制的 Fluent 或经校准 surrogate 筛选 | Fluent validation 必须通过 |

如果早期使用 surrogate 排序，必须在统一 manifest 中保留 `prediction` 与 `validation` 两类 provenance；不能把不同 fidelity 的数值直接混入当前 `_calculate_experiment_performance()` 的平均变化率。

## 8. 建议的状态机

```text
candidate_created
  -> relevance_classified
  -> plan_validated
  -> no_call
  -> cache_hit
  -> surrogate_queued -> surrogate_scored
  -> waiting_approval
  -> fluent_queued
       -> launching -> loading_case -> meshing -> configuring
       -> solving -> postprocessing -> quality_gate
  -> completed

任意外部阶段还可能进入：
  preflight_failed / blocked / cancel_requested / cancelled
  interrupted / failed / stale / retry_pending
```

状态语义应明确区分：

- `blocked`：还没有启动 Fluent，原因是 license、版本、输入、资源或审批问题；
- `failed`：已经启动但进程、连接或后处理失败；
- `stale`：结果曾经有效，但 plan/case/adapter digest 已变化；
- `quality_failed`：作业完成，但收敛/守恒/网格/指标门未通过；
- `completed`：作业和质量门都通过，结果可供 scorer 使用。

## 9. 与现有 Vegapunk seam 的落点

建议增加一个轻量的决策层，而不是把判断散在 prompt 和 backend 分支中：

```text
IdeaGenerator
    -> SimulationIntent（LLM 建议）
    -> SimulationInvocationController（确定性门控）
    -> ExperimentRunner / CfdExecutionService
    -> FluentAdapter
    -> scorer / memory / round summary
```

建议模块职责：

| 模块 | 新增责任 |
| --- | --- |
| `vegapunk/cfd/models.py` | `SimulationIntent`、`InvocationDecision`、`SimulationPlan`、`CfdJob`、`CfdMetrics` |
| `vegapunk/cfd/policy.py` | 相关性、证据等级、缓存、EVI/成本、审批和 per-launch quota 门控 |
| `vegapunk/cfd/validation.py` | plan、单位、变量白名单、case/mesh、资源和 artifact 预检 |
| `vegapunk/cfd/runner.py` | 异步 job、lease、timeout/cancel、状态事件和 stage-level resume |
| `vegapunk/cfd/fluent_adapter.py` | PyFluent session、settings/workflow、events/monitors、reduction 和输出写入 |
| `vegapunk/cfd/mcp_server.py` | 仅暴露 `inspect`、`validate`、`preview`、`submit`、`status`、`metrics` 等窄工具 |

`submit_job` 应要求服务端生成的 `decision_id`、`plan_digest` 和审批状态；即使 LLM 伪造了 `submit_job` 参数，服务端也必须重新执行策略校验。这样 `ModelToolLoop` 仍可以复用，但不会把“模型会调用工具”误当成“模型有权启动 solver”。

## 10. 第一版建议采用的保守默认策略

在没有历史成本/收益数据前，建议采用以下 P0 策略：

1. task manifest 必须显式写 `simulation_profile: none|optional|required`；没有该字段时按 `none`，不由 LLM 猜测。
2. 只支持一个固定 Fluent case、一个 solver mode、一个 primary metric 和一个版本化变量目录。
3. `none` 永不调用；`optional` 早期只用缓存/便宜 surrogate，最终最多一次 Fluent validation；`required` 才允许 Fluent baseline + candidate validation。
4. 每个 candidate 一次只允许一个 active Fluent job；首版 `parallelism=1`，每轮设 high-fidelity quota 和 wall-time quota。
5. `submit_job` 永远异步返回 job ID；模型通过状态/指标工具观察，不占住一次同步模型请求。
6. 结果必须通过 quality gate 才能进入候选选择；失败和未验证都要显式记录。
7. 后续 round 只在 plan digest 变化、结果 stale 或证据等级升级时重新调用；缓存命中优先。
8. LLM 的“需要 Fluent”只作为 `SimulationIntent`；策略控制器、资源/许可证服务和人工审批可以拒绝它。

这套默认策略牺牲了一些早期探索速度，但能先验证最关键的系统事实：许可证和版本是否可用、一个固定 case 是否能稳定运行、结果是否能进入现有 `final_info.json`/round summary，以及 job 是否能恢复和审计。

## 11. 仍需项目作出决定的问题

下面这些不是 Fluent API 能替项目回答的问题，建议在实现前形成 ADR 或 task profile 规范：

1. 哪些字段/代码变化被定义为“影响 CFD 输入”？是否维护从代码变量到 Fluent settings path 的依赖图？
2. 哪类任务必须做 Fluent validation，哪类任务允许 surrogate 或只做代码实验？
3. `optional` profile 的每轮和每个 launch 允许多少次高保真调用？license slot、CPU、GPU 和 wall time 如何计费？
4. 新几何、新网格、新物理模型或发表级结果是否强制人工审批？
5. quality gate 的最小集合是什么：残差、守恒、网格质量、monitor 稳定、单位和 finite metric 的阈值如何配置？
6. baseline 是否必须与 candidate 使用同一 fidelity；如果 surrogate 只用于筛选，何时做成对 Fluent 验证？
7. Fluent 失败后的策略是固定重试、修订计划，还是回退到 surrogate/代码实验？每种原因的上限是什么？

## 12. 最终建议

对当前 Vegapunk，最重要的设计决策不是“如何让 LLM 调用 Fluent”，而是**把“是否值得调用外部仿真”建模成一个可审计、可配置、可拒绝的策略决策**：

- 在候选方案物化并通过便宜检查后判断，而不是在 prompt/token 层判断；
- 在终态候选、边界候选或明确要求高保真证据时调用 Fluent；
- 早期探索优先缓存和 surrogate，避免把 10 轮 × 多候选的现有代码 loop 直接放大成 license/CPU 风暴；
- 由 SIC 决定 `NO_CALL/CACHE_HIT/SURROGATE/FLUENT/BLOCKED`，由 adapter 执行，LLM 只提交意图；
- baseline、candidate、prediction、validation 的 fidelity 和 provenance 必须一致或显式区分。

一句话结论：**Fluent 的调用时机应由“证据需求 + 候选状态 + 输入变化 + 资源/成本 + 质量策略”共同决定，不能由“LLM 想不想调用”单独决定。**

## 13. 资料索引

项目内事实：

- [主报告：Ansys Fluent 集成 Vegapunk 与 LLM 实验 loop](ANSYS_FLUENT_LLM_INTEGRATION_REPORT.md)
- [`launch_discovery.detect_task_type`](../../../launch_discovery.py#L38-L47)
- [`ExperimentRunner.run_experiments`](../../../vegapunk/stage.py#L1173-L1239)
- [`ExperimentRunner.run_codex_experiment`](../../../vegapunk/stage.py#L899-L993)
- [`ExperimentRunner._run_single_experiment`](../../../vegapunk/stage.py#L1061-L1171)
- [`ExperimentRunner._calculate_experiment_performance`](../../../vegapunk/stage.py#L597-L642)
- [`ModelToolLoop.run`](../../../vegapunk/mas/agents/tool_loop.py#L52-L131)
- [`config/default_config.yaml`](../../../config/default_config.yaml#L144-L160)

官方资料：

- [PyFluent 稳定文档](https://fluent.docs.pyansys.com/version/stable/)
- [启动/连接 Fluent](https://fluent.docs.pyansys.com/version/stable/user_guide/session/launching_ansys_fluent.html)
- [Session 生命周期](https://fluent.docs.pyansys.com/version/stable/user_guide/session/session.html)
- [Events](https://fluent.docs.pyansys.com/version/stable/user_guide/events.html)
- [Monitors](https://fluent.docs.pyansys.com/version/stable/user_guide/monitors.html)
- [Parametric API](https://fluent.docs.pyansys.com/version/stable/api/parametric.html)
- [Fluent 批处理执行](https://ansyshelp.ansys.com/public/Views/Secured/corp/v242/en/flu_ug/flu_ug_BatchExecution.html)
- [Fluent checkpointing](https://ansyshelp.ansys.com/public/Views/Secured/corp/v242/en/flu_ug/flu_ug_checkpointing.html)
- [Fluent 参数化 study](https://ansyshelp.ansys.com/public/Views/Secured/corp/v242/en/flu_ug/flu_ug_parametric_study.html)
- [Field reductions](https://fluent.docs.pyansys.com/version/stable/user_guide/fields/reduction.html)
- [文件传输](https://fluent.docs.pyansys.com/version/stable/user_guide/file_transfer.html)
