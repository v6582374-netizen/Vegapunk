<div align="center">
  <img src="./assets/ia_logo.png" alt="InternAgent Logo" width="180" />
  <h1>Vegapunk V1.0</h1>
  <p><strong>从科研问题、假设生成和实验验证，到可审查中文论文的端到端闭环系统</strong></p>
  <p>
    <a href="https://arxiv.org/abs/2505.16938">InternAgent 1.0 论文</a> ·
    <a href="https://huggingface.co/papers/2602.08990">InternAgent 1.5 技术报告</a> ·
    <a href="https://discovery.intern-ai.org.cn">项目主页</a> ·
    <a href="https://huggingface.co/collections/InternScience/internagent">Hugging Face</a>
  </p>
</div>

## 项目概览

Vegapunk 是一个面向长程自主科学发现的多智能体框架。系统能够围绕一个研究任务完成背景调研、假设生成、反思与演化、方法设计、实验执行、结果评估和跨轮次记忆。

本仓库进一步将 [PaperOrchestra](https://github.com/declare-lab/paper-orchestra) 迁移为 InternAgent 内部模块：一次实验模式的 Discovery Launch 完成后，系统会从已有实验产物中确定论文候选，整理可追溯的 Research Dossier，并通过中文友好的 [ElegantPaper](https://github.com/ElegantLaTeX/ElegantPaper) 模板生成经过内容审查和多模态版式审查的 LaTeX 与 PDF。

> [!IMPORTANT]
> PaperOrchestra 不维护独立的 Gemini/OpenAI 调用。所有写作、审查和视觉理解请求均复用 InternAgent 的统一模型配置与 `ModelFactory`；论文内容只使用已有实验、引用和图像产物，不推断未记录的科研事实。

## 核心能力

| 能力 | 说明 |
| --- | --- |
| 多智能体科研编排 | 串联生成、调研、反思、证据检索、演化、排序、方法开发与精炼 Agent |
| 多轮 Discovery Loop | 支持 `fresh` 与 `incremental` 模式，在多轮实验间更新候选和基线 |
| 可插拔实验执行 | 支持 Claude Code、iFlow 和 OpenHands 后端，以及顺序、并行和可选 MCTS 搜索 |
| 算法发现与论文复现 | 提供 `tasks/` 算法任务，并通过 `sci_tasks` 子模块支持 ResearchClawBench 论文复现任务 |
| 记忆与深度研究 | 提供任务记忆、在线记忆、IdeaGraph、经验生成、MCP 工具和独立 QA/Deep Research 流程 |
| 自动论文闭环 | Discovery 结束后自动执行候选选择、原料整理、提纲、写作、内容反思、PDF 编译和 VLM 版式审查 |
| 可解释与可恢复 | 保存候选选择依据、原始材料、阶段状态、错误信息和输出哈希，Dossier Run 支持断点续跑 |

## 系统架构

下图展示 InternAgent 核心系统的入口、Discovery 执行、多智能体系统、Deep Research、任务、模型、工具、记忆与外部服务之间的关系。

![InternAgent 系统架构](./diagram%20%281%29.png)

自动科研与论文产出的主路径如下：

```text
研究任务
  → 背景调研与假设生成
  → 反思、证据检索、演化与排序
  → 方法开发与候选实验
  → 多轮 Discovery Loop
  → discovery_summary.json
  → Terminal Candidate Selection
  → 可追溯 Raw Materials
  → PaperOrchestra 写作与审查
  → ElegantPaper LaTeX
  → final_paper.pdf
```

论文阶段遵循以下边界：

- 每个 Discovery Launch 最多生成一个规范 Research Dossier。
- 优先使用最后一轮中的成功候选；若最后一轮无成功实验，才向前回退到最近的成功轮次。
- 指标推断、轮次回退、并列或随机选择等例外必须记录在 `candidate_selection.json` 并披露于论文。
- 引用和图像只来自已有实验产物；初版不在写作阶段重新搜索文献或生成实验图。
- Dossier 失败不会篡改已经完成的 Discovery 结果，但会保留可诊断、可恢复的失败状态。

## 快速开始

### 前置条件

- Conda 或兼容的 Python 环境管理器
- Python 3.11
- 至少一个已配置的 OpenAI-compatible 或 OpenRouter 模型端点
- 至少一个实验执行后端：Claude Code、iFlow 或 OpenHands
- 生成论文时需要 `latexmk`、`xelatex` 和 `biber`

> [!NOTE]
> GPU 不是框架启动和 `AutoDebug` 任务的必要条件。系统会在可用时分配 CUDA GPU，否则实验可按任务实现回退到 CPU；是否需要 GPU 主要取决于具体研究任务。

### 安装

```bash
git clone --recurse-submodules https://github.com/v6582374-netizen/Vegapunk.git
cd Vegapunk

conda create -n InternAgent python=3.11
conda activate InternAgent
pip install -r requirements.txt
```

如果仓库已经克隆但尚未初始化论文复现任务：

```bash
git submodule update --init --recursive
```

### 配置模型与凭据

在项目根目录创建 `.env`，按实际使用的服务填写：

```dotenv
# OpenAI 或兼容端点
OPENAI_API_KEY=
OPENAI_API_BASE_URL=

# 使用 config/openrouter_config.yaml 时填写
OPENROUTER_API_KEY=

# Claude Code 使用 API 认证时填写；OAuth 登录用户可使用 claude auth login
ANTHROPIC_API_KEY=
```

模型、Agent、工作流、记忆和实验参数位于 `config/default_config.yaml`。如使用 OpenRouter，可改用 `config/openrouter_config.yaml`。

> [!WARNING]
> 默认配置面向完整研究运行，包含多候选、多轮 Discovery 和多次内容精炼，可能产生较长运行时间与较高模型费用。首次使用前请重点检查 `generation_count`、`top_ideas_count`、`loop_rounds`、`max_runs` 和并发设置。

### 运行发现—实验—论文闭环

`AutoDebug` 使用合成回归数据，不需要额外下载数据，适合作为首个端到端任务：

```bash
python launch_discovery.py \
  --config config/default_config.yaml \
  --task AutoDebug \
  --exp_backend claudecode
```

实验模式完成 `discovery_summary.json` 后，会同步触发默认 Dossier Run `primary`，并等待论文阶段成功或失败后再退出。

也可以使用统一入口：

```bash
python launch.py --mode discovery --task AutoDebug --exp_backend claudecode
```

### 为历史 Discovery Launch 生成或恢复论文

```bash
python launch_dossier.py \
  --launch-dir results/<task>/<timestamp>_launch \
  --config config/default_config.yaml \
  --dossier-run-id primary
```

相同的 Dossier Run ID 会校验已有阶段并从未完成处恢复；使用新的 ID 可创建一次独立写作尝试。

### 运行独立研究问答

```bash
python launch_qa.py \
  --question "记忆增强型大模型最近有哪些进展？" \
  --output answer.md
```

QA 模式走 Deep Research 流程，不执行实验，也不会触发论文生成。

## 输出与可追溯性

一次完整运行的核心目录如下：

```text
results/<task>/<timestamp>_launch/
├── prompt.json
├── discovery_summary.json
├── session_<id>/
│   ├── ideas.json
│   ├── traj.json
│   └── <candidate_experiment>/
│       ├── code/
│       ├── experiment_report.txt
│       └── run_<n>/
│           ├── final_info.json
│           └── code/
└── dossier_runs/
    └── primary/
        ├── dossier_run.json
        ├── candidate_selection.json
        ├── raw_materials/
        ├── outline.json
        ├── latex_writeup/
        └── final_paper.pdf
```

其中：

- `final_info.json` 是实验指标的主要事实源。
- `candidate_selection.json` 保存论文候选选择及所有例外情况的来源和理由。
- `raw_materials/` 是写作阶段允许读取的结构化材料集合。
- `dossier_run.json` 保存阶段状态、配置、错误、warning 和最终输出哈希。
- `final_paper.pdf` 与对应 LaTeX 构成 Research Narrative；原始实验产物仍是权威证据。

有关每类实验文件的可信层级和用途，请参阅 [实验产物说明](./EXPERIMENT_ARTIFACTS.md)。

## 配置入口

| 路径 | 用途 |
| --- | --- |
| `config/default_config.yaml` | 默认模型、Agent、记忆、Discovery Loop 和实验执行配置 |
| `config/openrouter_config.yaml` | OpenRouter 模型网关配置示例 |
| `config/paper_orchestra.yaml` | 论文模板、VLM 版式审查和内容/格式精炼次数 |
| `tasks/<task>/prompt.json` | 算法发现任务、数据、基线、指标与约束 |
| `tex_templates/elegantpaper/` | 当前默认的中文友好 Research Narrative 模板 |

## 项目结构

```text
InternAgent/
├── launch.py                   # discovery / qa 统一入口
├── launch_discovery.py         # 多轮发现与实验主流程
├── launch_qa.py                # 独立 Deep Research 问答
├── launch_dossier.py           # 历史 Dossier 生成与恢复
├── internagent/
│   ├── mas/                    # Agent、工作流、模型、工具与记忆
│   ├── paper_orchestra/        # 论文候选、原料、写作、审查与恢复
│   ├── stage.py                # Idea、实验与报告阶段适配
│   └── experiments_utils_*     # 各实验执行后端
├── tasks/                      # 算法发现任务
├── sci_tasks/                  # 科学论文复现任务子模块
├── tex_templates/              # 可选 LaTeX 模板
├── config/                     # 系统配置
├── docs/                       # 架构、Spec、ADR 与专题说明
└── tests/paper_orchestra/      # 自动论文闭环测试
```

## 验证

运行 PaperOrchestra 单元与集成测试：

```bash
python -m unittest discover -s tests/paper_orchestra -v
```

检查 Python 语法与代码风格：

```bash
python -m compileall launch_discovery.py launch_dossier.py internagent/paper_orchestra
flake8 launch_discovery.py launch_dossier.py internagent/paper_orchestra tests/paper_orchestra
```

## 延伸阅读

- [项目流程架构](./architecture.md)
- [实验自然产物与可信层级](./EXPERIMENT_ARTIFACTS.md)
- [PaperOrchestra 迁移 Spec](./docs/paper_orchestra_migration_spec.md)
- [架构决策记录 ADR](./docs/adr/)
- [记忆模块](./docs/memory_module.zh-CN.md)
- [Deep Research](./docs/deep_research.zh-CN.md)
- [OpenRouter 配置](./docs/openrouter.md)
- [科学论文复现任务](./docs/sci_tasks.md)

## 上游项目

本仓库在以下项目基础上进行集成与适配：

- [InternAgent](https://github.com/InternScience/InternAgent)：自主科学发现、多智能体编排、实验执行、记忆与 Deep Research 核心。
- [PaperOrchestra](https://github.com/declare-lab/paper-orchestra)：提纲、写作、内容反思、论文审查和版式审查架构。
- [ElegantPaper](https://github.com/ElegantLaTeX/ElegantPaper)：当前默认的中文友好 LaTeX 论文模板。

对应的导入版本、适配边界与上游声明保存在 `internagent/paper_orchestra/UPSTREAM.md` 和 `tex_templates/elegantpaper/UPSTREAM.md`。
