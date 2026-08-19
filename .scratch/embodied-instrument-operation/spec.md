# 可逆仪器操作的闭环实验 Harness

Status: ready-for-agent
Labels: ready-for-agent

## Problem Statement

实验室已经有一台 Unitree G1、BrainCo Revo2 手、真实操作台，以及 148
段 VR 遥操示教。现有数据是可训练的 LeRobot 格式观察—动作记录，不是已经
训练好的策略权重；其中四段分别对应开盖、取杯并做倾倒姿态、放回杯、关盖。

问题不在于再做一个“给机器人一次指令、看它是否成功”的演示。那种演示不能
回答部署时真正的问题：一个固定策略在什么条件下可靠，哪些外部条件、调用
方式和台面改造能让它更可靠，以及这些结论是否经得起下一批真实运行反驳。

比赛要求的是“任务规划与实验设计—实验运行与数据获取—数据分析与反馈迭代”
的闭环。当前系统已有安全的单回合执行、目标桥、策略服务、记录和独立见证
基础，但没有一个拥有“下一回合、下一批、下一世代”概念的系统。结果是，
策略、仿真和世界模型即使存在，也只是孤立工具，不能形成可审计的实验过程。

第一版的物理任务没有真实液体。所谓“倒水”只是杯子被拿起后进入一个规定的
倾倒姿态，再被放回。因此它是可逆操作序列，而不是液体转移实验；系统不得
宣称验证了液体转移或化学结果。

本规格检验一个可证伪的研究命题：在策略权重冻结的前提下，系统能否通过条件
搜索、调用方式调优和环境改造，显著扩大该策略的可靠工作包络。模型不是被
研究和反复改写的对象；“模型在这张真实台面上何时可靠”才是被研究的对象。

## Solution

构建一个独立于具体 VLA、世界模型或仿真器的 **Experiment Loop**。它以一次
完整的批次为最高调用接口，内部复用既有的单回合执行链，而绝不取得逐帧控制权。

闭环由七个职责组成：信念图、批次设计器、预测节点、真实执行通道、独立判官、
可追溯记录和批次刹车。

```text
研究目标 + 约束 + 当前世代的信念图
              │
              ▼
         批次设计器 ── 预注册预测与条件
              │
      ┌───────┴────────┐
      ▼                ▼
预测节点/仿真       真实 G1 单回合执行
（预测、置信度）     （既有策略→桥→tracker）
      │                │
      └───────┬────────┘
              ▼
   独立轨迹见证 + 复位见证 + 追加式记录
              │
              ▼
  分析、校准预测节点、更新信念图、设计下一批
```

**受试者**是可替换的固定策略。第一位受试者可由现有 148 段 VR 数据训练得到；
后续可以替换为外部 VLA、微调后的 VLA 或其他合规策略。Harness 不拥有策略
权重，也不把某一模型架构写入自身。

**预测节点**是第一版闭环的必需成员，而不是以后才加入的装饰。它必须是实际的
预测实现：可为经校准的仿真/数字孪生，或经本台面数据适配的世界—动作模型。
它接收候选条件和受试者策略的计划行为，输出对独立见证轨迹与成功概率的预测，
并明确给出不确定性。它只能建议实验点和排序候选；真实台面与独立见证器是唯一
能够判定成败的权威。每个批次至少保留真实锚点，用真实结果持续校准预测节点。

**独立判官**不再是只看“盖子当前开或关”的单一比特，而是见证整个可逆任务
轨迹：起始时盖子关闭且杯子在起始位；过程中盖子曾稳定打开；杯子曾被拿起并
进入倾倒姿态区域；最后杯子回到起始位且盖子稳定关闭。终态关闭本身不构成成功，
否则“机器人什么也没做”会被误判成功。见证器只观测、记录和裁定；它不向策略
下达下一步指令，因此不会成为隐藏的状态机或脚本控制器。

**世代**是一个冻结的台面配置：夹具、杯子、见证器姿态和标定、光照协议等共同
构成一个世代。批次只在一个世代内累计证据。环境改造会开启新世代：旧世代证据
被保留为历史，不得与新世代样本混合计算当前包络。

批次设计器有两条输出路径：可直接执行的条件/调用方式，以及需要人执行的工单。
工单提出夹具、标记或其他环境改造，并附带它预期扩大的可靠包络。具名人确认工单
已执行后才可开启新世代；这一确认不是逐回合遥操，也不是对成败的主观裁决。

