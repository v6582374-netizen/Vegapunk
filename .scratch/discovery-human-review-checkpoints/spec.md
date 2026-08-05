# Configurable Discovery Human Review Checkpoints

Type: spec
Status: open
Labels: ready-for-agent
Parent: map.md

## Problem Statement

Discovery 当前默认以全自动方式执行：MAS 生成并排名 idea，方法规格直接进入实验，Discovery 完成后自动交给 PaperOrchestra。研究者无法在这些高价值边界查看阶段性产物并主动决定何时继续。

我们需要一种低侵入的 Human-in-the-loop 机制，但不能破坏现有的全自动默认行为，也不能把人工控制散落到每个 Agent、工具调用或 PaperOrchestra 内部循环中。用户需要的是可选的断点：当某个 Launch option 开启时，Discovery 在指定边界完成当前执行并变为非活跃，保留可审阅产物；用户查看后显式执行一次 Resume，系统再从 checkpoint 之后继续。

Version 1 的目标是先把三个断点可靠地呈现出来并证明断点续传语义。阶段性产物只读，不在本版本中提供编辑、保存或 revision；Round 结束后、经验/baseline 更新前的第四个 seam 也不属于本版本。

## Solution

为每个 Discovery Launch 增加三个可选的布尔 Launch options：

1. MAS ranking/feedback checkpoint：每次 MAS 在 ranking 后进入 `AWAITING_FEEDBACK` 时触发；
2. Pre-experiment method checkpoint：每轮全部 refined methods 生成后、实验或报告执行路径开始前触发一次；
3. Pre-PaperOrchestra handoff checkpoint：一个 Launch 的 Discovery rounds 完成并写出 summary 后、PaperOrchestra 启动前触发一次。

三个 options 通过可选 CLI 参数和 Native Desktop Discovery Preparation 的 Run controls 暴露。参数缺省或值为 false 时，流程保持现有全自动行为；每个新 Launch 都重新以 false 开始，不隐式沿用上一次 Launch 的值。有效值写入不可变 Launch configuration snapshot。

所有 enabled seam 共享一个高层 checkpoint 生命周期：当前执行完成本 seam 的工作、写入 checkpoint 和只读 artifact manifest、退出当前执行，使 Launch 变为非活跃；用户查看对应的 seam-specific UI 后，通过唯一的 Resume 动作继续。Resume 不重新执行已经完成的阶段，不重复启动实验、经验写入、baseline 更新或 PaperOrchestra handoff。

三个 checkpoint 使用不同的用户呈现：MAS 展示排名与反馈上下文，方法 checkpoint 展示一轮的方法候选与执行前信息，handoff checkpoint 展示整个 Discovery Launch 的汇总结果。它们共享生命周期和 Resume 合同，但不共享一个通用编辑器。

## User Stories

