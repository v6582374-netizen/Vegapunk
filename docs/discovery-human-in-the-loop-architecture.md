# Discovery 引入 Human-in-the-loop 的架构开口分析

状态：架构审计与设计建议（2026-08-03）  
范围：CLI Discovery、MAS 工作流、Native Desktop sidecar、PaperOrchestra 交接  
目标：找到可以暂停、展示阶段性产物、接受人工意见并可安全断点续传的稳定 seam；本文件不实现功能。

## 1. 结论先行

当前 Discovery 有两条执行平面：

1. `launch_discovery.py` 驱动的 CLI 平面，连接 MAS、`ExperimentRunner`、经验库、incremental baseline 和 PaperOrchestra。
2. Native Desktop sidecar 平面，连接 GUI、Discovery HTTP API、持久化 Launch 状态和 runner 生命周期；它目前用 fake runner 验证生命周期契约，尚未接入 CLI 的真实 Discovery 执行器。

建议把人工介入放在“阶段性产物已经稳定、下一步会产生新副作用”的边界，而不是散落到各个 Agent 或工具调用内部。首批 seam 的优先级如下：

| 优先级 | seam | 人工要决定的事情 | 推荐理由 |
| --- | --- | --- | --- |
| P0 | MAS 排名/反馈后 | 哪些 idea 继续、扩大还是收窄，补充什么反馈 | 已有 `AWAITING_FEEDBACK` 状态、反馈历史和持久化 session；改动集中在外层驾驶员 |
| P0 | Discovery 完成、PaperOrchestra 交接前 | 是否进入论文阶段、使用哪个候选 | 当前无条件 handoff；这是研究判断的最后一道高价值闸门 |
| P1 | 方法规格完成、实验开始前 | 是否允许把哪些 refined methods 交给实验后端 | `ExperimentRunner` 之后会消耗代码、算力和外部服务，是最清晰的副作用边界 |
| P1 | 每轮实验结束、经验/baseline 更新前 | 结果是否可信，是否前移 baseline，是否继续下一轮 | 经验和 baseline 会影响后续 prompt、代码和指标，必须先批准再写入 |
| P1（平台能力） | Native Launch 的 stage 边界 | stage 产物是否通过、是否继续/编辑/拒绝 | sidecar 已有 checkpoint、events、timeline、artifacts 和 GUI，可承载统一 review 生命周期 |

最重要的状态判断是：

- `awaiting_feedback` 表示 MAS 内部请求研究反馈；
- `awaiting_review` 表示外层 Discovery 已经生成可审阅产物，主动等待用户决策；
- `stopped` 表示用户主动终止/暂停运行；
- `completed` 表示计算阶段完成，不表示用户已经批准后续交接。

`Stop` 和 `awaiting_review` 不能共用一个布尔值或同一套恢复语义，否则 UI 无法区分“系统等待判断”和“用户要求终止”，也无法保证审计记录完整。

## 2. 当前架构与自动流程

### 2.1 CLI Discovery 执行平面

