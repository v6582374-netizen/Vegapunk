# InternAgent-1.5：面向长程自主科学发现的统一智能体框架
> *跨越所有科学领域的自主发现*
- **论文**：[InternAgent 1.0](https://arxiv.org/abs/2505.16938) | [InternAgent 1.5](https://huggingface.co/papers/2602.08990)
- **链接**：[官网](https://discovery.intern-ai.org.cn) | [HuggingFace](https://huggingface.co/collections/InternScience/internagent)


## 🔥 最新动态
- **2026.5.07**：🔥🔥 我们已开源 InternAgent-1.5，并提供多项高级功能，包括增强型算法发现任务、自主科学论文复现、记忆模块，以及用于应对复杂研究挑战的深度研究能力。

- **2026.3.17**：🚀🚀 我们向公众开放了 InternAgent 深度研究能力的[访问入口](https://scphub.intern-ai.org.cn/detail/28)，帮助开发者和研究人员将其先进的深度研究功能无缝集成到自己的工作流中。

- **2026.2.14**：❤️‍🔥❤️‍🔥 我们开源了 **[MLEvolve](https://github.com/InternScience/MLEvolve)**，它是 InternAgent 面向算法设计任务的方案优化子系统的核心实现。作为在 **MLEBench 上取得第一名**的**开源方法**，MLEvolve 展示了在有界假设空间中进行方案优化的强大能力。

- **2026.2.10**：🔥 [InternAgent 1.5 技术报告](https://huggingface.co/papers/2602.08990)正式发布。InternAgent 1.5 在包括 **GAIA、HLE、GPQA 和 FrontierScience** 在内的科学推理基准上取得领先表现，并支持跨 **物理、生物、地球和生命科学领域**的端到端自主科学发现任务，可同时支持算法发现与实证发现（干实验/湿实验）。

- **2025.10.13**：InternAgent-1.0 代码已完全开源，支持 12 项科学研究任务中的端到端自动化和自主进化。

<details>
<summary>更多...</summary>

- **2025.07.17**：InternAgent 的源代码已部分开源。InternAgent 完整版本（覆盖 12 类自主科学研究任务）将很快开源。该代码仓库可用于从假设生成到自动化实验执行的全周期自主科学研究。

- **2025.07.10**：*NovelSeek* 已更名为 **InternAgent**。这一更名体现了我们对自主科学研究框架的美好愿景，也希望它能帮助所有研究人员取得重要科学发现。

</details>

---

## 🚀 快速开始

### 安装

```bash
conda create -n InternAgent python=3.11
conda activate InternAgent
pip install -r requirements.txt
```

### 配置 API 密钥

将 `.env.example` 重命名为 `.env`，并填入你的 API 密钥：

```bash
mv .env.example .env
```

`.env` 中的关键字段：

```
OPENAI_API_KEY=        # OpenAI 或兼容 API 密钥（用于嵌入和记忆）
OPENAI_API_BASE_URL=   # OpenAI 兼容端点的基础 URL
OPENROUTER_API_KEY=    # OpenRouter API 密钥（使用 openrouter provider 时）
ANTHROPIC_API_KEY=     # Anthropic API 密钥（用于基于 Claude 的实验后端）
```

如需使用 OpenRouter 作为模型网关，请设置 `OPENROUTER_API_KEY`，并使用
`config/openrouter_config.yaml` 运行。更多设置细节见 [docs/openrouter.md](docs/openrouter.md)。

### 运行发现实验

`AutoDebug` 是一个自包含的玩具任务（不需要下载数据集或模型），推荐作为首次运行任务，用于验证你的配置是否正确。

```bash
python launch_discovery.py \
    --config ./config/default_config.yaml \
    --task AutoDebug \
    --exp_backend claudecode
```

### 运行 QA 查询

QA 模式使用 InternAgent 的深度研究流水线直接回答研究问题，不运行实验循环，而是基于文献综合生成答案。

```bash
python launch_qa.py --question "What are recent advances in memory-augmented LLMs?"

# 可选：将答案保存到文件
python launch_qa.py -q "What are recent advances in memory-augmented LLMs?" -o answer.md
```

### 统一启动器

`launch.py` 是两种模式的统一入口：

```bash
python launch.py --mode discovery --task AutoDebug --exp_backend claudecode
python launch.py --mode qa --question "What are recent advances in memory-augmented LLMs?"
```

**配置提示：**
- 配置文件位于 `config/` 中，`default_config.yaml` 是主要起点。
- 结果保存在 `results/` 下，日志保存在 `logs/` 下。
- 如需跳过想法生成，并基于已有想法运行实验：添加 `--skip_idea_generation --idea_path <path/to/ideas.json>`。
- `scripts/` 中提供了可直接使用的示例脚本。

### 研究任务

**算法发现任务**位于 `tasks/` 下。每个任务都包含 `prompt.json`（任务描述）、基线 `code/` 和 `launcher.sh`。不同任务所需的数据集和环境相关设置各不相同，请参考各任务目录中的代码。

**科学论文复现任务**（`sci_tasks`）是一种独立模式：InternAgent 会获得一篇已发表论文及其数据，并被要求自主复现关键发现。这些任务位于 `sci_tasks/tasks/` 下，来自 [ResearchClawBench](https://github.com/InternScience/ResearchClawBench) 基准。完整指南见 [docs/sci_tasks.md](docs/sci_tasks.md)。

### 快速启动脚本

`scripts/` 下提供了可直接使用的示例脚本：

| 脚本 | 说明 |
|---|---|
| `run_discovery.sh` | 运行完整发现实验（想法生成 -> 实验） |
| `run_skip-idea.sh` | 基于已有想法文件运行实验，并跳过生成阶段 |
| `run_sci.sh` | 运行科学论文复现任务（默认使用 `Astronomy_000`） |
| `run_qa.sh` | 通过深度研究回答研究问题 |

---

## 🔧 高级功能

### 记忆模块

InternAgent 1.5 包含一个持久化记忆模块，可跨会话记录实验结果，帮助智能体避开此前失败的方向，并在成功经验基础上继续推进。配置和设置见 [docs/memory_module.md](docs/memory_module.md)。

### 深度研究

深度研究（DR）模块会将研究问题分解为子任务，并行地从学术数据库和网络中收集信息，再将发现综合为直接答案或结构化报告。配置和设置见 [docs/deep_research.md](docs/deep_research.md)。

---

## 📝 引用

```bibtex
@article{feng2026internagent,
  title={InternAgent-1.5: A Unified Agentic Framework for Long-Horizon Autonomous Scientific Discovery},
  author={Shiyang Feng and Runmin Ma and Xiangchao Yan and Yue Fan and Yusong Hu and Songtao Huang and Shuaiyu Zhang and Zongsheng Cao and Tianshuo Peng and Jiakang Yuan and Zijie Guo and Zhijie Zhong and Shangheng Du and Weida Wang and Jinxin Shi and Yuhao Zhou and Xiaohan He and Zhiyin Yu and Fangchen Yu and Bihao Zhan and Qihao Zheng and Jiamin Wu and Mianxin Liu and Chi Zhang and Shaowei Hou and Shuya Li and Yankai Jiang and Wenjie Lou and Lilong Wang and Zifu Wang and Jiong Wang and Wanghan Xu and Yue Deng and Dongrui Liu and Yiheng Wang and Wenlong Zhang and Fenghua Ling and Shufei Zhang and Xiaosong Wang and Shuangjia Zheng and Xun Huang and Siqi Sun and Shuyue Hu and Peng Ye and Chunfeng Song and Bin Wang and Conghui He and Yihao Liu and Xin Li and Qibin Hou and Tao Chen and Xiangyu Yue and Bin Wang and Liang He and Dahua Lin and Bowen Zhou and Bo Zhang and Lei Bai},
  journal={arXiv preprint arXiv:2602.08990},
  year={2026}
}
```

```bibtex
@article{team2025internagent,
  title={InternAgent: When Agent Becomes the Scientist--Building Closed-Loop System from Hypothesis to Verification},
  author={Team, InternAgent and Zhang, Bo and Feng, Shiyang and Yan, Xiangchao and Yuan, Jiakang and Ma, Runmin and Hu, Yusong and Yu, Zhiyin and He, Xiaohan and Huang, Songtao and others},
  journal={arXiv e-prints},
  pages={arXiv--2505},
  year={2025}
}
```

```bibtex
@article{hu2025flowsearch,
  title={FlowSearch: Advancing deep research with dynamic structured knowledge flow},
  author={Yusong Hu and Runmin Ma and Yue Fan and Jinxin Shi and Zongsheng Cao and Yuhao Zhou and Jiakang Yuan and Xiangchao Yan and Wenlong Zhang and Lei Bai and Bo Zhang},
  journal={arXiv preprint arXiv:2510.08521},
  year={2025}
}
```

```bibtex
@article{du2025automlgen,
  title={AutoMLGen: Navigating Fine-Grained Optimization for Coding Agents},
  author={Shangheng Du and Xiangchao Yan and Dengyang Jiang and Jiakang Yuan and Yusong Hu and Xin Li and Liang He and Bo Zhang and Lei Bai},
  journal={arXiv preprint arXiv:2510.08521},
  year={2025}
}
```
