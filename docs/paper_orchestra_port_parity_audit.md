# PaperOrchestra 移植对等性审计

状态：Active，首个端到端可运行基线已实现并通过真实 Relay Provider 验收
记录日期：2026-07-15

## 背景

本审计启动时，`internagent.paper_orchestra` 不是对上游 PaperOrchestra 的逐文件复制，而是基于上游提交 `ca1b3fa01c2970fc7cda32d16245db38d57b3f56` 完成的 InternAgent 原生异步适配。首次集成提交为 `b27892a6f0c2082a4a9a3f249227e76cfaf2ad80`。

该旧适配保留了 Outline、Literature Writing、Section Writing、Content Refinement、Layout Review 等角色和职责，但重写或重新组织了模型接口、异步调用、pipeline、checkpoint、resume、输入材料和错误传播。直接对应文件的低文本相似度也表明，它不是“复制后局部修改”的实现方式。按 ADR-0101 完成迁移后，当前运行路径已经改为完整 vendoring 固定上游提交，再由宿主适配层做最小接入；旧原生写作核心已删除。

## 迁移前已确认风险

N09 暴露了一项明确的移植回归：

- 上游格式修正循环把修正版视为候选；候选编译失败或修正过程抛出异常时，保留 `final_valid_pdf_path` 并继续输出此前有效版本。
- 旧原生实现新增了科学内容指纹检查，可以拒绝偷偷改变公式或正文的版式修正，这是必要的安全增强。
- 旧原生 pipeline 没有把新增的拒绝结果接回上游原有的候选回退边界，导致无效版式修正使整个 PaperOrchestra Run 失败。
- 这一行为也违反 ADR-0018 中“否则已编译的内容版本成为最终版本”的既有决定。

因此，迁移决策不能假设旧适配路径已经保留上游全部行为不变量。该风险是改用完整 vendoring 基线、删除第二套写作核心的直接依据之一。

## 后续审计范围

单独课题应建立“上游实现 → 当前实现”的逐项映射，并把每项归类为保留、适配、重写、删除或新增，至少覆盖：

- 内容修订候选的接受、拒绝和回退规则；
- 版式修正候选的验证、编译、复审和回退规则；
- 重试、普通失败、致命失败及异常传播；
- stage checkpoint、进程中断和 resume 语义；
- 必需阶段、可选输入和非阻断 warning；
- 最终 TeX/PDF 与中间产物的有效性约束；
- 上游 provider 调用与当前统一 `BaseModel`/Responses Runtime 的对应关系；
- 被删除的上游能力是否仍被其他流程隐式依赖；
- 当前新增的安全检查是否完整接入上游原有控制流。

每一项都应有行为级回归测试，不能只依赖文件名、类名或提示词相似。

## 审计边界

- 不再比较“完整复制上游”与“继续维护当前适配”两种方向；ADR-0101 已确定以前者为基线。
- 不假设上游实现天然正确；例如上游只以编译成功判断格式候选，缺少当前新增的科学内容保护。
- 不再把旧原生重写恢复为第二套运行时；其问题只作为迁移证据保留。
- N09–N12 作为旧实现的可复现行为记录保留，不再驱动一套并行写作核心。

## 已确认维护策略

按 ADR-0101，后续改造从上游提交 `ca1b3fa01c2970fc7cda32d16245db38d57b3f56` 的完整源码副本开始，只做接入 InternAgent 所必需的最小化适配。上游源码、控制流、提示词、角色和默认行为是实现基线；旧原生重写及其测试只作为 InternAgent 需求和已发现风险的迁移证据，不再作为替换实现的代码基线。新路径通过完整 mock E2E 与真实文本、视觉、生图 probe 后，旧 Agent、prompt、pipeline、checkpoint、图片适配和 ElegantPaper 运行代码已删除；其历史仍保存在 Git 与被取代的 ADR/Spec 中。

该决定取代 ADR-0015 的选择性内部移植策略。模型 Runtime、异步执行、checkpoint、resume、输入材料和新增安全检查等现有决定，需要逐项重新判断应位于上游副本内部还是外部适配层。

## 已确认源码拓扑

