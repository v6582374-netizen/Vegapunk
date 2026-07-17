# PaperOrchestra 到 InternAgent 的迁移 Spec

> [!WARNING]
> 本文是已被取代的原生重写方案，仅保留为历史设计证据。当前实现以完整 vendoring 固定上游源码并做最小适配为准；请阅读 [PaperOrchestra 移植对等性审计](./paper_orchestra_port_parity_audit.md) 与 ADR-0101 至 ADR-0122。

## 1. 文档状态

- 状态：已被完整 vendoring 方案取代，仅作历史参考
- 日期：2026-07-10
- 目标仓库：InternAgent `a5358fa079eb5c17c3b2d5de91cd4a5778abe404`
- 来源仓库：PaperOrchestra `ca1b3fa01c2970fc7cda32d16245db38d57b3f56`
- LaTeX 模板：ElegantPaper `40275032d6e3073e658038de30a98e1b4785f052`
- 领域术语：[CONTEXT.md](../CONTEXT.md)
- 架构决策：`docs/adr/` 中状态为 `accepted` 的 ADR；状态为 `superseded` 的 ADR 只保留历史背景，不参与实现。

本文定义首个可运行版本。除非后续 ADR 明确覆盖，否则实现不得扩展本文的能力边界。

## 2. 目标

在 InternAgent 的全部 Discovery Rounds 完成后，自动触发一次 PaperOrchestra 写作流程，把现有 Discovery Launch 产物转化为一份中文优先、可审查、可恢复、带候选选择说明的 Research Dossier，并生成最终 LaTeX 和 PDF。

核心目标如下：

1. 最大限度保留 PaperOrchestra 的 Outline、文献写作、章节写作、内容反思、版式审查和 PDF 审查架构。
2. 除 `launch_discovery.py` 末尾的单一触发调用外，不修改 InternAgent 现有发现、实验、模型、任务配置和产物生成逻辑。
3. Candidate Experiment 目录对 PaperOrchestra 完全只读。
4. 所有模型调用统一使用 InternAgent 的 `UnifiedModelRuntime`。
5. 标准 `experiment` 模式默认完成 Discovery 到最终论文的同步闭环。
6. 所有候选选择回退、模型主观判断和随机选择均可审计，并按约定进入论文。

## 3. 非目标

首版明确不包含：

- 修改 Candidate Experiment 的目录结构或补写 manifest。
- 修改现有 `config/default_config.yaml` 或任务 `prompt.json`。
- PaperOrchestra 自带的 Gemini/OpenAI 客户端、API key 加载和 provider 选择。
- 在线文献搜索、元数据补全或论文阶段的引用扩展。
- Plotting Agent、图像生成和替代实验图生成。
- Streamlit 前端、批处理驱动、benchmark CLI 和旧 shell 脚本。
- ICLR/CVPR 模板及模板注册表、插件系统或能力协商系统。
- Citation F1、side-by-side paper rating 和其他离线 benchmark。
- `report` 模式的简化论文类型。
- 多个并发写进程操作同一个 Dossier Run。
- 修改或重新判定 InternAgent 已完成的轮间 baseline 选择。

## 4. 系统边界

### 4.1 执行关系

```text
launch_discovery.py
│
├── Discovery Round 1
├── Discovery Round 2
├── ...
├── Discovery Round N
├── 写入 discovery_summary.json
│
└── 同步调用一次 Dossier Service
    ├── 终局候选选择
    ├── 原材料生成
    ├── PaperOrchestra 写作与审查
    └── 最终 LaTeX/PDF
```

目录层级不决定执行频率。`dossier_runs/` 位于 Discovery Launch 下，但只在整个 round 循环结束且 `discovery_summary.json` 写入后触发一次。

### 4.2 唯一允许的现有源码改动

`launch_discovery.py` 在最终 summary 成功落盘后增加一个 Dossier Service 调用。该调用必须满足：

