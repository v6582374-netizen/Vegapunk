# 优秀顶会论文的章节规划调研

调研日期：2026-07-13

## 结论摘要

当前 Research Narrative 的固定八章结构不适合作为“优秀顶会论文”的统一合同。抽样论文真正稳定的不是章节名称和顺序，而是若干论证职责：界定问题、说明差距、提出贡献、建立必要背景、给出方法或分析、设计可信评估、解释结果、陈述边界并收束结论。优秀论文会按照贡献类型重新组合这些职责。

建议保留 ElegantPaper 作为中文友好的排版容器，但取消模板对顶层章节名称和顺序的控制。章节规划应成为 Manuscript Sculptor 的编辑职责，并允许随着研究从问题探索转向最终候选而整体改写。

## 调研方法

本次抽取了 2024-2026 年 ICLR、NeurIPS、ICML、CVPR、ACL 的 12 篇 Outstanding Paper、Best Paper 或 Honorable Mention，覆盖理论、方法、实证诊断、数据/基准、视觉和 NLP 论文。

- 获奖身份由会议官方获奖页面确认。
- 章节名称从论文 PDF 提取，而不是从二手博客概括。
- 对五篇代表论文的前三页进行了渲染检查，以确认标题层级、图表位置和正文布局。
- 使用的 PDF 主要是对应 arXiv 版本；它们可能与最终 camera-ready 版本存在轻微排版差异，因此本报告只据此判断论证结构，不据此判断会议格式细节。

这是一项结构观察，不是因果研究。论文获奖并不意味着其章节结构本身导致了获奖。

## 样本与真实顶层章节