- 上游提交的全部 Git 跟踪文件原样导入 `third_party/paper_orchestra/`，包括 frontend、CLI、templates、autoraters、文档和许可证。
- 该目录由 InternAgent 主仓库直接跟踪，不携带上游 `.git`，也不使用 Git submodule。
- 首个迁移变更只建立未经适配的完整源码基线；模型接入、输入输出桥接和其他适配分别进入后续变更。
- “完整源码基线”定义改造起点，不表示副本永久只读；后续允许在该目录内做已确认的最小化适配，但每项偏离必须能与固定上游提交直接比较。
- 不把上游文件覆盖到 InternAgent 根目录，也不把上游 Agent 和 pipeline 再次重写进 `internagent.paper_orchestra`；后者只承担当前项目的外部接入职责。
- `internagent.paper_orchestra` 现在只保留宿主适配职责；旧原生写作核心已经在替代路径通过 mock E2E 与模型能力 probe 后移除，不再形成第二套可执行 PaperOrchestra。

## 固定上游提交的模型调用清单

以下盘点以提交 `ca1b3fa01c2970fc7cda32d16245db38d57b3f56` 为准。上游源码中只出现三个具体模型标识：

- `gemini-3.1-pro-preview`：默认 Writing、Reflection、Plotting 和离线 Autorater 模型；
- `gemini-3-flash-preview`：带 Google Search grounding 的论文发现，以及一个未接入主链的标题提取工具；
- `gemini-3-pro-image-preview`：把 diagram prompt 直接生成 raster image。

上游同时具有通用 OpenAI 分支：当 `model_name` 包含 `gpt`、`o1` 或 `o3` 时，`utils/llm_backend_utils.py` 会转入 `utils/openai_utils.py`。但固定提交没有任何具体 GPT 模型作为默认值，并且该分支使用 Chat Completions，不是 InternAgent 当前的 Responses Runtime。

### 单篇生成主链

“静态可承接性”只判断当前 `ModelRunRequest` 契约是否具备所需模态，不表示上游现有调用无需适配，也不代替真实 API probe。

| 工作 | 上游调用入口 | 原模型 | 输入与输出 | `gpt-5.6-sol` 静态可承接性 |
| --- | --- | --- | --- | --- |
| Outline | `OutlineAgent.run` | Writing，默认 `gemini-3.1-pro-preview` | 纯文本到 JSON | 可承接；当前 Runtime 支持文本和 JSON Object |
| 论文候选发现 | `HybridLiteratureAgent._discover_candidates` | 硬编码 `gemini-3-flash-preview` | 文本加 Gemini Google Search grounding 到 JSON | 不可直接承接；当前 Runtime 未启用 hosted search，需另行设计搜索工具语义 |
| Introduction 与 Related Work 合成 | `HybridLiteratureAgent._synthesize_content` | Writing，默认 `gemini-3.1-pro-preview` | 纯文本到 LaTeX | 可承接 |
| 其余 Section 写作 | `SectionWritingAgent.run` | Writing，默认 `gemini-3.1-pro-preview` | 文本加 raster figures 到 LaTeX | 已由真实 smoke 以三张 raster figures 完成多模态写作 |
| Peer Review ensemble 与 meta-review | `perform_review_agentreview`、`get_meta_review` | Reflection，默认 `gemini-3.1-pro-preview` | 提取后的 PDF 文本到 JSON | 可承接 |
| 内容修订候选 | `ContentRefinementAgent.run` 的 content loop | Reflection，默认 `gemini-3.1-pro-preview` | 原始 PDF bytes 加文本到 JSON 和 LaTeX | 不可原样承接；当前 Runtime 没有 PDF input item，必须明确改成提取文本、页面图像或其他文件输入 |
| Layout Review | `ContentRefinementAgent._get_formatting_review` | Reflection，默认 `gemini-3.1-pro-preview` | PDF 页面截图到 JSON | 已由真实 smoke 完成页面截图评审和 1 轮格式修正 |
| 格式修正候选 | `ContentRefinementAgent.run` 的 format loop | Reflection，默认 `gemini-3.1-pro-preview` | 纯文本到完整 LaTeX | 可承接 |
| Figure few-shot 检索 | `retrieve_few_shot_examples` | Plotting，默认 `gemini-3.1-pro-preview` | 大段文本候选池到 ID 列表 | 可承接；另依赖上游仓库之外的 PaperBanana 数据目录 |
| Figure 内容规划 | `predict_figure_content` | Plotting，默认 `gemini-3.1-pro-preview` | 文本加 few-shot reference images 到描述 | 长上下文主链已实测；本机缺少外部 PaperBanana 数据，因此 reference-image few-shot 分支未覆盖 |
| Figure 风格化 | `style_figure_content` | Plotting，默认 `gemini-3.1-pro-preview` | 纯文本到描述 | 可承接 |
| Statistical Plot 生成 | `generate_figure_visuals` 的 `plot` 分支 | Plotting，默认 `gemini-3.1-pro-preview` | 文本到 Python/Matplotlib code，再由本地执行生成图像 | 模型部分可承接；图像不是由模型 API 输出 |
| Diagram 生成 | `generate_figure_visuals` 的 `diagram` 分支 | Image，默认 `gemini-3-pro-image-preview` | 文本到 IMAGE bytes | `gpt-5.6-sol` 当前 Responses API 不可承接；需要独立生图 provider 或改变能力范围 |
| Figure Critic | `critique_and_revise_figure` | Plotting，默认 `gemini-3.1-pro-preview` | 文本加生成图像到 JSON 修订建议 | 已由真实 smoke 对三张图分别完成 3 轮视觉评审 |
| Figure Caption | `generate_figure_caption` | Plotting，默认 `gemini-3.1-pro-preview` | 文本，可选生成图像，到 caption | 已由真实 smoke 为三张最终图生成 caption |