- 仅在 `args.mode == "experiment"` 时生效。
- 默认启用；`config/paper_orchestra.yaml` 可显式关闭。
- 只传 Discovery Launch 目录、现有 InternAgent 配置和 PaperOrchestra 配置。
- 不传 Candidate Experiment 路径。
- 不导入或编排任何单独的 PaperOrchestra Agent。
- 同步等待 Dossier Run 到达 `succeeded` 或 `failed`。
- Dossier 失败只记录错误，不把已完成的 Discovery 改判为失败。

建议调用形状：

```python
result = asyncio.run(
    run_dossier(
        launch_dir=Path(args.output_dir),
        internagent_config=config,
        paper_config_path=Path("config/paper_orchestra.yaml"),
        dossier_run_id="primary",
    )
)
```

实际实现可避免在已有事件循环中嵌套 `asyncio.run`，但公开服务必须保持异步。

## 5. 目标文件布局

### 5.1 新增代码

```text
internagent/
└── paper_orchestra/
    ├── __init__.py                  # 仅导出 run_dossier 及结果类型
    ├── service.py                   # Dossier Service 应用入口
    ├── config.py                    # PaperOrchestra 配置加载与验证
    ├── data_types.py                # Dossier/selection/stage 类型
    ├── checkpoint.py                # dossier_run.json 与恢复
    ├── candidate_selection.py       # 终局候选收敛
    ├── artifact_linker.py           # result -> ideas.json -> traj.json
    ├── raw_materials.py             # 确定性输入投影
    ├── pipeline.py                  # 完整写作阶段调度
    ├── methods/
    │   ├── agents/
    │   │   ├── outline_agent.py
    │   │   ├── literature_review_agent.py
    │   │   ├── section_writing_agent.py
    │   │   └── content_refinement_agent.py
    │   └── prompts/
    ├── autoraters/
    │   └── agent_review.py
    └── utils/
        ├── common_utils.py
        ├── content_parsing_utils.py
        ├── pdf_utils.py
        └── prompt_utils.py

config/
└── paper_orchestra.yaml

tex_templates/
└── elegantpaper/

launch_dossier.py                    # 历史 Launch 的独立入口
```

模块名可按现有风格小幅调整，但以下边界不可改变：

- `internagent.paper_orchestra` 只有一个公开应用入口。
- Discovery 不导入 `methods/agents/`。
- candidate selection、artifact linking、raw-material rendering 均位于 PaperOrchestra 侧。
- ported agents 继续保持 PaperOrchestra 的职责分离。

### 5.2 不迁移的来源文件

不迁移或不进入运行路径：

- `frontend/`
- `methods/agents/plotting_agent.py`
- `methods/paper_writer_with_plotting.py`
- `utils/gemini_utils.py`
- `utils/openai_utils.py`
- `utils/scholar_utils.py`
- `utils/paper_banana_utils.py`
- `autoraters/citation_f1.py`
- `autoraters/sxs_*`
- `templates/iclr2025/`
- `templates/cvpr2025/`
- `paper_writing_cli.sh`
- benchmark/batch 入口

来源仓库的 LICENSE 必须保留；目标包增加 `UPSTREAM.md`，记录来源 URL、commit、迁移范围和本地改造。

## 6. 配置契约

新增 `config/paper_orchestra.yaml`：

```yaml
enabled: true
template_dir: tex_templates/elegantpaper
layout_review_enabled: true
max_content_refinement_iterations: 3
max_format_correction_iterations: 1
```

规则：

- 不包含 provider、model、endpoint、API key 或 credential。
- 不覆盖 InternAgent 的模型配置。
- `primary` Dossier Run ID、阶段顺序、输出文件名和 checkpoint 语义不可配置。
- 配置加载后必须验证路径、布尔值和非负迭代上限。
- resolved PaperOrchestra 配置快照写入 `dossier_run.json`，用于审计；模型只记录 provider/model 身份，不写入 credential、API key 或 endpoint secret。
- `enabled: false` 时不创建 Dossier Run。

## 7. Dossier Service API

建议接口：

