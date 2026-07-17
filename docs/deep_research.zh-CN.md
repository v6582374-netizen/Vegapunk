## 深度研究

FlowSearch：深度研究（Deep Research，DR）模块是 InternAgent 内置的文献与网络研究流水线。给定一个问题或研究主题后，它会将任务分解为子任务，并行地从学术数据库和网络中收集信息，再将发现综合为结构化答案或报告。它是 QA 模式的核心支撑，也会在发现实验的想法生成阶段使用，帮助基于已有文献构建假设。

**什么时候有用？**

当任务需要超出智能体当前上下文的信息时，都可以使用它：例如调研某个研究领域、根据近期论文验证某项主张，或生成一份独立的研究答案。在发现模式中，它会在后台运行，为想法生成提供依据；在 QA 模式中，它会直接响应用户问题。

---

### 模式

DR 模块有两种输出模式：

| 模式 | 输出 | 何时使用 |
|---|---|---|
| `qa` | 简洁的直接答案 | 单个事实性问题或研究问题 |
| `report` | 带章节和参考文献的结构化 Markdown 报告 | 综述、深入背景、多部分主题 |

QA 模式会跳过大纲生成和章节润色，因此速度明显更快。Report 模式会运行完整的多阶段综合流水线，并可选择对每个章节进行润色。

---

### 发现模式中的配置

运行发现实验时，DR 由 `config/default_config.yaml` 中的 `agents.dr` 配置块控制：

```yaml
agents:
  dr:
    enabled: true              # 设为 false 可完全禁用 DR 后台研究
    mode: "simple"             # 使用哪种 DR 配置："simple" 或 "complex"
                               #   simple  → config_simple.yaml（更快，无协调器）
                               #   complex → config_complex.yaml（更全面，带协调器）
```

禁用 DR（`enabled: false`）会跳过想法生成阶段的后台文献依据构建，适合离线运行或 API 速率限制较紧的场景。

DR 接收进程拥有的 `UnifiedModelRuntime`，所有角色统一使用 Catalog 的 Active Text Model。
声明为 Responses 的 binding 在支持时可通过 `previous_response_id` 做普通续接。
Provider-side background execution 已禁用。

---

### 配置

`internagent/mas/agents/dr_agents/` 下提供了三份预置配置：

| 配置文件 | 模式 | 协调器 | 润色 | 最适合 |
|---|---|---|---|---|
| `config_qa.yaml` | `qa` | 关 | 关 | 直接问答（约 5-10 分钟） |
| `config_simple.yaml` | `report` | 关 | 关 | 快速背景研究（约 10-20 分钟） |
| `config_complex.yaml` | `report` | 开 | 开 | 综合性报告（约 20-40 分钟） |

协调器是一个可选的验证阶段，用于检查研究完整性，并在发现缺口时添加后续子任务。启用协调器会提升质量，但会增加耗时和 API 调用量。

需要调节的关键参数：

```yaml
main:
  max_iter: 5              # 最大执行周期；调高可获得更充分的研究
  enable_coordinator: false # 设为 true 可启用质量验证循环（仅 complex 配置）

global_planner:
  max_nodes: 7             # 生成的研究子任务数量；越高 = 覆盖面越广

global_execution:
  max_workers: 10          # 并行线程数；如果触发 API 速率限制，可降低
  execution:
    max_tool_calls: 5      # 每个子任务的工具调用次数

synthesizer:
  mode: "qa"               # "qa" 表示直接答案；省略则为 report 模式
  polish: false            # 设为 true 可优化每个章节（仅 report 模式）
```

如需在代码中覆盖 DR 工作流设置，请保留共享项目配置，只传入必要的工作流覆盖：

```python
import yaml
from internagent.mas.agents.dr_agent import DRAgent
from internagent.mas.models.unified_runtime import UnifiedModelRuntime

with open("config/default_config.yaml", encoding="utf-8") as file:
    project_config = yaml.safe_load(file)

runtime = UnifiedModelRuntime.from_catalog_path(project_config["model_catalog_path"])
agent = DRAgent(
    model=runtime.model_for(capability="text"),
    config={
        "mode": "qa",
        "workflow_config": {"main": {"max_iter": 3}},
        "_global_config": project_config,
        "_runtime": runtime,
    },
)
```

---

### API 密钥与环境设置

DR 模块使用五种搜索工具。所需密钥取决于启用的工具。

#### `arxiv_search`
搜索 arXiv 上的预印本。不需要 API 密钥。

#### `openalex_search`
搜索 OpenAlex 学术数据库（覆盖所有学科的 2.5 亿+作品）。不需要密钥，但建议设置邮箱以便礼貌访问：

```
OPENALEX_EMAIL=you@example.com
```

#### `crossref_search`
搜索 CrossRef 中的 DOI 元数据和引用信息（1.5 亿+记录）。不需要密钥，但建议设置邮箱：

```
CROSSREF_EMAIL=you@example.com
```

#### `volc_search`
通过火山引擎进行网络搜索，具备较强的中文支持和自动全文提取能力。需要企业 API 密钥：

```
VOLC_SEARCH_API_KEY=your-key
```

#### `url_processor`
从 URL 获取并提取内容，然后基于该内容回答特定查询。默认使用 Tavily 作为主要提取器（快速且干净），不可用时回退到火山引擎：

```
TAVILY_API_KEY=tvly-your-key
```

将这些配置与已有的 OpenAI 密钥一起添加到 `.env` 文件中。

---

### 独立使用

QA 模式是主要的独立入口。Report 模式由发现流水线内部使用；如果你需要在发现运行之外使用它，可以直接用 report 配置实例化 `DRAgent`（见上文[配置](#配置)）。

**QA 模式**（直接问答）：

```bash
python launch_qa.py --question "What are recent advances in memory-augmented LLMs?" \
                    --config config/default_config.yaml \
                    --output answer.md
```

通过 `--file` 传入本地文件，可以让答案基于某个特定文档（例如论文 PDF 或笔记）：

```bash
python launch_qa.py --question "What methodology does this paper use?" \
                    --file path/to/paper.pdf \
                    --output answer.md
```

直接调用 `DRAgent`（例如使用自定义配置）：

```python
from internagent.mas.agents.dr_agent import DRAgent
import asyncio
import yaml
from internagent.mas.models.unified_runtime import UnifiedModelRuntime

with open("config/default_config.yaml", encoding="utf-8") as file:
    project_config = yaml.safe_load(file)

runtime = UnifiedModelRuntime.from_catalog_path(project_config["model_catalog_path"])
agent = DRAgent(
    model=runtime.model_for(capability="text"),
    config={"mode": "qa", "_global_config": project_config, "_runtime": runtime},
)
answer = asyncio.run(agent.execute({'task': 'Your research question'}, {}))
print(answer)
```


## 📝 引用

```bibtex
@article{hu2025flowsearch,
  title={FlowSearch: Advancing deep research with dynamic structured knowledge flow},
  author={Yusong Hu and Runmin Ma and Yue Fan and Jinxin Shi and Zongsheng Cao and Yuhao Zhou and Jiakang Yuan and Xiangchao Yan and Wenlong Zhang and Lei Bai and Bo Zhang},
  journal={arXiv preprint arXiv:2510.08521},
  year={2025}
}
```