系统用两条曲线表达实验成效：世代内的可靠性提升，以及世代间由环境改造带来的
可靠包络扩大。前者优化固定场的使用方式；后者改变场本身。

## User Stories

1. As a laboratory researcher, I want to declare a fixed operation goal, constraints, and a frozen policy version, so that the system studies a concrete, reproducible subject rather than changing the subject while evaluating it.

2. As a laboratory researcher, I want the system to treat the no-liquid task as a reversible manipulation sequence, so that an automated loop can run repeatedly without pretending to measure liquid transfer.

3. As a competition evaluator, I want to see the research goal, the next experimental plan, the observed results, and the changed next plan in one chain, so that the feedback loop is visible rather than inferred from a one-off demo.

4. As the batch designer, I want to pre-register each batch's conditions, predictions, budget, and expected outcome before execution, so that later claims about adaptation can be falsified.

5. As the experiment loop, I want to invoke an existing single-episode execution path without owning robot joints or control ticks, so that feedback planning cannot bypass the Whole-Body Target Contract or Target Bridge.

6. As the policy provider, I want to substitute a compliant VLA or other fixed policy without changing the harness, so that the harness measures policy reliability rather than becoming an accessory for one model.

7. As a model developer, I want the 148 VR demonstrations to be admitted as provenance-marked training input rather than mislabeled as a trained policy, so that subsequent claims distinguish data, model weights, and evaluation evidence.

8. As an independent witness, I want to observe the whole externally visible operation trace, so that a terminal closed lid cannot be mistaken for a completed operation.

9. As a safety authority, I want the existing Safe Hold, Authority Latch, Manual Safety Authority, and target validity rules to remain authoritative, so that adding an experiment loop never weakens physical safety.

10. As the reset witness, I want to confirm the initial condition before every autonomous episode, so that episodes in a batch are comparable rather than silently starting from drifted physical states.

11. As the experiment loop, I want to stop a batch when reset, evidence, or safety cannot be established, so that it cannot manufacture a large dataset by repeating an unknown or unsafe state.

12. As the predictive-node owner, I want to run an actual simulator or world model on candidate conditions and record its confidence, so that prediction is a genuine participant in the loop rather than a post-hoc visualization.

13. As the predictive node, I want every prediction to be scored against real witness results, so that my authority is earned by calibration rather than assumed from model branding.

14. As the batch designer, I want to direct scarce real-robot runs toward predictive uncertainty, reliability boundaries, and calibration anchors, so that real hardware time purchases information rather than repetition.

15. As the laboratory researcher, I want a reliability envelope that names the generation, conditions, policy version, witness, sample count, and uncertainty, so that “the robot works” becomes an actionable deployment statement.

16. As the batch designer, I want to distinguish a condition change from an environment change, so that searching within an existing bench does not accidentally invalidate its accumulated evidence.

17. As the system, I want to issue a work order for a fixture or protocol change together with an expected gain, so that environment shaping becomes a falsifiable experiment rather than an undocumented human adjustment.

18. As the laboratory owner, I want to approve and record a completed work order before a new generation begins, so that a physical bench change cannot silently contaminate comparisons.

19. As an analyst, I want old generations retained but excluded from current-generation aggregation, so that history remains inspectable without creating false confidence from incomparable samples.

20. As the experiment loop, I want failed, held, indeterminate, and completed episodes kept as distinct facts, so that no failure can be silently laundered into a clean success rate.

21. As a policy operator, I want a retry or retreat protocol to be learned from recorded failure patterns only after evidence exists, so that the harness does not conceal a hand-authored recovery script inside its evaluation.

22. As an evaluator, I want the loop to report both within-generation improvement and cross-generation envelope growth, so that superficial tuning is distinguishable from a genuine improvement to the physical workcell.

23. As a future model integrator, I want the predictive-node contract to remain stable while its internal simulator or world model changes, so that improved prediction technology can be measured against the same experiment history.

24. As a governance reviewer, I want language models limited to between-batch proposal generation and explanation, so that no language model can steer real-time movement or adjudicate its own experimental claims.

## Implementation Decisions

- Introduce one new highest-level seam: **Experiment Loop**. Its public operation runs a complete campaign or one batch from a declared generation, returns a sealed batch record, and is the only seam new tests need to call. It owns neither robot joints nor individual 50 Hz ticks.