```python
async def run_dossier(
    *,
    launch_dir: Path,
    internagent_config: dict[str, Any],
    paper_config_path: Path,
    dossier_run_id: str = "primary",
) -> DossierRunResult:
    ...
```

建议结果类型：

```python
@dataclass(frozen=True)
class DossierRunResult:
    dossier_run_id: str
    status: Literal["succeeded", "failed"]
    run_dir: Path
    final_pdf: Path | None
    final_tex: Path | None
    warnings: tuple[str, ...]
    error: DossierError | None
```

Service 内部构造一个共享 `UnifiedModelRuntime`，并将其传给所有 ported agents。

历史入口：

```bash
python launch_dossier.py \
  --launch-dir results/<task>/<launch_id>_launch \
  --config config/default_config.yaml \
  --paper-config config/paper_orchestra.yaml \
  --dossier-run-id primary
```

规则：

- `--launch-dir` 必须显式指定，不能扫描全局 results 并猜测最新 Launch。
- 不传 `--dossier-run-id` 时使用 `primary`。
- 显式使用新 ID 表示从头开始一份独立写作尝试。
- standalone 命令在 Dossier 失败时返回非零退出码；Discovery 内嵌调用保持 Discovery 原退出语义。

## 8. Discovery Launch 输入验证

模型调用前必须验证：

1. `launch_dir` 存在且为目录。
2. `discovery_summary.json` 存在、可解析且属于该目录。
3. summary 的 `mode` 为 `experiment`。
4. `rounds` 是非空列表，每一轮具有 `round`、`session_id` 和 `results`。
5. 每个 result 的 `success`、`idea_name` 字段形状合法；只有 `success: true` 的 result 必须具有合法 `folder_name`。失败 result 缺少目录时只作为失败事实，不推断路径，见 ADR-0045。
6. 所有被使用的路径解析后仍位于当前 Discovery Launch 内。
7. `dossier_runs/<id>/` 不与普通 session 或 Candidate Experiment 重叠。

Candidate Experiment 及 session 文件只能读取，不得写入、移动、删除或补充文件。

## 9. Terminal Candidate Selection

### 9.1 Paper Candidate Round

按 `round` 从大到小扫描已完成轮次，选择最近一个包含至少一个 `success: true` result 的轮次。

- 找到后停止向前扫描，不跨轮比较。
- 如果整个 Launch 没有成功候选，Dossier Run 进入 `failed`，错误码为 `no_successful_candidate`，且不调用写作模型。
- 跳过的较新轮次及其无成功事实写入 Candidate Selection Provenance，并按 ADR-0032 进入论文。

### 9.2 候选比较

1. 只有一个成功候选：直接选择。
2. 多个成功候选：优先读取 launch 根目录 `prompt.json` 的：
   - `metrics.primary`
   - `metrics.optimization_direction`
3. 任一字段缺失时，只在此终局阶段调用一次 `BaseModel.generate_json()`：
   - 输入限于现有 `prompt.json` 文本和候选实际报告的指标名。
   - 已存在的结构化字段不能被模型覆盖。
   - 不搜索外部资料。
   - 输出必须验证为实际指标名及 `minimize|maximize`。
4. 从每个候选当前有效 Experiment Run 的 `final_info.json` 读取主指标值。
5. 缺失、非数值、NaN 或无穷值不参与数值比较。
6. 有可比较集合时，按方向选择唯一最优值。
7. 完全相同的最优值构成 tie pool，并在 tie pool 中随机选择。
8. 任何其他无法产生唯一候选的情况，直接在相应成功候选池中随机选择，不继续增加恢复分支。
9. 随机选择永不包含 `success: false` 的候选。

随机结果必须在后续模型调用前持久化；同一 Dossier Run 恢复时不得重新抽取。新的 Dossier Run ID 可以产生新的选择。

### 9.3 当前有效 Experiment Run

当前有效 run 定义为：按数字从大到小扫描 `run_<n>`，选择第一个具有可读、非空 `final_info.json` 的 run。它是“current valid run”，不得称为“best run”。

### 9.4 `candidate_selection.json`