入口是 [`launch_discovery.py`](../launch_discovery.py#L620) 的 `_main()`。它通过 `resume_state` 从 `discovery_summary.json` 或目录扫描恢复已经完成的轮次；恢复粒度是轮次和共享目录，而不是任意阶段的 review checkpoint。

当前正常流程可以概括为：

```text
加载/创建 Launch 与配置快照
  -> IdeaGenerator.generate_ideas()（MAS）
  -> 保存 session/ideas.json 与轨迹
  -> ExperimentRunner.run_experiments() 或 ReportWriter
  -> 汇总 round_result
  -> 生成经验库
  -> incremental 模式挑选结果并前移 baseline
  -> 写 discovery_summary.json
  -> 无条件 _handoff_to_paper_orchestra()
  -> PaperOrchestra 自动准备材料、候选选择并生成论文
```

几个关键代码边界：

- MAS 返回后到实验调用之间的边界位于 [`_main()`](../launch_discovery.py#L1026) 附近的 `experiment_runner.run_experiments(...)`。
- 每轮结果加入 `all_round_results` 后，当前立即生成经验（[`_main()`](../launch_discovery.py#L1045) 和 [`_generate_experiences_for_round()`](../launch_discovery.py#L253)），随后在 incremental 模式更新 baseline（[`_main()`](../launch_discovery.py#L1082) 和 [`_update_baseline_for_incremental()`](../launch_discovery.py#L159)）。
- 最终摘要写入 [`discovery_summary.json`](../launch_discovery.py#L1172) 后，`_handoff_to_paper_orchestra()` 会直接调用 [`run_paper_orchestra()`](../launch_discovery.py#L343)。如果 `start_round > loop_rounds`，恢复路径还会在 [`_main()`](../launch_discovery.py#L789) 直接进入 handoff，因此该路径也必须纳入 review guard。

### 2.2 MAS 的 `AWAITING_FEEDBACK` 已存在，但尚未成为真正的 HITL

MAS 状态机已经提供了可复用的深模块接口：

- [`OrchestrationAgent.run_session()`](../vegapunk/mas/workflow/orchestration_agent.py#L170) 每个 phase 后保存 session；遇到 `WorkflowState.AWAITING_FEEDBACK` 会保存并返回。
- [`OrchestrationAgent.add_feedback()`](../vegapunk/mas/workflow/orchestration_agent.py#L221) 记录反馈、目标 idea 和迭代号，并把等待状态切换到 `REFLECTING`。
- [`_run_awaiting_feedback_phase()`](../vegapunk/mas/workflow/orchestration_agent.py#L982) 本身是被动 phase，不执行 Agent 任务。
- `FileSystemMemoryManager` 持久化 `traj_<session_id>.json`；`IdeaGenerator` 在会话完成后再把轨迹复制为 session 目录中的 `traj.json`。

问题在于外层驾驶员 [`IdeaGenerator.generate_ideas()`](../vegapunk/stage.py#L284)：

1. 轮询到 `awaiting_feedback` 时，如果存在 `args.offline_feedback`，就自动读取 JSON 并调用 `interface.add_feedback(...)`。
2. [`VegapunkInterface.add_feedback()`](../vegapunk/mas/interface.py#L213) 默认 `auto_resume=True`，会在反馈后自动调用 `resume_session()`。
3. 因此当前 `AWAITING_FEEDBACK` 是“离线反馈插槽”，不是“把产物展示给人并等待明确批准”的 review 状态。没有离线反馈时，外层循环也没有清晰的用户可见停靠协议。

首要修正不是重写 MAS，而是让外层明确区分：

```text
awaiting_feedback -> 持久化 review bundle，退出当前驱动
用户提交反馈 -> add_feedback(auto_resume=False)
用户明确 Resume -> resume_session()
```

### 2.3 Native Desktop sidecar 执行平面

Native 平面的所有权边界是：

```text
DiscoveryView.tsx
  -> /v1/discovery/... HTTP API
  -> DiscoveryFacade
  -> DiscoveryLaunchStore
  -> runner（当前 _run_fake）
```

相关入口：

- API 与认证在 [`server/app.py`](../desktop/openworker/upstream/coworker/server/app.py#L225)；Discovery route 包括 preparation、revisions、launch、status、events、logs、artifacts。
- preparation、immutable revision、execution input/config snapshot 和 Launch 操作由 [`server/discovery.py`](../desktop/openworker/upstream/coworker/server/discovery.py#L313) 的 `DiscoveryFacade` 组织。
- durable lifecycle、attempt、runner marker、checkpoint、timeline、events 和 artifact 由 [`server/discovery_launch.py`](../desktop/openworker/upstream/coworker/server/discovery_launch.py#L101) 的 `DiscoveryLaunchStore` 负责。
- GUI 已有状态轮询、事件回放、原始日志、artifact 查看以及 Stop/Resume 控件（[`DiscoveryView.tsx`](../desktop/openworker/upstream/surfaces/gui/src/components/DiscoveryView.tsx#L1813)、[`DiscoveryView.tsx`](../desktop/openworker/upstream/surfaces/gui/src/components/DiscoveryView.tsx#L2061)）。

sidecar 当前观察 stage 是 `preparing -> research -> finalizing`。每个 Launch 已经写入：

- `input_snapshot.json`、`launch_configuration.json`；
- `checkpoint.json`；
- `runner.log` 与 `events.jsonl`；
- timeline/milestone、activity、attempts；
- 可列举和读取的 produced artifacts。

`DiscoveryLaunchStore.stop()` 会把运行中的 Launch 变成 `stopping`，runner 在 checkpoint 后结束为 `stopped`；`resume()` 只允许从 `stopped` 或 `interrupted` 且存在 checkpoint 的 Launch 创建新的 attempt（[`discovery_launch.py`](../desktop/openworker/upstream/coworker/server/discovery_launch.py#L344)）。sidecar 重启时，若 runner marker 不再匹配，`_reconcile_locked()` 会将其标记为 `interrupted`，要求显式 Resume（[`discovery_launch.py`](../desktop/openworker/upstream/coworker/server/discovery_launch.py#L641)）。

这套设施适合承载 HITL，但要注意：`_run_fake()` 只是生命周期样板，不能把它当作 CLI Discovery 的真实执行器或现成的阶段性研究产物来源。

## 3. 选择 seam 的标准

一个可用的 HITL seam 至少应满足以下条件：

1. 产物已经冻结或可通过 manifest 冻结，用户看到的内容不会在等待期间悄悄变化。
2. 下一步存在明显的外部副作用、昂贵计算或不可逆状态变更。
3. 能保存“停在哪里、依据什么产物、用户作了什么决定、如何继续”的完整 checkpoint。
4. Resume 是幂等的；重复点击不会重复实验、重复写 baseline 或重复 handoff。
5. seam 位于已有模块接口之间，优先修改编排层/adapter，不把 UI 逻辑或人工判断塞进单个 Agent。

按 codebase-design 的术语，下面选择的是有明确输入/输出协议的 seam，而不是把模块内部的每个函数都改成可暂停。这样可以保持模块的 depth：Agent 负责生成，实验器负责执行，编排器负责决定何时把控制权交给人。

## 4. 推荐的 HITL seam 详解

### Seam A：MAS 排名/反馈后暂停（P0）

**位置**

- `IdeaGenerator.generate_ideas()` 轮询 `awaiting_feedback` 的分支（[`stage.py`](../vegapunk/stage.py#L284)）；
- `OrchestrationAgent.run_session()` 的持久化返回点（[`orchestration_agent.py`](../vegapunk/mas/workflow/orchestration_agent.py#L170)）；
- `OrchestrationAgent.add_feedback()` 与 `VegapunkInterface.resume_session()`（[`interface.py`](../vegapunk/mas/interface.py#L213)）。

**用户应看到的阶段性产物**

- 当前迭代的候选 idea、排名、总分和分项分数；
- critique、evidence、references 以及 idea 的父子演化关系；
- `top_ideas`、当前 `iterations_completed`、方法阶段标记；
- MAS 轨迹 `traj_<session_id>.json` / `traj.json`，并带有 session/revision 标识。

注意：标准 `ideas.json` 是 `generate_ideas()` 完成后才由 CLI 写出的，因此在该 seam 暂停时不能只依赖它。应生成一个明确的 `mas_review_bundle.json` 或 review manifest，从持久化 session 状态读取当前候选。

**用户决策**

- 批准全部或部分候选继续；
- 指定 target idea IDs；
- 提供全局或局部反馈，要求扩大、收窄、补证据或重新排名；
- 结束本轮/终止 Discovery。

**暂停与恢复**

- MAS 内部保留 `awaiting_feedback`；外层同时持久化 `review_checkpoint`，标明 session、iteration、候选 artifact 和问题。
- 提交反馈只调用 `add_feedback(auto_resume=False)`；反馈落盘后状态应保持可见。
- 用户再次点击 Resume 才调用 `resume_session()`，继续进入 `REFLECTING`。

**为什么这里是首要开口**

- 现成状态机已经保证“执行一个 phase、保存 session、遇到等待就返回”；
- 反馈历史有时间戳、目标 idea 和迭代上下文；
- 不需要把暂停协议注入 generation/reflection/ranking 等所有 Agent；
- 当前自动 offline feedback 正好说明这里是全自动与 HITL 的转换点。

**边界条件**

`completed` 只表示 MAS 已形成 refined methods，不表示这些 methods 已获准运行实验；两者必须由外层 review 状态区分。

### Seam B：方法规格完成、实验开始前暂停（P1）

**位置**

在 `asyncio.run(idea_generator.generate_ideas())` 返回、保存标准 `ideas.json` 之后，调用 `ExperimentRunner.run_experiments()` 之前；对应 [`_main()`](../launch_discovery.py#L1026) 的实验调用边界。`report` 模式也应在进入 `ReportWriter` 前使用同一套候选批准策略，只是后续副作用不同。

**用户应看到的阶段性产物**

- 每个 refined method 的标题、目标、方法步骤、假设和预期改动；
- 候选与 baseline 的关系、指标定义和成功判据；
- 实验后端、资源/挂载配置、超时与成本估计；
- 将被复制到 `session_*`/`run_*` 的执行输入快照。

**用户决策**

- 选择要运行的 idea 子集；
- 修改方法规格、约束、指标或资源配置；
- 允许执行、要求回到 MAS 重新 refine，或直接结束。

**暂停与恢复**

- 生成不可变的 `execution_review`（候选 ID、方法 revision、配置快照、artifact hashes）。
- `awaiting_review` 期间不得创建实验进程、复制可写 baseline 或调用外部 OpenHands/backend。
- Resume 时将批准后的候选和编辑过的规格固化成新的 execution input，再调用 `ExperimentRunner`。

**理由**

这是“研究想法”变成“真实代码和计算资源”的高风险 seam。把 gate 放在 runner 外面，可以阻止错误的候选进入昂贵副作用，同时避免在 ExperimentRunner 内部处理中断半个工具调用。

### Seam C：每轮实验完成后、经验与 baseline 更新前暂停（P1）

**位置**

当前 `_main()` 在 `all_round_results.append(round_result)` 后：

```text
round_result / session artifacts
  -> _generate_experiences_for_round()
  -> _update_baseline_for_incremental()
```

推荐把 review gate 放在这两个函数之前（[`_main()`](../launch_discovery.py#L1045)、[`_main()`](../launch_discovery.py#L1060)、[`_main()`](../launch_discovery.py#L1082)）。不要等 baseline 更新后再征求意见。

**用户应看到的阶段性产物**

- 每个 idea 的成功/失败、错误和报告路径；
- `final_info.json`、代码 diff、outputs/report/figures，以及与上一 baseline 的指标变化；
- 当前轮候选的排序依据、资源使用和复现实验信息；
- 将被写入经验库的事实和摘要预览；
- incremental 模式下一轮将使用的 code path、指标和 `run_0` 内容预览。

**用户决策**

- 哪些结果可信、哪些结果应标为失败/不可比较；
- 是否把某个结果写入 experience library；
- 是否把代码、`final_info.json`、outputs/report 前移为下一轮 baseline；
- 继续下一轮、重跑指定候选、还是结束 Discovery。

**暂停与恢复**

- 先写只读的 `round_review_bundle` 和候选 manifest；不要在等待前修改经验库或 baseline。
- Resume 采用事务式决策：先记录批准的候选与 metric provenance，再分别提交 experience update 和 baseline update。
- `experience approved` 与 `baseline approved` 应是两个可审计的决定，避免“接受经验但不改变起跑线”无法表达。

**理由**

经验会改变下一轮 prompt，incremental baseline 会改变下一轮代码、指标和复制目录；这两种写入都会改变后续研究路径。当前代码在每轮结束后自动执行，正是需要人工判断的地方。

### Seam D：Discovery 完成、PaperOrchestra 交接前暂停（P0）

**位置**

- 正常路径：写完 `discovery_summary.json`（[`_main()`](../launch_discovery.py#L1172)）后、调用 `_handoff_to_paper_orchestra()`（[`launch_discovery.py`](../launch_discovery.py#L375)）之前；
- 已完成轮次的 resume 路径：[`_main()`](../launch_discovery.py#L789) 中直接 `_run_paper_orchestra()` 之前。

**用户应看到的阶段性产物**

- 完整 `discovery_summary.json`、每轮 session 和成功候选；
- candidate paths、指标、报告、代码和复现实验材料；
- 自动候选选择的 criterion、候选池和 fallback 解释预览。

PaperOrchestra 当前在 [`service.py`](../vegapunk/paper_orchestra/service.py#L156) 调用 `select_candidate()`，后者会读取 `discovery_summary.json` 并持久化不可变的 `candidate_selection.json`（[`candidate_selection.py`](../vegapunk/paper_orchestra/candidate_selection.py#L57)）。因此 review 应发生在选择和论文生成之前，不能等 `candidate_selection.json` 写完再询问用户。

**用户决策**

- 选择一个候选、改选候选或确认“不进入论文阶段”；
- 确认候选选择 criterion 是否符合研究意图；
- 若材料不足，返回某一轮重跑或补充实验。

**暂停与恢复**

- 以 `scope=handoff` 保存 review checkpoint，引用 summary、候选 manifest 和 artifact hashes。
- 批准后把用户选择作为 PaperOrchestra 的显式输入；禁止在无批准时让 `select_candidate()` 随机/自动落盘终端候选。
- 若拒绝，Launch 应保持 `awaiting_review` 或进入明确的 `rejected` 终态，而不是伪装成 PaperOrchestra 失败。

**理由**

这是 Discovery 对外产生研究结论的最后边界，人工判断的价值最高，且不需要把人工反馈塞进 PaperOrchestra 的内部写作循环。PaperOrchestra 继续作为独立运行边界，获得一份已批准的候选输入即可。

### Seam E：Native Launch 的 stage 级暂停（平台能力）

**位置**

以 [`DiscoveryLaunchStore._run_fake()`](../desktop/openworker/upstream/coworker/server/discovery_launch.py#L448) 目前的 stage 循环为生命周期样板；真实 runner 接入后，在 stage 完成/产物落盘处调用与 [`_activate_stage_locked()`](../desktop/openworker/upstream/coworker/server/discovery_launch.py#L792)、[`_write_checkpoint_locked()`](../desktop/openworker/upstream/coworker/server/discovery_launch.py#L730)、[`_emit_event_locked()`](../desktop/openworker/upstream/coworker/server/discovery_launch.py#L907) 对齐的 review adapter。

推荐的观察点不是每个 heartbeat，而是：

```text
preparing 完成       -> 审阅输入/转换结果
research 的一轮完成  -> 审阅实验/候选结果
research 完成        -> 审阅最终候选与 summary
finalizing 之前      -> 批准 PaperOrchestra handoff
```

**现有能力可以直接复用**

- `status` 已返回 checkpoint、timeline、activity、allowed actions 和 produced outputs（[`_status_unlocked()`](../desktop/openworker/upstream/coworker/server/discovery_launch.py#L949)）；
- `events.jsonl` 支持按 sequence 回放，`runner.log` 支持流式读取；
- `input_snapshot.json`、`launch_configuration.json` 与 immutable preparation revision 能保证审阅依据固定；
- sidecar 重启后的 interruption reconciliation 已经要求显式 Resume。

**需要新增的语义**

- 增加 `awaiting_review`（或内部拆分 `execution_state=paused` 与 `review_state=pending`），并增加 `review_request`/`review_decision` 对象；
- review 暂停时 runner 应结束当前 attempt、写入 checkpoint 和 artifact manifest，但不能被视作 `stopped`；
- `allowed_actions` 应区分 `approve`、`reject`、`edit/replace`、`cancel` 与普通 `stop`/`resume`；
- GUI 要有 review card、产物列表、意见输入和明确的 Resume/Approve 动作，而不是把 Stop 按钮改名。

**重要限制**

Native sidecar 当前 runner 是 fake runner，因而该 seam 只能先实现生命周期协议和 GUI 合同；真实 Discovery runner 接入前，不能宣称 Native 已经提供完整 Discovery HITL。

## 5. 建议的状态与持久化契约

### 5.1 状态不要互相覆盖

最小兼容方案是在现有 Launch `state` 中增加 `awaiting_review`，并把它放在单独的 `REVIEW_LAUNCH_STATES` 集合中；`ACTIVE_LAUNCH_STATES` 不应包含它，runner 已经停止，sidecar 可以安全释放 active slot。`resume` 不能直接复用为“批准 review”，应有带幂等键的 review action。

更清晰的长期模型是拆成两条轴：

```text
execution_state: starting | running | stopping | paused | stopped |
                 interrupted | completed | failed
review_state:    none | pending | approved | rejected | superseded
pause_reason:    review | user_stop | interruption
```

对外可以继续返回 `state=awaiting_review` 作为兼容性的派生值，但内部不应让“等待人工”和“runner 被 Stop”走同一分支。

### 5.2 Review checkpoint 最小字段

每个 seam 都应生成同一形状的 review record（文件名可以按平面不同调整）：

```json
{
  "schema_version": 1,
  "review_id": "review-...",
  "scope": "mas_session | pre_experiment | round | handoff",
  "launch_id": "...",
  "session_id": "...",
  "stage": "ranking | pre_experiment | round_complete | handoff",
  "round": 2,
  "status": "pending",
  "requested_at": "...",
  "resume_from": {
    "phase": "...",
    "round": 2,
    "attempt_id": "..."
  },
  "artifact_refs": [
    {"path": "session_2/ideas.json", "kind": "candidate", "sha256": "..."}
  ],
  "request": {
    "questions": ["approve candidates", "allow baseline update"],
    "allowed_decisions": ["approve", "reject", "edit", "continue"]
  },
  "decision": null,
  "feedback": null
}
```

`artifact_refs` 必须指向冻结的文件或不可变 revision，并记录 hash；用户反馈、决策人、时间、父 review 和输入 revision 都要追加到审计历史。等待期间不应覆盖用户正在查看的文件。

### 5.3 Resume 的不变量

1. Resume 必须从 review record 的 `resume_from` 恢复，而不是重新扫描目录猜测完成度。
2. 已经批准的 round 不得再次生成经验、前移 baseline 或重复启动实验。
3. 相同 `review_id + decision_id` 重放必须返回同一结果；不同 decision 不能复用同一个幂等键。
4. sidecar 重启后，`awaiting_review` 必须仍可见，不能被 reconciliation 当作 runner 丢失而标成普通 `interrupted`。
5. Handoff 只能成功一次；已存在用户批准的 candidate selection 时，PaperOrchestra 必须复用它。

## 6. 不建议插入暂停的位置

### 6.1 每个 Agent 或每次工具调用之后

这会把一个可理解的研究阶段切成大量微状态，产生无法复现的上下文组合，也迫使所有 Agent 了解 UI 和持久化协议。Agent 内部保留普通日志和中间产物即可，HITL 应停在编排器拥有完整输入/输出的边界。

### 6.2 ExperimentRunner 已经启动之后

工具调用可能正在修改工作树、占用 GPU、创建远程会话或写入半成品。此时暂停既不能提供稳定审阅物，也难以定义“从哪一个副作用之后恢复”。应在 runner 前审批候选，在 runner 后只审阅完整 round。

### 6.3 baseline 或 experience 已经写入之后

这会让用户的意见落后于真正改变下一轮的状态；恢复时还要回滚代码、指标和经验库。正确顺序是：生成只读 bundle -> 等待 -> 事务式提交批准的 memory/baseline 更新。

### 6.4 PaperOrchestra 内部写作循环

论文生成可以有自己的失败/重试机制，但 Discovery 的研究候选选择属于 handoff 前的外层决策。把 HITL 直接塞进 PaperOrchestra 会混淆两个运行边界，也会使“拒绝候选”看起来像论文生成错误。

### 6.5 把 stage heartbeat 当成 review 请求

timeline、SSE 和原始日志是观察能力，不等于每条事件都要用户做决定。只有产物冻结并且存在明确的下一步选择时，才创建 review request。

## 7. 分层实现路线

### Phase 0：修正 MAS 的自动反馈语义（P0）

1. 让 `IdeaGenerator` 在 `awaiting_feedback` 且没有明确外部决定时返回结构化 review request，而不是自动循环。
2. 将 `add_feedback(auto_resume=False)` 作为人工反馈 API，保留 `resume_session()` 作为显式动作。
3. 为 MAS review 生成 manifest，补足尚未完成时 `ideas.json` 不存在的问题。
4. 在 CLI launch 目录保存 review checkpoint，并让 `--resume` 优先消费它。

### Phase 1：在 CLI 建立三个高价值 gate（P0/P1）

1. MAS 结束后、实验/报告执行前增加 candidate/method review。
2. 每轮实验后、经验与 incremental baseline 更新前增加 round review；将两类写入改为批准后的事务。
3. summary 写入后、两个 handoff 路径（正常终点与已完成 resume）都增加 handoff review。
4. 将 `--skip_idea_generation`、`report` 模式和失败轮次纳入同一 review schema，而不是另开一套隐式逻辑。

### Phase 2：Native sidecar 生命周期与 GUI（P1）

1. 在 `DiscoveryLaunchStore` 增加 review state、review checkpoint、review events 和幂等 action。
2. 更新 `_status_unlocked()`、`_allowed_actions()`、`_reconcile_locked()` 和 history 逻辑，明确 `awaiting_review` 不是 `stopped`/`interrupted`。
3. 在 `DiscoveryFacade`/`app.py` 暴露 review request、decision、resume endpoints；GUI 显示 review artifact 和反馈。
4. 真实 Discovery runner 接入后，在真实 stage 产物完成处调用同一 review adapter；fake runner 只用于契约测试。

### Phase 3：统一两条执行平面

用一个与执行器无关的 `ReviewGate`/`ReviewCheckpoint` 协议连接 CLI 和 sidecar：CLI 可以使用文件/命令行 adapter，Native 可以使用 HTTP/GUI adapter。PaperOrchestra 只接受已批准的 handoff input，不直接拥有 Discovery 的人工决策。

## 8. 验收标准

实施后，以下行为应可通过集成测试验证：

- Discovery 在每个 review seam 停下时，用户能看到稳定的产物清单、轮次、session、候选和 provenance。
- sidecar 或 CLI 进程重启不会跳过 pending review，也不会把 review 当成普通 Stop/Interruption。
- 用户拒绝、编辑或批准都能留下带时间、actor、hash 和父 checkpoint 的审计记录。
- 重复提交同一 decision 不会重复启动实验、重复更新 baseline、重复写经验或重复 handoff。
- 用户批准后，恢复从精确的 phase/round/attempt 继续；已完成轮次不会重跑。
- incremental 模式只有在批准后才改变 `run_0`、主 `code/`、`outputs/`、`report/` 或经验库。
- PaperOrchestra 在 handoff 前没有被启动；批准后只消费已批准候选，并能复用已有 `candidate_selection.json`。
- `Stop` 仍表示主动终止，`Resume` 仍表示从 stopped/interrupted checkpoint 恢复；两者不承担 review approve/reject 的语义。

## 9. 代码索引

| 组件 | 关键文件 |
| --- | --- |
| CLI 编排与 resume | [`launch_discovery.py`](../launch_discovery.py#L620) |
| MAS 驱动 | [`vegapunk/stage.py`](../vegapunk/stage.py#L284) |
| MAS 状态机/反馈 | [`orchestration_agent.py`](../vegapunk/mas/workflow/orchestration_agent.py#L170)、[`interface.py`](../vegapunk/mas/interface.py#L213) |
| Discovery round 结果、经验、baseline | [`launch_discovery.py`](../launch_discovery.py#L1045)、[`launch_discovery.py`](../launch_discovery.py#L253)、[`launch_discovery.py`](../launch_discovery.py#L159) |
| PaperOrchestra handoff | [`launch_discovery.py`](../launch_discovery.py#L375)、[`service.py`](../vegapunk/paper_orchestra/service.py#L33) |
| 候选选择 | [`candidate_selection.py`](../vegapunk/paper_orchestra/candidate_selection.py#L57) |
| Native Discovery API | [`app.py`](../desktop/openworker/upstream/coworker/server/app.py#L225)、[`discovery.py`](../desktop/openworker/upstream/coworker/server/discovery.py#L313) |
| Native Launch 状态机 | [`discovery_launch.py`](../desktop/openworker/upstream/coworker/server/discovery_launch.py#L250) |
| Native GUI | [`DiscoveryView.tsx`](../desktop/openworker/upstream/surfaces/gui/src/components/DiscoveryView.tsx#L1703) |