### 随仓库提供但不属于单篇生成主链

| 能力 | 上游入口 | 默认模型 | 模态 | 备注 |
| --- | --- | --- | --- | --- |
| Citation Priority/F1 | `ReferenceF1V1Evaluator._get_citation_priorities` | `gemini-3.1-pro-preview` | 文本到 JSON | 离线 evaluator |
| Literature Review Quality | `rate_single_paper` | `gemini-3.1-pro-preview` | Gemini 接收原始 PDF；OpenAI 分支只接收提取文本 | 离线 evaluator，两个 provider 分支并不模态等价 |
| SxS Literature Review | `rate_sxs_lit_review` | `gemini-3.1-pro-preview` | 两篇论文文本到 JSON | 离线 evaluator |
| SxS Paper Quality | `rate_sxs_paper_quality` | `gemini-3.1-pro-preview` | Gemini 接收两份原始 PDF；OpenAI 接收提取文本及每篇最多 15 页图像 | 离线 evaluator；OpenAI 分支与当前 Runtime 的输入形态接近 |
| Reference Text Extraction | `extract_reference_from_pdf_text` | `gemini-3.1-pro-preview` | 文本到文本 | Utility，不直接读取 PDF bytes |
| Citation Title Extraction | `extract_paper_title_from_citation` | 硬编码 `gemini-3-flash-preview` | 文本到文本 | 当前图谱没有主链调用者 |

### 共享调用层

- Gemini 直连入口：`call_gemini_with_contents`、`call_gemini_with_images`、`call_gemini_with_text_prompt` 和 `generate_image_with_gemini`。
- 双 provider 入口：`call_llm_with_text_prompt`、`call_llm_with_images` 和 `call_llm_with_pdf`；按模型名选择 Gemini 或 OpenAI。
- OpenAI 直连入口：`call_openai_models_with_content` 和 `call_openai_models_with_text_prompt`，使用 Chat Completions。
- CLI 分别暴露 Writing、Reflection、Plotting 和 Image 四个模型参数；Frontend 只让文本角色选择 `gemini-3.1-pro-preview` 或 `gemini-3-flash-preview`，Image 固定为 `gemini-3-pro-image-preview`。

### 当前 Runtime 的已知边界