1. As a Sole Researcher, I want Discovery to remain fully automatic when no Human Review option is provided, so that existing CLI runs do not change behavior.
2. As a Sole Researcher, I want to enable the MAS checkpoint independently, so that I can inspect MAS output without enabling later checkpoints.
3. As a Sole Researcher, I want to enable the pre-experiment method checkpoint independently, so that I can inspect methods before they consume experiment resources.
4. As a Sole Researcher, I want to enable the pre-PaperOrchestra handoff checkpoint independently, so that I can inspect the complete Discovery outcome before paper generation.
5. As a Sole Researcher, I want every new Launch to start with all three options disabled, so that a previous manual run cannot silently make a later run interactive.
6. As a Sole Researcher, I want the CLI options and Preparation Run controls to express the same three fields, so that the execution entry point does not change the meaning of a policy.
7. As a Sole Researcher, I want the effective option values captured in the Launch snapshot, so that a resumed Launch keeps the policy with which it started.
8. As a Sole Researcher, I want changes made in Preparation after Launch admission to leave the active Launch unchanged, so that the reviewed run remains reproducible.
9. As a Sole Researcher, I want the MAS checkpoint to occur every time MAS enters `AWAITING_FEEDBACK` after ranking, so that I can observe each iteration boundary rather than only the final MAS result.
10. As a Sole Researcher, I want the MAS checkpoint to show the current ranked ideas, scores, critiques, evidence, references, iteration, and trajectory context, so that I can understand what the next MAS cycle will consume.
11. As a Sole Researcher, I want the MAS checkpoint to remain visible even when the normal completed `ideas.json` has not yet been written, so that an early checkpoint is reviewable from durable session state.
12. As a Sole Researcher, I want the MAS process to be inactive at its checkpoint, so that no background model call or automatic feedback injection continues while I inspect it.
13. As a Sole Researcher, I want one Resume action to continue the MAS session without requiring a second feedback-specific action in Version 1, so that the first implementation proves checkpoint and continuation semantics without inventing an edit protocol.
14. As a Sole Researcher, I want the method checkpoint to occur once per completed round after all refined methods are available, so that I review the round as one coherent batch rather than approving ideas one by one.
15. As a Sole Researcher, I want the method checkpoint to appear before `ExperimentRunner` or `ReportWriter` begins, so that no expensive or externally visible execution starts before Resume.
16. As a Sole Researcher, I want the method checkpoint to show method details, candidate identity, baseline context, metrics, and execution configuration, so that the execution boundary is understandable.
17. As a Sole Researcher, I want the method checkpoint to Resume exactly into the pending execution/reporting path, so that already generated MAS work is not repeated.
18. As a Sole Researcher, I want the handoff checkpoint to occur once per Launch after the Discovery summary is complete, so that I can inspect the whole outcome at the final research-to-paper boundary.
19. As a Sole Researcher, I want the handoff checkpoint to show the summary, successful candidates, metrics, reports, and provenance, so that I can judge whether the Launch is ready for PaperOrchestra.
20. As a Sole Researcher, I want PaperOrchestra not to start before I Resume from the handoff checkpoint, so that paper generation is an explicit continuation of the reviewed Discovery Launch.
21. As a Sole Researcher, I want a completed-round resume path to apply the handoff checkpoint before PaperOrchestra as well, so that restarting a finished Discovery does not bypass the configured human boundary.
22. As a Sole Researcher, I want the three checkpoint surfaces to be visually and semantically distinct, so that each review presents the artifacts appropriate to its stage instead of forcing all stages into one generic screen.
23. As a Sole Researcher, I want checkpoint artifacts to be read-only in Version 1, so that the first release has a clear provenance model while editing and revision semantics remain a later decision.
24. As a Sole Researcher, I want Resume to be idempotent, so that a repeated click or retried request cannot start two execution attempts.
25. As a Sole Researcher, I want the system to persist which stage, round, session, attempt, and artifacts produced the checkpoint, so that I can understand and recover a paused Launch after a process restart.
26. As a Sole Researcher, I want a restart to preserve an unresumed checkpoint as a checkpoint, so that process recovery does not turn a deliberate human pause into an accidental interruption.
27. As a Sole Researcher, I want fully automatic runs to continue using the current experiment, experience, baseline, and PaperOrchestra behavior, so that adding the options is backward compatible.
28. As a Sole Researcher, I want the discarded round-review seam to remain absent, so that the first implementation does not expand into a separate approval protocol for experiment results, experience generation, or baseline mutation.

## Implementation Decisions

### First-principles design choices

- A Human Review Checkpoint is valuable only where a stable artifact exists and the next operation creates a meaningful new commitment, side effect, or subsystem handoff. The three selected boundaries satisfy this test; the round-review seam is intentionally excluded.
- The control point belongs at the highest existing orchestration seam. Agents continue to generate, the experiment path continues to execute, and PaperOrchestra remains its own subsystem. A shared checkpoint coordinator owns lifecycle and persistence; seam-specific producers own artifact selection and presentation.
- Disabled options must be a no-op at the orchestration level. The automatic path must not require a synthetic checkpoint, a fake Resume, or a new background scheduler.
- Version 1 optimizes for a trustworthy pause/resume contract, not human mutation of research content. Checkpoint artifacts are immutable/read-only; editing and saved revisions require a later decision.

### Launch options and configuration