文件位于 Dossier Run 根目录，一次原子写入后不可变。建议结构：

```json
{
  "schema_version": 1,
  "created_at": "2026-07-10T12:00:00+08:00",
  "launch_id": "20260710_100000_launch",
  "dossier_run_id": "primary",
  "paper_candidate_round": {
    "round": 8,
    "session_id": "session_123",
    "skipped_later_rounds": [10, 9],
    "skipped_later_round_facts": [
      {
        "round": 10,
        "session_id": "session_125",
        "result_count": 2,
        "successful_candidate_count": 0
      },
      {
        "round": 9,
        "session_id": "session_124",
        "result_count": 1,
        "successful_candidate_count": 0
      }
    ]
  },
  "successful_candidates": [
    {
      "idea_name": "method_a",
      "folder_name": "session_123/20260710_method_a",
      "metric_source": "run_2/final_info.json",
      "primary_metric_value": 0.76,
      "exclusion_reason": null
    }
  ],
  "criterion": {
    "source": "task_config|model_inference|unavailable",
    "primary_metric": "mse",
    "optimization_direction": "minimize",
    "source_paths": ["prompt.json"],
    "model_input": null,
    "model_output": null,
    "reasoning": null
  },
  "selection_method": "sole_success|metric|random_tie|random_fallback",
  "fallback_reason": null,
  "fallback_pool": [],
  "selected_candidate": {
    "idea_name": "method_a",
    "folder_name": "session_123/20260710_method_a"
  }
}
```

模型推断时必须保留完整结构化输入/输出和理由。随机选择时必须保留触发原因和完整随机池。

## 10. Selected Result 到完整 Idea 的精确关联

关联顺序固定：

1. 从 selected result 的 `folder_name` 取得 Candidate Experiment 路径。
2. 从所属 round 的 `session_id` 定位 `session_<id>/ideas.json` 和 `traj.json`。
3. 在 `ideas.json` 中按 `idea_name` 完全相等匹配一个执行方法。
4. 取得该方法的完整 `refined_method_details` 对象。
5. 在 `traj.json.top_ideas` 指向的 Ideas 中，按完整 `refined_method_details` 对象完全相等匹配。
6. 唯一匹配的完整 Idea 是 `idea.md`、evidence 和 references 的来源。

禁止：

- 模糊名称匹配。
- 标题相似度。
- 目录时间戳推断。
- 模型判断。
- 在多个 Idea 中随机绑定。

缺文件、零匹配或多匹配均为 `artifact_link_failed`，在 raw-material 阶段前终止。

## 11. Dossier Run 目录契约

```text
<discovery_launch>/
├── discovery_summary.json
├── prompt.json
├── session_*/
└── dossier_runs/
    └── primary/
        ├── dossier_run.json
        ├── candidate_selection.json
        ├── raw_materials/
        │   ├── idea.md
        │   ├── experimental_log.md
        │   ├── references.bib
        │   ├── citation_map.json
        │   └── figures/
        │       ├── info.json
        │       └── ...
        ├── latex_writeup/
        │   ├── final_refined_paper.tex
        │   └── ...
        └── final_paper.pdf
```

所有 Dossier 文件都写在 launch 级 `dossier_runs/` 下。Candidate Experiment 目录在前后必须保持字节级不变。

## 12. Raw Materials 契约

### 12.1 `idea.md`

`idea.md` 是完整选中 Idea 的确定性 Markdown 投影，不调用模型，不总结，不补全。

字段映射：

| 输出 | 来源 |
|---|---|
| Title | 执行方法 `title` |
| Method name | 执行方法 `name` |
| Research hypothesis | `Idea.text` |
| Motivation | `Idea.rationale` |
| Baseline context | `Idea.baseline_summary` |
| Method overview | 执行方法 `description` |
| Novelty/theory | 执行方法 `statement` |
| Method details | 执行方法 `method` |

执行方法优先级与 InternAgent 一致：

1. 非空 `refined_method_details`
2. 非空 `method_details`
3. 支持的 flat fields