- `gpt-5.6-sol` 通过 Responses API 支持文本输入、JSON Object 输出和 `input_image` 请求形态。
- 当前 Runtime 没有原始 PDF input item；PDF 调用不能被视为无损模型名替换。
- 当前 Runtime 只暴露 application-owned function tools，未启用上游所用的 Gemini Google Search grounding。
- `gpt-5.6-sol` 文本 Runtime 不输出 raster image。当前仓库原有独立 image-generation provider 方案已被 ADR-0102 取代；生图仍可使用不同模型，但必须由同一家中转 provider 提供。
- 当前 Relay Provider 的 `/models` 对现有令牌公开 `gpt-image-2`，而上游默认名 `gemini-3-pro-image-preview` 会返回 403 无权访问；因此配置将该上游名映射到同一家 provider 的 `gpt-image-2`。真实 image-endpoint probe 已返回有效 PNG。
- `gpt-5.6-sol` 的真实文本 probe 已成功。该部署的 Responses endpoint 拒绝 `temperature`，PaperOrchestra 专用桥会同时清除 provider 默认值和上游逐调用值，不改变其他 InternAgent Agent 的配置。
- `gpt-5.6-sol` 的真实 `input_image` probe 已用仓库正常尺寸 PNG 返回 `VISION_OK`。该 provider 会拒绝 1×1 PNG 为无效图像，因此视觉输入验证使用正常论文图片尺寸，不能用极小像素占位图代替。
- PB-Twin 真实 smoke 已生成两张 Matplotlib 统计图并送入 Figure Critic，也已由 `gpt-image-2` 成功生成 16:9 架构 diagram 并送入 Figure Critic；绘图代码执行、生图和视觉回看三条子链均已通过真实 provider。
- 真实上游并发曾触发 500、504 与 `no_available_account`；兼容层现在以 `max_concurrent_model_requests: 2` 限制同一 PaperOrchestra Run 的文本和生图在途请求，而不改写上游 Agent、任务拆分或 ThreadPool 控制流。
- 长上下文与完整真实论文主链已经通过 PB-Twin smoke；验收细节见下一节。

### 真实端到端验收结果

- 2026-07-15 使用统一 Relay Provider 完成一次 PB-Twin 真实 PaperOrchestra Run，总耗时 `10144.87` 秒（约 2 小时 49 分）。Outline、Literature、Plotting、Section Writing、Content Refinement、Layout Review 和最终编译均正常结束，宿主状态为 `succeeded`。
- Literature Agent 规划并执行 95 个检索任务，最终补全 7 篇唯一论文。Semantic Scholar 公共 API 对两个条目出现 5 秒连接超时或 SSL EOF；上游按非致命 warning 跳过并继续，不影响论文生成。这些请求不属于模型 provider 流量。
- Plotting Agent 生成两张 Matplotlib 统计图和一张 `gpt-image-2` 架构 diagram；三张图均经过 3 轮 Figure Critic、caption 生成，并以有效 raster 文件写入 run-local `figures/`。raw draft 曾插入三张图；Content Refinement 自主删掉了最终 TeX 中的全部 `includegraphics`，因此最终 PDF 未使用这些图。这是当前允许的上游自主取舍，不由宿主层改写。
- Section Writing 生成 raw LaTeX 与初始 PDF。初始 ensemble review 为 3/10；v1 仍为 3/10 且子维度稳定，v2 总分不变但 Originality 与 Quality 各下降 1，因此上游停止精修并回退，再完成 1 轮独立版式修正。
- 最终产物为 11 页、244976 bytes 的 PDF 1.7 文件和约 38 KB 的 `final_refined_paper.tex`。PDF 头、EOF、全页 raster 渲染及最终编译日志均通过检查；未发现裁切、重叠、黑块、fatal LaTeX error 或未解析引用。
- 相同 Launch 再次调用在 0.29 秒内返回既有成功结果；PDF mtime、stdout 大小和 SHA-256 均未变化，确认没有重新调用模型或生成第二篇论文。
- 整个主链没有出现 `temperature`、403、500、503、504 或 `no_available_account` 错误。stderr 只有 Matplotlib 字体权重 fallback；上述两条 S2 warning 是唯一外部检索异常。
- 该长运行在最终 cwd 隔离补丁落地前已经启动，因此模型生成的临时绘图文件曾落到 vendored 根并在验收后清理。当前代码把子进程 cwd 设为 run-local Paper workspace；该边界已由 mock E2E 验证，但没有为这一个纯执行目录修正重复消耗另一轮 2 小时 49 分的真实模型流量。

## 已确认 Provider 策略

- 按 ADR-0102，PaperOrchestra 的文本、JSON、视觉理解、搜索相关调用和图片生成统一经过一家第三方 OpenAI-compatible 中转 provider；当前选择来自 `https://yunwu.apifox.cn/` 所记录的服务。
- 统一的是 provider、base URL、凭据和运维边界，不是模型 ID。文本与视觉角色优先映射到 `gpt-5.6-sol`，生图可映射到同一家 provider 下的独立 image model，搜索能力也可使用该 provider 下的其他模型或兼容接口。
- 不再保留上游 Gemini client 与 InternAgent OpenAI client 两套 provider stack，也不再为生图配置第二套 provider 凭据。
- 对当前凭据和主链所需能力，单一 provider 覆盖已由 `/models`、文本/视觉/生图 probe 与上述真实端到端 Run 证实：文本、JSON、视觉理解使用 `gpt-5.6-sol`，生图使用同一 provider 的 `gpt-image-2`。这不等于承诺该服务未来模型目录不变，也不覆盖未执行的离线 evaluator。
- 后续若发现该 provider 缺少必要能力，必须显式失败或重新讨论 ADR-0102；不得静默跳过 Literature Search、视觉评审、Diagram 生成或其他上游阶段。