- The canonical logical fields are `human_review_after_mas_ranking`, `human_review_before_experiment`, and `human_review_before_paperorchestra`.
- CLI arguments and Preparation Run controls are two adapters for these same fields. They must not create separate policy models.
- The CLI exposes the same fields as optional presence switches: `--human_review_after_mas_ranking`, `--human_review_before_experiment`, and `--human_review_before_paperorchestra`. An omitted switch resolves to false; including it resolves to true. The Native Run request and the Launch snapshot always carry explicit boolean values, so a Native checkbox can represent either true or false without inventing a second policy model.
- The Preparation labels are, respectively, “Pause after MAS ranking”, “Pause before experiment”, and “Pause before PaperOrchestra”. They are unchecked for every new Launch. No negative CLI switches are required in Version 1 because false is the default and omission is the least surprising all-automatic invocation.
- The three options are validated before Launch admission and are copied into the immutable snapshot as explicit booleans.
- The Native Preparation surface presents the options alongside the Run controls, not in a new Settings module. Every new Launch resets them to false unless the researcher explicitly enables them for that Run.
- The effective options are copied into the Launch configuration snapshot and remain immutable for the lifetime of that Launch. Preparation changes after admission affect only a future Launch.

### Shared checkpoint coordinator

- Introduce one Launch-level checkpoint coordinator/adapter at the outer Discovery orchestration boundary.
- A checkpoint record contains a unique checkpoint identity, Launch identity, seam kind, session/round context when applicable, source attempt, creation time, effective Launch options, artifact references, and a resumable continuation point.
- Artifact references point to Launch-owned, read-only material and include enough provenance to render the correct seam surface after reconnect or restart.
- The public lifecycle distinguishes an inactive `awaiting_review` checkpoint from active execution, user-requested Stop, interruption, completion, and failure. A checkpoint ends the current attempt; Resume creates the next attempt from the recorded continuation point.
- Resume is the only Version 1 user action. It is idempotent and cannot be accepted twice for the same checkpoint. It never reruns completed work or creates a second downstream side effect.
- The coordinator emits durable state/activity/event updates through the existing observation and Launch persistence seams. It does not keep a process alive to poll for user input.
- For MAS, Resume means continue the paused MAS session without a new mutable artifact/feedback path in Version 1; the later feedback/editing protocol is explicitly deferred.

### MAS checkpoint

- The MAS driver observes every transition into `AWAITING_FEEDBACK` after ranking when `human_review_after_mas_ranking` is true.
- It flushes the current session state and a review manifest before ending the current execution attempt. The review bundle is derived from durable session state so it is available even before the normal completed `ideas.json` projection.
- The presenter is MAS-specific and includes ranked candidates, score context, critiques, evidence/references, iteration, and trajectory links. It is read-only and has one Resume action.
- Resume uses the existing session continuation seam and records that no new Version 1 artifact edit was supplied. Automatic `offline_feedback` injection must not bypass an enabled checkpoint.

### Method checkpoint

- After a round's MAS result has produced all refined methods, the coordinator creates one batch checkpoint when `human_review_before_experiment` is true.
- The checkpoint is before both the experiment execution path and the report-generation path, so the policy cannot be bypassed by selecting a different mode.
- The presenter is method-specific and shows the round's candidate methods, baseline/metric context, execution configuration, and expected downstream artifacts. It is read-only and has one Resume action.
- Resume continues from the pending round execution/reporting boundary without regenerating MAS output.

### Handoff checkpoint

- After Discovery completes its configured work and writes its summary, the coordinator creates one per-Launch checkpoint when `human_review_before_paperorchestra` is true.
- The normal terminal path and the already-completed-round resume path must both pass through this guard before the first PaperOrchestra invocation.
- The presenter is handoff-specific and shows the aggregate Discovery summary, successful candidates, metrics, reports, artifact provenance, and the intended Paper Input context. It is read-only and has one Resume action.
- Resume invokes the existing one-Paper-per-Launch PaperOrchestra boundary. Candidate selection remains non-blocking context under the accepted PaperOrchestra design; this feature does not add candidate editing or a PaperOrchestra-internal checkpoint.

### Native Desktop integration

