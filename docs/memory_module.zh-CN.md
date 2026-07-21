## 记忆模块

记忆模块是 Vegapunk 1.5 的一项新功能。它会跨会话维护过往实验的持久化记录：每个已完成的想法都会连同其指标和标签一起存储（相对基线为正向/中性/负向）。在想法生成阶段，智能体会查询这些历史记录，避免重复已经失败的方法，并在有效方向的基础上继续推进。

该模块包含两个彼此独立的组件：

- **检索**：在想法生成时查询累积记录，并将指导性摘要注入生成提示词
- **保存**：在每个想法的实验完成后，立即写入一条记录

二者由不同的开关控制，因为它们适用于不同组合：

| 保存 | 检索 | 何时使用 |
|--------|-----------|-------------|
| 开 | 关 | 首次会话：还没有可检索内容，但可以开始构建存储 |
| 开 | 开 | 后续会话：使用历史记录，并继续向其中添加新记录 |
| 关 | 开 | 只读评估：查询历史记录，但不添加新记录 |
| 关 | 关 | 完全禁用该模块 |

**什么时候有用？**

记忆模块在首次运行时不会带来收益，因为存储中还没有内容。它的价值会随着同一任务上的重复使用而增长：经过多次会话后，生成智能体可以避免重新发现相同的失败方向，并拥有更具体的依据来优先选择已有成功记录的方向。

---

### 配置

#### 检索

由配置文件中的 `memory.task_memory` 控制。

```yaml
memory:
  task_memory:
    enabled: false          # 设为 true 以在想法生成期间启用检索
    memory_dir: "./config/mem_store"  # 读取记忆存储的位置
    top_k: 5                # 每次查询返回的相似历史记录数量
    alpha: 0.5              # 搜索权重：1.0 = 仅关键词，0.0 = 仅语义
                            # 当存储较稀疏（记录较少）时，可调向 1.0
    embedding_mode: "description"  # 要嵌入想法的哪个部分：title / description / method / full
    embedding:
      model_type: "local"   # local / openai / azure
      model_name: ""        # 本地模型目录路径（见下文），或 API 模型名称
```

检索需要可用的嵌入模型来支持语义搜索组件。如果 `model_name` 为空或模型加载失败，该模块会被静默跳过。

#### 保存

由配置文件中的 `memory.online_memory` 控制。

```yaml
memory:
  online_memory:
    enabled: false          # 设为 true 以在每次实验后自动保存结果
    aggregation: "best"     # 如何将多次运行的指标汇总为一条记录：
                            #   best — 使用最佳运行结果（默认）
                            #   avg  — 对所有运行求平均
                            #   last — 使用最后一次运行结果
```

保存同样需要可用的嵌入模型（记录会在写入时立即被嵌入）。

---

### 设置嵌入模型

两个组件都需要本地句向量嵌入模型。请在启用任一开关前先下载模型。

如果 HuggingFace 可访问：
```bash
huggingface-cli download BAAI/bge-base-en-v1.5 --local-dir ./models/bge-base-en-v1.5
```

如果不可访问（例如在受限网络中），可尝试镜像：
```bash
HF_ENDPOINT=https://hf-mirror.com huggingface-cli download BAAI/bge-base-en-v1.5 --local-dir ./models/bge-base-en-v1.5
```

或通过 ModelScope 下载：
```bash
pip install modelscope
modelscope download --model BAAI/bge-base-en-v1.5 --local_dir ./models/bge-base-en-v1.5
```

然后将 `model_name` 设置为下载路径：
```yaml
memory:
  task_memory:
    embedding:
      model_name: "./models/bge-base-en-v1.5"
```

记忆存储会写入 `memory_dir`（默认：`./config/mem_store`），并跨会话持久存在。前一次运行的记录会在下一次运行时自动加载。

---

### 长期记忆（IdeaGraph 和 PromptEvolver）

除任务记忆和在线记忆外，Vegapunk 1.5 还包含一个长期记忆组件，用于跟踪完整的想法历史，并随着时间自动演化生成提示词。

它包含两个子组件：

- **IdeaGraph**：构建跨会话生成的所有想法图谱，并根据嵌入相似度连接相似想法。用于检测冗余，并衡量探索广度。
- **PromptEvolver**：基于累积经验定期重写生成提示词，引导智能体靠近已验证有效的方向，并远离无效方向。

```yaml
memory:
  long_memory:
    enabled: true
    idea_graph:
      similarity_threshold: 0.7   # 在两个想法之间连边所需的最小相似度；
                                   # 越低 = 连接越多，越高 = 只连接近似重复项
    prompt_evolver:
      enabled: true               # 设为 false 可禁用自动提示词演化
      evolution_interval: 1       # 每 N 轮循环演化一次提示词
                                  #   1 = 每轮演化（更激进的适应）
                                  #   2 = 每隔一轮演化（更保守）
```

长期记忆需要与任务记忆相同的嵌入模型。如果未配置嵌入模型，它会回退为仅基于关键词的想法跟踪，不创建语义边。


## 📝 引用

```bibtex
@article{feng2026vegapunk,
  title={Vegapunk-1.5: A Unified Agentic Framework for Long-Horizon Autonomous Scientific Discovery},
  author={Shiyang Feng and Runmin Ma and Xiangchao Yan and Yue Fan and Yusong Hu and Songtao Huang and Shuaiyu Zhang and Zongsheng Cao and Tianshuo Peng and Jiakang Yuan and Zijie Guo and Zhijie Zhong and Shangheng Du and Weida Wang and Jinxin Shi and Yuhao Zhou and Xiaohan He and Zhiyin Yu and Fangchen Yu and Bihao Zhan and Qihao Zheng and Jiamin Wu and Mianxin Liu and Chi Zhang and Shaowei Hou and Shuya Li and Yankai Jiang and Wenjie Lou and Lilong Wang and Zifu Wang and Jiong Wang and Wanghan Xu and Yue Deng and Dongrui Liu and Yiheng Wang and Wenlong Zhang and Fenghua Ling and Shufei Zhang and Xiaosong Wang and Shuangjia Zheng and Xun Huang and Siqi Sun and Shuyue Hu and Peng Ye and Chunfeng Song and Bin Wang and Conghui He and Yihao Liu and Xin Li and Qibin Hou and Tao Chen and Xiangyu Yue and Bin Wang and Liang He and Dahua Lin and Bowen Zhou and Bo Zhang and Lei Bai},
  journal={arXiv preprint arXiv:2602.08990},
  year={2026}
}
```