| 会议 | 论文与类型 | PDF 中的主要顶层章节 | 结构信号 |
| --- | --- | --- | --- |
| ICLR 2026 | [Transformers are Inherently Succinct](https://arxiv.org/abs/2510.19315)，理论论文 | Introduction -> Preliminaries -> The Size of Smallest Witness via Non-Emptiness Problem -> Succinctness Across Representations -> Applications -> Concluding Remarks | 没有独立 Related Work、Method 或 Experiments；正文由定理链条组织 |
| ICLR 2026 | [LLMs Get Lost In Multi-Turn Conversation](https://arxiv.org/abs/2505.06120)，实证诊断论文 | Introduction -> Background and Related Work -> Simulating Underspecified, Multi-Turn Conversation -> Task and Metric Selection -> Simulation Scale and Parameters -> Results -> Implications -> Conclusion -> Limitations | 把任务、指标、规模和影响分别提升为顶层论证步骤 |
| ICLR 2025 | [Safety Alignment Should be Made More Than Just a Few Tokens Deep](https://arxiv.org/abs/2406.05946)，诊断与干预论文 | Introduction -> The Shallow Safety Alignment Issue... -> What If the Safety Alignment Were Deeper? -> What If the Initial Tokens Were Protected...? -> Related Work -> Conclusion | 章节直接表述研究问题和反事实干预，而不是使用笼统的 Method/Experiments |
| ICLR 2025 | [Learning Dynamics of LLM Finetuning](https://arxiv.org/abs/2407.10490)，理论加实证论文 | Introduction -> Definition of Learning Dynamics and an MNIST Example -> Learning Dynamics of LLM Finetuning -> Experimental Verifications -> Conclusion | 先以小例子建立概念，再迁移到核心问题，最后做实验验证 |
| NeurIPS 2024 | [Visual Autoregressive Modeling](https://arxiv.org/abs/2404.02905)，方法论文 | Introduction -> Related Work -> Method -> Implementation Details -> Empirical Results -> Zero-Shot Task Generalization -> Ablation Study -> Limitations and Future Work -> Conclusion | 结果、泛化和消融不是一个笼统 Experiments 章节中的平级小节，而是独立论证阶段 |
| NeurIPS 2024 | [Stochastic Taylor Derivative Estimator](https://arxiv.org/abs/2412.00088)，理论方法论文 | Introduction -> Related Works -> Preliminaries and Discussions -> Method -> Experiments -> Conclusion | 接近经典结构，但大量篇幅用于前置定义与复杂度动机 |
| NeurIPS 2025 | [Artificial Hivemind](https://arxiv.org/abs/2510.22954)，数据集与诊断论文 | Introduction -> Infinity-Chat: Real-World Open-Ended Queries... -> Artificial Hivemind... -> How Do LMs, Reward Models, and LM Judges Handle Alternative Responses...? -> Related Work -> Conclusion | 数据资源、核心发现和后续研究问题各自形成顶层章节 |
| NeurIPS 2025 | [Gated Attention for Large Language Models](https://arxiv.org/abs/2505.06708)，大规模方法论文 | Introduction -> Gated-Attention Layer -> Experiments -> Analysis: Non-Linearity, Sparsity, and Attention-Sink-Free -> Related Works -> Conclusion | 将“证明为什么有效”的分析与“是否有效”的实验分开 |
| ICML 2024 | [Discrete Diffusion Modeling by Estimating the Ratios of the Data Distribution](https://arxiv.org/abs/2310.16834)，理论方法论文 | Introduction -> Preliminaries -> Score Entropy Discrete Diffusion Models -> Simulating Reverse Diffusion... -> Experiments -> Related Work -> Conclusion | 方法被拆成理论目标和推断机制，Related Work 放在实验之后 |
| CVPR 2024 | [Generative Image Dynamics](https://arxiv.org/abs/2309.07906)，视觉方法论文 | Introduction -> Related Work -> Overview -> Predicting Motion -> Image-Based Rendering -> Applications -> Experiments -> Discussion and Conclusion | 用 Overview 先给读者全景，再按系统组件拆方法，并单列应用 |
| ACL 2024 | [Mission: Impossible Language Models](https://arxiv.org/abs/2401.06416)，控制实验论文 | Introduction -> Background and Related Work -> Impossible Languages -> Experiments -> Discussion and Conclusion -> Limitations -> Ethics Statement | 研究对象本身先成为一章；Discussion 与 Conclusion 合并 |
| ACL 2024 | [Aya Model](https://arxiv.org/abs/2402.07827)，大型资源论文 | Introduction -> Data -> Experimental Set-up -> Evaluation -> Results -> Safety Mitigation -> Benchmarking Toxicity and Bias -> Related Work -> Discussion -> A Participatory Approach to Research -> Conclusion | 资源、评估、安全和协作治理具有独立科学责任，无法塞进统一 Method/Experiments 骨架 |

## 官方获奖来源

- [ICLR 2026 Outstanding Papers](https://blog.iclr.cc/2026/04/23/announcing-the-iclr-2026-outstanding-papers/)
- [ICLR 2025 Outstanding Paper Awards](https://blog.iclr.cc/2025/04/22/announcing-the-outstanding-paper-awards-at-iclr-2025/)
- [NeurIPS 2025 Best Paper Awards](https://blog.neurips.cc/2025/11/26/announcing-the-neurips-2025-best-paper-awards/)
- [NeurIPS 2024 Best Paper Awards](https://blog.neurips.cc/2024/12/10/announcing-the-neurips-2024-best-paper-awards/)
- [ICML 2024 Awards](https://icml.cc/virtual/2024/awards_detail)
- [CVPR 2024 Best Paper Awards](https://cvpr.thecvf.com/Conferences/2024/News/Awards)
- [ACL 2024 Best Paper Awards](https://2024.aclweb.org/program/best_papers/)

## 跨论文观察

### 1. Introduction 是唯一近乎普遍的固定正文入口

所有样本都以 Introduction 开始。优秀引言通常同时承担四项职责：问题的重要性、现有工作的具体缺口、本文的中心主张或方案、主要结果和贡献预告。它不是背景资料的容器，而是整篇论文的论证压缩包。

Abstract 仍然适合作为固定前置内容，但不应被视为一个顶层正文章节。

### 2. Related Work 的位置不固定

样本中至少出现了三种成熟做法：

- 放在正文前部，为方法建立坐标，例如 Generative Image Dynamics、STDE、Mission: Impossible Language Models。
- 放在结果或分析之后，避免在提出贡献前打断叙事，例如 SEDD、Gated Attention、Artificial Hivemind、Aya。
- 融入 Introduction 或 Preliminaries，不设置独立章节，例如 Transformers are Inherently Succinct、Learning Dynamics of LLM Finetuning。

因此，固定要求“Introduction 后必须是 Related Work”没有经验依据。正确位置取决于读者在理解核心贡献前是否确实需要文献坐标。

### 3. Method 和 Experiments 不是可靠的统一抽象

经典 Method/Experiments 骨架适用于一部分算法论文，但会压扁其他贡献：

- 理论论文需要 Preliminaries、核心定理链、比较和应用。
- 诊断论文需要现象定义、测量设计、干预和 Implications。
- 数据/资源论文需要 Data、Evaluation、Results、Safety/Bias 等独立章节。
- 大型实证论文常把 Setup、Results、Analysis、Ablation、Generalization 分开，因为它们回答不同问题。

优秀章节标题往往直接表达本节要回答的科学问题，例如 “What If the Safety Alignment Were Deeper?”，而不是只标注内容类型。

### 4. “发现”与“解释为什么”通常被分开

Gated Attention 把 Experiments 与机制分析分开；VAR 把主结果、规模规律、零样本泛化和消融分开；LLMs Get Lost 把 Results 与 Implications 分开。这种结构让证据链更容易审查：先证明现象存在，再解释原因或意义。

当前单一“实验”章节容易生成流水账，把设置、主结果、消融、误差分析和解释混在一起。

### 5. 章节是论证步骤，不是项目目录

样本论文没有按照“调研 -> 编码 -> 实验 -> 失败 -> 选择候选 -> 复现”的项目执行顺序写正文。论文只保留审稿人理解和检验核心主张所需的内容。

本次 12 篇样本中，没有一篇把 Research Process 或 Reproduction Guide 作为主论文的固定顶层章节。复现细节通常进入方法细节、实验设置、附录、checklist、代码仓库或补充材料；失败尝试只有在构成消融、边界条件或科学发现时才进入正文。

### 6. Limitations 是重要职责，但不是固定位置

Limitations 可能是独立章节、与 Future Work 合并、放在 Conclusion 后，或按 venue 要求出现在附录附近。应要求论文覆盖证据支持的局限，而不应强制它始终位于某个固定章节序号。

### 7. 图表参与章节规划，而不是写完文字后补入

视觉检查显示，方法和诊断论文常在前一至三页放置任务定义图、系统总览图或核心现象图。这些图决定后续章节的解释顺序。理论论文则可能以定义和公式作为主要导航。

因此，Outline 阶段必须同时规划章节、关键图表和每个图表支持的主张；把图表当作写作结束后的装饰无法复现这些论文的叙事方式。

## 对当前固定八章合同的评价

当前合同是：

1. 引言
2. 相关工作
3. 方法
4. 实验
5. 研究过程
6. 复现指南
7. 局限性与适用边界
8. 结论

主要问题如下：

- 它只适合最典型的经验方法论文，无法自然表达理论、诊断、数据集和资源型贡献。
- Related Work 被固定得过早。
- Method 与 Experiments 粒度过粗，容易造成长而无中心的章节。
- Research Process 和 Reproduction Guide 服务于旧的“可复现手册”定位，会挤占投稿论文的核心论证空间。
- Candidate Selection 的流程披露被要求写入正文，即使它对科学主张没有价值。
- 固定模板阻止 Manuscript Sculptor 随研究变化增加、删除、改名或重排顶层章节，与 Living Manuscript 冲突。

## 推荐的章节规划模型

推荐把“固定章节合同”替换成“自适应论证合同”。排版模板继续固定，但正文骨架由论文的贡献类型决定。

### 所有论文都必须覆盖的论证职责

这些是内容职责，不要求使用相同标题：

1. **问题与价值**：研究问题是什么，为什么值得解决。
2. **差距与定位**：现有方法、知识或评估缺少什么。
3. **中心贡献**：本文提出或发现了什么。
4. **方法或推理依据**：贡献如何建立，理论假设或设计选择是什么。
5. **可信评估**：使用什么任务、指标、baseline、协议和控制变量。
6. **结果与解释**：主要发现是什么，为什么可信，它意味着什么。
7. **边界**：哪些结论有证据支持，哪些条件尚未验证。
8. **收束**：读者最终应记住什么。

### 四种建议原型

#### 经验方法论文

Introduction -> Background/Related Work（位置可变） -> Overview/Method -> Experimental Setup -> Main Results -> Analysis/Ablations/Generalization -> Limitations -> Conclusion

#### 现象诊断与干预论文

Introduction -> Background -> Phenomenon/Measurement Design -> Diagnostic Results -> Intervention or Counterfactual Test -> Implications -> Limitations -> Conclusion

#### 理论论文

Introduction -> Preliminaries -> Core Results/Theorems -> Comparisons or Consequences -> Applications/Empirical Verification（可选） -> Concluding Remarks

#### 数据集、基准或资源论文

Introduction -> Resource/Data Construction -> Evaluation Protocol -> Results and Analysis -> Safety/Bias/Ethics（按证据需要） -> Related Work/Discussion（位置可变） -> Limitations -> Conclusion

这些原型是起点而不是新模板。Manuscript Sculptor 可以按实际论证需要合并、拆分、重命名和重排章节。

## 对 Living Manuscript 的直接含义

1. ElegantPaper 只负责排版，不再提供固定正文骨架。
2. Living Manuscript 初期可以只有 Introduction 和若干暂定论证章节，不必预先创建八个空章节。
3. Manuscript Sculptor 在掌握足够结果后选择最接近的论文原型；随着研究变化，可以整体换型。
4. 每次 Research-Significant Action 到来时，雕刻 Agent 应判断它影响的是中心主张、方法、评估、结果、分析还是边界，而不是按 artifact 来源把内容塞进固定章节。
5. Terminal Candidate Selection 后必须执行一次全局结构审查，删除探索期残留并围绕最终候选收束。
6. Outline 必须联合规划章节与图表；没有对应证据的图表槽位不能凭空生成。
7. 最终验证应检查论证职责是否被覆盖，而不是检查八个固定 `\\section` 是否存在并按顺序排列。

## 建议下一步决策

第一项应先决定：是否正式取消跨论文固定的顶层章节名称和顺序，改为根据贡献类型自适应规划章节。只有这一原则确定后，才值得继续决定哪些职责必须进入正文，以及 Research Process、Reproduction Guide 和 Candidate Selection Provenance 应移到何处。