空可选字段省略标题；执行方法为空则输入验证失败。score、critique、evidence、references、旧方法版本和 evolution history 不进入方法主体。

### 12.2 `experimental_log.md`

来源仅为选中 Candidate Experiment 的现有目录，覆盖：

- `run_0` baseline。
- 所有数字 run，按数字升序。
- 每个 run 的 ID、相对路径和结构状态。
- 存在时原样嵌入 `final_info.json`。
- 存在时原样嵌入 `report/report.md`。
- 失败 run 只引用 `traceback.log` 相对路径，不嵌入或分类堆栈。

结构状态限于 baseline、successful、failed、no metrics produced。不得计算新的改善率、聚合分数或“best run”，也不得把普通迭代称为 ablation。

### 12.3 `figures/`

只使用当前有效 Experiment Run 的 `report/images/`：

- 解析该 run 的 `report/report.md` 中显式 Markdown 图片引用。
- 目标必须位于 `report/images/` 且真实存在。
- 保留文件名。
- alt text 原样作为 caption；空 alt 使用文件名。
- 不引用未在 Markdown 中出现的诊断图。
- 不用 VLM 生成 caption。
- 没有图片时写空数组 `info.json`，不判失败。

首版只走 PaperOrchestra existing-figure 路径。

### 12.4 引用材料

完整可引用集合来自选中 Idea：

- `Idea.references` 提供 authors、year、journal、DOI、URL 等元数据。
- `Idea.evidence` 提供 abstract/content 和 relevance。

确定性关联：

1. 规范化 DOI 完全相等。
2. 无 DOI 时，规范化 title 完全相等。
3. 禁止 fuzzy matching、模型修复和在线补全。

只有同时具有 reference metadata 与 evidence content 的记录进入可引用集合。相同集合写入：

- `references.bib`
- `citation_map.json`

未匹配项可留在 Dossier 审计数据中，但不得被论文引用。Literature Agent 只能从批准 citation keys 中选择，不能创建 key、搜索或补全元数据。

### 12.5 Candidate Selection Provenance

`candidate_selection.json` 不转换成中间 Markdown。Pipeline 直接把结构化内容提供给 `研究过程` writer。

以下情况必须在论文的候选选择小节中明确出现：

- 向更早 Discovery Round 回退及跳过的轮次。
- 模型推断的主指标或方向，并标注为“模型的主观判断”。
- 模型判断使用的来源文件及实际参与比较的候选指标值。
- 被排除的成功候选及缺失指标原因。
- metric tie 与随机 tie-break。
- 任意 random fallback 的候选池、最终选中者及其触发原因。

缺少必需披露属于最终验证失败，而不是 warning。

## 13. ElegantPaper 模板契约

完整 ElegantPaper 项目导入 `tex_templates/elegantpaper/`，作为普通 InternAgent tracked files，不使用 submodule 或嵌套 Git 仓库。

必须保留：

- 上游 README。
- LPPL 1.3c license 与 notices。
- 未修改的 `elegantpaper-cn.tex` 示例。
- `UPSTREAM.md`，记录 URL、版本、commit 和本地改造。

集成新增：

- `template.tex`：干净的中文写作入口。
- `guidelines.md`：PaperOrchestra 使用的写作和版式约束。

不得把上游示例正文作为论文原材料。PaperOrchestra 只重写集成自有的 `template.tex`。

## 14. Research Narrative 内容契约

默认语言为中文。模型名、代码标识符、数据集名、原论文标题和必须保真的术语可保留原语言。

固定结构：

```text
摘要（前置内容）
引言
相关工作
方法
实验
研究过程
复现指南
局限性与适用边界
结论
```

规则：

- top-level section 固定，subsection 可由 outline 动态生成。
- `研究过程` 位于实验之后，包含有记录时的失败尝试、过程修正和候选选择说明。
- 不存在显式记录时，不生成失败尝试或过程修正内容。
- `复现指南` 必须从现有环境、代码、配置和运行路径生成，不补造命令。
- `局限性与适用边界` 只能陈述已有证据、未评估条件或明确未知项。
- 论文标题取执行方法的 `title`，writer 不得替换。
- authors、institutions、contacts 默认空，不从 Git、OS 用户或 Agent 名推断。
- 日期使用 Dossier Run 首次创建日期。