- Preparation owns the three Run controls and includes their effective values in the Launch admission request; no separate Settings module or persistent cross-Launch policy is introduced.
- Native sidecar status, event replay, artifact listing, and reconnect surfaces expose the same checkpoint identity, seam, artifact references, and allowed `Resume` action as the CLI contract.
- The existing Launch store's durable record, checkpoint file, events, timeline, activity, and attempt model are extended rather than replaced. Reconciliation must preserve `awaiting_review` as deliberate inactivity and must not convert it into ordinary interruption.
- The current fake runner remains a lifecycle test harness. The checkpoint contract must be placed where the real Discovery runner can later emit stage artifacts without changing the public semantics.
- Each checkpoint type gets a distinct Preparation/Launch presentation. Shared components may render status and Resume, but the artifact hierarchy and copy remain seam-specific.

## Testing Decisions

Tests should verify externally visible behavior and persisted contracts, not implementation method names or private helper structure. A good test proves which artifacts exist, which state/action is exposed, whether a downstream side effect has or has not happened, and what a repeated Resume does.

- CLI option tests cover omitted/default false, present/true, validation, and inclusion in the effective Launch snapshot; Native transport tests cover explicit false as well as true.
- Preparation/Run admission tests cover three controls, reset-to-false behavior for a new Launch, and immutable snapshot semantics after admission.
- Shared lifecycle tests cover active execution to `awaiting_review`, inactive process behavior, read-only artifact manifest, one Resume, duplicate Resume rejection/idempotency, restart/reconnect, and continuation from the exact checkpoint.
- MAS integration tests cover every ranking-to-`AWAITING_FEEDBACK` checkpoint, durable session-derived artifacts before `ideas.json`, no automatic offline feedback bypass, and Resume without rerunning completed phases.
- Method-boundary tests cover one checkpoint per round, all refined methods present, no ExperimentRunner/ReportWriter invocation before Resume, and exactly one continuation after Resume.
- Handoff tests cover one checkpoint per Launch, summary persistence before the checkpoint, both normal and completed-resume paths, no PaperOrchestra invocation before Resume, and one PaperOrchestra invocation after Resume.
- Native sidecar tests cover status/event/artifact exposure, checkpoint persistence, reconnect, process restart, deliberate review pause versus ordinary Stop/interruption, and action availability.
- Fully automatic regression tests run the existing Discovery paths with all options absent/false and assert unchanged experiment, memory, baseline, summary, and PaperOrchestra behavior.
- Prior art to reuse includes the existing Preparation run-gate tests, Launch Stop/Resume/restart-reconciliation tests, event-cursor/raw-log tests, and PaperOrchestra one-run/failure-isolation tests.

## Out of Scope

- The `每轮实验结束、经验/baseline 更新前` Human Review Checkpoint.
- A standalone Settings module or a persistent global/per-task Human Review policy.
- Reusing a prior Launch's option values as defaults for a new Launch.
- Editing, saving, or revisioning checkpoint artifacts in Version 1.
- A separate Resume-with-Feedback action or a new human feedback transport in Version 1.
- Changing MAS ranking/evolution/refinement algorithms or ExperimentRunner experiment semantics.
- Changing experience generation or incremental baseline semantics; they remain automatic after the relevant checkpoint is resumed.
- Candidate editing, mandatory candidate selection, or internal PaperOrchestra stage checkpoints.
- Parallel Launches, multiple Preparations, or a new multi-user authorization model.

## Further Notes

- This spec supersedes the earlier exploratory four-seam architecture discussion for implementation scope: only three checkpoints remain, and the Settings-module proposal is replaced by Preparation Run controls plus optional CLI arguments.
- The accepted one-Paper-per-Launch and candidate-selection-nonblocking ADRs remain authoritative. A handoff checkpoint delays the existing handoff; it does not create a second PaperOrchestra lifecycle.
- The current Native sidecar fake runner proves lifecycle shape, not real Discovery execution. The implementation should preserve the contract while replacing the runner behind the same adapter seam.
- The accompanying UI prototype is intentionally throwaway and is meant to compare three embedded Current Launch layout directions before production UI work begins. The terminal/runtime output remains the dominant surface; the three fixed seam bundles are present from Launch start and remain greyed out until their boundary is reached.
- Prototype entry point: [prototype README](./prototype/README.md). It is a static, in-memory artifact with no production API calls; the browser smoke test covers all three variants, six lifecycle states, artifact opening, Resume continuation, keyboard switching, and zero console errors.