- Reuse the existing **Operation Session** unchanged in role: it remains one non-reusable physical attempt. The Experiment Loop creates a fresh session for each episode through an executor/factory boundary; it never restarts a held session under the same record.

- Keep the existing **Policy Server → Target Bridge → whole-body tracker** chain as the sole motor path. A policy, replay source, VLA, or future controller participates only by producing Whole-Body Targets at the existing policy seam. Direct joint control, a second action publisher, or control-time LLM calls are forbidden.

- Replace the liquid-specific task interpretation. Remove liquid transfer, mass, cup volume, and the “pour posture may proceed only if lid open” task gate from the experimental outcome model. Retain general safety holds and target-envelope checks.

- Introduce an **Operation Trace Witness** alongside the existing Independent Witness concept. It emits an append-only trace of externally observed predicates, each carrying channel identity, observation time, freshness, and a definite/indeterminate verdict. It must support at least: initial lid closed, lid opened, cup lifted, cup reached tilt region, cup returned home, and final lid closed. It may not emit policy commands or select the next task phase. Probabilistic confidence belongs only to the predictive node, never to the adjudicator.

- Define task adjudication as a pure reduction over that witness trace. The only successful outcome is the required ordered trace with fresh evidence and a valid reset. A missing predicate, stale evidence, or indeterminate required predicate produces an indeterminate/failed outcome, never success.

- Introduce a **Reset Witness** that verifies the next episode's start state from external evidence. The reversible task itself may return the cup and close the lid; the harness does not assume that it did. If reset cannot be confirmed, the batch is stopped and marked as awaiting human intervention.

- Introduce first-class records for **Generation**, **Batch Plan**, **Prediction**, **Batch Result**, **Reliability Envelope**, and **Work Order**. All are append-only and link to policy identity, configuration/generation identity, witness identity, and source episodes.

- A Generation is created only from an explicit, frozen bench configuration digest. It covers the fixture, object identity, camera/witness pose and calibration, lighting protocol, policy identity, and applicable invocation protocol. Samples from different generations must never be pooled for a current reliability estimate.

- A Batch Plan is immutable once sealed. It includes research objective, admissible condition axes, real-versus-predicted execution budget, selection rationale, predictive-node version, confidence thresholds, real anchor allocation, and expected outcomes. Results attach to the plan; they do not rewrite it.

- The **Batch Designer** receives the current generation's reliability envelope, prior sealed plans and results, predictive-node calibration, constraints, and remaining budget. It can propose four classes of action: condition variation, invocation variation, data acquisition recommendation, and environment work order. It must state the class and rationale of every proposal.

- The **Predictive Node** is mandatory in the first release and must have a real implementation, initially either a calibrated simulator/digital twin or a learned world—action model. It returns predicted trace outcome, uncertainty, and supporting predicted observations. It never produces an authoritative result, never writes targets to the real robot, and never converts a simulated outcome into a real success.

- Real anchors are mandatory in every batch. The predictive node may only reduce real-run budget according to a recorded calibration policy. Missing, uncalibrated, or poorly calibrated predictions force more real anchors; they never allow a purely imagined conclusion.

- The initial policy is an admitted artifact trained from the 148 VR demonstrations or another explicitly versioned fixed policy. The harness must retain that the source archive contains demonstrations, not weights, and carries no success labels. The four recorded task segments are not evidence of an end-to-end transition policy; no end-to-end claim is allowed until such transitions are separately evidenced.

- A Work Order contains a proposed physical modification, its expected reliability-envelope gain, its cost/risk, and the evidence that motivated it. It is generation-level pre-registration. The loop may propose it; a named human executes and confirms it. Confirmation seals the old generation and opens a new one. Historical data stays readable but becomes non-current evidence.

- Evaluation reports two separate curves: within-generation reliability under fixed bench geometry, and cross-generation envelope growth after approved environment shaping. They must not be merged into a single success-rate plot.

- A batch-level circuit breaker terminates the batch after a configured pattern of unresolved holds, failed reset, missing witness evidence, or repeated equivalent failures. It records why it stopped and cannot silently retry forever.

- LLMs may translate a high-level research objective into candidate batch proposals or explain results between batches. Deterministic constraint checking, the predictive node, the witness, and the Experiment Loop decide admissibility; no LLM is inside the motion control or adjudication path.

## Testing Decisions