## 已确认协议边界

- 按 ADR-0103，上游所有文本、JSON 和图像理解调用保留原 helper 签名与返回结构，但通过薄兼容层委托给 InternAgent 的 `ModelRunRequest -> ModelRunResult` Responses Runtime。
- 不复用上游 Chat Completions 分支，也不保留 Gemini SDK；Responses 不可用时显式失败，不允许静默降级到 Chat Completions。
- 不再向每个上游 Agent 注入 `BaseModel`，也不把同步 Agent 和 pipeline 全面重写为 async；兼容改造集中在共享模型 helper 边界。
- Raster image generation 不经过 `ModelRunRequest`，而是用 ADR-0102 选定的同一家 provider、同一凭据边界和能力专用 image model 调用其 image endpoint。
- Gemini Google Search grounding 没有在 Responses bridge 中复刻；当前真实主链以模型候选发现加 Semantic Scholar enrichment 完成文献阶段，这是已知的搜索语义对等性缺口。原始 PDF bytes 则由兼容层提取为文本后送入 Responses Runtime，不承诺保留原始 PDF 的版面模态。
- 该决定取代 ADR-0016 的全面 `BaseModel` 注入与原生异步化实现策略，但保留 ADR-0048 的 Responses-native Runtime 政策。

## 已确认执行边界

- 按 ADR-0104，每个 PaperOrchestra Run 由 InternAgent 启动一个内部 Python 子进程；它仍属于当前仓库和当前机器，不是外部服务、容器或第二个项目。
- 子进程通过绝对路径执行 `third_party/paper_orchestra/paper_writing_cli.py`，并把 vendored 根目录加入 `PYTHONPATH`，以保留上游同步 pipeline、根目录导入、模块状态和内部 ThreadPool；它的 cwd 是 run-local Paper workspace，防止模型生成的相对路径绘图产物污染 vendored 源码。
- InternAgent 异步服务负责准备 run-local 输入与配置、启动和取消子进程、捕获日志，并读取持久化产物。
- 子进程内的同步模型 helper 通过 ADR-0103 的 Responses 兼容层调用单一中转 provider；每个上游工作线程可复用现有 Deep Research 的 thread-local event loop 与 Runtime client 模式。
- 进程隔离避免上游顶层 `methods`、`utils` 包、provider adapter 状态和并发 Figure worker 污染或串扰其他 InternAgent Run。
- 宿主成功边界由 `final_paper.pdf` 与 `content_refinement_workdir/final_refined_paper.tex` 共同确定；成功后重入直接复用。首版明确不提供 PaperOrchestra 的逐 stage checkpoint 或 host-restart resume。
- 英文成功边界完成后，宿主通过同一 Responses backend 追加一次完整 LaTeX 翻译，并以 XeLaTeX、`ctex`、`xeCJK` 和 Fandol 字体集编译 `final_paper.zh-CN.pdf` 与 `content_refinement_workdir/final_paper.zh-CN.tex`。中文伴随稿翻译全部可编辑正文、caption 与附录，但保留公式、引用、参考文献、标识符、代码、数值、URL 和 raster 图片内容；默认 `final_pdf`、`final_tex` 仍指向英文权威版本。

## 已确认 Paper 生命周期

- 按 ADR-0105，一个 Discovery Launch 在其配置的 Discovery 工作结束后最多自动调用一次 PaperOrchestra，并且最多拥有一篇完成的 Paper。
- Provider retry 和上游进程内 retry 都属于同一次 PaperOrchestra Run，不创建论文版本或新的 Run。
- Paper 完成后再次进入该 Launch 只返回既有产物，不重新生成；新增研究若要产出新论文，必须创建新的 Discovery Launch。
- Paper Handoff 对一个 Launch 只发生一次；它从当时已有的 Native Discovery Artifacts 构造固定 Paper Input Bundle，不启动或停止任何 Research Draft 捕获。
- 首次忠实移植不提供 PaperOrchestra 的持久化逐 stage checkpoint，也不设计 host 或子进程重启后的恢复；保留上游运行期间的普通重试，耗尽后显式报告失败。
- 该决定取代 ADR-0019、ADR-0096 和 ADR-0099 中的 PaperOrchestra stage resume、多 Run 及后续 Handoff 语义；Discovery 自身的核心恢复不受影响。