## 15. LaTeX 与 PDF

编译工具链固定为 XeLaTeX + Biber，使用：

```tex
\addbibresource{references.bib}
```

实现可使用 `latexmk -pdfxe` 驱动必要的 XeLaTeX/Biber 多遍编译，但必须：

- 设置明确 timeout。
- 捕获 stdout/stderr 到 Dossier Run 内日志。
- 验证退出码、PDF 存在、PDF 非空且可打开。
- 不回退到 PDFLaTeX/BibTeX。
- 不引入 bibliography 转换层。

最终交付：

- `final_paper.pdf`
- `latex_writeup/final_refined_paper.tex`

二者缺一或为空，Dossier Run 不能进入 `succeeded`。

### 15.1 运行前置条件

Python 侧优先复用 InternAgent 已有依赖：

- `json_repair` / `pydantic`：结构化模型输出验证。
- `PyYAML`：PaperOrchestra 配置。
- `pdfplumber` / `pypdf`：PDF 文本与结构读取。
- `pypdfium2` / `Pillow`：页面渲染与 VLM 图片输入。

首版不因来源仓库的实现习惯而引入新的 Gemini/OpenAI SDK、`thefuzz`、Matplotlib 或 OpenCV 运行依赖。若 ported utility 仍需新的非 provider Python 包，应放入 PaperOrchestra 自有依赖声明并在实现 PR 中单独说明，不能静默扩大 InternAgent 根依赖。

系统侧必须可执行：

- `latexmk`
- `xelatex`
- `biber`

Dossier Service 在创建写作阶段前执行 preflight。缺少二进制或 ElegantPaper 所需 TeX/font 资源时，记录明确环境错误，不等待到最终编译才暴露。

## 16. 统一模型接口

所有 ported agents 共享同一个 `BaseModel`：

| 场景 | API |
|---|---|
| 文本与 LaTeX | `await model.generate(...)` |
| JSON/结构化审查/候选判断 | `await model.generate_json(...)` |
| 页面截图/VLM | `await model.generate_with_messages(...)` |

要求：

- ported pipeline 和 agents 原生 async。
- 删除硬编码 Gemini/OpenAI model names。
- 删除 provider clients、API key 读取、fallback provider 和同步 event-loop bridge。
- 不新增 PaperOrchestra model gateway；`BaseModel` 已是唯一模型抽象。
- 配置模型不支持图片时，layout review 阶段明确失败，不静默跳过或切换 provider。

## 17. PDF 内容与版式审查

内容审查输入：

- 完整当前 LaTeX。
- 从当前编译 PDF 确定性提取的完整文本。

版式审查输入：

- 当前 PDF 的逐页截图或网格截图。
- 使用 `generate_with_messages()`。

禁止向模型发送 Gemini `application/pdf` 原生二进制输入，也不扩展 `BaseModel` 的 PDF upload API。

PDF 文本提取失败与页面渲染失败分别记录为对应阶段失败。

## 18. 写作与反思流水线

固定执行顺序：

```text
validate_launch
→ terminal_candidate_selection
→ link_selected_artifacts
→ prepare_raw_materials
→ prepare_latex_workspace
→ generate_outline
→ write_introduction_and_related_work
→ write_remaining_sections
→ compile_initial_draft
→ refine_content
→ review_layout_and_optionally_correct
→ compile_final
→ validate_final_outputs_and_disclosures
```

内容优化：

- 最多 3 轮。
- 每轮产生新的 TeX、PDF 和 peer review。
- 新版本整体评分或 review axes 降级时，停止并保留上一份已接受版本。

版式优化：