- The principal test seam is the **Experiment Loop**. Tests must drive a whole declared batch with deterministic fakes for episode execution, trace witnessing, reset witnessing, predictive-node output, and clock. They assert sealed externally visible records and next-plan decisions, not internal calls or field mutation.

- Retain existing tests around the lower seams: target validity and atomic bridge publication, policy chunk continuity and starvation-to-hold behavior, session recording, independent-witness freshness/dwell, and monitor/hold behavior. The new loop composes these guarantees; it does not reimplement them.

- Test that a no-op run ending with a closed lid fails task adjudication because the required witnessed trace is absent.

- Test that a complete externally witnessed trace succeeds only when reset evidence is valid, and that stale or indeterminate witness facts cannot be promoted to success.

- Test that every planned batch is immutable before its first episode, and that a next batch can change only after a sealed prior result exists.

- Test that the batch designer actually changes a later plan when a reliability boundary, calibration error, or repeated failure pattern is returned; do not accept a loop that merely repeats a fixed schedule.

- Test that the predictive node is invoked and scored in every batch, while a prediction alone cannot create a success, finish a batch without a real anchor, or publish real robot targets.

- Test calibration governance: an uncalibrated or inaccurate predictive node cannot reduce the required real-anchor budget; a well-calibrated one may rank or prioritize candidates but may not state an unverified real success rate as fact.

- Test that a failed reset, safety hold, or missing required evidence stops the current episode and causes the configured batch-level circuit breaker behavior. A held episode must never become a completed success through recovery or later editing.

- Test generation isolation: two otherwise identical episodes in different generations do not pool into one reliability envelope; historical records remain queryable.

- Test the work-order lifecycle end to end: proposal includes expected gain, unconfirmed work order cannot open a generation, named confirmation seals the prior generation, and the first new-generation batch receives a new identity and real anchor.

- Add an end-to-end software dry run that uses the real policy server, bridge, episode writer, Experiment Loop, and deterministic witness adapters. It must demonstrate a complete batch from pre-registration through result analysis without a robot, while hardware tests remain the only proof of physical behavior.

- The quality bar for tests is behavioral: a test should read like an experiment claim or safety rule, not like a test of private implementation structure.

## Out of Scope

- Whole-body locomotion, navigation, SLAM, route planning, and a new balance/tracker foundation model.

- Direct policy-to-joint control, a second motor path, or any bypass around the Target Bridge and existing tracker.

- Real liquid transfer, chemical measurement, fluid simulation, mass/volume outcomes, or a claim that this reversible gesture proves material transfer.

- Training a new VLA foundation model, training a new whole-body control foundation model, or using autonomous real-robot reinforcement learning to change the subject policy during the reported experiment.

- Treating the 148 VR demonstrations as proof that all demonstrations succeeded, as trained policy weights, or as end-to-end data across the four recorded task boundaries.

- A world model or simulator serving as final judge, as a real-robot actuator, or as a substitute for real anchor episodes.

- A task-state machine that authorizes robot gestures one by one; the trace witness observes outcomes but never sequences the policy.

- Human judgment of per-episode success inside the autonomous batch. Humans may execute and confirm a work order, and retain Manual Safety Authority.

- Unconstrained language-to-motor control, LLM participation in the 50 Hz loop, or an LLM declaring an experiment successful.

## Further Notes

- This specification supersedes prior liquid-transfer assumptions in the embodied-operation map and associated tickets. “Pour” now means a visible tilt gesture only. The old liquid-specific gate, balance measurement, and human reset assumptions are to be retired rather than carried forward as optional complexity.

- The physical instrument is mute. A fixed bench camera or equivalently independent fixed sensor is therefore load-bearing: it supplies both the task trace and reset evidence. The policy's head/wrist cameras may inform the policy but cannot be the adjudicator.

- The existing 148 demonstrations are valuable seed data: 59 open episodes, 31 tilt episodes, 31 return episodes, and 27 close episodes, with four synchronized visual views and 26-dimensional state/action traces. They are suitable for training/adapting a policy and a predictive model only after provenance and outcome limitations are kept explicit.

- “Automatic” in this specification means no human is needed between ordinary reversible episodes. It does not mean unsupervised physical safety, automatic fixture installation, or permission to run after a safety latch.

- The system's contribution is not a claim that its model is intrinsically smarter. Its contribution is a reliable, evidence-bearing mechanism that maps where a fixed model works, tests its own predictions against reality, and makes environment/protocol improvement falsifiable.