## 已核实输入契约

- 上游 CLI 只接收一个 `raw_materials_dir`，随后把它完整复制到本次输出目录的 `raw_materials/`。主链硬性要求其中存在 `idea_sparse.md` 与 `experimental_log.md`；InternAgent 的 Launch root、Research Draft 或 Selected Research Candidate 都不是上游原生概念。
- `OutlineAgent`、`HybridLiteratureAgent` 和 `SectionWritingAgent` 会把上述两个 Markdown 的正文直接放进模型上下文。上游把前者理解为技术方法，把后者理解为实验结果与表格的原始数据；只在文件中记录 Launch artifact 路径不能让模型读取对应文件内容。
- Plotting 路径同样只主动读取 `raw_materials/` 根目录下的 Markdown。它根据 outline 中的 `data_source` 选择文件，无法匹配时回退到 `experimental_log.md` 和 `idea_sparse.md`。
- 上游的 `--use_plotting` 路径会自行生成 figures；它不会自动复用 `raw_materials/figures/` 中的已有图片。首个可运行基线按 ADR-0122 直接保留这条自主绘图路径，不增加已有图片合并逻辑。
- 迁移前的 InternAgent 原生重写曾用模型把 Research Draft 分批提取、递归合并为 `paper_materials.md`，再扫描整个 Launch 的 JSON 和 `report.md` 收集引用与图片。该 pipeline 不是固定上游提交的行为，已被 ADR-0110 排除并随旧写作核心删除。
- 实际 Research Draft 混合初始 prompt、运行配置、参数、模型与工具流量、日志及实验事件；一个尚未完成的 AutoDebug 样本已达到约 122 KB。它不再进入首版 Paper Input Bundle，也不再触发任何前置模型整理。
- Selected Research Candidate 目录已有更接近上游契约的自然产物：`notes.txt`、`experiment_report.txt`、`run_*/final_info.json`、最终代码与日志。Launch 级 `prompt.json`、`discovery_summary.json`、citation records 和已有 figures 同样是可确定性映射的自然产物。

## 已确认自然产物基线

- 按 ADR-0110，InternAgent 在启动子进程前创建一次 run-local `raw_materials/`；上游 CLI 和写作 pipeline 仍只看到原生输入位置，不认识 Launch 内部结构。
- Paper Input Bundle 只能来自不依赖论文功能也会产生的 Native Discovery Artifacts。不得读取或生成 `manuscript/draft.md`，也不得在上游主链前调用模型提取、总结、筛选或改写材料。
- `idea_sparse.md` 由确定性程序呈现 Launch prompt 与候选方法记录；`experimental_log.md` 按 ADR-0113 呈现候选级实验叙述、各次 `final_info.json`、存在的 Run 报告及失败记录，不嵌入 `discovery_summary.json`。原始数值、公式和失败记录保持不变。
- 首个可运行基线不构造额外的 figure catalog，也不修改上游互斥的 figure 路径；`--use_plotting=true` 由 Plotting Agent 自主决定并生成本次论文所需图片。
- 这一约束用于控制变量：先评估完整上游 PaperOrchestra 在系统自然产物上的论文质量，再根据实测结果单独讨论是否引入 Research Draft 或其他材料增强机制。

## 已确认候选范围

- 按 ADR-0111，当 Terminal Candidate Selection 成功时，Paper Input Bundle 只接收一个 Selected Research Candidate 的候选级自然产物；同一 Paper Candidate Round 的其他候选即使成功也不进入输入。
- Selected Research Candidate 内部的全部 Experiment Runs 都进入范围，包括早期版本、失败尝试和最终成功版本。它们属于同一方法的实验轨迹，可支持改进对比、消融、限制与负面结果。
- Launch 级 `prompt.json` 和 citations 仍是共享模型输入，不因候选收窄而丢弃。`discovery_summary.json` 与 Candidate Selection Provenance 继续供适配层定位和审计，但按 ADR-0113 不进入上游模型上下文。
- 该决定只约束存在 Selected Research Candidate 时的输入范围；没有 selection 时仍按 ADR-0110 的非阻断规则进入 Paper Handoff，具体 fallback material 另行确定。

