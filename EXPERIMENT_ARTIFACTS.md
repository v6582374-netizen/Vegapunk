# InternAgent 当前实验自然产物说明

本文档说明 InternAgent 在现有 discovery / experiment 流程中自然产生的文件和目录。这里的“自然产物”指当前代码已经稳定或半稳定留下的执行痕迹，不包括未来要新增的论文生成 pipeline。

## 1. 总体输出结构

一次 discovery launch 通常写入：

```text
results/<task_name>/<launch_id>_launch/
  prompt.json
  discovery_summary.json
  session_<id>/
    ideas.json
    traj.json
    <timestamp>_<idea_name>/
      notes.txt
      prompt.json
      launcher.sh
      log.txt
      experiment_report.txt
      code/
      run_0/
      run_1/
      run_2/
      ...
```

其中 `session_<id>/` 来自一轮 idea generation；每个 `<timestamp>_<idea_name>/` 是一个候选 idea 的实验工作区；`run_0/` 是基线备份，`run_1..N/` 是该 idea 的多次实验尝试。

## 2. Launch 级产物

### `prompt.json`

位置：

```text
results/<task_name>/<launch_id>_launch/prompt.json
```

含义：

- 本次 discovery 的任务定义快照。
- 通常包括 `task_name`、`domain`、`goal`、`dataset`、`baseline`、`metrics`、`constraints`、`task_description` 等字段。
- 这是理解任务目标、指标方向和实验约束的首要上下文。

使用建议：

- 后续论文或报告应从这里读取任务背景、数据描述、baseline 描述和指标定义。
- 不应从候选 idea 的自由文本里反推任务目标。

### `discovery_summary.json`

位置：

```text
results/<task_name>/<launch_id>_launch/discovery_summary.json
```

含义：

- launch 结束后的汇总索引。
- 当前代码写入 `timestamp`、`launch_id`、`task`、`task_type`、`mode`、`loop_rounds`、`loop_mode`、`sessions`、`total_ideas`、`total_successful`、`total_failed`、`rounds` 等字段。
- incremental 模式下还会包含 `incremental_mode.final_best_code_path` 和 `incremental_mode.final_best_performance`。

使用建议：

- 适合作为 launch 级索引入口。
- 其中的 `rounds[].results[]` 记录每个实验候选的返回结果，包括 `idea_name`、`success`、`folder_name`、`code_path`、`performance`。
- `performance` 是派生字段，不应替代 `final_info.json`。

## 3. Session 级产物

### `ideas.json`

位置：

```text
results/<task_name>/<launch_id>_launch/session_<id>/ideas.json
```

含义：

- 当前 session 选出的 top ideas。
- 每个 idea 通常包含 `name`、`title`、`description`、`method` 等字段。

使用建议：

- 适合作为论文中方法动机、候选方法描述、实验设计背景的输入。
- 其中的主张是“计划/设想”，不是实验事实。实验事实必须回到 `run_N/final_info.json` 和代码。

### `traj.json`

位置：

```text
results/<task_name>/<launch_id>_launch/session_<id>/traj.json
```

含义：

- MAS idea generation / refinement 的轨迹记录。
- 是否存在取决于具体运行路径。

使用建议：

- 适合做可追溯性、审计和过程复盘。
- 不应作为论文结果的事实源。

## 4. 候选实验工作区产物

每个 candidate experiment folder 代表一个 idea 的完整实验尝试：

```text
results/<task_name>/<launch_id>_launch/session_<id>/<timestamp>_<idea_name>/
```

### `notes.txt`

含义：

- 实验开始时写入的 idea 摘要。
- 通常包括 `Name`、`Title`、`Description`、`Method` 和 `Run 0: Baseline`。

使用建议：

- 适合快速理解该候选的设计意图。
- 不代表最终实现一定严格符合这些描述。

### `code/`

含义：

- 当前候选实验的最新代码目录。
- successful experiment 返回结果中的 `code_path` 当前指向这个候选实验工作区，而不是只指向 `code/` 子目录。

使用建议：

- 这是理解最终实现的主要来源。
- 若存在 `code/code_summary.json`，可作为代码结构摘要，但不能替代源代码。

### `launcher.sh`

含义：

- 实验执行入口。
- 当前 prompt 明确要求 agent 不要随意修改 launcher，实际是否被修改仍需按文件内容确认。

使用建议：

- 后续复现实验时应记录实际执行入口。
- 若候选根目录和 `run_N/` 中都有 `launcher.sh`，应以该 run 实际使用的文件为准。

### `log.txt`

含义：

- 候选实验的执行日志。
- 包含 agent 输出、执行过程和错误信息。

使用建议：

- 适合排查失败原因和核对实验过程。
- 日志很长时，不适合作为论文正文输入，应先抽取关键事实。

### `experiment_report.txt`

含义：

- Claude Code backend 在实验结束后生成的简短实验报告。
- 当前提示要求它概述每个 run 做了什么、从 `final_info.json` 得到什么结果，或失败时总结错误。

使用建议：

- 这是叙述性辅助材料，不是事实源。
- 已观察到 run 编号表述可能和真实目录存在轻微错位，因此应以目录结构和 `final_info.json` 为准。
- 可用于生成论文初稿的“实验过程摘要”，但每个数字都要回查 `final_info.json`。