- `layout_review_enabled: true` 是默认值；默认路径必须执行 VLM layout review。
- 只有配置显式设为 `false` 时才跳过该阶段，并记录 `layout_review_disabled_by_config` warning。
- 有 actionable issues 时最多做 1 次 formatting-only correction。
- 无问题时直接使用当前内容版本。
- 迭代上限后残留建议进入 `warnings`；只要全部必要阶段与最终编译完成，仍可成功。

不运行 Citation F1、paper-to-paper rating 或其他 benchmark autoraters。

## 19. Checkpoint 与恢复

不保留 PaperOrchestra 的“异常后整条管线最多从头重跑三次”。

每个阶段具有：

- `pending`
- `running`
- `succeeded`
- `failed`

总状态只有：

- `running`
- `succeeded`
- `failed`

`dossier_run.json` 建议结构：

```json
{
  "schema_version": 1,
  "dossier_run_id": "primary",
  "launch_id": "20260710_100000_launch",
  "status": "running",
  "created_at": "...",
  "updated_at": "...",
  "resolved_config": {},
  "model": {
    "provider": "...",
    "name": "..."
  },
  "stages": [
    {
      "id": "terminal_candidate_selection",
      "status": "succeeded",
      "started_at": "...",
      "completed_at": "...",
      "outputs": ["candidate_selection.json"],
      "error": null
    }
  ],
  "warnings": [],
  "final_outputs": {
    "pdf": null,
    "tex": null,
    "pdf_sha256": null,
    "tex_sha256": null
  },
  "error": null
}
```

规则：

- manifest 使用临时文件 + rename 原子更新。
- 阶段只有在预期输出通过验证后才标记 `succeeded`。
- 同一 ID 从首个非 `succeeded` 阶段恢复。
- crash 留下的 `running` stage 在恢复时视为未完成，可重跑该阶段，但不得重跑更早成功阶段。
- `candidate_selection.json` 存在后必须验证并复用，不得覆盖。
- `primary` 已成功时直接返回已有输出。
- 恢复同一 ID 时，解析后的配置和模型身份必须与 manifest 快照一致；不一致时使用新 ID。
- 新 Dossier Run ID 才表示全新选择和写作。
- 同一 Dossier Run 只允许一个 writer；并发启动应明确失败，不做多进程协调。

## 20. 错误与 warning

必须区分：

- 输入/路径验证错误。
- 无成功候选。
- artifact 精确关联错误。
- raw-material 渲染错误。
- 模型调用或结构化解析错误。
- LaTeX/Biber 编译错误。
- PDF 文本提取错误。
- 页面渲染/VLM 错误。
- 必需候选选择披露缺失。

错误对象至少包含：

```json
{
  "stage": "compile_final",
  "code": "latex_compile_failed",
  "message": "...",
  "log_path": "latex_writeup/logs/compile_final.log"
}
```

异常不得触发 provider 切换、在线搜索、科研内容补全或整管线重跑。

## 21. 完成判定

Dossier Run 只有满足全部条件才是 `succeeded`：

1. `candidate_selection.json` 存在、合法且与 selected artifacts 一致。
2. 所有 raw materials 通过确定性验证。
3. accepted pipeline 的每个必要阶段均为 `succeeded`。
4. 内容审查实际执行；VLM layout review 在默认启用时实际执行，显式关闭时具有对应 warning。
5. 所有要求的候选选择披露出现在 `研究过程`。
6. `latex_writeup/final_refined_paper.tex` 存在且非空。
7. `final_paper.pdf` 存在、非空且可打开。
8. PDF 为最终 TeX 的本次编译产物。
9. manifest 中记录的最终 TeX/PDF SHA-256 与磁盘文件一致。

审查残留建议只进入 `warnings`，不增加第四种终态。

## 22. 测试要求

### 22.1 单元测试