## 已确认暂不传入代码

- 真实 PB-Twin 候选的最终 `run_2/code/experiment.py` 约 13.6 KB，而对应 `code_summary.json` 约 1.2 KB；代码全文本身不足以构成明显上下文压力。
- 该 `code_summary.json` 仍把方法描述为使用 16 个原始特征的 baseline ridge，但最终代码和 `final_info.json` 已使用 18 个工程化物理特征。摘要并不具备随最终代码同步更新的可靠性，不能作为论文方法的唯一事实源。
- `code_summary.json` 是 Idea Generation 对 baseline 代码的一次性理解缓存；候选和各 Experiment Run 通过目录复制继承它，实验修改完成后没有刷新契约。它虽然物理上存在于 Run 目录中，但不是最终实现产物。
- 按已确认决定，`code_summary.json` 完全不进入 Paper Input Bundle。原文件不删除，仍留在 Native Discovery Artifacts 中供历史排查，但 PaperOrchestra 不读取、不复制、不引用它。
- 首版同样不传最终源码、早期 Run 源码或派生代码差异。原始代码目录继续作为实现事实源保留，但 PaperOrchestra 暂时不读取任何代码内容。
- 各 Experiment Run 的改动说明、运行结果、失败和精确指标仍进入 `experimental_log.md`；这一基线先评估现有自然语言方法记录和实验产物能支持怎样的论文质量，再决定是否引入代码材料。

## 已确认 `idea_sparse.md` 组成

- 真实 Launch 的根 `prompt.json`、Selected Research Candidate 根目录的 `prompt.json` 和最终 Run 内的 `prompt.json` 哈希完全相同；后两者只是目录复制产生的重复件。
- Launch 根 `prompt.json` 已包含研究问题、领域、目标、数据集、baseline、指标、优化方向和约束，应作为任务背景的唯一副本。
- Candidate 根 `notes.txt` 由系统直接从候选的 name、title、description 和 method 字段写出，是当前最接近上游 `idea_sparse.md` 语义的自然产物。
- 按 ADR-0112，当 Terminal Candidate Selection 成功时，`idea_sparse.md` 只确定性呈现 Launch 根 `prompt.json` 与 Selected Research Candidate 根 `notes.txt`，并分别标明来源；不调用模型总结、补全或改写。
- 候选和 Run 内重复的 `prompt.json`、包含多个候选的 `ideas.json`、实验结果、Draft、代码及代码摘要均不进入 `idea_sparse.md`。
- 没有 Selected Research Candidate 时应使用什么 fallback material 仍单独留待决定，不在本决定中推断。

## 已确认 `experimental_log.md` 组成

按 ADR-0113，`experimental_log.md` 从 Selected Research Candidate 的全部 Experiment Runs 和候选级自然产物中确定性构造，并保持失败记录、精确数值和来源边界。

### 已核实证据

- 上游 `OutlineAgent` 和 `SectionWritingAgent` 会读取 `experimental_log.md` 全文；写作提示明确把它当作构造实验表格的原始数据。因此该文件必须内嵌实际内容，不能只列 Launch 内的来源路径。
- `run_0/final_info.json` 与各数字 `run_N/final_info.json` 是原始精确指标和运行配置的事实源。它们应按 `run_0`、`run_1`、`run_2` 的数字顺序原样呈现，不重新计算改善率、聚合分数或 best run。
- Candidate 根 `experiment_report.txt` 是 Claude Code 后端在实验结束后根据所有 Run 生成的自然产物，能说明每次修改和结果，但它是模型生成的二级叙述，可能不存在，也可能出现展示编号与目录编号不一致；数值冲突时不能覆盖 `final_info.json`。
- Candidate 根 `log.txt` 是 Claude Code 与 iFlow 后端共有的完整活动日志，包含模型回复、实验 stdout、临时失败和修复过程。PB-Twin 中两次 return-code-127 的临时失败只在该日志与后生成的 `experiment_report.txt` 中可见。
- `run_N/log.txt` 是创建 Run 目录时从 Candidate 根复制的阶段性快照；PB-Twin 的多个副本哈希不同但分别只是根日志的早期前缀，全部传入只会重复内容。
- `run_N/report/report.md` 和 `run_N/traceback.log` 若存在，分别是该 Run 的科学报告与失败事实。它们比 Launch 级调度摘要更接近上游 `experimental_log.md` 的实验语义。
- `discovery_summary.json` 主要保存恢复和调度信息，并列出所有轮次与候选；完整嵌入会重新带入 ADR-0111 已排除的兄弟候选。它适合用于定位 Selected Research Candidate，不适合作为论文实验正文。