## 5. Run 级产物

每个候选实验下会有：

```text
run_0/
run_1/
run_2/
...
```

### `run_0/`

含义：

- 基线快照。
- 通常包含 `final_info.json`，有时也包含基线代码备份。

使用建议：

- 用于和后续 `run_1..N` 比较。
- incremental 模式下，`run_0` 可能已经是上一轮 best result 更新后的基线，不一定等于原始 task baseline。

### `run_N/final_info.json`

含义：

- 每次实验运行的机器可读结果。
- 这是当前实验事实中最重要的产物。

常见 schema：

```json
{
  "combined_score": 0.02,
  "mean_r2": 0.99
}
```

或：

```json
{
  "TaskName": {
    "means": {
      "metric": 1.23
    }
  }
}
```

使用建议：

- 后续论文、报告和 best-result 选择都应优先读取这里。
- 当前 `ExperimentRunner._extract_metrics_from_final_info()` 主要处理 nested `means` 结构；flat metric map 可能不会被提取到派生 `performance` 字段。因此不能假设 `performance` 一定完整。
- 不同任务指标方向不同。比如有些任务 `combined_score` 越小越好，有些指标越大越好。不能只按 `(current - baseline) / abs(baseline)` 排序。

### `run_N/code/`

含义：

- 该 run 对应的代码快照。

使用建议：

- 当根目录 `code/` 和 `run_N/code/` 不一致时，应以目标 run 的 `run_N/code/` 作为该 run 结果的实现证据。

### `run_N/notes.txt`、`run_N/log.txt`、`run_N/prompt.json`

含义：

- run 级补充痕迹。
- `prompt.json` 记录该 run 使用的任务/环境上下文。
- `log.txt` 记录执行过程。
- `notes.txt` 记录该 run 的简要说明。

使用建议：

- 适合审计和失败诊断。
- 论文正文不应直接依赖这些文件中的未经校验解释。

## 6. Sci task 特有产物

Sci task 是论文复现任务，和普通 auto discovery 不同。其工作区通常额外包含：

```text
data/
related_work/
target_study/
outputs/
report/
  report.md
  images/
```

含义：

- `data/`：原始数据。
- `related_work/`：参考论文。
- `target_study/`：复现目标和 checklist。
- `outputs/`：中间结果。
- `report/report.md`：sci task 要求生成的最终复现报告。
- `report/images/`：报告图像。

使用建议：

- `report/report.md` 是 sci task 的评分对象，但它仍然需要和 `final_info.json`、`outputs/`、`report/images/` 交叉核验。
- 普通 auto discovery 当前不稳定生成 `report/report.md`，不能把 sci task 的报告契约直接套到 auto task。

## 7. Report mode 产物

`--mode report` 会调用当前 `ReportWriter`，它生成的是 idea-only markdown：

```text
results/<task_name>/<timestamp>_<idea_name>/report.md
```

含义：

- 由 idea 的 `title`、`description`、`method`、`expected_outcomes`、`limitations` 直接拼成。
- 不基于真实实验结果。

使用建议：

- 不应把这个 `report.md` 当作成品论文或实验后报告。
- 它可以作为 idea 草稿，但不能作为实验结果证据。

## 8. 可信层级

建议按以下顺序判断事实可信度：

1. `run_N/final_info.json`：实验指标事实源。
2. `run_N/code/` 和根 `code/`：实现事实源。
3. `prompt.json`：任务定义、指标方向、约束事实源。
4. `launcher.sh`、`log.txt`：执行过程事实源。
5. `outputs/`、`report/images/`：数据和图像事实源，若存在。
6. `experiment_report.txt`：实验叙述辅助。
7. `notes.txt`、`ideas.json`：设计意图和过程辅助。

## 9. Best result 的当前含义

当前实验返回结果中，每个成功候选会带：

```json
{
  "idea_name": "...",
  "success": true,
  "folder_name": "...",
  "code_path": "...",
  "performance": {
    "baseline_metrics": {},
    "current_metrics": {},
    "improvement_rates": {},
    "overall_improvement_rate": 0.0
  }
}
```

注意：

- `success` 表示 backend 认为实验流程成功完成，不等于科学结果一定有效。
- `folder_name` 是候选实验工作区路径。
- `code_path` 当前等于候选实验工作区路径，主要服务 incremental mode。
- `performance` 是派生比较结果，可能因 `final_info.json` schema 或指标方向而为空或误导。
- 对于论文生成或最终 best selection，应重新读取 `prompt.json` 的 metric direction 和目标 run 的 `final_info.json`，不要盲信 `overall_improvement_rate`。

## 10. 对后续论文产物的直接启示

如果未来要把实验自然产物升级为论文产物，最小事实输入应包括：

- launch 级 `prompt.json`
- session 级 `ideas.json`
- best candidate folder
- best run 的 `final_info.json`
- best run 或 candidate root 的 `code/`
- 可选的 `experiment_report.txt`
- 可选的 `outputs/`、`report/images/`

论文系统应避免直接从自然语言叙述中复制实验结论。所有指标、表格、图注和贡献声明都需要能追溯到上述事实产物。