- Paper Candidate Round 从最终轮向前回退。
- 整个 Launch 无成功候选。
- 单一成功候选直接选择。
- 显式 maximize/minimize 指标选择。
- 结构化字段缺失时的受限模型判断。
- 非有限指标排除。
- 无可比较值时随机 fallback。
- exact tie 随机选择。
- 同一 Dossier Run 恢复不重新随机或推断。
- result、`ideas.json`、`traj.json` 精确关联。
- ambiguous Idea join 明确失败。
- `idea.md` 字段与空字段处理。
- run 数字排序，避免 `run_10` 排在 `run_2` 前。
- `experimental_log.md` 原样内容与失败路径。
- Markdown 图片引用解析及路径逃逸拒绝。
- DOI/title exact citation join。
- checkpoint 原子写入与首个未完成阶段恢复。
- 三状态总生命周期。

### 22.2 集成测试

- 使用 fake `BaseModel` 运行完整 async pipeline。
- 验证所有 agents 收到同一个 model 对象。
- 验证 structured calls 使用 `generate_json()`。
- 验证页面截图使用 `generate_with_messages()`。
- 编译最小中文 ElegantPaper 文档，确认 XeLaTeX/Biber 成功。
- 从 content-refinement 或 layout-review 故障恢复，不重跑 outline。
- 候选随机 fallback 后中断并恢复，选择保持不变。
- PaperOrchestra disabled 时不创建 `dossier_runs/`。
- `report` 模式不触发 Dossier。

### 22.3 端到端验收

准备一个完整、可控的 Discovery Launch fixture，至少包含两个 rounds 和多个 Candidate Experiments。验收：

- 自动调用只发生一次且位于 round loop 之后。
- `dossier_runs/primary/` 创建在 launch 层。
- 所有 Candidate Experiment 文件在执行前后 hash 不变。
- 候选选择记录与论文披露一致。
- 无 PaperOrchestra 网络文献搜索。
- 无 Gemini/OpenAI helper 调用。
- VLM layout review 默认实际发生。
- 最终 PDF 可打开、非空、包含中文章节和引用。
- 第二次调用直接复用成功的 `primary`。
- 人为删除中间阶段输出时，验证失败并从对应阶段恢复。

## 23. 实现顺序

建议按以下可独立验证的顺序实施：

1. 导入 ElegantPaper、license 和 `UPSTREAM.md`，完成最小 XeLaTeX/Biber smoke test。
2. 建立 `internagent.paper_orchestra` 包和统一 async model 调用。
3. 移植 PDF/LaTeX utilities、Outline/Section/Literature/Refinement agents 与必需 autorater。
4. 实现 Dossier data types、三状态 manifest 和 stage checkpoint。
5. 实现 Terminal Candidate Selection 与 `candidate_selection.json`。
6. 实现 selected result 到完整 Idea 的精确关联。
7. 实现 raw-material renderers。
8. 组装完整 pipeline、内容迭代、VLM 审查和最终验证。
9. 增加 `launch_dossier.py` 历史入口。
10. 最后在 `launch_discovery.py` summary 写入后增加单一同步触发器。
11. 完成单元、集成与端到端验收。

每一步都必须保持 Candidate Experiment 只读，并避免在中间阶段引入旧 provider、在线搜索或 Plotting Agent。

## 24. 验收清单

- [ ] 现有 InternAgent 实验与任务逻辑未被修改。
- [ ] `launch_discovery.py` 只有单一 Dossier Service 焊点。
- [ ] Candidate Experiment 目录只读。
- [ ] `experiment` 默认同步生成一个 `primary` Dossier。
- [ ] `report` 与 disabled 路径不创建 Dossier。
- [ ] 候选选择、回退、推断和随机行为完整落盘并进入论文。
- [ ] 完整 Idea、证据和引用通过精确结构化关联获得。
- [ ] PaperOrchestra 使用统一 `BaseModel`，无私有 provider client。
- [ ] online literature search 与 Plotting Agent 不在运行路径。
- [ ] ElegantPaper 中文模板由 XeLaTeX/Biber 编译。
- [ ] 内容审查、VLM 版式审查和 bounded refinement 完整执行。
- [ ] checkpoint 可从首个未完成阶段恢复。
- [ ] 最终输出严格为 `final_paper.pdf` 与 `latex_writeup/final_refined_paper.tex`。
- [ ] 所有必要 license 与 upstream provenance 已保留。