### 已确认规则

- `experimental_log.md` 先原样呈现 Candidate 根 `experiment_report.txt`（若存在），并明确它只是叙述性索引。
- 随后按数字升序呈现 `run_0` 和全部 `run_N`：原样嵌入各自的 `final_info.json`，以及存在时的 `report/report.md` 和 `traceback.log`。
- Candidate 根 `experiment_report.txt` 不存在时，才原样使用 Candidate 根 `log.txt` 作为实验过程叙述；存在 report 时不再重复传入该日志。
- 不传 `run_N/log.txt`、完整 `discovery_summary.json`、Candidate Selection Provenance、代码、代码摘要或代码差异。`discovery_summary.json` 和 selection record 仅由适配层用于定位与审计，不进入上游模型上下文。
- 任一叙述与精确指标冲突时，`run_N/final_info.json` 优先；渲染器只标示来源和优先级，不调用模型修复冲突。

## 已确认首版图像策略

按 ADR-0122，首个端到端可运行基线保留固定上游提交的完整 `--use_plotting=true` 行为。PaperOrchestra 可以自主规划、生成、撰写 caption、批评和修订统计图或 diagram；适配层不再新增 figure provenance gate、Figure Catalog、图像去重、只允许 diagram 的类型限制或已有图片合并路径。

这一决定不是对生成图科学可靠性的最终评价，而是明确控制当前工程优先级：先验证完整上游流程能够在 InternAgent 的自然产物和统一 Relay Provider 上跑完，再根据实际论文质量与失败数据讨论图像约束。ADR-0114、ADR-0116 至 ADR-0121 已被 ADR-0122 取代；ADR-0115 继续保持 superseded。

`report/report.md` 若存在，仍按 ADR-0113 原样进入对应 Run 的 Experimental Record。它不是 Experiment Run 成功、Terminal Candidate Selection 或 Paper Handoff 的前置条件；首版不新增 report repair，不改变现有实验成功判定。

## 当前实施与验收结果

1. 固定上游提交的 56 个 Git 跟踪文件已完整导入 `third_party/paper_orchestra/`，未经适配基线提交为 `befecd3`。
2. 最小宿主适配层已从 Launch 与 Selected Research Candidate 确定性构造 `idea_sparse.md` 和 `experimental_log.md`，不传 Draft、代码或 `code_summary.json`。
3. 上游子进程使用 run-local Paper workspace 作为 cwd；一个 Discovery Launch 最多拥有一个成功 Paper，成功后重入直接复用。
4. 共享模型调用已适配到统一 OpenAI-compatible Relay Provider 与 InternAgent Responses Runtime，生图使用同一 provider 的能力专用模型。
5. mock E2E、真实文本/视觉/生图 probe 和完整真实 PB-Twin smoke 均已通过；图像治理继续不阻塞首个可运行基线。
6. 英文论文完成后会自动生成一份中文伴随稿；翻译是一次无工具调用的直接 backend 请求，不复用 Codex CLI 的工具历史，英文默认返回路径保持不变。

## 当前 Vendored 偏离面

未经适配的基线提交先以 56 个 Git 跟踪文件完整导入，并逐文件验证内容哈希与固定上游提交一致。当前在该基线上只保留以下运行必需偏离：

- `utils/genai_types.py` 提供上游使用到的最小 `google.genai.types` 兼容容器；6 个上游文件只替换对应 import，不改 Agent prompt 或控制流。
- `utils/internagent_adapter.py` 把上游内容容器转成 InternAgent `MessageContent`，将 PDF bytes 提取为文本，并将图片 bytes 转为 Responses `input_image`。
- `utils/gemini_utils.py` 与 `utils/openai_utils.py` 保留原 helper 签名、解析与重试形状，但把文本/视觉调用委托给 Responses bridge，把生图委托给同一 Relay Provider 的 image endpoint。
- `paper_writing_cli.sh` 恢复为可执行模式；其文本内容保持上游基线不变。

除此之外，Outline、Literature、Section Writing、Content Refinement、Plotting、autorater、prompt、template 和 CLI 主控制流均来自固定上游副本。InternAgent 的候选选择、原料投影、运行目录、provider 配置和子进程管理位于 vendored 树外的宿主适配层。
