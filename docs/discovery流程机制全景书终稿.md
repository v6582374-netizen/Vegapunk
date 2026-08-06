# Discovery 机制全景书（长篇终稿）

## 从一封任务信到一份可复核的研究发现

> 本书写的是 Discovery，不写论文编排。
>
> 故事在 `discovery_summary.json` 写下最后一行时暂时停住。那一刻，想法已经走过生成、批评、查证、演化、排序、方法开发、实验和多轮反馈，但还没有进入任何论文排版工坊。这样做不是把系统砍掉一半，而是把一个可以独立运行、独立恢复、独立审计的研究发现边界讲清楚。

这本书的主角不是一个会说话的模型，而是一条会留下脚印的流水线。它从一个目录开始，从一个 JSON 文件开始，从一行看起来平常的命令行参数开始。随后，目录被复制，任务被规范化，代理被装配，状态被推进，工具被调用，想法被拆开又重新组合，代码被放进隔离工作台，指标被拿来比较，失败被保留下来，成功也被要求给出路径。最后，所有轮次被压成一份汇总。

为了让读者既能看懂故事，又能追到代码，本书反复采用一种固定的叙述节奏：先讲研究工坊里正在发生的动作，再给出一段不依赖语法的机制骨架，然后指出它在仓库中的真实落点，最后说明这个动作留下了什么证据。机制骨架不是可以直接运行的 Python，也不是逐句转写；它只把真实实现中的顺序、条件、异常和数据流摊在桌面上，让读者不会被“模型提出了一个想法”这种模糊句子带走。

本书中的“队长”“书记员”“资料员”等称呼只是为了建立直觉。真正负责调度的是 `launch_discovery._main` 和 `OrchestrationAgent`，真正保存结构化状态的是 `WorkflowSession`，真正承载候选变化的是 `Idea`，真正负责跨服务模型入口的是 `UnifiedModelRuntime`。故事人物不能替换代码对象，故事只帮助我们在脑中保持对象边界。

## 写法说明：颗粒度在机制，不在代码行

这次修订把“伪代码层面的颗粒度”重新解释为机制的颗粒度：读者需要知道谁在什么时候拿到什么、做出哪一个判断、把什么写回哪里、失败后谁继续、恢复时凭什么接上，而不需要把每个 Python 参数逐个背下来。

因此，正文只保留少量足以定位对象的真实名称，流程用故事中的动作、门槛、账本和工作台来转译。遇到一个条件，我会说明它改变哪条路；遇到一个字段，我会说明它承担哪种证据；遇到一个异常，我会说明影响范围。这样既能覆盖系统细节，也不把本书写成 API 手册。

如果读者想回到仓库，章节中的对象名仍可作为索引；如果读者只想理解 Discovery 的运行逻辑，连续阅读故事即可，不必在段落之间切换到源代码。

## 阅读边界：哪些东西在门外

发现流程有一个很容易被误解的门槛。很多人一看到 `launch_discovery.py` 末尾调用了论文阶段，就以为 Discovery 的每一行都在为论文服务。本书不这样讲。Discovery 可以在没有论文阶段的情况下完整完成：它可以创建 Launch，可以恢复轮次，可以选出 top ideas，可以运行实验，可以更新 baseline，可以生成经验，可以写出 `discovery_summary.json`。论文编排是另一个可插拔的消费者，而不是 Discovery 内部的必要齿轮。

因此，本书不解释 `PaperOrchestra` 的章节、TeX、PDF、候选论文选择或论文审查。读者只需要知道一个事实：Discovery 的最终交付物是发现结果及其证据目录，后续模块可以读取它，也可以不读取它。把这个边界画清楚以后，很多看似互相牵连的逻辑会变得简单：研究发现可以失败而不代表论文编排失败，论文模块也不能反过来改变已经落盘的 Discovery 事实。

## 全书的总地图


主线可以这样记：命令行先把任务领进工坊，启动器为本次运行留下输入快照；外层 Round 驾驶 Session，Session 让想法经过生成、批评、查证、演化和排序；被选中的方向进入方法开发和实验工作台；实验结果回到基线、记忆与下一轮，最后由 `discovery_summary.json` 把事实封存。换成一条连续的因果链，就是“确认输入 → 建立会话 → 加厚候选 → 隔离验证 → 比较指标 → 选择基线 → 封存证据”。


这张图有意把几个不同尺度的循环放在一起。最外层循环由 `_main` 控制，重复的是完整的 Discovery Round；中间的状态循环由 `OrchestrationAgent.run_session` 控制，重复的是一个 Session 内的想法加工；模型工具循环由 `ModelToolLoop.run` 控制，重复的是一次 Agent 请求和工具结果回填；实验重试由外部实验后端和 `ExperimentRunner` 控制，重复的是一个候选工作台里的代码尝试。四个循环都有“轮次”这个词，但它们的计数器、停止条件和产物完全不同。

---

# 第一幕　工坊在真正开门以前

## 第一章　任务信不是一句提示词，而是一件需要验收的货物

夜里，研究工坊收到一封任务信。信上可能写着：“在现有图像分类代码上寻找改进，目标是提升少数类召回率，不能显著增加推理成本。”也可能写着一份科学复现任务：论文、数据、核对清单、报告目录都已经准备好，只等系统开始工作。

信到了，并不代表研究可以立即开始。系统第一件事不是把整封信塞进生成模型，而是确认它属于哪一种任务。`detect_task_type(task_dir)` 的动作很小，却决定了后续工作台如何建造：如果目录里有 `task_info.json`，它返回 `sci`；否则返回 `auto`。这不是根据文字猜测任务类型，也不是让模型分类，而是用一个明确的文件存在性条件完成分流。


入口只做一次确定的分流：目录里有 `task_info.json` 就按科学任务处理，否则按普通自动任务处理。它不阅读任务文本，也不让模型猜类型；这个朴素判断让后续所有目录和评分选择都有可追溯的起点。


这个函数的朴素之处反而很重要。它没有检查“有没有 `prompt.json`”，因为自动任务的约定是没有 `task_info.json` 就走普通分支；它也没有扫描整个目录寻找“看起来像论文”的文件。越靠近入口，越需要少做推断。入口的任务是把不确定性压缩成一个可审计的分支，而不是提前替用户做科学判断。

在仓库里，这个动作位于 `launch_discovery.py`。调用者是 `_main`，它先把命令行里的任务名统一成 `args.task_dir` 和 `args.task_name`，确认目录存在，然后才调用 `detect_task_type`。如果用户传的是 `tasks/AutoCls2D`，任务名就是目录最后一段；如果传的是一个绝对路径，系统不会再拼一次 `tasks/`。这一步看起来像路径整理，实际上是在防止后续的 baseline、prompt 和结果目录彼此指向不同任务。

故事里的书记员会在账本上写下四个事实：任务目录、任务名称、任务类型、参考代码路径。对 `auto` 任务，默认参考代码是 `task_dir/code`；对 `sci` 任务，参考代码可以为空，因为科学复现任务可能把代码放在运行工作区里，由 `launcher.sh` 负责启动。只要这四个事实没有固定，后面任何“相对 baseline 的提升”都可能失去参照物。

## 第二章　普通任务和科学任务走进同一扇门

科学任务的原始材料通常不是普通 Discovery 直接消费的格式。它有 `task_info.json`，里面包含任务描述和数据项；它可能还有 `target_study/checklist.json`，每一项带有权重、类型和核对内容。MAS 需要的是一个统一的 `Task`：描述、领域、背景、约束和参考代码路径。于是 `normalize_sci_task` 像一位翻译员，把科学任务折叠成一个合成的 `prompt.json`。

翻译员先打开 `task_info.json`，再尝试打开 `target_study/checklist.json`。清单不存在时，系统不把它伪造成空白成功，而是把清单当作空列表，继续构造一个明确缺少评分项的任务描述。目录名被拆成领域名，例如 `Chemistry_000` 变成 `Chemistry`。数据项被转成一串 `- name: description`，清单项则被转成带 `type`、`weight` 和最多两百字符预览的约束。


科学任务的翻译顺序是固定的：先读任务说明，再尽力读核对清单；把目录名整理成领域，把数据项变成背景，把清单变成约束，最后写出一份 MAS 能读懂的合成提示。缺少清单时保留“没有清单”的事实，缺少任务说明时让入口明确失败，而不是用模型补写。


故事中，翻译员并没有改变研究目标。它只是把“论文复现任务”包装成 MAS 能理解的统一入口。后面的 `IdeaGenerator.load_task` 不需要知道任务来自 `task_info.json` 还是普通 `prompt.json`，它只读取 `task_description`、`domain`、`background` 和 `constraints`。这就是输入适配器应该做的事：消除格式差异，不偷偷添加科学结论。

这里还有一个细节值得停下来。`normalize_sci_task` 会写出 `task_type: "sci"`，但 `Workflow Task` 的核心字段仍然只有描述、领域、背景、约束和参考代码路径。任务类型留在启动器参数里，既被实验阶段用来选择目录结构，也让审计者知道这次运行是复现型任务。数据流里存在两个“类型”，一个是启动层的分支，一个是提示快照里的事实，它们相互呼应却不互相替代。

## 第三章　Launch 是一次研究的房间，不是一个临时文件夹

当任务类型确定以后，`_main` 开始准备 Launch。新启动时，它生成一个形如 `YYYYMMDD_HHMMSS_launch` 的目录；如果用户给了 `--launch_dir`，系统直接使用那个已经由外层入口创建好的耐久目录；如果用户给了 `--resume`，系统从已有目录恢复。三条路径最后都要回答同一个问题：这次运行的所有输入和输出放在哪里？

Launch 至少承载这些东西：一份本次使用的 `prompt.json`，配置和提示快照（如果外层启动器提供），日志，`session_*` 子目录，轮次结果以及最终的 `discovery_summary.json`。它让“同一任务的不同运行”和“同一运行的不同轮次”有了层次。共享的长期经验放在 `base_output_dir`，当前运行的证据则放在具体 Launch 里；这两个目录不能混成一个，否则恢复时很难知道某份经验属于哪个运行。


Launch 的准备只有三条路：已有目录就复用，恢复就回到原目录，新启动就创建带时间标记的目录。三条路最后都要把 prompt 快照、共享资源位置和当前输出位置固定下来；科学任务生成合成提示，普通任务复制原提示，找不到输入就停在门口。


复制 prompt 而不是直接在任务目录里读取，是为了建立输入快照。第一轮运行开始以后，任务目录里的原始提示可能被用户编辑，下一轮也可能发生提示演化。Launch 内的 `prompt.json` 是本次运行曾经看到的版本；即使后来被提示演化覆盖，历史备份也应该留在同一目录里，便于解释“为什么第二轮和第一轮的生成条件不同”。

如果是科学任务，Launch 里写入的是合成 prompt；如果是普通任务，`shutil.copy2` 把任务目录的 prompt 复制过来。缺失 prompt 时，系统抛出 `FileNotFoundError`，而不是让 Agent 自己猜一个任务。入口阶段宁可明确失败，也不要把任务事实交给概率模型补齐。

## 第四章　配置决定节奏，但不是事实本身

配置文件像工坊墙上的节拍器。`default_config.yaml` 里，Discovery 的典型默认值是：MAS 内部最多四次迭代，保留五个 top ideas，开启 top ideas 演化，模型任务并发上限为五；外层完整 Discovery 轮数为十，loop mode 为 `incremental`；实验最大运行次数为两（`run_0` 是基线，`run_1` 到 `run_N` 是改动后的尝试），实验最多四个并行槽位。

这些数字是默认节奏，不是科学定律。`_main` 从命令行或配置读取 `loop_rounds` 与 `loop_mode`；`OrchestrationAgent.__init__` 从 `workflow` 段读取 `max_iterations`、`top_ideas_count`、`top_ideas_evo` 和 `max_concurrent_tasks`；`ExperimentRunner` 再读取实验段的并发和后端设置。每个层级只消费自己负责的字段，避免把“外层十轮”误当成“Session 内四轮”。


配置的传递像分层的节拍器：外层只消费轮数和模式，Session 只消费内部迭代和并发，排序只消费保留数量，实验器只消费运行和资源限制。一个数字可以影响后续产物的数量，却不应越过边界改写另一个层的意义。


一个配置字段可能影响多个产物，却不应该跨越边界改变别人的语义。例如 `top_ideas_count` 影响排序后哪些 Idea 进入方法开发，也间接影响实验工作台的数量，但它不直接决定实验指标怎么算。`max_parallel_experiments` 决定多少工作台同时运行，却不改变 `overall_improvement_rate` 的公式。只有把配置放回它所属的层，读者才能在错误发生时定位责任。

## 第五章　命令行参数是一条可追踪的河

`parse_arguments` 把外部输入变成 `args`。任务名或任务路径、配置路径、输出目录、实验模式、实验后端、是否跳过想法生成、已有 Idea 文件、离线反馈和恢复路径，都会汇入这个对象。随后 `_main` 只在少数几个地方修改 `args`：补上任务目录和任务名称，确定 prompt 路径，确定输出目录，写入任务类型，必要时补默认参考代码路径。

这条河的上游是用户，下游是每个组件的构造函数。`IdeaGenerator` 读取 `args.config`、`args.task_dir`、`args.task_name` 和 `args.exp_backend`；`ExperimentRunner` 读取 `args.exp_backend` 和 `args.task_type`；恢复逻辑读取 `args.resume`。如果某个组件需要的信息没有在入口整理好，它就不应该再次从环境变量或工作目录猜测。


参数进入系统后先被整理成一张运行通行证：任务目录、任务名称、类型、参考代码、输出位置、模式、后端、恢复路径和可选反馈都在这里落定。下游房间只领取通行证，不再从环境或当前工作目录猜答案。


故事里，队长不会在每一间房都重新问“我们要去哪儿”。`args` 就是他手里那张运行通行证：不包含模型回答，不包含未经确认的实验指标，只包含启动时可以确定的边界。它可以被记录、被测试、被恢复，因此比一段自然语言说明更适合做流程的骨架。

---

# 第二幕　外层驾驶员把一轮又一轮接起来

## 第六章　`_main` 不是一条长函数，而是一列车站

第一次看到 `launch_discovery._main` 的人，往往会被它的长度吓到。它从参数解析一路走到摘要写入，期间还要处理恢复、任务类型、长期记忆、模型运行时、想法生成、报告模式、实验模式和增量基线。若把它当成一段“应该一次看懂”的代码，叙事很快会重新变成技术报告。更好的看法是把它当成一列火车：每个站只接收一组行李，完成一件边界清楚的事，再把行李交给下一站。

第一个站是恢复站。`args.resume` 存在时，`load_resume_state` 读取已有 Launch；没有完成轮次，就从第一轮开始；有完成轮次，就把 `start_round` 设为 `completed_rounds + 1`。注意，恢复状态告诉系统“已经完成到哪里”，但当前配置仍然可以把总轮数延长。旧摘要不是一把锁，而是一个起点。

第二个站是输入站。任务目录、任务类型、参考代码和 prompt 路径在这里被固定。第三个站是节奏站，读取 `loop_rounds` 与 `loop_mode`。第四个站是提前结束检查：如果 `start_round > loop_rounds`，说明 Discovery 轮次已经完成，系统可以只写出“已完成”状态并返回；本书不继续讲门外的论文模块。

第五个站是运行时站。模型运行时一开始可能是 `None`，因为“只读取已有 Idea 并生成报告”的路径不需要立即检查凭据或初始化昂贵客户端。只有真正选择模型驱动的阶段时，`create_model_runtime(config)` 才会被调用。这个延迟不是偷懒，而是让一个已经完成的 Launch 能在没有实验依赖的环境里被安全查看。


外层驾驶员按车站工作：先认领恢复信息，再固定任务和 Launch，读取节奏，决定是否需要模型运行时，逐轮交给想法生成和实验，轮末记录结果、沉淀经验、准备下一轮，最后写汇总。每一站都把前一站已经确认的事实当作输入，不偷偷跨站重算。


这一段机制骨架故意不列每个日志字符串，但保留了真实顺序。顺序本身就是机制：如果先创建 ExperimentRunner 再确定 baseline，实验目录会失去可靠起点；如果先生成经验再写本轮结果，经验库可能读到半完成的实验；如果摘要写在循环中间，恢复时可能把未完成轮次当成完成轮次。

## 第七章　外层 Round 与内层 Iteration 不共享一只钟

工坊墙上有两只钟。大钟每完成一次“生成想法—运行候选—更新记忆”的整圈就跳一格，它叫 Discovery Round。小钟在一个 MAS Session 内工作，每经过一次生成、批评、查证、演化和排序就跳一格，它叫 `iterations_completed`。

默认配置里，外层可以是十轮，内层最多四次。第一轮可能产生十五个初始想法，内层四次之后留下五个 top ideas；这五个想法被送到实验工作台，实验结果又决定第二个外层 Round 的 baseline。若把两只钟合成一只，读者会以为“第二轮”一定指第二次生成，或者以为内层 `iteration=2` 已经代表第二个代码基线。


外层 Round 和 Session 内部 Iteration 各自拥有计数、停止条件和产物。外层重复的是一整次“想法到实验”，内层重复的是候选加工；实验中的 `run_0`、`run_1` 又是第三种计数。故事里要把三只钟分开，否则恢复和基线会被误读。


外层钟决定“要不要再开一间新的实验室”；内层钟决定“同一间研究会还要不要继续磨候选”。两只钟的连接只有几个明确的接口：Session 完成时返回 top ideas，实验完成时返回结果列表，结果列表进入经验和 baseline 选择。除此之外，外层不应该直接改动 Session 内部的 Idea。

## 第八章　`fresh` 不是失忆，`incremental` 也不是复制粘贴

`fresh` 模式每一轮都从原始任务目录开始。它适合比较“不同轮次各自探索出的方向”，因为每一轮的代码起点一致。`incremental` 模式则在下一轮使用上一轮的最佳结果。它适合研究“改进能否逐步叠加”，但也更容易把早期错误带到后面。

有一个常见误会：fresh 是不是意味着长期记忆清空？答案是否定的。代码起点和认知起点是两条不同的反馈边。fresh 会把 `base_code_dir` 指回 `args.task_dir`，但历史的 `ideas.json`、实验 notes、经验库和 IdeaGraph 仍然可能被加载。系统可以一边站回原始代码，一边记得某个方向在上一轮已经失败过。

incremental 的动作也不是“把最好的目录改名成 baseline”。它必须同时移动代码和指标。`_update_baseline_for_incremental` 会扫描 `run_[1-9]*`，读取最后一个存在且能解析的 `final_info.json`，把它写回 `run_0/final_info.json`；如果有 `code/`，还会把最佳运行的代码覆盖到主 `code/` 和 `run_0/code/`。科学任务还要同步 `outputs/` 与 `report/`。


选择下一条基线时，系统先排除失败结果，再比较成功结果的总体改善率；没有成功者就保持原基线。选择只是做决定，真正的复制和替换由后续基线更新动作完成，两者之间留下日志和文件证据。


机制骨架里最后一步看似多余，真实实现却有更具体的路径：被选中的 `best_code_path` 里，最新 run 的指标被写入该候选的 `run_0`，然后下一轮以这个候选目录作为 `base_code_dir`。这里的“接力棒”必须包含代码和它的参考分数，否则下一轮的提升率会出现数学上的错配。

## 第九章　恢复：不是把进程从内存里复活，而是重新读懂房间

停电后，队长不会要求机器恢复所有 Python 对象。他只需要知道：哪几轮已经有结果，哪些 Session 目录存在，是否有有效的 `discovery_summary.json`，增量模式的最佳代码路径在哪里，Launch 里是否有 prompt 快照。

`load_resume_state` 先创建一个带默认值的字典，包含 `completed_rounds`、`all_round_results`、`all_session_ids`、`best_code_path`、`best_overall_performance`、`launch_id`、`loop_mode`、`loop_rounds`、`original_task_dir`、`base_output_dir` 和 `prompt_path`。如果恢复路径不存在，它记录错误并返回这份空状态；如果存在，它从目录名得到 `launch_id`，从父目录得到 `base_output_dir`。

优先读取 `discovery_summary.json`。摘要能直接提供完成轮数、轮次结果、Session 列表、模式和增量状态。如果摘要损坏或不存在，系统退回 `_scan_completed_rounds`：扫描 `session_*`，寻找候选目录下任何 `run_*/final_info.json`。只要有一个实验文件存在，就把该 Session 当作完成轮次的候选证据。


恢复像考古而不是复活进程：先检查摘要，再扫描轮次记录和会话目录，找出已经完成的最后一轮，恢复共享目录、会话列表和最佳代码位置；未完成的轮次不会被当作成功。当前配置仍可把总轮数延长，旧运行只提供起点。


恢复扫描的判断很保守，也很有限。它不检查每个 `experiment_report.txt` 是否写完，不检查某个模型是否真的返回了最终文本，只检查能被外层循环识别的硬产物。更复杂的完整性核验可以在后续工具中完成；启动器的任务是找到安全的起点，不是重新解释所有日志。

## 第十章　每轮都像一封短电报

外层循环每完成一轮，就构造一个 `round_result`：轮次编号、Session ID、结果列表、成功数、失败数。成功和失败的数量来自 `results` 中的 `success` 字段，而不是来自日志里出现了多少次“completed”。这一区别非常关键：日志是观察材料，结构化结果才是统计入口。

轮次结束后，如果长期记忆可用，`_generate_experiences_for_round` 读取该 Session 的 `ideas.json` 和实验 notes，把已经落盘的 Idea—实验配对交给 `ExperienceGenerator`。经验生成失败不会让本轮实验结果消失；它只是让下一轮少了一层指导。这样，记忆是增强项，不是主流程的单点故障。


一轮的记录至少要有轮次编号、Session 身份、每个候选的结果、成功数和失败数。它不是漂亮的报表，而是下一次恢复和最终汇总共同依赖的最小事实集合；结果顺序不代表排名，排名必须从结果字段重新判断。


这封短电报还决定下一轮是否换 baseline。最后一轮不再做基线晋级，因为已经没有下一轮需要接力；前面的轮次才调用 `_find_best_experiment_result`，只在成功结果中寻找 `overall_improvement_rate` 最大者。没有成功实验时，旧 baseline 保留，失败原因写在结果里。

---

# 第三幕　模型运行时与研究队伍

## 第十一章　`VegapunkInterface` 是外部驾驶员碰到的方向盘

`IdeaGenerator` 并不直接操作 `OrchestrationAgent` 的所有细节。它通过 `VegapunkInterface`：启动系统、创建 Session、查询状态、注入反馈、运行 Session、读取 top ideas。这个接口把“外部驾驶员”与“内部状态机”分开。

构造 `VegapunkInterface` 时，系统读取配置，补上 `work_dir`、`task_name`、`exp_backend`，接收一个进程所有者提供的 `model_runtime`。如果外部没有传运行时，接口才自己创建默认运行时。随后它初始化 memory manager、AgentFactory、本地工具、Agent 注册表和 OrchestrationAgent，并把 `system_ready` 设为 `False`。


外部驾驶员通过 `VegapunkInterface` 只做四类事：创建会话、启动或恢复会话、查询状态、注入反馈。它不直接改 Idea，也不绕过状态机；当会话停在等待点，驾驶员把外部意见写入历史，再让内部流程继续。


`startup` 是一个真正的门闩。它可以初始化远程 MCP 工具，打印工具注册表，启动 memory manager，然后才把 `system_ready` 设为 `True`。如果远程工具连接失败，系统不会假装已经可以运行。`create_session`、`run_session`、`add_feedback` 都先调用 `_ensure_system_ready`，避免一个半启动对象把错误拖到更深的阶段。

接口的 `add_feedback` 还有一个小动作：默认 `auto_resume=True`。它先把反馈写入 OrchestrationAgent；如果状态已经回到 `reflecting`，就调用 `resume_session` 继续推进。离线反馈文件因此可以被外层驾驶员自动注入，人工或其他服务也可以通过同一接口插入反馈。

## 第十二章　统一运行时像一座只有一个总闸的发电站

Discovery 里有很多 Agent，外层实验也可能使用模型。最危险的做法是让每个组件各自解析模型提供方、各自创建客户端、各自决定并发。当前实现选择一个进程拥有的 `UnifiedModelRuntime`，把它注入 Interface、AgentFactory、每个角色和实验执行器。

`UnifiedModelRuntime.__init__` 接收 `ModelCatalog`，建立适配器工厂、模型缓存、线程锁和每个 provider 的 `BoundedSemaphore`。`create_model_for_agent` 的实现很短：忽略角色配置，返回 `model_for(capability="text")`。角色的差异不在于各自偷偷选模型，而在于角色提示、上下文和允许工具。


统一运行时先根据冻结的模型目录决定文本、结构化输出和嵌入等能力，再把请求交给对应适配器。调用者只描述“要什么能力”，不直接持有某一家服务的客户端；恢复时使用 Launch 自己的目录，避免后来全局配置变化污染旧证据。


`run` 先根据请求和能力解析模型定义，再取得 provider adapter，通过 `_execute` 进入集中并发槽位。provider 级限流意味着“资料员、生成员、实验分析员”不会因为各自创建了客户端就绕过同一条供电线。测试中也明确要求 provider concurrency centralized：限流属于运行时，而不是某个 Agent 的私有技巧。

统一运行时还有一个观察意义。ResearchDraft 的 Agent hook 可以在运行时入口记录请求和原始响应；工具循环可以沿用同一 response chain；恢复和测试可以用一个假的 runtime 替换真实 provider。接口统一之后，代码不需要在每个角色里复制一套“凭据、重试、提供方选择”的逻辑。

## 第十三章　AgentFactory 的柜子里放的不是答案，而是角色

AgentFactory 注册了 `generation`、`reflection`、`evolution`、`method_development`、`refinement`、`ranking`、`survey`、`scholar`、`dr`、`prompt_evolver`、`experience` 等类型。它并不直接编排谁先说话，只在被请求时提供正确的角色实例。

创建一个 Agent 时，Factory 先检查类型是否注册；未注册就抛出 `ValueError`。随后用 `agent_type + active_text_model` 生成缓存键。如果缓存命中，返回已有实例；否则从运行时创建模型，实例化 Agent，附加 ResearchDraft hook，写入缓存。


AgentFactory 的职责是把角色名、角色配置和统一运行时装配成可执行角色。未知角色立即暴露为配置错误；已知角色获得自己的系统提示、能力开关和工具入口，但共享同一个运行时边界，便于审计请求从哪里发出。


`create_all_agents` 读取配置里的 `agents` 映射。一个角色配置可以是 `null`，表示使用默认值；也可以是字典。Factory 会复制字典，挂入 `_global_config`、`_runtime`，必要时挂入全局 memory 配置，不修改调用者的原始配置树。任何角色初始化失败都会进入 `failures`，最后抛出 `AgentInitializationError`，而不是返回一个半完整的注册表让流程继续。

这个细节解释了“共享运行时不等于共享脑子”。Factory 缓存的是角色实例和模型入口，提示、职责、阶段上下文仍然不同。生成员不会因为和排序员复用同一模型客户端，就自动看到排序结果；它只能看到 OrchestrationAgent 在下一次请求里放进去的字段。

## 第十四章　一个 Agent 的门牌号是 `execute(context, params)`

所有具体 Agent 都沿用 `BaseAgent.execute` 的形状：一个异步的 `context`，一个可选的 `params`。`context` 是阶段编排器准备的事实包，`params` 是角色级的运行覆盖。GenerationAgent 看到 `goal`、`iteration`、`feedback`、`paper_lst`；ReflectionAgent 看到 `goal`、`hypothesis`、`iteration`、`feedback`；RankingAgent 看到 `goal`、`hypotheses`、`iteration`、`feedback`。它们都不直接读取整个 Session 对象。

这个门牌号有一种很朴素的安全性：每个角色必须面对一份明确的输入合同。生成员如果拿不到 `goal.description`，就抛出 `AgentExecutionError`；反思员如果拿不到 `hypothesis.text`，就拒绝工作；排序员如果没有候选列表，也不能输出一个“空的冠军”。异常因此不是随机的 API 崩溃，而是输入合同被破坏的信号。


每个角色都遵循同一套门禁：先确认上下文有它必须知道的事实，再构造自己的工作提示，调用运行时，验证结构化结果，最后把结果交回编排器。缺字段时角色应给出可解释的空结果或错误，不把一团自然语言假装成完整对象。


角色的输出也有各自的结构。生成员返回 `hypotheses`、`metadata`、`baseline_summary`；反思员返回 `critiques`，在未进入方法阶段时还返回 `strengths`、`overall_assessment` 和 `improvement_suggestions`；演化员返回 `evolved_hypotheses`、`reasoning` 和 `changes`；排序员返回 `ranked_hypotheses`、`scoring_explanation` 和 `top_hypotheses`；方法开发和精炼则分别返回 `method_details` 与 `refined_method`。

这些结构不是为了让模型显得规整，而是为了让 OrchestrationAgent 能在不用理解自然语言的情况下，把结果写回 `Idea`。若模型返回的是字符串形式的 JSON，RankingAgent 还会尝试解析；如果解析失败，抛出清晰的 `AgentExecutionError`。如果候选数量与评分数量不一致，排序器记录警告，但不会悄悄复制分数填满缺口。

## 第十五章　工具循环：模型先问路，再决定下一步

资料员的工作很少是一次请求就结束。它可能先生成检索词，再调用文献搜索，再读取摘要，再决定要不要补一条查询。`ModelToolLoop` 把这件事压缩成一个小接口：给它 instructions、prompt、工具列表、最大迭代数、最大工具调用数，它就负责请求模型、执行工具、回填结果，直到模型不再请求工具或达到上限。

真实实现的第一个请求把用户 prompt 包成 `Message.user(prompt)`，把工具 tuple 放进 `ModelRunRequest`。每轮拿到响应后，先保存 `response.text`；如果 `response.tool_calls` 为空，马上返回 `ToolLoopResult`。如果有调用，先检查累计调用数是否会超过 `max_tool_calls`，再逐个执行。


工具循环是一场短对话：模型先提出工具请求，循环器检查请求格式和剩余配额，工具执行后把结果放回历史，模型再决定继续查、改走另一条路，还是结束。达到迭代上限、工具调用上限或出现不可恢复错误时，循环必须留下终止原因。


这个循环有两个值得反复讲的边界。第一，工具错误会变成模型可见的证据：`{"error": "..."}` 被放进下一次请求，模型可以换参数或承认材料不足。第二，工具循环不会直接改变 `WorkflowState`。ScholarAgent 调三次搜索，仍然只是 EXTERNAL_DATA 阶段里的局部动作；只有 OrchestrationAgent 把结果写回 Idea 并转移状态，研究会才会离开房间。

## 第十六章　工具是什么，什么不是工具

本地函数工具由 `init_tools()` 注册，远程 MCP 工具在 `startup()` 中异步连接。工具注册表能回答“有哪些工具”，MCPManager 能回答“如何执行某个远程工具”，但它们不回答“这一阶段应该做什么”。决策仍然属于 Agent 的提示和编排器的状态路由。

搜索工具返回一组论文，不等于“这个 Idea 已经被证明”。代码执行工具返回一个零退出码，不等于指标已经改善。文件读取工具找到 `final_info.json`，也不等于它属于当前候选。每一次工具结果都要经过阶段逻辑的归属和解释，才能成为 `evidence`、`references` 或实验事实。


工具返回先经过边界检查：错误被包装成工具结果并回送模型，模型可以据此调整；成功结果保留名称、输入、输出和时间线。工具不是“模型知道的一切”，而是有权限、有副作用和有失败可能的外部动作。


这里的“写回”尤其重要。工具结果通常只在短期上下文里存在，Agent 的解释才可能被写入 Idea 的 `evidence` 或 `critiques`。长期记忆再从落盘的 Idea 和实验记录中学习。若跳过写回，系统看似调用过很多工具，下一阶段却没有任何可检索的事实。

## 第十七章　ResearchDraft：一只不会替你改写历史的记录盒

`ResearchDraft.open(launch_dir)` 在 Launch 下创建 `manuscript/draft.md`，如果目录不存在就建立目录，如果文件不存在就 touch。`append(content)` 把可观察内容渲染成文本，在全局 `_APPEND_LOCK` 下追加；已有历史时先写入块分隔符，随后写入当前内容，确保内容末尾有换行。

它最重要的词是“append”。Draft 不重写旧块，不把多个 Agent 的回答压成一段光滑的总结，也不声称捕获了模型隐藏的内部推理。它保存请求、原始响应、工具调用、工具结果、日志、stdout、stderr 和异常这些外部可见事件。


ResearchDraft 是一条只追加的观察带。打开时确保目录和文件存在，写入时把一段完整观察作为不可分割的块追加；并发写入靠锁或等价的临界区保持块边界，重新打开只会接着写，不会重排历史。


`activate()` 通过 `start_research_draft_capture` 和 `stop_research_draft_capture` 管理一个作用域。退出上下文时，无论内部是否抛异常，捕获都会停止。测试覆盖了重新打开 Launch 后追加块、不覆盖历史、并发追加不交错、公式文本原样保留、stdout/stderr 镜像和进程级捕获可以在论文阶段以前停止等行为。

这些测试揭示了 Draft 的真正价值：它是“发生过什么”的索引，不是“最终应该相信什么”的裁判。研究者复盘时可以沿 Draft 找到一个工具调用的原始参数，再回到结构化 `final_info.json` 核对数字；二者职责不同，互相补充。

## 第十八章　Task、Idea 和 Session：三张不同尺寸的卡片

`Task` 记录研究目标的稳定事实：`id`、`description`、`domain`、`constraints`、`background`、`ref_code_path` 和 `created_at`。它的 `to_dict()` 把时间转成 ISO 字符串，`from_dict()` 在读回时把字符串转回 `datetime`。Task 是所有 Agent 共享的研究委托，但它不是某一轮的候选结果。

`Idea` 是一张会不断加厚的方案卡。最初它只有 `id`、`text` 和 `rationale`，生成阶段还会写入 `baseline_summary` 与 `iteration`。反思阶段增加 `critiques`；外部数据阶段增加 `evidence`、`references`，进入方法阶段可能增加 `refine_evidence`；排序阶段写入 `score` 和 `scores`；方法开发阶段写入 `method_details`；精炼阶段写入 `refined_method_details`；演化产生的子 Idea 还带有 `parent_id`。


Idea 不是一段想法文本，而是一张会随着流程变厚的卡片：先有方向和理由，再有批评、证据、评分、父子关系，进入方法阶段后才出现方法细节和精炼结果。字段的缺席本身也有含义，不能用空字符串把“尚未发生”和“发生但为空”混成一件事。


`WorkflowSession` 是更大的账本。它包含 `id`、`task`、`ideas`、`iterations_completed`、`max_iterations`、`state`、`feedback_history`、`top_ideas`、`tool_usage`、`started_at`、`completed_at`、`error` 和 `method_phase`。Session 不等于所有日志；它是流程能否继续的压缩状态，Draft 和 trajectory 才承载更长的观察历史。

## 第十九章　`to_dict` 是恢复的桥，不是装饰函数

Session 的 `to_dict()` 递归调用 `task.to_dict()` 和每个 `idea.to_dict()`，把 `WorkflowState` 写成 `.value`，把 `started_at` 与 `completed_at` 写成 ISO 字符串。这个方法让 FileSystemMemoryManager 可以把会话写入 JSON，也让测试可以在不启动模型的情况下检查状态字段。


Session 的持久化要能把任务、Idea、状态、计数、反馈、时间和错误一起还原。时间被写成可读格式，状态保持枚举语义；遇到半成品、暂停或失败时仍然可序列化，这才称得上恢复桥梁。


恢复时，MemoryManager 的 `load_session` 根据 JSON 重建 Task、Idea 和 WorkflowSession，再把 `state` 字符串映射回 Enum。这个过程意味着字段名和枚举值是持久化合同。把 `iterations_completed` 改成另一个名字、把 `state` 改成日志文本，都可能让旧 Launch 失去可读性。

更深一层的原则是：落盘对象要能表达“未完成”。`completed_at` 可以为空，`error` 可以包含诊断；Idea 可以只有 `text` 没有 `method_details`；Session 可以停在 `AWAITING_FEEDBACK`。如果序列化函数只接受成功对象，恢复机制就会被迫把失败和暂停伪装成成功。

## 第二十章　状态枚举像房间的门牌

`WorkflowState` 的门牌包括 `INITIAL`、`GENERATING`、`REFLECTING`、`EVOLVING`、`METHOD_DEVELOPMENT`、`REFINING`、`RANKING`、`AWAITING_FEEDBACK`、`EXTERNAL_DATA`、`COMPLETED` 和 `ERROR`。它们是有限枚举，不是任意自然语言标签。

`INITIAL` 表示会话已经建立但还未开始；`GENERATING` 让生成员产生候选；`REFLECTING` 让反思员检查风险；`EXTERNAL_DATA` 让 ScholarAgent 查证；`EVOLVING` 产生下一代 Idea；`RANKING` 综合打分；`AWAITING_FEEDBACK` 是一个停靠点；`METHOD_DEVELOPMENT` 和 `REFINING` 处理进入方法阶段的候选；`COMPLETED` 和 `ERROR` 是终点。


状态门牌限制了流程的合法房间。每次进入新房间前，编排器检查是否有对应的处理者；门牌与门后证据不匹配时，状态应转为错误，而不是继续走一条没有材料的走廊。


门牌本身不保证房间里的东西完整。Session 可能写着 `RANKING`，但如果当前迭代没有任何 Idea，`_run_ranking_phase` 会把它转成 `ERROR`。恢复时也不能只看门牌；必须核对门后是否有对应的 ideas、证据或实验目录。

## 第二十一章　状态转移同时通知观察者和记忆

`_update_session_state` 先保存旧状态，再写入新状态；如果提供了错误信息，就写入 `session.error`；如果新状态不是 `ERROR`，就清空旧错误；进入 `METHOD_DEVELOPMENT` 时，把 `method_phase` 设为 `True`。随后根据旧状态和新状态查找角色名称，写日志，并调用已经注册的状态回调。


状态转移先写事实，再通知观察者和记忆。回调只是旁观者，回调失败不应把研究状态倒退；错误信息随状态保存，后续转入正常房间时清理旧错误，方法阶段则留下已经进入收束期的标记。


回调失败不会反向改变状态。外部界面可能想显示进度，日志收集器可能想写一条事件，但它们不是研究流程本身。这个隔离让观察层可以短暂出错，而不让候选消失。

---

# 第四幕　研究会在状态机里点亮一盏又一盏灯

## 第二十二章　创建 Session：先补背景，再给任务编号

`OrchestrationAgent.create_session` 接收 goal description、domain、background、ref_code_path 和 constraints。它用当前时间生成 `task_<timestamp>`，再生成 `session_<timestamp>`。时间戳不是科学 ID，却提供了人类可读的运行线索；真正的关系由 Session 里的 Task 和 Idea 字段保存。

创建任务以前，代码会查看 `agents.dr` 的配置。DR 默认启用时，系统尝试取出 `dr` Agent，让它根据研究目标生成背景报告。如果 DR 初始化失败或执行失败，日志写下警告，然后继续使用用户传入的原始 background。这个降级策略说明背景调研是增强项：它能丰富上下文，但不能覆盖任务事实，也不能阻止最基本的 MAS 流程。


创建 Session 时先确定任务身份，再尝试让背景调研角色补充上下文；补充失败就保留用户背景。任务卡和会话卡随后一起写入记忆，未来恢复时靠它们找到同一条研究走廊，而不是靠时间戳猜。


这里有一个微妙的实现事实：`dr_agent.execute` 返回的内容会整体替换 `background`，而不是把用户背景和 DR 背景自动拼接。阅读代码时不能把“尝试生成背景”想象成“总会叠加背景”。如果用户希望保留两者，应该在输入设计或 Agent 提示中明确，而不是靠叙事猜测。

## 第二十三章　生成阶段：十五张卡片先被摊开

生成阶段的故事很容易被写成“模型提出十五个好点子”。代码其实更精确。`_run_generation_phase` 先从注册表拿 `generation` Agent，拿不到就抛出 `ValueError`。如果这个 Agent 的配置里 `do_survey` 为真，它会先调用 `survey` Agent，得到 `papers` 和 `web_results`，其中 `papers` 被放进生成上下文。

生成上下文包含 `goal=session.task.to_dict()`、`iteration=session.iterations_completed`、`feedback=session.feedback_history`、`paper_lst` 和 `task_name`。GenerationAgent 自己再读取 `goal.description`，创建输出 schema，要求 `hypotheses` 数组中的每项有 `text` 和 `rationale`；如果参考代码路径存在，还要求 `baseline_summary`。


生成阶段先决定要不要做调查，再把目标、轮次、反馈和可用资料交给生成角色。角色产出候选的方向与理由，编排器只把必要事实写入 Idea；更长的推理和工具轨迹留在观察记录，避免卡片变成无法维护的转录稿。


生成阶段只写入 Idea 的最初字段。它不会把模型的 `reasoning` 放进 `Idea`，也不会把工具返回的所有原文塞进 `baseline_summary`。GenerationAgent 的结果里有 metadata 和 reasoning，但 OrchestrationAgent 只取 `hypotheses` 和 `baseline_summary`。这是一种有意的压缩：Session 保存流程需要的结构化事实，Draft 才保留更完整的可观察事件。

生成 Agent 内部还有一层工具判断。它先获取允许工具，再用 `get_related_tools(query=prompt, tools=all_tools)` 选择和当前问题相关的工具。如果有相关工具，就通过 `_call_model_with_tools` 运行最多十次迭代、最多二十次工具调用；成功后把工具回答附加到主 prompt，再执行真正的结构化想法生成。如果没有相关工具，它记录 warning，继续用没有工具上下文的 prompt。

## 第二十四章　反思阶段：每张卡片都要面对同一盏审讯灯

生成结束后，状态进入 `REFLECTING`。`_run_reflection_phase` 先取出当前迭代的 Idea。`_get_current_ideas` 默认按 `idea.iteration == current_iter` 过滤；如果 `top_ideas_evo` 开启且当前不是第一迭代，还会只保留上一次排名中的 top IDs。这样，系统既能让早期搜索面宽一些，也能在后期把计算集中到有潜力的分支。

反思前，`_extract_feedback_content` 读取反馈历史。没有反馈就返回空字符串；全局反馈返回一个字符串；局部反馈返回列表并尝试按 Idea ID 过滤。实现中局部反馈的处理很值得仔细阅读：`feedback_content` 可能是列表，但 `reflect_one_idea` 内部按字典访问 `feedback_content.get("id")`。因此，系统设计上期待局部反馈在进入这里时已经被规范化成适合单个 Idea 的结构；如果输入形状不符合预期，日志和空反馈是比默默扩大影响范围更安全的结果。


反思阶段为每张当前候选安排一盏独立的灯。全局反馈先被理解，局部反馈再按候选归位；任务并发受模型信道限制，结果按候选原有顺序写回。早期写入普通批评，方法阶段写入方法批评，两条意见不会混账。


反思 Agent 对没有 `method_details` 的 Idea 返回四类结果：批评、优点、总体判断、改进建议；对已有方法的 Idea 只要求批评。这使同一个状态在两个时间点有不同含义：早期反思是“这个方向值得不值得继续”，方法阶段的反思是“这个已经具体的方案哪里还不严密”。

并发不是为了让批评互相聊天。每个任务拿到独立 Idea 的快照，使用同一个 semaphore 控制模型调用上限，最后按 `ideas` 列表顺序写回结果。完成顺序可以不同，写回顺序仍然稳定，这就避免了“先返回的 Idea 获得更高优先级”的隐式偏差。

## 第二十五章　外部数据阶段：资料员不替队长做决定

`_run_external_data_phase` 取出 `scholar` Agent，按当前迭代过滤 Idea。它使用 `MAX_CONCURRENT_SEARCH_TASKS`，这和模型任务的 `MAX_CONCURRENT_LLM_TASKS` 是两个不同的限制。搜索服务的并发瓶颈和模型 provider 的并发瓶颈不是同一件事；测试专门检查了这两个限制保持分离。

每个 Idea 的搜索上下文只有 `goal`、`hypothesis` 和 `iteration`，调用参数额外带 `method_phase=session.method_phase`。ScholarAgent 首先要求 goal 和 hypothesis 存在，要求 hypothesis 有 `text`；然后生成查询词，执行文献检索，收集 evidence 和 references，再生成 relevance summary。


外部资料阶段把搜索资源和模型资源分开限流。资料员按目标与候选查找证据并给出相关性说明；普通想法的证据进入早期证据栏，具体方法的资料进入精炼证据栏。搜索失败的隔离范围由当前实现决定，不能用想象中的“总是局部成功”覆盖真实行为。


资料员的结果分成两种桶。早期证据进入 `evidence`，它回答“这个想法为什么值得查证”；方法阶段的证据进入 `refine_evidence`，它回答“这个具体方案怎样补足理论和实现细节”。如果把两者混在一个列表里，后续精炼员就很难判断一条引用是在支持初始方向，还是在限制某个具体步骤。

ScholarAgent 的内部过程也不是“搜索一次”。`_generate_search_queries` 根据目标和 Idea 产生查询，`_gather_literature_evidence` 调用来源，`_evaluate_paper_relevance` 判断相关性，`_generate_relevance_summary` 形成摘要。任意外部服务失败都会上抛到阶段处理器，阶段处理器把 Session 置为 `ERROR`。这条策略与反思阶段不同：反思的单个 Idea 失败可以返回空批评继续，文献阶段的任务列表目前按整体结果读取，因此一个未处理的 task 异常可能使整个阶段失败。阅读系统时必须尊重这种真实差异，不能把所有阶段都概括成“局部失败隔离”。

## 第二十六章　演化阶段：父卡片不会消失，子卡片带着来处出生

文献阶段完成后，早期流程进入 `EVOLVING`。`_run_evolution_phase` 取当前 Idea，为每个 Idea 创建一个受 `MAX_CONCURRENT_LLM_TASKS` 限制的任务。上下文包含目标、父 Idea 的 `critiques`、`evidence`、全部反馈和当前迭代。

EvolutionAgent 的输出 schema 要求每个子候选都有 `text`、`rationale` 和 `improvements`，同时给出整体 `reasoning` 和 `changes`。OrchestrationAgent 只把 text、rationale、baseline_summary、iteration 和 parent_id 写进新的 `Idea`；`improvements` 和 changes 留在 Agent 的返回或 Draft 中，并不自动成为 Idea 字段。这意味着如果读者想追踪“子 Idea 改了什么”，要结合父子关系和演化事件，而不能只看子卡片的五个基本字段。


演化从父卡片开始：把批评、证据和反馈带给演化角色，生成子卡片，给子卡片留下父亲和出生轮次。某个父分支失败只丢掉它的孩子，不应让其他家族消失；这使搜索树保留真实的谱系。


失败的父 Idea 返回空列表，不会拖垮所有分支；这是演化阶段明确写在代码里的隔离策略。相反，生成阶段和排序阶段对 Agent 缺失更严格，直接把 Session 置为错误。不同错误策略反映了阶段的角色：演化是一个可丢失的分支扩展，排序是决定流程下一步的闸门。

## 第二十七章　排序阶段：先把候选分批，再决定谁能留下

排序发生在演化之后，也可能在初始生成之后的特定流程中发生。`_run_ranking_phase` 找的是 `idea.iteration == current_iter + 1` 的 Idea，因为当前 `iterations_completed` 仍然记录上一轮已经完成的计数。若没有任何 Idea，它不会调用模型，而是构造一条清晰的错误消息并进入 `ERROR`。

RankingAgent 把候选按五个一批切分。每一批都用同一个 schema 请求 `id`、`overall_score`、`criteria_scores` 和 `scoring_rationale`。返回的 `scored_hypotheses` 如果是 JSON 字符串，会先尝试 `json.loads`；每个元素必须包含四个字段，否则被过滤。所有批次的评分解释拼接起来，候选再按分数排序。


排序先把候选分成小批，分别得到分数、标准分项和理由，再合并、校验、归一化和排序。可选的多样性策略会在同一父节点的子代中保留代表；最终的 top 列表只记录谁被选中，不抹掉未入选者。


`strategy == "distinct"` 时，排序器先按 `parent_id` 分组，每个父节点只留下最高分的一个，再从这些代表中选 top N。这是一种保持候选家族多样性的规则。默认配置中的 strategy 是 `default`，所以实际运行是否启用 distinct 取决于角色配置；书中不能把“父节点去重”说成永远发生的事实。

OrchestrationAgent 收到排序结果后，把每个 Idea 的 `score` 和 `scores` 写回，把 `session.top_ideas` 设置为返回的 ID 列表，然后 `iterations_completed += 1`。如果当前已经在 `method_phase`，状态回到 `AWAITING_FEEDBACK`；否则达到 `max_iterations` 就进入 `METHOD_DEVELOPMENT`，还没达到就进入 `AWAITING_FEEDBACK`。看起来奇怪的“方法阶段排序后仍等待反馈”，正是代码当前的状态规则，阅读时应记录而不是用理想化流程图替换它。

## 第二十八章　AWAITING_FEEDBACK：一扇可以没人站在门后的门

`_run_awaiting_feedback_phase` 本身几乎不做计算。它记录 Session 正在等待外部反馈，然后 `pass`。真正的动作发生在外层 `IdeaGenerator.generate_ideas`：它循环查询 `get_session_status`，看到状态是 `awaiting_feedback`，如果 `args.offline_feedback` 存在，就读取 JSON，调用 `interface.add_feedback`。


等待反馈不是空白，而是有意停下的插槽。自动驾驶可以读取离线反馈立即续跑，人工驾驶也可以把意见留在门外；反馈带着时间、轮次和作用范围进入历史，不能静默改写任务目标。


`add_feedback` 追加一条带有 text、timestamp、target_ideas 和 iteration 的记录。如果 Session 正处于 `AWAITING_FEEDBACK`，它把状态转为 `REFLECTING`；Interface 的 `auto_resume` 默认开启，看到 reflecting 就再次调用 `resume_session`。所以在自动运行语境中，这个状态可以被离线 JSON 立即穿过；在交互式语境中，它也可以成为人工插槽。

反馈有全局和局部两种概念。全局反馈可以是“下一轮必须优先考虑推理成本”；局部反馈可以只针对某个 Idea。任务事实优先于反馈：如果反馈要求改变研究目标，系统应把冲突作为记录，而不是把 Task.description 静默改写。

## 第二十九章　方法开发：把形容词换成动词

当内层迭代达到上限，`_run_method_development_phase` 开始收束搜索。它先取当前迭代的 Idea；如果 `session.top_ideas` 非空，只保留这些候选。方法开发不是给所有历史 Idea 写长文，而是把排序已经认可的方向变成可以交给实验执行器的协议。

在调用方法 Agent 以前，OrchestrationAgent 会尝试用 ScholarAgent 补证据。`_gather_evidence_for_ideas` 只对没有 `idea.evidence` 的候选发起请求；如果子 Idea 没有直接证据，`_get_idea_evidence` 可以沿 `parent_id` 找父 Idea 的 evidence。随后 `_format_paper_context` 把每条证据格式化为 Title、Content、Relevance 三段，拼成方法 Agent 的 `paper_context`。


方法开发把“值得尝试”翻译成“可以执行”：先为缺证据的候选补资料，再把基线、想法、证据和反馈交给方法角色，生成名称、陈述、步骤和限制。失败会留下带失败标记的方法卡，宁可可见地失败，也不制造虚假的完整方案。


方法 Agent 的 schema 要求五个字段：name、title、description、statement 和 method。OrchestrationAgent 即使原始返回缺少其中某些字段，也会写入默认值。若处理结果时发生异常，它会写入一个以 `failed_` 开头的 name，并把错误放进 statement 和 method。这个 fallback 的意义不是把失败伪装成方法，而是让 Idea 卡留下“方法开发失败”的可观察痕迹。

## 第三十章　方法阶段的反思：同一盏灯照向更近的裂缝

方法开发完成后，状态回到 `REFLECTING`。这次 `_run_reflection_phase` 仍然读取当前迭代 Idea，但由于 `method_details` 已经存在，ReflectionAgent 使用方法系统提示，只返回 `critiques`。OrchestrationAgent 把这些批评写入 `idea.method_critiques`，而不是早期的 `idea.critiques`。

这两个列表的差别不是名字装饰。`critiques` 讨论一个方向是否合理，可能涉及新颖性、任务相关性和风险；`method_critiques` 讨论一个已经写出步骤的方案是否内部一致、是否有遗漏、是否需要改变对照。后续 RefinementAgent 只读取 `method_critiques` 和 `refine_evidence`，因此如果把方法批评写错地方，精炼阶段就会像没有收到意见一样工作。


方法阶段再次反思，但审讯对象已经从方向变成步骤。批评写入独立的 `method_critiques`，随后资料员为精炼阶段寻找更贴近实现的证据；这样一条证据链支持方向，另一条证据链约束动作。


这个阶段还会再次进入 EXTERNAL_DATA。`session.method_phase` 已经为真，ScholarAgent 返回的 evidence 被写进 `refine_evidence`。于是方法精炼拥有两条证据链：早期 evidence 支持方向，后期 refine_evidence 支持具体实现。

## 第三十一章　精炼：成功不等于一定得到一份新文本

`_run_refinement_phase` 先取当前迭代的 Idea，再按 top IDs 过滤。如果没有活跃 Idea，它直接把 Session 置为 `COMPLETED`；如果没有 refinement Agent，也记录 warning 并完成。这说明精炼是可选的收束器，而不是让 Discovery 进入 completed 的唯一门槛。

每个 Idea 在 semaphore 下执行。它先把 Idea 转成字典，读取 `method_details`；如果为空或所有值都是空，返回 `(idea, None, "invalid")`，不调用模型。有效 Idea 才把 goal、hypothesis 和 `literature=idea.refine_evidence` 传给 RefinementAgent。结果中的 `refined_method` 写回 `idea.refined_method_details`；空结果只记录 warning；异常被隔离，其他 Idea 仍可完成。


精炼员只接收确实有方法内容的卡片。有效结果写入精炼方法；空方法直接跳过，单个候选失败不拖走其他候选。精炼角色在服务异常时可以返回原方法并附错误标记，因此“有精炼字段”不等于“精炼成功”。


RefinementAgent 自己还有一个宽容的策略：模型调用异常时，它返回原始 `method_details`，并在 metadata 里写入 error。这和 OrchestrationAgent 对任务异常的隔离叠加在一起，形成一种“保留最后可用方法，但明确它没有被成功精炼”的结果。读者看到 `refined_method_details` 时仍应检查旁边的 metadata 或日志，不能把存在字段当成精炼成功的证明。

## 第三十二章　一个 Session 的完整走廊

把前面的房间连起来，可以得到一条更贴近代码的走廊。Session 创建后是 INITIAL；`run_session` 发现 INITIAL 就先转成 GENERATING。每次循环执行当前 phase，调用 `memory_manager.store_session`，如果状态变成 AWAITING_FEEDBACK 就停下，把控制权交给外部驾驶员。


完整走廊的核心节奏是：建立、生成、反思、查证、演化、排序、等待；达到内部上限后进入方法开发、方法反思、精炼证据和收束。每个箭头都由一个状态转移和一批可观察字段支撑，不能只凭概念图理解。


这张走廊有一处和理想化流程图不同：`RANKING` 在每次排序后都把状态转成 `AWAITING_FEEDBACK`，除非是在 method_phase 且后续逻辑另有设置。外层 `IdeaGenerator` 负责看到停靠点后注入反馈，再触发 Session 继续。流程图的箭头不是静态设计稿，而是代码中 `_update_session_state` 的真实调用顺序。

## 第三十三章　谁能看到什么：上下文不是全景摄像机

同一个 Session 中，所有 Idea 都在 `session.ideas` 列表里，但每个 Agent 的输入并不自动包含全部内容。生成员得到 Task、反馈、轮次和可选论文；反思员得到单个 Idea；ScholarAgent 得到单个 Idea 和目标；演化员得到父 Idea 的批评与证据；排序员得到当前迭代的整批候选；方法开发员得到 top Idea、证据上下文和 baseline_summary；精炼员得到 method_details、method_critiques 和 refine_evidence。


上下文按角色裁剪。生成员看任务与反馈，反思员看一张卡，排序员看一批卡，方法员看证据与基线，精炼员看方法与精炼证据；长期记忆只有在被检索并嵌入的地方才真正可见。


这张上下文表解释了为什么“长期记忆检索到了一个相似 Idea”并不代表所有 Agent 都会看到它。记忆只有在角色实现里被取出并嵌入 prompt，或者在阶段编排里被写入 context，才会影响模型。隐式可见性是调试的敌人；显式 context 是可测试的边界。

## 第三十四章　并发：速度之外还有归属关系

Discovery 中至少有三类并发上限：模型阶段的 `MAX_CONCURRENT_LLM_TASKS`，搜索阶段的 `MAX_CONCURRENT_SEARCH_TASKS`，实验阶段的 `max_parallel_experiments` 与 GPU allocator semaphore。它们作用在不同资源上，不应被一个全局数字替换。

反思、演化、方法开发和精炼通常共用模型请求的并发信号量；外部数据使用搜索专用的信号量；实验 Runner 在普通配置下保持串行，在显式并行配置下才开启工作台并行。GPU allocator 再为每个实验分配 GPU 环境，确保实验槽位数量不会直接等于 GPU 数量。


并发控制分三层：模型请求、搜索请求、实验工作台。它们共享“不要超卖资源”的原则，却各有计数器和失败语义；实验完成顺序只是事件顺序，不能被误读成结果排名。


并发还有一个数据归属问题。反思任务按 `ideas` 顺序收回结果，演化任务把每个 task 返回的子列表按任务列表顺序展开，实验并行模式则按完成顺序 append 结果。实验结果列表的顺序不应被解释为排名；真正的排序键是 Idea 名称、成功字段和性能字段。

---

# 第五幕　记忆把一轮的余温带到下一轮

## 第三十五章　会话记忆和长期记忆是两只不同的抽屉

会话记忆回答“从哪里继续”。它由 `MemoryManager` 保存 `WorkflowSession`，包括状态、Idea、计数、反馈和时间。长期记忆回答“过去哪些想法和实验值得参考”。它包含 Task Memory、Online Memory、IdeaGraph、ExperienceGenerator 和 PromptEvolver。二者都叫 memory，却不能互相替代。

`OrchestrationAgent.run_session` 每完成一个 phase 都调用 `memory_manager.store_session(session)`；进入 completed 后再保存一次带 `completed_at` 的版本；异常时也保存 `ERROR` 和 error 文本。长期记忆则通常在一轮实验结束后被外层 `_generate_experiences_for_round` 调用，读取已经写完的 `ideas.json` 和 notes。


会话记忆保存“从哪里继续”，长期记忆保存“过去什么值得参考”。前者每个阶段都要写，后者在轮末读取已完成的想法和实验；长期记忆失效可以降级，会话记忆失效则必须提高警惕。


如果长期记忆不可用，IdeaGenerator 仍然可以生成想法；如果会话记忆不可用，Session 可能无法可靠恢复。这个优先级决定了故障处理：长期记忆失败通常 warning 后继续，会话持久化失败则应更严肃地记录并阻止假装完成。

## 第三十六章　Task Memory：相似案例先被筛出来，再交给角色

配置中的 Task Memory 使用 `memory_dir` 保存短期实验记录，`top_k` 控制检索数量，`alpha` 控制关键词与语义检索的混合权重，`include_details` 决定是否返回完整细节，`embedding_mode` 决定用 title、description、method 或 full 哪一部分构造检索文本。

在 GenerationAgent 和 EvolutionAgent 中，memory retriever 可以查找过去类似的成功或失败案例。生成阶段还支持过滤与失败尝试相似的候选，并在最多两次再生成尝试后返回剩余结果。这里的“过滤”不是删除历史，而是阻止当前候选无声地重复已知失败模式。


任务记忆先筛相似案例，再把带来源的指导交给角色。它可以提醒某条路曾经失败，却不能替当前任务下结论；过滤重复失败是当前候选的防线，不是删除历史的橡皮擦。


检索结果只是一种指导。它必须带来源和相似理由，避免模型把过去案例当成当前任务的事实。fresh 模式也可以读取 Task Memory，因为 fresh 只改变代码 baseline，不会自动抹掉记忆抽屉。

## 第三十七章　IdeaGraph：历史想法在墙上长出关系线

IdeaGenerator 初始化 IdeaGraph 时，默认把任务级共享的 `base_output_dir` 作为工作目录，把任务名作为 namespace，把 similarity threshold 设为 0.7，并把统一运行时传给图。它随后扫描历史 Launch/session 中的 `ideas.json`，也兼容旧结构的 `session_*/ideas.json` 和 `ideas_*.json`。

加载一个文件时，代码接受列表格式或字典格式；字典优先取 `hypotheses`，找不到再取 `ideas`。如果 Idea 没有 id，但有 name，就用 name；两者都没有就生成 `idea_<loaded_count>`。每张卡都通过 `add_idea_node` 放入图中，之后可以检索相似 Idea、统计节点边数量、在节点数达到三时用 Louvain 聚类。


IdeaGraph 把历史卡片放到一面有关系线的墙上。它兼容几种旧文件形状，缺少编号时补上稳定的替代身份，节点足够多时才做聚类；它帮助看见邻近方向，却不替排序器宣布冠军。


IdeaGraph 不决定 `top_ideas`，也不替代 RankingAgent。它是搜索空间的地图：告诉生成员某个方向附近已经有多少节点，告诉 PromptEvolver 哪些簇经常被探索，帮助避免“换个标题再提出同一个机制”。

## 第三十八章　提示演化：修改 prompt 以前先留下备份

`IdeaGenerator.load_task` 每轮都会检查长期记忆配置中的 `evolution_interval`。只有 `round_num > 1` 且 `(round_num - 1) % evolution_interval == 0` 时，才计划提示演化。需要演化时，系统确认 `experience_library.json` 存在、长期记忆可用且 PromptEvolver 可导入，然后把当前 prompt 复制成 `prompt_backup_round{round_num}.json`，再调用 `evolve_prompt`，输出路径仍指向当前 prompt 文件。


提示演化遵守“先备份、后替换”。到达周期且经验库可用时，当前提示先复制成轮次备份，再生成新版本；演化失败就沿用旧提示。每次替换都应该能回答：哪一轮、依据什么经验、改变了什么。


这里的备份是机制的一部分，不是便利脚本。提示演化改变了下一轮的输入条件，如果没有旧版本，恢复时无法解释“这一轮为什么突然强调某种失败模式”。演化失败时日志写 warning，继续使用原始 prompt；这再次说明长期记忆增强主流程，但不拥有任务目标的最终权力。

## 第三十九章　经验生成：失败可以被提炼，但不能被抹掉

一轮实验结束后，`_generate_experiences_for_round` 先确认 memory 不为空，尝试导入 `ExperienceGenerator`；导入失败就记录“long memory not available”并返回 False。它从 `args.prompt_path` 读取 domain，默认值是 `machine learning`；再打开当前 Session 目录的 `ideas.json` 和所有 notes，把它们加载进 MemoryModule。

如果 memory summary 显示确实有实验，才创建 ExperienceGenerator，并从外层同步入口启动经验生成任务。结果里有 `new_experiences` 和 `updated_library`，日志记录新增经验数和经验库总数。没有实验时，它跳过经验生成，避免把只有想法没有现实检验的材料写成经验。


经验生成只在确实有实验材料时启动。它读取想法、笔记和指标，把成功与失败进行对比，再以新增或更新的方式写入经验库；没有实验就不把推测升格为经验，旧失败也不被擦掉。


经验生成器内部可以做对比学习：先评估每个 Idea 的 run 改进，再做 Idea 之间的 pairwise contrastive analysis，最后综合成功和失败模式。它还会用 ADD、UPDATE、DELETE、NONE 等操作把新经验合并进现有经验库。故事里的书记员不会把失败页撕掉；系统只把失败转译为下一轮的检索和提示线索。

# 第六幕　想法走出会话，进入可以被证伪的工作台

## 第四十章　从候选卡到实验委托单

当 Session 终于选出 top ideas，工坊里会出现一种短暂的错觉：好像研究已经完成了。其实这只是从“我们认为它值得尝试”走向“我们愿意让它接受现实检查”的门槛。排在前面的 Idea 仍然可能只有一个漂亮的名字、一段合理的描述和一条尚未被运行验证的推理。实验阶段要做的第一件事，就是把这种含有不确定性的卡片翻译成一张可以交给外部执行器的委托单。

委托单有两个来源。正常路径里，`IdeaGenerator` 从 MAS 会话拿到 `refined_method_details`，把它们整理成实验器能够识别的候选列表；跳过想法生成的路径则直接读取用户提供的 Idea 文件。如果文件是带有 `hypotheses` 和 `top_hypotheses` 的完整会话快照，系统只挑出被选中的编号；如果文件本身就是一个列表，就把列表当作已经筛过的候选。两种入口看起来不同，实验器收到的都应该是“名称、描述、方法和可选的预期结果”这组最小语义。

这里的对齐动作很容易被忽略。编排器不会把 Idea 的全部历史塞进工作台，也不会把模型内部的推理当作代码修改指令。它从优先级最高的细节层取名称和方法；如果精炼层为空，再退回方法层；如果两者都没有，才使用较早的标题、描述和内容字段。退回并不意味着缺失可以忽略，而是让失败的候选仍然能以可观察的方式抵达实验边界，随后被工作台明确拒绝或记录为失败。

可以把这一步理解成三张卡片的合并：第一张是“为什么要做”，第二张是“准备怎么做”，第三张是“如何判断做成了”。前两张来自 Idea，第三张通常要从基线目录里的 `experiment.py`、`run_0/final_info.json` 和任务本身的指标约定中确认。如果第三张卡没有内容，实验也许仍能启动，但结果不能被解释成改善。Discovery 不会替执行器创造不存在的评价标准。

委托单还会携带 Session 身份。这个身份让实验目录落在正确的 `session_*` 子目录，并让在线记忆保存时能找到同一会话的轨迹文件。若这一联系丢失，实验结果仍可能被写到磁盘，却无法回答“是哪一轮、哪一个 Idea、基于哪一份反馈得出的”。因此，Session ID 不是日志里的装饰字符串，而是候选从语言空间走向代码空间的接驳器。

## 第四十一章　复制一间不会污染原作的房间

实验开始前，ExperimentRunner 为每个候选建立独立工作区。它用时间标记和 Idea 名称组成候选目录名，把当前 baseline 目录复制进去，再确认工作台里存在 `experiment.py`。复制是一个有意的物理动作：外部后端可能修改主代码、创建新的运行目录、生成图表，甚至在失败时留下半截文件。若它直接在原任务目录里工作，一次探索就会改变下一次探索的起点，所有比较都会失去意义。

普通任务的工作台以代码为中心。基线中的 `code/`、实验脚本以及已有的运行记录被带入候选目录；如果基线缺少必要的 `experiment.py`，系统在开始调用后端以前就报出缺失，而不是让模型在半空中猜测如何运行。科学任务的工作台则多一层语义：除了代码，还要保留 `outputs/`、`report/` 以及数据和核对清单能够被脚本找到的相对路径。科学任务的“可运行”不仅意味着程序能启动，还意味着生成的中间产物和报告仍然处在任务约定的家里。

复制过程中有两个容易混淆的目录。候选根目录是外部后端可以改写的临时工坊；其中的 `run_0/` 是开始实验前留下的基线影子。候选根目录里的主代码代表“当前这一候选可能改变成什么样”，`run_0/` 里的代码和指标代表“比较时我们以什么为零点”。两者都存在，才能在实验结束后解释改动的来源。

工作台还会写一份 `notes.txt`。它不是论文，也不是模型日志，而是给未来读者的门牌：候选名称、标题、描述、方法，以及从基线开始的记录。后来每个运行的结果和异常都会继续附在这份工作台周围。即使外部后端完全失败，目录仍然应该告诉人们“它试图验证什么”，而不是留下一个没有名字的临时目录。

如果同一时间两个候选生成了同名目录，系统宁愿抛出目录已存在的错误，也不会静默覆盖旧工作台。覆盖会把恢复线索和失败证据一并抹掉。时间戳提供了大部分唯一性，显式的存在性检查则是最后一道防线。

## 第四十二章　`run_0` 不是第一次失败，而是测量的零点

进入工作台后，实验器把基线的 `experiment.py` 和 `final_info.json` 复制到 `run_0`。这个编号有一种刻板的命运：它看起来像“第一次尝试”，实际上它是没有候选改动的参照。外部后端从 `run_1` 开始工作，后续还可以有 `run_2`、`run_3`，数量由实验配置和后端策略决定。哪怕后端最后只成功了一次，`run_0` 仍然要存在，因为改善率必须有分母。

一次运行可能只改一个文件，也可能先修改训练脚本，再调整数据处理，最后重新运行评估。对 Discovery 来说，重要的不是它在中间做了多少动作，而是每个 `run_N` 是否留下了可以读取的最终信息。执行器会从较新的运行开始寻找有效的 `final_info.json`；若最新运行没有指标，就向前查找最近一个有指标的运行。这样，最后一次命令失败并不会自动抹掉此前已经得到的可比较结果，但失败本身仍要留在日志和轨迹里。

“成功”也有两个层次。后端层面的成功表示它完成了自己承诺的执行流程，例如修改代码、运行实验并返回；测量层面的成功则要求结果目录里存在可解析的指标。如果外部程序退出码为零却没有写出 `final_info.json`，Discovery 可以记录后端成功，但性能字段会是空的或无法计算，不能把“完成了命令”写成“取得了改善”。

配置中的最大运行次数控制后端愿意尝试多少次，而不是保证一定产生多少个 `run_N`。超时、模型主动结束、脚本持续报错，都会让实际运行数少于上限。对读者来说，`max_runs` 是机会的上限，`run_0` 是比较的起点，真实的 `run_N` 文件才是发生过的证据。

某些后端还支持 MCTS 一类的搜索式执行。此时外部执行器可能在多个候选修改之间探索和回退，工作台的目录结构仍然遵循同一份合同：基线保存于 `run_0`，成功的尝试拥有自己的运行记录，最后的性能从可解析结果中计算。Discovery 不把后端内部的搜索树当作自己的状态机，它只接收一个可追溯的结果边界。

## 第四十三章　三个后端，三种脾气，一张结果合同

实验器目前可以把候选交给 OpenHands、Codex 或 Qwen Code 一类的后端。它们的启动方式、提示词风格和工具生态不同，但在 ExperimentRunner 的外面被压成同一种节奏：准备目录，启动执行，监控过程，关闭日志，返回成功标志和工作台位置。

Codex 后端通常获得完整的任务类型上下文。普通任务需要知道代码在哪、基线指标在哪；科学任务还会把 `task_info.json` 和可用的核对清单传入，让执行者不把“跑通程序”误认为“完成复现”。它可以使用统一模型运行时，也可以通过配置选择 MCTS 路径；无论哪条路径，GPU 分配和日志生命周期由 ExperimentRunner 负责。

OpenHands 的工作方式更像一个带有挂载目录的工人。启动前要确认配置中允许哪些路径被挂载、服务地址如何找到；缺少挂载配置并不一定立即失败，但会留下 warning，因为后端可能无法看到任务需要的文件。Discovery 只记录它被怎样配置，不替 OpenHands 猜测一个安全的工作目录。

Qwen Code 与 Codex 共享许多实验语义，却有自己独立的适配入口。它同样可以按最大运行次数尝试、按 GPU 环境执行、写入同一类工作台和结果字段。后端选择由 `exp_backend` 决定，未知值会在单候选执行时被明确拒绝。这样，换后端不会改变候选的身份和比较口径。

结果合同中最关键的是五件事：候选名称、是否成功、工作台位置、使用的 GPU 信息、性能对象。失败时还要带错误文字；成功但没有可比较指标时，性能对象可以为空，但不能伪造零改善。外层 `_main` 只依赖这份合同来统计成功数、寻找最佳候选和构造最终摘要。

## 第四十四章　资源分配的门口：GPU、并行槽位和进度观察

当多个候选同时进入工作台，真正稀缺的往往不是目录，而是 GPU、模型请求额度和外部进程。ExperimentRunner 先让 GPU allocator 分配环境，再调用后端；分配器用自己的信号量限制同时占用的资源。配置允许并行，不代表系统可以无限并行，实际可运行数量还受可用 GPU 数量和每个实验需要的 GPU 份额影响。

默认配置倾向于串行。串行不是退化模式，而是一种可解释的基线：候选依次运行，日志顺序和工作台创建顺序一致，旧版行为也能保持。只有当并发数或 GPU 配额明确改变时，Runner 才会使用线程池提交多个实验。线程池的完成顺序可能与提交顺序不同，因此结果列表中的位置不能被当成优先级。

每个候选还有独立的进度观察器。它定期查看工作台里是否出现新的运行、日志或最终信息，并把可读状态写入日志。观察器不是实验本身，停止观察器也不等于杀掉外部后端；执行结束时，无论成功、失败还是异常，都要进入 finally 路径关闭观察器和日志文件，避免后台线程继续盯着已经结束的工作台。

资源失败与研究失败要分开。GPU 分配不到、后端服务不可达、模型凭据缺失，属于执行环境问题；候选代码跑通但指标没有改善，属于研究结果问题。两者都可能让 `success` 为假，但错误位置、修复方法和下一轮是否应该继续都不同。结果对象保留错误文本，日志保留更长的上下文，正是为了不把不同性质的失败压成一个“失败了”。

## 第四十五章　改善率如何从一堆数字里长出来

实验器不会要求所有任务使用同一种指标名。它先从基线 `run_0/final_info.json` 读出指标，再从候选工作台里寻找最近一个包含有效指标的运行；只比较两边都存在的字段。字符串形式的数字会尝试转为数值，无法转换的值被跳过；基线为零的指标不计算相对改善率，以免产生没有意义的除法。

对于每个可比较指标，系统计算“当前值减去基线值，再除以基线绝对值”的百分比。指标可能是准确率、损失、召回率或任务自定义的量，因此这个公式本身并不知道“越大越好”还是“越小越好”。Discovery 当前把数值变化当作改善率候选，真正的科学解释仍然依赖任务的指标约定和方法报告。读者不能只看到正号就断言研究成功。

总体改善率是各个可比较指标改善率的平均值。如果没有任何共同的可用指标，总体改善率记为零，但这不是“没有变化”，而是“没有足够证据计算变化”。这个区别很重要：在增量模式下，系统会从成功结果中选择总体改善率最高者；一个缺指标的结果不应凭空成为接力点。

性能对象同时保存基线指标、当前指标、逐指标改善率和总体值。它像一张小型审计表：读者可以回到 `final_info.json` 检查原始数字，也可以看到系统为什么得出某个总体值。日志中的 `+x.xx%` 只是面向人的摘要，真正用于比较的是结构化字段。

如果候选后端返回成功，但当前运行没有有效指标，工作台仍可用于诊断，候选结果也仍可计入“执行完成”。外层汇总会把成功状态和性能可用性分开看；这使得“代码改动成功但评估缺失”不会被误写成“取得了正收益”。

## 第四十六章　候选结果被谁看见，又被谁忽略

单候选完成后，ExperimentRunner 先生成一个轻量结果，交给外层统计；如果在线记忆可用且实验成功，它再把候选的名称、方法、分数、理由、证据和参考资料送进 `memory_saver`。在线记忆保存失败只记录 warning，不回滚已经完成的实验，因为记忆是增强层，工作台才是这次运行的事实层。

保存记忆时，系统还会尝试找到同一 Session 目录下的 `traj.json`。这条轨迹把模型和工具曾经做过的动作串起来，使未来的经验生成器不必只看最终指标。如果轨迹不存在，保存器仍可以接收 Idea 和结果，但日志会说明缺少轨迹。缺失轨迹不能被补成一段虚构推理。

外层 Round 看到的结果通常只有“候选名、成功、错误、工作台、性能”。Session 看到的是更丰富的 Idea 卡片；长期记忆看到的是被筛选后的成功与失败样本；最终摘要则把轮次级结果压缩成可以恢复的结构。不同观察者看到不同切片，不代表事实不一致，而是每个层级都只拿自己需要的粒度。

报告模式是另一条旁路。它不调用实验后端，而是把 Idea 的名称、标题、描述、方法、预期结果和限制写成 `report.md`。报告生成失败可以让这一候选失败，但不会影响同一轮其他候选的报告；最终摘要仍然使用同一套成功数和失败数语义。它是 Discovery 的一种输出方式，不是 PaperOrchestra 的章节编排。

## 第四十七章　挑出接力棒：最佳结果与增量基线

一轮结束时，增量模式要回答一个朴素问题：下一轮从哪一份代码开始？系统先看成功结果，再比较总体改善率；它不会因为某个候选运行得更久、日志更多或名字更响亮就偏爱它。若一轮没有成功结果，接力棒留在原处，下一轮仍从旧基线出发。

找到最佳结果只是第一步。`_update_baseline_for_incremental` 还要在最佳工作台里找最近的有效运行，把它的 `final_info.json` 写入新的 `run_0`，把运行里的 `code/` 复制回当前基线的 `code/`，并同步更新 `run_0/code/` 的备份。指标和代码必须一起移动，否则下一轮会拿新指标对比旧代码，改善率就失去意义。

科学任务还要搬运 `outputs/` 与 `report/`。这些目录不是华丽的附件，而是代码运行后留下的状态：图表、分析表、复现报告和后续检查可能都依赖它们。只复制代码会让下一轮看见一份“会运行但没有上下文”的半任务。普通任务没有这两个额外目录，就保持代码和指标的双轨更新。

基线更新的每一步都有可能失败。没有运行目录、运行目录里没有有效的最终信息、代码目录无法复制、报告目录权限异常，都会让函数返回失败或记录 warning。外层不应把一次更新失败伪装成“下一轮已经采用最佳结果”；日志和摘要中的最佳路径要与实际文件状态一致。

增量模式的故事因此不是“模型越来越聪明”，而是“起跑线被一轮轮前移”。每次前移都必须有一名候选、一组指标、一套代码和一条日志作为凭据。没有凭据的跃迁只是叙事，不是实验流程。

## 第四十八章　fresh 不是清空，incremental 也不是无条件继承

fresh 模式每轮都从原始任务目录建立工作台。它适合检验不同轮次是否在同一条起跑线上探索，也适合需要严格独立重复的实验。上一轮的成功代码不会自动污染下一轮的 `base_code_dir`，但长期记忆和提示演化仍可能把过去的经验带入生成阶段。代码基线独立，不等于思想历史被清空。

incremental 模式在第二轮以后使用当前保存的最佳代码路径，同时仍然使用原任务的 prompt 和任务身份。这个分离很关键：代码可以继承，研究问题不能在文件复制中悄悄改变。提示的变化只能由明确的提示演化过程产生，背景、约束和任务类型仍由 Launch 快照和当前任务定义共同约束。

恢复时，若摘要里已有最佳代码路径，外层会先把它作为接力棒；若摘要只记录了轮数而没有可靠路径，就退回原任务目录。旧摘要提供事实线索，当前文件系统提供最终验证。路径不再存在时，恢复不能仅凭字符串继续，它要记录降级原因或在需要时停止。

skip idea generation 让用户把一份已经整理过的 Idea 文件直接送进单轮实验或报告流程。它不是 incremental 的缩写，也不是跳过所有验证；工作台仍然需要基线、运行记录和结果合同。这个开关只改变候选从哪里来，不改变实验如何证明自己做过什么。

## 第四十九章　科学任务的第二层工作台

普通自动任务通常把“改代码、跑实验、比较指标”作为主要闭环。科学任务在它之外还带着一层研究材料：任务说明、数据清单、核对清单、输出目录和报告目录。它们构成了一种更严格的环境：程序即使返回成功，也可能没有满足清单中的关键条目。

因此，科学任务的委托单会把原始任务信息和核对清单再次传给后端。执行者可以据此安排输出、生成报告、核对图片和表格。Discovery 不在入口把清单判成通过或失败，它把清单当作实验上下文，让后端的运行结果和后续报告有材料可对照。

科学任务的 baseline 更新会同步中间产物和报告。比如第一轮的最佳代码同时生成了更完整的图表，第二轮就应该从这套图表和代码一起出发；如果只带走代码，第二轮的报告可能引用失效路径，最终结果看起来比第一轮更差，实际却只是上下文被剪掉了。

科学任务的失败也更细。代码启动失败是执行失败，指标缺失是测量失败，清单项未满足是任务验收失败。三个层次可以同时发生，结果对象不一定能完全表达它们，因此 notes、日志、清单输出和报告共同构成证据。全景阅读必须看这些层次如何叠在一起，而不是只看一个布尔值。

## 第五十章　轮末的封存：一轮结束不等于事实消失

当候选结果全部回收，外层先把成功数和失败数写进轮次记录，再触发经验生成，最后才准备下一轮的基线。顺序让经验生成器读到完整的想法和实验材料，也让下一轮的提示演化看到刚刚发生的成功与失败。若把经验生成放在结果写入之前，未来的提示可能依据一份尚未完成的记忆库改变方向。

每轮至少会留下 Session 目录、候选工作台、运行目录、日志、笔记和结构化结果。轮次记录只保存对恢复有用的摘要，不把所有日志复制一遍。这样做既避免 `discovery_summary.json` 变成巨型转储，也让读者知道去哪里寻找更细的证据。

在最终轮之后，系统汇总所有轮次的数量、Session 列表、总候选数、成功数和失败数；增量模式还会写最终最佳代码路径与总体改善率，实验模式会写后端和模型信息。摘要是给机器恢复的，也是给人复盘的，因此字段应描述事实而不是表达感想。

Discovery 的终点在这里变得清晰：摘要写下最后一轮的事实，经验库可以继续被下一次运行读取，论文编排或其他消费者可以另行决定如何使用这些材料。本书到此停下，是为了让发现的边界保持独立、可重放、可审计。

# 第七幕　Launch 既是文件夹，也是一个可被观察的承诺

## 第五十一章　从研究草稿到可启动的版本

在命令行入口之外，Discovery 还有一条面向应用界面的准备路径。用户先把研究文字和附件交给 Preparation，系统把它们保存成一个可以反复修改的草稿；草稿被标记为 dirty 时，不能直接开跑。用户确认保存以后，系统把草稿转换成结构化的 Execution Input，再为这份输入生成 revision。Launch 认领的不是“当前页面上的文字”，而是一个已经保存、转换成功且指纹匹配的 revision。

这个过程像实验室里的签字。研究文字是原材料，转换是把原材料整理成任务描述、领域、背景和约束，revision 是签字后的版本。只要原材料在签字后被改过，旧 revision 就不再代表当前内容；启动器会拒绝把过时版本当作新运行的依据。这样做看似多了一道门，却避免“用户看见的任务”和“后台真正运行的任务”不一致。

Conversion 失败也有明确的位置。系统会保留原始准备状态和失败信息，而不会生成一个半结构化的 revision。用户可以修订文字、再次转换，再用新的 revision 开始。Discovery 不让模型承担输入校验的最后责任，因为输入边界一旦模糊，后续所有实验和摘要都会失去可解释性。

当 revision 被选中时，Launch 会把研究文字、来源文件的公共描述和 content reference 一起写入输入快照。原始文件内容存放在私有的内容寻址区域，快照只保留摘要和哈希指针。于是运行既能复现当时使用的材料，又不需要把源文件字节暴露在每个公共状态响应里。

## 第五十二章　开始一次 Launch 之前的最后盘点

应用入口要求启动请求是一个对象，只接受准备身份和 revision 身份；多余字段会被拒绝。它还要求 `Idempotency-Key`，并限制长度，防止同一个按钮被重复点击时产生两个逻辑相同的 Launch。启动请求的有效身份由准备和 revision 组合而成，系统为它计算指纹，之后用指纹判断重试是不是同一件事。

启动前有四项检查。准备是否已经保存，revision 是否仍然属于当前准备，revision 是否包含结构化 Execution Input，最近一次 Conversion 是否成功且对应同一 revision。任何一项不成立，系统都停在接待台，不创建半个 Launch。这样，错误会尽早暴露在输入边界，而不是等到外部实验器启动后才变成难以定位的失败。

如果所有检查通过，系统会把当前模型身份、设置和 Discovery 运行偏好复制进 configuration snapshot。这份快照属于 Launch，不会随着应用设置下一次编辑而改变。恢复时，运行器读取的是 Launch 自己的模型目录和偏好；即使全局默认已经更新，旧 Launch 仍然沿用曾经承诺的配置。

启动响应可以被安全重放。第一次请求在锁内物化来源引用、写入快照、登记 Launch；同一幂等键和同一请求指纹再次到达时，系统返回原来的响应，而不重复创建资源。如果同一幂等键携带了不同 revision，指纹不一致会让请求失败，提醒调用者不能把一个键当作任意操作的通行证。

## 第五十三章　Launch 目录里每一层都在回答一个问题

Launch 根目录回答“这是哪一次研究运行”。里面的 prompt、配置快照和最终摘要回答“它当时看见什么、采用什么节奏、最后得到什么”。`session_*` 目录回答“某一轮的 MAS 会话如何推进”。候选工作台回答“一个方向如何被执行”。`run_0` 与 `run_N` 回答“指标从哪里来、修改经历了几次尝试”。

这几层不能随意合并。把所有 Session 的 Idea 都放在 Launch 根目录，恢复时就难以区分轮次；把候选工作台平铺在任务共享目录，增量基线就会混淆不同 Launch 的最佳代码；把最终摘要写进候选目录，外层就无法在没有打开每个候选的情况下判断整个运行是否结束。

目录名的可读性也有功能。时间戳帮助人从日志中定位工作台，Session 前缀让恢复扫描知道哪里是会话，`run_0` 的固定名称让指标比较拥有共同语言。可读名称不能替代结构化 ID，但可以减少人工复盘时的歧义。

共享目录另有职责。长期经验、历史 Idea 和任务级图谱放在 `base_output_dir`，它跨 Launch 共享；当前运行的 prompt、Session、实验和摘要放在 Launch 内。共享目录提供历史连续性，Launch 目录提供运行隔离。两者若混为一谈，fresh 模式会误删长期资料，incremental 模式会找错接力棒。

## 第五十四章　配置快照和提示快照的冻结时刻

模型目录、能力模型、外部后端和运行偏好都在启动时被物化。一个用户可能在上午选择某个模型，在下午修改全局设置；上午启动的 Launch 不应在恢复时突然使用下午的模型。快照让配置成为运行事实，而不是随时间漂移的环境状态。

提示快照同样有冻结时刻。普通任务的 `prompt.json` 在 Launch 建立时被复制，科学任务的合成提示在同一位置生成。后续提示演化可以产生新的版本，但旧版本必须有备份；恢复读取 Launch 的提示树，而不是盲目读取任务目录当前内容。

这并不意味着所有东西都冻结。外部实验工具、GPU 可用性和服务状态可能改变，长期记忆也可能继续增长。冻结的是“本次运行约定的输入与配置”，不是把外部世界伪装成静止。恢复报告应该同时说明哪些条件来自快照，哪些条件是重新获得的环境。

配置快照的另一个作用是诊断。出现模型输出异常时，读者可以从 Launch 找到实际的模型身份和设置；出现并发超限时，可以检查当时的实验和搜索限制；出现 baseline 漂移时，可以确认当时是 fresh 还是 incremental。没有快照，日志中的一行“使用默认配置”无法支撑复盘。

## 第五十五章　公共观察不是内部全景图

应用界面需要看到 Launch 的状态、允许的动作、时间线和可读产物，但不应该把源代码、私有文件绝对路径、运行器日志或模型凭据塞进公共响应。Discovery 的观察层因此对内部事实做一次投影：它保留状态和证据索引，隐藏不应传播的字节。

状态响应由服务器权威的 Launch store 生成。读取时，如果当前进程没有持有事务锁，系统先从磁盘加载索引，再做必要的 reconcile，把外部运行器已经发生的变化同步进观察状态，最后返回这一刻的快照。前端看到的不是某个旧内存对象，而是经过恢复和对账后的服务器判断。

公开观察还会拒绝无穷或非有限数字，避免一个异常指标污染排序、进度条或 JSON 消费者。没有意义的数字被转成可解释的缺失或错误，而不是在界面上显示一条看似精确的无限改善。科学系统的可观察性首先要保证“可相信”。

内部日志仍然存在，但它不等于公共时间线。日志可以包含后端命令、堆栈和调试路径；公共观察只需知道某一阶段开始、完成或失败，以及用户可以采取什么动作。两套记录有不同的读者和安全边界，不能为了方便直接复用。

## 第五十六章　产物浏览器只给你这一个 Launch 的门牌

产物列表从选定 Launch 的根目录生成。它把可预览的文件映射成相对路径、类型、大小和修改时间，不把绝对路径泄露出去。像 `report.md`、`summary.json` 这样的用户需要阅读的文件可以被列出；`runner.log` 一类包含内部执行细节的文件可以被隐藏或限制访问。

读取产物时，路径先经过规范化，再确认它仍然位于该 Launch 的根目录之下。`../record.json`、绝对路径和通过符号链接逃出根目录的请求都会被拒绝。这个检查不是 Web 层的附加装饰，而是 Discovery 产物合同的一部分：用户可以阅读证据，但不能借由一个路径参数读取任意服务器文件。

产物的“可预览”也有边界。Markdown 和 JSON 可以返回文本内容，二进制文件可以只提供类型和大小，特别大的文件可能只展示摘要。列表中的路径是公共相对路径，内部物理位置由服务器掌管。这样，未来即使 Launch 存储从本地目录迁移到对象存储，前端仍然使用同一个证据坐标系。

产物被绑定到 Launch ID，而不是绑定到任务名。两个 Launch 可以处理同一个任务，也可以有同名候选；读取时必须先选定 Launch，再在它的根目录内解析路径。测试会专门验证“拿 A Launch 的路径去读 B Launch”被拒绝，防止名字相似造成跨运行泄露。

## 第五十七章　状态、动作和终态的三角关系

一个 Launch 的公共状态不只是 `running` 或 `completed`。它还携带允许动作：等待中的运行可以被停止或恢复，完成的运行没有这些动作，失败的运行可能允许再次启动或只读查看。动作集合由服务器根据状态、运行器标记和快照完整性计算，而不是由前端自己猜。

停止和恢复都需要幂等键。停止一个已经停止的 Launch，不应再次发送杀进程命令；恢复一个正在恢复的 Launch，不应重复创建子进程。相同请求的重试返回相同的观察结果，状态变化只发生一次。状态机和幂等机制共同保证了网络抖动不会被解释成用户连续点击。

终态是只读的承诺。完成后，状态、摘要和公开产物仍可读取，但停止和恢复应返回冲突，而不是把一个已经封存的运行改成另一种历史。失败终态也应保留失败证据，让用户看到它为什么失败，而不是把错误清理成一个空白的可重试按钮。

允许动作的计算还会考虑恢复材料。如果摘要显示轮次已完成，但 Launch 配置快照缺失，服务器可以把它标成只读并提示材料不完整；如果运行器标记仍然存在而状态索引落后，reconcile 会先更新观察再决定动作。状态是事实的投影，不是一个脱离文件和进程的标签。

## 第五十八章　断点恢复的两条时间线

命令行恢复和应用恢复解决相邻但不同的问题。命令行的 `--resume` 关注 Discovery 外层轮次：它扫描 `discovery_summary.json`、Session 目录和最佳代码路径，决定从哪一轮继续。应用的 Resume 关注 Launch 生命周期：它把一个暂停、失败或服务重启后的 Launch 重新交给运行器，让公共状态继续向前。

两条时间线最终在 Launch 目录汇合，却不能互相冒充。应用层知道某个 Launch 是 running 还是 paused，但不替 MAS 恢复具体的 `WorkflowSession`；命令行层知道某一轮是否完成，却不替公共 API 判断前端允许哪个按钮。每层恢复自己负责的状态，再通过摘要、标记和目录结构交换事实。

服务重启时，内存中的等待不会被当作可恢复的事实。恢复依赖持久化的输入快照、配置快照、状态索引、运行器标记和 Session JSON。没有这些材料，系统宁愿把 Launch 标成需要人工处理，也不会凭一个“曾经在运行”的状态继续发送模型请求。

一个被中断的 MAS Session 可能停在等待反馈、外部资料或实验完成之前。恢复程序首先读取最后一次已保存的 Session；如果状态处在明确的等待点，它可以从该点继续；如果状态在错误房间且错误没有解决，恢复只能重试被允许的阶段，不能假装已经完成。每一步续跑都要追加新的观察块，原来的轨迹保持不动。

## 第五十九章　ResearchDraft 是时间线的缝线

当运行器、Agent 或后端产生一段值得保留的观察，它可以追加到 Launch 内的 manuscript 草稿。ResearchDraft 的核心不是排版，而是把多个来源的观察串成一条不会互相覆盖的时间线。每段文字写完以后插入一个明确的块边界，未来打开文件能分辨不同事件，而不是看到一整段无法归属的拼接文本。

并发追加时，二十个线程可以同时提交观察，但每个观察必须完整出现，不能把一个线程的开头和另一个线程的结尾交错。锁的作用是保护块的原子性，不是让观察按开始时间排序。真正的时间顺序仍应从事件字段、运行日志和候选编号判断。

CodexRunner 一类的执行器会把自己的调用参数、最后一条消息和 JSONL 事件记录写入 Draft。它只在进程成功结束且确实找到最终消息时返回；进程失败却输出了“看起来像成功”的文字，也要抛出失败。这个合同避免模型的最后一句礼貌话覆盖操作系统给出的失败信号。

Draft 可以被多个阶段使用，但它不是 `discovery_summary.json` 的替代品。Draft 记录过程，摘要记录可恢复事实；过程可以很长、包含重复和局部错误，摘要必须稳定、结构化、可被下一次启动器读取。把两者混成一个文件会让过程太重、事实太模糊。

## 第六十章　从暂停点继续，而不是从头再猜

一个好恢复故事应该能回答四个问题：上一次在哪里停，已经写下什么，接下来应该执行哪个阶段，哪些外部条件仍然有效。Session JSON 提供状态、Idea 和计数；Launch 摘要提供轮次与基线；配置快照提供模型和偏好；Draft 与日志提供停下前的上下文。

如果暂停发生在 `AWAITING_FEEDBACK`，恢复不应重新生成一批候选，而应等待反馈或读取离线反馈文件，再回到反思。若暂停发生在实验工作台，恢复器要先看外部进程是否仍在、最终信息是否已经出现，再决定等待、收割结果还是把它记为失败。没有这一步，重启很容易把同一个候选跑两遍并互相覆盖。

如果摘要显示 Round 1 完成、Round 2 有目录却没有完整结果，`_scan_completed_rounds` 只能把 Round 1 算作完成。目录存在不是成功的同义词，必须有轮次结果或可验证的摘要字段。正因为扫描严格，用户才可以在中断后安全地继续，而不必手工删除半成品。

## 第六十一章　输入快照和产物快照的相互照应

输入快照说“当时研究的是什么”，产物快照说“当时留下了什么”。前者包括研究文字、来源引用、Execution Input 和配置，后者包括摘要、Session、实验和报告。恢复时只读产物而不核对输入，可能把一份旧结果误套在新任务上；只读输入而不核对产物，又可能重复已经完成的工作。

指纹把两者连接起来。准备内容变更会改变 fingerprint，旧 revision 与当前准备不再匹配；来源文件用内容哈希寻址，Launch 记录它们在当时的引用；摘要里的任务目录和原始任务路径帮助命令行恢复确认代码基线。指纹不是加密意义上的秘密，而是用来发现“这不是同一份输入”的证据。

输入材料的物化也考虑清理。若某个来源在 Launch 建立过程中写入了私有存储，但随后快照构造失败，系统可以删除没有被其他 Launch 引用的内容 blob。清理不是为了省几兆空间，而是避免一个半成品 Launch 留下无法解释的孤儿来源。

## 第六十二章　失败类型的四层地图

第一层是输入失败：任务目录不存在、prompt 缺失、准备未保存、revision 过期、Conversion 失败。这一层的失败应该阻止运行启动，因为系统还没有一个可信的研究问题。

第二层是编排失败：Agent 缺失、状态没有处理者、Session 无法序列化、模型运行时无法建立。这些失败发生在想法加工尚未完成时，通常会把 Session 置为 `ERROR`，并保存错误上下文。

第三层是外部执行失败：搜索服务超时、后端进程退出、GPU 分配失败、运行器没有最终消息。它们可以只影响一个 Idea，也可以在共享资源不可用时影响整轮；结果对象和日志应该揭示影响范围。

第四层是科学结果失败：代码运行成功但指标不改善、指标缺失、核对清单未满足、输出报告不完整。这一层不一定需要让整个 Discovery 停止，因为失败本身是研究发现的一部分；它应该被标记、比较、写入经验，而不是被重新命名为异常。

这四层之所以要分开，是因为修复路径不同。输入失败需要改任务或准备，编排失败需要改配置或代码，外部执行失败需要恢复服务或调整资源，科学结果失败需要修改方法或接受负结果。一个总括的“失败”字段不足以指导下一步。

## 第六十三章　失败的候选为什么仍然值得保留

一张失败卡片有三种价值。它告诉我们某条方向没有通过现实检查；它告诉经验生成器哪些条件可能导致失败；它告诉未来的人工读者为什么另一个看似相似的方向值得谨慎。删除失败卡片会让下一轮的搜索空间虚假变干净，模型可能再次提出同一条路，只是换了一个名字。

保留失败不等于把失败当作成功。排序时失败候选不进入 top；增量基线只从成功且有可比较结果的候选中选择；最终摘要同时统计成功和失败；经验库在合并时可以更新一条“曾经失败”的经验，而不是把它改写成推荐。

失败工作台也有证据价值。`traceback.log`、notes、最后的运行目录和外部后端日志能够说明失败发生在哪一步。公共产物层可能隐藏敏感日志，但内部 Launch 仍应保留它们或至少保留可指向的位置。发现流程的严谨性不只体现在成功案例的漂亮曲线，也体现在失败案例没有被擦除。

## 第六十四章　可重放性不是让每次都得到同一个答案

Discovery 的可重放性首先要求重新找到同一组输入、配置和流程边界，而不是要求模型在概率采样下逐字复现。Prompt 快照、配置快照、任务类型、实验基线和 Session 状态让读者可以重建“这次为什么走了这条路”。模型响应可能不同，但差异能够被归因于输入、服务或随机性，而不是因为系统忘记了自己做过什么。

可重放还需要保持目录关系。候选的 `run_0` 必须来自它真正使用的 base code，增量模式前移后的代码和指标必须成对保存，科学任务的输出和报告不能在复制时分离。否则即使重新运行同一 Idea，比较的也不是同一个实验问题。

服务重启、线程并行和失败重试都会改变时间顺序。重放时不要把日志行号当作因果关系，而要依据 Session 状态、Idea 父子关系、运行目录和结构化时间字段。系统保存这些结构，正是为了让读者不必从一堆交错日志里猜故事。

## 第六十五章　从空目录开始的端到端回放

想象一个没有历史经验、没有旧 Launch 的空目录。用户准备研究文字和附件，保存后转换，得到第一份 revision；启动请求通过幂等校验，物化来源引用，写入配置和输入快照。命令行入口认出任务类型，建立 Launch，复制或生成 prompt，读取当前配置，决定第一轮的 baseline。

IdeaGenerator 建立 Interface 和 Session，背景调研可能成功也可能降级；生成员摊开候选，反思员标出风险，资料员补证据，演化员产生孩子，排序员选出 top ideas。状态和 Idea 被反复写入记忆，Draft 接住长观察，最后方法开发把候选变成可执行委托单。此时还没有任何实验指标，只有待验证的方案。

ExperimentRunner 为每个方案复制工作台，建立 `run_0`，选择后端和资源，执行一到多次尝试，读取最近有效的最终信息，计算逐指标和总体改善率。成功结果写入在线记忆，失败结果保留工作台和错误。轮次记录封存，经验生成器读取真正存在的实验材料，下一轮如果是 incremental 就把最佳代码和指标一起前移。

最后一轮不再寻找下一条接力棒。外层统计所有轮次和 Session，把实验后端、模式、数量、成功和失败写进 `discovery_summary.json`。应用层可以把摘要与报告列为公共产物，但不暴露私有运行器日志和源文件字节。整个回放没有依赖一段“模型说它完成了”的话，每个阶段都留下了可以核对的物证。

# 第八幕　把全景拆成可以检查的契约

## 第六十六章　准备区的三次盖章

面向用户的准备区不是一个简单的文本输入框。它至少经历三次盖章：第一次是草稿被保存，第二次是草稿被转换成结构化执行输入，第三次是这份输入被生成 revision 并与当前材料建立指纹关系。任何一枚章缺失，Launch 都没有资格进入运行队列。

保存盖章回答“用户是否明确把这一版交给系统”。转换盖章回答“系统能否把它解释成 Discovery 所需的字段”。revision 盖章回答“以后恢复时，哪一份输入才是被用户选中的版本”。这三件事分开，意味着用户可以在保存后继续修改，也意味着一次旧转换不会因为页面刷新而自动代表新内容。

附件也遵循同样的顺序。上传时记录文件名、大小和哈希，保存时把文件放到内容寻址的私有存储，转换和 revision 只引用它们。启动时重新确认引用存在；某个附件被删除或哈希不匹配，Launch 会在输入门口拒绝，而不是让模型在运行中发现数据缺口。

准备区会呈现 dirty 状态，提醒用户当前页面与已保存版本不同。这个状态不是前端的视觉效果，而是启动校验的一部分。即使有人绕过界面直接调用 API，服务器仍会比较当前准备指纹和 revision 指纹，保证“未保存修改”不会悄悄进入研究运行。

## 第六十七章　锁不是为了让系统变慢

启动、停止、恢复和产物读取都可能同时发生。DiscoveryLaunchStore 用事务锁把“加载磁盘、对账、修改索引、持久化响应”放在一个一致性边界里。锁内的代码不追求做完所有耗时工作，而是保证关键事实不会被两个请求交错写成互相矛盾的版本。

例如两个相同幂等键的启动请求同时到达，第一请求先确认准备和 revision，物化来源，登记 Launch；第二请求在锁内看到同一键已经有结果，就重放第一次响应。若没有这个锁，两个请求都可能通过“尚未存在”的检查，随后各自创建一个 Launch，用户只看到一次点击却得到两条运行。

来源物化还有一个清理窗口。假如第一请求已经写入一个新来源 blob，随后写配置快照时失败，锁保证清理动作可以判断这个 blob 是否已被其他 Launch 引用。没有锁，清理可能把第二个 Launch 正在使用的来源删除，造成一个很难在日志中还原的随机损坏。

锁的存在不意味着所有请求串行到最后一毫秒。外部运行器的长任务在锁外执行，状态变化通过标记和对账重新进入锁内。这样，系统既能保持文件索引的一致，又不让一个长时间实验阻塞用户查询其他 Launch 的状态。

## 第六十八章　幂等键背后的请求指纹

幂等键只说明“这组重试属于同一组意图”，不能单独说明意图是什么。Discovery 因此还计算请求指纹，把准备身份和 revision 身份按稳定顺序编码后哈希。相同键、相同指纹可以重放；相同键、不同指纹必须拒绝，因为这通常意味着调用方错误地复用了一个本应只代表一次操作的键。

停止和恢复的指纹只需要包含 Launch 身份，因为它们的目标已经由路径确定。启动的指纹则包含被选中的 revision，因为同一准备可以有多份历史版本。这个差异体现了“幂等不是一个全局开关”，而是对每种动作定义其不可变的意图。

重放返回的是原响应，而不是重新读取后生成一份看起来类似的新响应。原响应中可能有创建时间、Launch ID、状态和观察游标；保持它们不变，客户端才能把网络重试当作同一件事。状态随后发生变化时，新的查询才会得到新的观察快照。

## 第六十九章　运行器标记与服务器观察的对账

外部运行器有自己的生命周期：进程可能已经退出，日志可能已经写完，服务也可能在服务器不知道时重启。服务器索引不能永远相信自己上次写下的 `running`。每次需要生成状态观察时，DiscoveryLaunchStore 都可能重新读取磁盘和运行器标记，把“进程已完成但索引仍显示运行”的差异对账成最新状态。

对账不是重新执行任务。它只检查持久化的标记、心跳、摘要和已知产物，确认某个状态变化是否已经发生。若证据不足，状态保持保守，例如继续显示需要恢复，而不是猜测任务成功。宁可让用户多看一次“正在确认”，也不应把一个没有最终结果的运行写成 completed。

状态观察还会计算允许动作。对账发现进程已经结束且摘要完整，停止按钮消失；对账发现 Launch 仍有可恢复材料，恢复按钮保留；对账发现目录被破坏，状态进入需要处理。前端只展示服务器给出的动作，不把本地缓存的旧按钮当成授权。

## 第七十章　模型目录是每次运行的电路图

统一运行时不是把一个模型字符串传给所有地方。模型目录区分主文本模型、结构化输出能力、图像能力和嵌入能力，并记录它们的规范身份。Launch 开始时把目录物化成自己的快照，MAS 和实验器共享这一快照，避免一个阶段使用了不同于另一个阶段的模型。

这解释了为什么配置里可能同时出现用户界面的模型拼写和运行时的规范身份。前者服务于选择和显示，后者服务于适配器路由；两者在启动时被映射，之后以不可变的目录为准。恢复时如果只读取当前全局目录，就可能把同一 Launch 的前后两半接到不同模型上。

统一运行时提供文本、结构化 JSON、图像和嵌入等能力，但调用者不直接依赖 provider 客户端。Agent 只说“我要生成符合 schema 的候选”或“我要为这些文本求嵌入”，运行时负责解析能力、选适配器、执行请求和整理结果。这个深模块边界让模型替换不会穿透每个 Agent 的故事。

## 第七十一章　能力缺失时如何降级

有些阶段只需要读取已有 Idea 和摘要，不需要模型调用；有些阶段必须生成候选或运行后端。`_main` 因此延迟构造模型运行时，直到真正选择模型驱动的阶段。这样，用户可以在缺少凭据的环境里查看已完成 Launch，也可以对报告模式进行只读处理。

能力缺失不是同一种错误。缺少文本生成模型会阻止生成阶段；缺少搜索工具可以让外部资料阶段失败或返回空证据；缺少嵌入模型可能让长期记忆退回关键词检索；缺少实验后端则让候选执行失败。每种降级都要在日志和结果中标明，不能让用户以为系统默默换了一条等价路径。

运行时的适配器也要区分“请求失败”和“返回格式不合约”。网络错误说明外部服务没有给出结果，schema 校验失败说明服务给了结果但无法被当前阶段理解。前者通常可以重试或降级，后者需要检查提示、模型能力或解析器。错误分类越接近原因，下一次恢复越不容易重复同一条路。

## 第七十二章　测试不是流程之外的守门员

Discovery 的测试不是只验证函数返回值。它们把一组系统契约固定下来：启动必须拥有当前 revision，重复请求必须幂等，公共观察不能暴露源码字节，产物路径不能越界，失败 Launch 必须保留只读历史，运行时必须被注入到正确的后端。

测试中的临时目录模拟真实 Launch。它们创建 prompt、摘要、Session、候选工作台、`run_0` 和 `run_1`，然后通过入口、Facade 或 Runner 读取和修改。这样的测试比只 mock 一个函数更接近用户会遇到的边界，因为它会发现目录命名、文件复制和恢复扫描之间的缝隙。

一些测试故意写入“看起来像成功”的错误材料，例如进程失败却留下成功文本、最新运行没有指标、候选目录中存在过期报告。测试要求系统保留失败信号、选择最近的有效指标、避免用旧报告覆盖新事实。它们把经验中的坑变成可以持续运行的规则。

## 第七十三章　启动垂直切片测试了什么

垂直切片从准备区开始：提交研究文本和 CSV，检查草稿变 dirty，保存后变干净，转换得到执行输入，生成 revision，再用幂等键启动 Launch。它随后等待运行器完成，读取状态和产物，确认 `report.md` 与 `summary.json` 可以读到，最后验证终态不再允许停止或恢复。

这条测试的价值在于它跨越了多个边界，却不依赖真正的模型或外部实验。它用假的转换提供者和假的运行器，把用户可见的合同全部走一遍。只要某个环节把内部路径泄露到公共响应、把未保存 revision 误当作当前版本，垂直切片就会失败。

测试还验证冲突：同一准备和 revision 用不同幂等键再次启动时，服务器返回冲突，而不是再开一个进程。它验证产物读取的路径穿越被拒绝，验证状态终态的动作列表为空。于是“按钮应该如何表现”不再只是前端约定，而是服务端可执行的事实。

## 第七十四章　观察层测试的安全边界

公共观察测试会递归检查返回值，确保里面没有源文件字节、私有绝对路径或内部运行器输入。它还会用非有限数字和异常浮点值构造运行结果，确认状态投影不会把它们原样传播。观察层的目标不是隐藏所有错误，而是把错误以安全、稳定、可理解的形式呈现。

产物测试会先列出一个 Launch 的文件，再尝试读取另一个 Launch 的同名文件、`../` 路径、绝对路径和符号链接逃逸路径。只有选定根目录下的可预览文件能够成功返回。测试因此覆盖了“路径解析”和“Launch 身份绑定”两个不同问题。

失败运行也有专门的只读断言。运行器设置失败后，状态应转成 failed，历史和错误仍可查询，产物列表不应凭空消失；用户不能对一个已经失败的历史再发出会改变它的动作。这样，失败是可研究的对象，而不是服务端试图清理的垃圾。

## 第七十五章　Draft 测试守住了观察的连续性

ResearchDraft 测试首先验证重新打开同一个 Launch 不会覆盖已有文字，而是追加新的块。随后用多个线程同时追加观察，检查每段文字完整出现。这个测试表面上关注文件写入，实际守住的是“过程证据不会因为并发而失真”。

CodexRunner 的测试还检查命令行参数和输出最后消息的关系：工作目录、模型、沙箱策略、网络设置和跳过仓库检查都要被正确传入；最后消息缺失时不能把 JSONL 事件流当作最终回答；进程返回失败时，即使文本里出现“完成”，也必须抛出错误。

这些细节让 Draft 成为可靠的观察层。没有它们，后续读者可能把一个中途日志当成最终答案，把一段失败后的礼貌文字当成成功，或者在并发写入时看到拼接错乱的因果链。

## 第七十六章　实验器测试守住运行时的同一性

ExperimentRunner 的运行时测试会把一个假的 UnifiedModelRuntime 注入 Runner，再检查 Codex 或其他后端收到的正是这一个对象。它确保想法生成和实验执行不会各自偷偷构造不同的模型客户端，也确保 Launch 快照中的模型能力真正贯穿两个阶段。

实验 artifact 测试则让后端写出多个运行、最终指标、traceback 和过期摘要，检查 Discovery 是否只读取正确的最终信息、是否保留失败日志、是否不把源代码泄露到不该出现的产物。测试关注的不是某个模型答案，而是“结果目录如何证明发生过什么”。

并行实验测试会让 futures 按任意顺序完成，确认每个结果仍然归属于正确的 Idea。它不会要求结果列表按提交顺序排列，因为实现选择了按完成顺序回收；真正的归属由候选名称、工作台路径和性能字段共同确定。

## 第七十七章　把测试名称读成一份系统誓约

读测试名往往比读一段长实现更快理解边界。诸如“completed discovery can resume without opening a draft”“artifacts are bound to the selected launch”“failed launch is read-only history”“same runtime is shared between stages”这样的断言，都是 Discovery 不能轻易破坏的誓约。

这些誓约互相连接。只读历史要求失败证据仍然在目录里；产物绑定要求目录层次和 Launch ID 一致；共享运行时要求 `_main` 延迟构造但在需要时只构造一次；Durable resume 要求输入、配置和状态快照在进程重启后仍可被重建。

当未来有人修改实现时，最危险的不是某个函数变长，而是无意中改变这些关系。例如把公共观察直接换成内部字典、把结果列表重新排序后仍用位置解释、把配置改为每轮重新读取、把失败的工作台删掉。测试会在这些“看起来只是重构”的变化上发出警报。

# 第九幕　沿着一条真实运行的脚印再走一次

## 第七十八章　普通任务的第一夜

我们先跟随一个普通自动任务。任务目录里有 `prompt.json` 和 `code/`，没有 `task_info.json`。用户在命令行输入任务名，启动器把它补成 `tasks/` 下的目录，确认目录存在，再把任务类型记为 auto。这个判断没有惊动模型，却决定了后面工作台会以代码为中心，也决定参考代码路径默认指向任务目录里的 `code/`。

Launch 被安排在 `results/<task_name>/<timestamp>_launch`。原 prompt 被复制进去，配置从 YAML 或 JSON 读取，外层轮数和 loop mode 被确定。假设当前是 incremental，第一轮仍然从原始代码开始；因为没有恢复状态，最佳路径和最佳改善率都还没有历史值。日志写下这些事实，未来的人才能知道第一轮不是从某个看不见的旧实验开始。

IdeaGenerator 接过任务。它初始化 Interface、统一运行时和可选的长期记忆，加载历史 Idea 和 notes；如果长期记忆目录为空，主流程仍然继续。Session 建立后，生成员提出一组候选。反思员逐张卡片检查，资料员搜索文献，演化员在批评和证据上生成孩子，排序员把候选分批评分。

内层流程可能在等待反馈处停一次。自动脚本有离线反馈文件，就把文件内容追加到 Session，再触发反思；没有文件，驾驶员可以等待人工。反馈不会覆盖旧批评，而是带着时间、轮次和目标范围加入历史。第二次生成看到的是“用户后来强调了推理成本”，而不是一份被静默改写的初始任务。

达到内部上限后，top ideas 进入方法开发。方法卡完成、反思和精炼证据到位，候选被写进 Session 目录的 `ideas.json`。外层只取可实验的细节，ExperimentRunner 为每张卡片建一间复制的工作台。夜已经深了，研究才真正从语言转向代码。

## 第七十九章　普通任务的第二夜

候选工作台先复制原始代码，再创建 `run_0`。外部后端在根目录里看到 notes 和方法，在 `run_0` 里看到基线实验脚本与基线指标。它可以修改自己的 `code/`，也可以在 `run_1`、`run_2` 中重复尝试；原始任务目录不会被触碰。

假设第一个候选的后端执行了两次。`run_1` 修改了训练策略但没有写出最终指标，`run_2` 修复了脚本并写出一组指标。性能计算器从最新目录开始，跳过无效的 `run_1`，读取 `run_2` 与 `run_0` 的共同指标。另一个候选只运行到 `run_1` 就超时，工作台里有 traceback，但结果对象的成功标志为假。两个候选的时间长短都不影响排名。

所有候选收回后，外层把轮次记录写入内存。假设一个候选的总体改善率为正，另一个候选虽然运行成功却没有共同指标，第三个候选失败。最佳选择只能是第一个；第二个不能因为“成功”而成为基线，第三个更不可能成为基线。这个判断用的是结构化性能字段，而不是日志中的情绪词。

增量更新把第一候选最后一个有效运行的 code 复制到下一轮的 `code/`，把它的最终信息复制到新的 `run_0`，并保存同一份代码到 `run_0/code/`。下一轮的实验不再对比原始代码，而是对比这一份已经验证过一次的代码。与此同时，第一轮的失败工作台仍然留在 Session 目录，长期记忆也可以读取它。

第二轮会重新生成想法，除非使用 skip idea generation。它可以从 IdeaGraph 看到第一轮探索过的邻近方向，从经验库看到某种失败模式，但 prompt 仍然来自 Launch 的版本树。代码基线向前走，研究问题和输入证据保持可追溯，这就是 incremental 的真正含义。

## 第八十章　科学任务的一次长途复现

科学任务通常从一个更厚的目录出发。`task_info.json` 说明任务和数据，`target_study/checklist.json` 说明哪些结果需要核对，代码和报告目录则提供运行的物理空间。启动器先把这些材料翻译成合成 prompt，数据项变成背景，清单项变成约束；原始 JSON 仍然保留在任务目录里，作为实验执行时可以回看的源头。

第一轮生成的 Idea 不能只说“换一种网络结构”。它要在方法开发阶段说明数据如何进入程序、需要观察哪些输出、如何对照清单。ScholarAgent 的早期证据支持方向，方法阶段的 `refine_evidence` 支持具体步骤。这样，实验委托单既包含研究动机，也包含报告和图表需要的落点。

科学工作台复制代码、输出和报告的初始结构，`run_0` 保存当前基线的实验脚本与指标。后端执行时收到任务信息和清单上下文，知道生成图片、表格和报告不是可有可无的副作用。它可能成功运行却只写出部分输出，结果对象对此保持诚实；清单是否完全满足，要从报告和产物中继续核对。

如果第一候选生成了更好的图表和报告，增量更新会把 `outputs/` 和 `report/` 与代码一起带到新的基线。第二轮不会从一份空报告开始，也不会误读第一轮遗留的旧图。代码、指标、中间产物和报告共同组成科学任务的状态，少搬一件都可能改变问题本身。

最终摘要只保存轮次和结果概览，详细清单核对留在候选工作台和报告中。这样，摘要适合恢复和统计，报告适合科学阅读，日志适合诊断，三者各自承担一层证据。全景书若只写摘要字段，就会漏掉科学任务真正的验收面。

## 第八十一章　跳过想法生成的另一扇门

有时用户已经在外部会议中整理好一份 Idea 文件，不希望再调用 MAS。`--skip_idea_generation` 让外层只跑一轮，并从 `--idea_path` 读取候选。它会先确认文件存在，再判断它是完整的 `hypotheses` 结构还是简单列表；若是完整结构，只抽取 `top_hypotheses` 指定的候选，避免把所有草稿都送去实验。

这个入口跳过的是“产生和筛选想法”，不是“验证输入和实验”。外层仍然建立或恢复 Launch，仍然需要模型运行时给实验后端，仍然复制工作台、保存 `run_0`、计算性能、记录成功失败。这样，外部人工挑选的 Idea 仍然享受同一套基线和产物合同。

如果 Idea 文件路径里带有 `session_`，启动器会尝试从路径提取 Session 身份，使实验结果能回到原会话目录。提取不到时，结果仍可写入当前 Launch，但日志会缺少历史接驳信息。这个细节说明“跳过生成”不是脱离 Session，而是允许 Session 的产生方式从模型改成文件。

报告模式也可以使用这条门。ReportWriter 从精炼方法、普通方法或简单字段中抽取名称、标题、描述、方法、预期结果和限制，逐个建立报告目录。报告失败只影响当前 Idea，其他报告仍可生成；最终摘要仍然列出每个候选的成功或失败与报告路径。

## 第八十二章　反馈如何改变下一次灯光

全局反馈像挂在工坊中央的一盏灯：“所有方案都要降低显存占用。”它进入下一轮生成、反思和演化的共同上下文。局部反馈像贴在某张卡片上的便签：“这个候选的对照组不够”。它只应该影响目标 Idea 及其后代。反馈记录里有作用范围、轮次和时间，编排器据此选择送给每个角色的内容。

如果局部反馈的结构不符合预期，系统不能把它当作全局意见扩散。实现里会尝试按 Idea 身份筛选；筛选失败时，安全的结果是空反馈、warning 或明确错误，而不是让所有候选都承担一条只针对一个人的批评。反馈的范围和格式同样是系统契约。

反馈不能改写 Task。用户可以说“优先考虑成本”，但不能通过一条外部字符串让任务描述、领域或参考代码路径无声变化。若反馈与任务约束冲突，冲突应出现在历史和后续判断中，供人决定是修订准备输入还是让流程结束。

自动运行常把反馈文件作为离线控制面。文件读取失败、JSON 结构错误或反馈为空，都应留下可观察结果。自动驾驶的价值是减少等待，不是绕过验证；`AWAITING_FEEDBACK` 仍然是一个真实状态，反馈只是从门外递进来的事件。

## 第八十三章　并发时间线里的四种顺序

在反思阶段，任务创建顺序、模型完成顺序、写回顺序和日志顺序可能不同。系统通常按 Idea 列表创建任务，模型服务按可用资源完成，编排器按列表位置写回，日志则记录真实发生的时间。四种顺序各自有用，不能混成一条伪时间线。

演化阶段同样如此。父 Idea A 可能先返回三个孩子，父 Idea B 后返回一个孩子；编排器把任务结果按提交列表展开，子卡片的 `parent_id` 负责保留谱系。孩子在列表里的位置不等于它比另一个孩子更好，评分阶段会重新决定。

实验并行时，线程池按完成顺序收集结果。候选 B 先结束并不意味着它排在 A 前面；性能比较读取 `overall_improvement_rate`，增量选择重新扫描成功结果。日志中的 `[2/5]` 是提交编号，不是名次。

并发上限也不应合并成一只总信号灯。模型信道可以允许五个请求，搜索服务可能只允许三个，GPU allocator 还要根据设备数量动态限制实验。某层速度变快不等于其他层可以无条件跟随；分层限制让瓶颈和故障归属更清楚。

## 第八十四章　记忆的一年四季

一轮刚结束时，Session 记忆是最热的。它包含完整 Idea、状态和反馈，适合短期恢复；几轮之后，Task Memory 变得重要，它把相似任务的成功和失败筛出来；更久以后，IdeaGraph 和经验库提供结构上的地图，帮助生成员避开已经反复失败的方向。

这几类记忆有不同的衰减速度。会话记忆要精确到字段和状态，不能因为“过时”被随意删掉；任务记忆可以在检索时按相似度排序，只把最相关的若干案例交给角色；经验库可以合并更新，但每次 ADD、UPDATE、DELETE、NONE 都应有来源和理由。

长期记忆初始化失败时，IdeaGenerator 仍可工作，只是没有历史指导。在线记忆保存失败时，实验结果仍保留在工作台。会话记忆写失败则更严重，因为下一次恢复可能失去状态；实现应至少记录错误并避免在摘要里假装一切可恢复。

经验生成只读取已发生的实验。没有运行目录或 `total_experiments` 为零时，系统跳过经验生成；一个只有模型推理、没有现实反馈的 Idea 只能称为候选，不能升级成经验。这个门槛保护经验库不被漂亮但未经验证的语言填满。

## 第八十五章　提示演化的回声室风险

PromptEvolver 让失败经验可以改变下一轮的提示，但它也带来回声室风险：如果经验库把某一类失败描述得过于强烈，生成员可能只围绕既有模式修补，而不再探索新的方向。因此提示演化必须保留原 prompt、说明依据，并允许下一轮重新看到任务原始约束。

演化周期由轮次和间隔决定，不是每次启动都发生。第一轮通常使用原始 prompt，之后在满足周期且经验库存在时才备份并演化。这样，第一轮的结果仍然提供一个干净的对照，读者能分辨“任务本身的探索”和“经验反馈驱动的探索”。

演化失败要沿用旧提示。新提示如果解析失败、经验库格式错误或模型不可用，系统只写 warning，不写出一份部分替换的 prompt。备份文件让人工可以比较前后差异，发现演化是否只是改了措辞，还是实际改变了研究关注点。

下一轮的 prompt 变化还要与代码基线分开记录。incremental 可能在同一轮同时改变代码起点和提示版本，但摘要、备份和经验库要让读者分别追踪两条变化线。否则改善率上升时，无法判断是代码接力有效，还是提示演化改变了候选分布。

## 第八十六章　基线是研究叙事里的“昨天”

每一轮都需要一个“昨天”来比较今天。fresh 模式的昨天是原任务目录，incremental 模式的昨天是上一轮被选中的最佳工作台经过更新后的 `run_0`。实验器从 `base_dir/run_0/final_info.json` 读取这个昨天，当前候选从自己的最近有效运行提供今天。

基线不仅是一组数字，也是代码、数据路径、输出结构和运行脚本的组合。把指标复制而不复制代码，或者把代码复制而不复制科学输出，都会生成一个自相矛盾的昨天。全景叙事必须把基线当成“可运行的状态”，不能把它缩小成一个浮点数。

一个候选的性能可以是正、负或不可计算。负改善仍是有效结果，因为它说明该方向在当前约束下造成退化；不可计算说明测量链断了，需要检查输出而不是给它一个中性分数。排序器可以综合有效分数，经验生成器可以从退化模式学习，外层不能因为负号难看就删除。

如果最佳结果更新失败，下一轮不应引用它的路径作为新基线。外层可以保留上一条可靠路径并记录更新失败，也可以在配置要求严格一致时停止。一个已经写入摘要但尚未复制完成的路径，不能成为下一轮的隐形输入。

## 第八十七章　产物清单是一份反向导航

读一个 Launch 时，最有效的顺序常常不是从日志开始，而是先列产物。看到 `discovery_summary.json`，可以知道轮数、Session 和结果数量；进入 `session_*`，可以看到 Idea 和轨迹；进入候选工作台，才能看到 notes、运行目录和最终信息；回到 prompt 与配置快照，又能确认输入条件。

产物清单把“看什么”与“为什么看”连起来。想知道为什么某候选被选中，读排序后的 Idea 和评分；想知道为什么没有成为下一轮基线，读性能和 `_find_best_experiment_result` 的选择；想知道为什么恢复从某轮开始，读摘要的完成轮次和扫描到的 Session；想知道为什么报告缺一张图，读科学候选的 outputs 和 report。

公共产物清单则是这个导航的安全投影。它可以列出 report 和 summary，隐藏 runner log，给文件相对路径而不暴露绝对路径。内部读者若有权限可以进入 Launch 目录排查，普通用户先从安全投影开始，避免把调试细节当作研究结论。

产物也有生命周期。Session 和候选工作台在运行中不断增长，摘要通常在轮末和最终阶段更新，prompt 备份在演化时产生，经验库在轮末合并。删除或移动任何一层都可能破坏恢复链，因此清理策略应知道哪些文件属于共享历史、哪些属于当前 Launch、哪些仍被其他运行引用。

## 第八十八章　从任务信到摘要的字段血缘

任务描述的血缘起点可能是用户输入，也可能是科学任务的 `task_info.json`。它被保存进 prompt 快照，再进入 Task，随后出现在每个角色的目标上下文。Idea 的 `text` 和 `rationale` 来自生成响应，`critiques` 来自反思，`evidence` 来自资料员，`score` 和 `scores` 来自排序，`method_details` 与 `refined_method_details` 来自方法阶段。

实验候选的名称来自精炼方法或方法细节，工作台 notes 记录它的描述和方法；`run_0` 的指标来自基线目录，当前指标来自候选最近有效运行，performance 由两者计算；成功、失败和错误回到 Round 结果，再进入摘要。每一层都应该能沿着这条血缘回到上游，不能只留下一个孤立的最终数字。

反馈的血缘从外部驾驶员进入 `feedback_history`，在生成、反思、演化和方法阶段被裁剪后注入上下文。长期记忆的指导则从历史 Idea、notes 和实验读出，经检索、相似度和经验合并后再次进入提示。两种血缘都可能影响结果，但它们的来源不同，审计时必须分开。

配置字段也有血缘。外层轮数影响 Round 数量，内部迭代影响 Session 状态，top ideas 数量影响进入方法和实验的候选，并发限制影响同时运行的数量，backend 影响执行器，model catalog 影响模型适配器。摘要记录关键配置，让结果读者不必猜“为什么这次只有三个候选”。

字段血缘的意义不是让每个读者画一张图，而是提供一种追问方式：这个值是谁写的？什么时候写？能否由另一个文件验证？如果答案模糊，那里就是系统最值得补强的边界。

# 第十幕　最后的账本与仍然敞开的门

## 第八十九章　摘要不是结论，而是可恢复的横截面

`discovery_summary.json` 很像一本研究日志的封面：上面有日期、Launch 身份、任务名称、任务类型、模式、轮数、Session 列表、候选总数和成功失败数量。它不会把每个 Agent 的句子全文抄进去，也不会宣称哪条路线在科学上“最终正确”。它只保存足以重建流程位置和找到详细证据的横截面。

摘要中的 `rounds` 是一组轮次记录。每条记录带轮次编号、Session ID、结果列表、成功数和失败数；结果里有候选名称、成功标志、错误、工作台路径和性能对象。读者可以先从摘要发现某轮没有成功实验，再进入对应 Session 和工作台寻找原因，而不必扫描所有目录。

摘要还保留 `original_task_dir` 与 `base_output_dir`。前者告诉恢复逻辑和人工读者最初的任务代码在哪里，后者告诉长期经验和 IdeaGraph 的共享资源在哪里。增量模式额外记录最终最佳路径和性能，实验模式记录后端和模型。它们不是为了让报告更漂亮，而是为了在下一次启动时决定“从哪里继续”。

摘要写入时机很重要。最终汇总在所有轮次完成后写，轮次结果则在每轮结束时写入内存并参与经验生成。一个正在运行的中间状态可以存在于 Session JSON 和日志里，但不能被提前包装成最终摘要。恢复扫描以可验证的完成事实为准，而不是以目录创建时间为准。

## 第九十章　报告模式：把候选变成可读的短文

并不是每次 Discovery 都需要启动外部实验。有时研究团队已经完成实验，只想把整理过的 Idea 生成内部报告；有时模型凭据暂时不可用，但希望先审阅方法文本。`--mode report` 提供一个不进入实验后端的旁路，同时保留 Launch、Session 和摘要的外层骨架。

ReportWriter 从候选中抽取最完整的一层细节。它优先读精炼方法，再读方法细节，最后兼容直接提供 name、title、description、method 的简单结构。这个优先级让同一份报告器既能消费完整 MAS 产物，也能消费用户手工写的 Idea，而无需为每种输入创建一套模板。

报告目录用时间和候选名称命名，正文通常包含标题、Idea 名称、生成时间、描述、方法、预期结果和限制。字段为空时不硬塞占位句，避免一份报告看起来完整却没有实质内容。报告生成成功只说明文本文件写好了，不说明方案已经被实验验证。

报告模式仍然会把结果写进轮次记录。一个报告写入失败的候选标为失败，其他候选继续；总报告数和成功数进入摘要。这样，模式切换只改变“第二阶段的验证方式”，不改变外层恢复、统计和观察合同。

## 第九十一章　为什么 Discovery 在摘要处停下

Discovery 的工作是把研究问题变成候选，把候选变成方法，把方法放进工作台，接受实验和证据的检验，再把结果和经验保存下来。论文编排需要另一套职责：选择章节结构、组织引用、处理版式、生成最终文稿。两者可以串接，却不应在叙事上混成一个不可分割的函数。

把边界停在摘要处还有一个工程好处。Discovery 可以在没有 TeX、PDF 或论文服务的环境里独立恢复；论文消费者可以只读取 `discovery_summary.json`、报告和实验产物，不必重启模型或重新运行实验。如果论文阶段出现问题，研究发现的事实仍然存在；反过来，论文阶段也不能回写已完成轮次的结果。

本书仍会说明“后续消费者可以读取哪些产物”，但不展开 PaperOrchestra 的章节、排版和审稿逻辑。这样既尊重用户允许去除该模块的决定，也保留 Discovery 作为一个自足系统的边界。

## 第九十二章　字段字典：同一个词不要在不同房间变义

| 名称 | 在故事中的含义 | 主要来源 | 主要去处 |
|---|---|---|---|
| task | 研究问题的结构化身份 | prompt 或科学任务翻译 | Task、Session、角色上下文 |
| launch | 一次隔离的外层运行 | 启动或恢复 | Launch 目录、摘要、公共观察 |
| round | 一次完整的想法到结果循环 | `_main` 外层计数 | 轮次记录、摘要 |
| iteration | Session 内候选加工的计数 | WorkflowSession | Idea 的轮次、状态流转 |
| idea | 可追踪的候选方向或方法卡 | 生成/演化/输入文件 | Session、工作台、记忆 |
| parent_id | 子候选的来处 | 演化阶段 | IdeaGraph、排序前的谱系 |
| evidence | 支持早期方向的资料 | ScholarAgent | Idea、演化上下文 |
| refine_evidence | 支持具体方法的资料 | 方法阶段外部数据 | Idea、精炼上下文 |
| top_ideas | 当前被排序器选中的身份集合 | RankingAgent | Session、方法阶段 |
| method_details | 可执行方法的草案 | 方法开发 | Idea、实验委托单 |
| refined_method_details | 经反思和精炼后的方法 | 精炼阶段 | Idea、实验/报告输入 |
| run_0 | 当前候选的基线影子 | 工作台复制 | 性能计算的零点 |
| run_N | 外部后端的一次尝试 | 实验执行 | 工作台、最终信息 |
| performance | 指标比较的结构化结果 | 实验器 | Round 结果、增量选择 |
| session_id | MAS 会话的接驳身份 | Session 创建 | Session 目录、结果、轨迹 |
| feedback_history | 按时间累积的外部意见 | Interface | 生成、反思、演化上下文 |
| baseline | 下一轮要比较的代码与指标状态 | 原始任务或最佳结果 | ExperimentRunner、摘要 |
| fresh | 每轮回到原始代码起点 | workflow 配置 | 外层基线选择 |
| incremental | 采用前轮最佳代码起点 | workflow 配置 | 基线更新、摘要 |
| observation | 对外可读的状态投影 | Launch store | 状态接口、运行台 |
| artifact | 可定位的公开或内部产物 | Launch 目录 | 列表、读取、审计 |

字典的价值在于阻止“同名不同物”。例如 `round` 不能在一段文字里突然指 Session 内的 iteration，`success` 不能在一个结果里表示“后端返回零退出码”、在另一个结果里表示“指标改善”。如果一个字段需要两种解释，应改名或增加新的字段，而不是让读者靠上下文猜。

## 第九十三章　五条不会轻易让步的不变量

第一条是输入不变量：运行只能由当前、已保存且转换成功的 revision 启动。它保护研究问题不被未保存编辑和旧版本偷换。

第二条是隔离不变量：候选实验必须在自己的工作台中运行，不能直接污染原始任务目录或其他候选。它保护比较的公平和恢复的可行性。

第三条是基线不变量：任何性能改善都必须相对于同一候选工作台里的 `run_0` 计算，增量前移时指标与代码必须成对移动。它保护数值的含义。

第四条是证据不变量：状态、Idea、日志、实验目录和摘要之间不能互相矛盾；失败不能被成功字段覆盖，缺指标不能被零改善冒充。它保护审计的可信度。

第五条是边界不变量：公共观察只能暴露允许的产物和相对路径，不能通过 Launch、符号链接或路径参数读出私有文件。它保护运行系统的安全，也保护研究者不被无意的内部细节淹没。

这些不变量比某个默认数字更稳定。默认轮数可以从十改成五，并发可以从四改成二，模型可以更换；只要不变量仍然成立，机制的骨架就没有被破坏。

## 第九十四章　当你需要诊断一次运行时

诊断不要从“模型为什么这么想”开始，而应先问“流程现在在哪里”。先读取公共状态和摘要，确认 Launch、Round、Session 和候选数量；再看状态是否与目录匹配；最后才进入 Draft、日志和外部后端的细节。这样可以先排除输入、恢复和编排错误，再讨论科学结果。

如果状态卡在准备区，检查 dirty、revision、conversion 和来源引用；如果卡在生成或反思，检查运行时、Agent 注册表、Session JSON 和模型调用日志；如果卡在外部数据，检查搜索服务和并发限制；如果卡在实验，检查工作台、GPU 分配、后端日志和 `run_N/final_info.json`。

如果结果成功但性能为空，先确认 `run_0/final_info.json` 和候选最近有效运行都存在，再确认两边是否有共同的数值字段，最后检查基线是否为零或字段是否含非数字文本。不要直接把性能对象补成零，因为那会掩盖测量链断裂。

如果恢复从错误轮次开始，检查摘要里的 `rounds` 是否包含完整结果，Session 目录是否有可解析的 JSON，当前配置是否覆盖了旧的 loop rounds，以及最佳代码路径是否仍然存在。恢复是扫描和判断的组合，不是简单地把 `start_round` 减一。

## 第九十五章　故障回放一：提示缺失

任务目录存在，却没有 `prompt.json`。普通任务的 Launch 准备在复制输入时抛出缺失错误，外层不会建立一个让模型自由发挥的空 prompt。公共应用路径则会在准备转换阶段要求结构化执行输入。两条入口的错误位置不同，但都把问题留在输入边界。

如果有人手工在 Launch 目录创建一份空文件再恢复，系统仍应读取它的内容并让后续校验发现字段不足；它不会因为文件名存在就把空白当成有效任务。这个例子说明“存在性”和“有效性”是两道不同的门。

故障修复是补齐原始任务或重新转换 revision，然后建立新的 Launch 或在明确允许的恢复路径上继续。旧的失败记录保留，用来解释为什么第一次没有开始。删除失败目录只会让下一位读者失去输入链索引。

## 第九十六章　故障回放二：模型回答完整但工具调用断裂

工具循环可能收到模型提出的工具请求，工具执行也返回了结果，但最后一次模型调用没有给出结构化回答。ModelToolLoop 应把“没有最终答案”作为失败，而不是拿中间工具文本填入 GenerationAgent 的候选数组。否则，一个调查结果会被误认成研究 Idea。

反过来，工具调用失败不一定意味着整个生成阶段失败。若错误被封装成工具结果回送模型，模型可能换一条查询或直接结束；如果工具是该角色的硬依赖，错误才会上升为阶段错误。工具的可选性由 Agent 配置和角色语义决定，不应凭经验一概而论。

诊断时要看工具轨迹：请求名称、参数、结果、错误和循环终止原因。只看最后一句模型文字无法判断它有没有真正查过外部资料，也无法知道它是主动停止还是达到调用上限。

## 第九十七章　故障回放三：指标写在错误的位置

候选后端运行成功，却把指标写在 `run_1/metrics.json`，没有写 `final_info.json`。性能计算器找不到当前指标，于是性能对象为空；外层仍可记录后端成功，但不能选择它作为增量基线。这个结果不是系统“太严格”，而是执行器没有履行当前结果合同。

如果最新的 `run_2/final_info.json` 损坏，而 `run_1/final_info.json` 有效，计算器会向前寻找最近的有效运行。日志应指出它跳过了损坏文件；未来的读者可以知道结果来自 `run_1`，而不是假设最后一个目录总是权威。

修复可以是让后端遵守文件合同，也可以在受控实验中增加一个适配器把指标转换到最终信息。无论哪种方式，转换过程都要留下记录，不应在外层偷偷读取任意位置并让系统合同失去意义。

## 第九十八章　故障回放四：恢复时全局配置已经变了

第一轮使用一个模型目录和五轮配置，运行中途用户把全局设置改成另一个模型和十轮。恢复时，Launch 的配置快照仍然指向原模型，但当前命令行配置可能要求延长轮数。系统应该保留快照中的运行身份，同时允许明确的当前配置延长剩余轮数；它不能因为全局变化而重写已经完成的轮次。

loop mode 的处理也有优先级。若当前配置没有显式覆盖，恢复摘要里的模式可以作为参考；若用户明确指定 fresh，旧摘要里的 incremental 不应强行夺回控制权。配置的来源和覆盖关系要在日志中说清楚，让人知道哪一份决定了行为。

模型能力发生不兼容时，恢复可以在生成阶段前失败，或者把已完成的报告和摘要开放为只读。它不应使用一个不同能力的运行时继续同一 Session，然后让读者误以为所有 Idea 都经过同一评价器。

## 第九十九章　性能、透明度和成本的三角

把所有阶段串行运行最容易解释，却可能让大量候选等待模型和搜索。把所有阶段并行运行最快，却会超卖资源、混淆日志和放大失败。Discovery 选择分层并发：同类任务共享一个信号量，结果按身份写回，外部实验再用独立的 GPU 和线程池控制。

提高 `top_ideas_count` 会扩大方法和实验的工作量，也会增加记忆和摘要体积；提高内部迭代会让候选更充分地反思，但可能让每轮耗时增长；提高外层轮数会给 incremental 更多接力机会，却也让基线漂移的风险更长。参数调优不是单纯追求速度，而是在探索广度、证据厚度和成本之间做选择。

透明度也有成本。保存完整 Draft、工具轨迹和每次失败会占空间，但删除它们会让科学复盘失去上下文。公共观察则需要再做一次投影和路径检查，增加实现复杂度，却避免泄露内部细节。一个成熟系统不会把透明与安全看成互斥，而是为不同读者维护不同层的证据。

## 第一百章　当系统终于可以被讲清楚

如果把整个 Discovery 压缩成一句话，可以说：它把一个经过确认的研究输入，交给一支状态化的多角色队伍，产生并筛选候选，再把候选复制到隔离工作台接受外部执行，最后把成功、失败、指标、记忆和下一轮起点都写入可恢复的事实目录。

如果再展开一层，故事里至少有六种动作：确认输入、推进状态、调用能力、保存观察、隔离实验、封存证据。每种动作都有自己的对象和失败边界。入口不替模型猜任务，模型不替实验造指标，实验不替摘要改写历史，摘要不替论文决定叙事。

这就是本书所谓的“伪代码层面”：不是把每一行 Python 翻译成中文，而是把每个决定写到读者可以跟随的位置。谁先做，谁后做；什么条件让路径分叉；什么字段被写回；什么失败只影响一张卡；什么失败让整条走廊停下；恢复凭什么判断已经完成。这些关系比参数列表更接近系统的真实颗粒度。

到这里，Discovery 仍然不是一个会替研究者做最终判断的神谕。它是一座有门牌、有账本、有隔离工作台和有回放路径的研究工坊。它能让探索变快，也能让失败留下；它能让模型提出更多方向，也要求每个方向接受证据和代码的检验。研究发现因此不再是一句“模型说可以”，而是一条可以被别人重新走过的路。

# 第十一幕　给后来者留下足够多的路标

## 第一百零一章　入口的五分钟：先听见系统的犹豫

启动命令刚进入终端时，工坊还没有任何模型声音。日志先记录时间，随后确认任务路径、任务名称、类型和参考代码。这个阶段的沉默很有价值：它让输入错误在模型调用以前暴露，也让一个没有凭据的环境不会因为“先试试看”而消耗外部资源。

路径整理必须面对人类输入的多种样子。用户可能传任务名，也可能传相对目录、绝对目录或带尾部斜杠的目录；启动器把它们统一成同一个 task_dir 和 task_name。统一后，下游不再重复拼接 `tasks/`，也不再从当前 shell 目录推断任务名字。一个任务身份只有一份。

任务类型的判断很窄，正因为窄才可靠。目录中有没有 `task_info.json` 是一个可验证的事实；文件内容是否“像科学任务”则留给后续标准化。入口不提前扫描论文、数据和报告，避免一个额外文件意外改变分支。任何需要更复杂判断的逻辑，都应该写成后续阶段的显式动作。

参考代码路径也在这一刻被固定。普通任务默认使用 `task_dir/code`，科学任务允许没有参考代码，依赖它自己的运行工作区。这个差异必须写入启动日志，因为后面同样叫 baseline 的目录，在两种任务里可能承载不同的起点。

## 第一百零二章　Launch 的第一盏灯：输入快照

输入快照写入 prompt、任务来源和配置位置。普通任务复制已有 prompt，科学任务把 task_info 和 checklist 译成合成 prompt。快照的意义不是备份文件那么简单，它让“本次运行看到的任务”脱离了会被用户继续编辑的原始目录。

如果用户在第一轮结束后修改任务目录里的 prompt，第二轮仍然应该从 Launch 的提示版本出发，除非明确触发提示演化或建立新的 Launch。否则同一个摘要里的 Round 1 和 Round 2 就会使用两个没有记录的任务，改善率和 Idea 变化都无法解释。

提示演化会在快照树上留下新节点。当前 prompt 被复制成 `prompt_backup_roundN.json`，新版本写回运行使用的位置；失败时旧版本继续生效。这样，恢复者可以从备份比较每一轮提示的语义变化，而不是只看到最后一版的句子。

输入快照还承担人为沟通的职责。研究者把 Launch 目录交给同事时，对方不需要猜原始任务后来是否改过；只要打开 prompt 和配置快照，就能知道本次运行的边界。可追溯性从入口第一盏灯开始，而不是等摘要写完才补。

## 第一百零三章　Session 的第一声回响

创建 Session 时，系统生成任务身份和会话身份，建立 Task、WorkflowSession 和可选的背景报告。时间戳提供了便于人读的线索，真正的关系由 JSON 中的 Task 和 Session 字段保存。一个时间相同的会话也不会因为名字相似而自动合并。

背景调研角色如果启用，会先调查领域、术语和已有工作，再把结果交给任务上下文。它失败时，用户给出的 background 仍然在。这个降级让背景报告成为增强，而不是让一项可选服务掌握研究问题的解释权。

Session 写入记忆以后，状态从 INITIAL 准备进入 GENERATING。记忆保存动作是一个边界：在它完成以前，外层不应把会话 ID 当成已经可恢复的事实；在它完成以后，任何阶段都可以通过同一个身份找到当前状态。

Session 的时间字段也有含义。started_at 说明研究走廊何时开启，completed_at 只在真正完成时写入；错误和暂停可以没有完成时间。读者看到一个空的 completed_at，不应把它当作缺字段，而应先问“这条走廊是否还没有走到终点”。

## 第一百零四章　候选卡片的加厚过程

第一张 Idea 卡片通常很薄：一个文本、一个理由、一个出生轮次。反思阶段给它加上优点、批评和改进方向；资料阶段加上证据与参考；演化阶段通过 parent_id 把它接入家族；排序阶段加上分数和标准分项；方法开发和精炼再写入可以执行的步骤。

卡片加厚不是把所有原文堆进去。编排器选择结构化字段，Draft 保存完整观察；Idea 的 `critiques` 不是一段长对话，`evidence` 不是所有搜索结果，`score` 不是模型的情绪。字段的压缩让后续 Agent 能够消费，也让恢复不会被一段巨大文本拖垮。

字段的时机比字段的数量更重要。一个还没有经过资料阶段的 Idea 没有 evidence 并不异常；一个已经完成外部数据却仍然没有 evidence，才需要检查 ScholarAgent 或结果解析。一个方法阶段之前的 Idea 没有 method_details 是正常的，方法阶段之后仍为空则应写入失败标记或在精炼阶段跳过。

父子关系保留了搜索的形状。孩子继承基线摘要，但不继承一个“看不见的成功结论”；它的文本、理由和证据仍然要独立形成。父卡片不会因为子卡片出现而消失，排序可以比较不同家族，经验生成器可以观察某个家族如何从批评走向改进或走向失败。

## 第一百零五章　工具回路中的耐心

一个 Agent 请求工具时，工坊里暂时多了一位外部工人。它可能是文献检索、代码读取、指标查询或其他注册工具。循环器先确认工具请求的名称和参数，再执行，随后把结果放回模型历史。模型可以继续，也可以根据错误换方向。

工具回路有两个上限：允许的思考迭代数和工具调用总数。前者防止模型在没有新信息时无限自言自语，后者防止一个错误查询反复消耗外部服务。达到上限时，循环结束并记录原因；“停止”也是一种有意义的观察。

工具结果要保留输入和输出的对应关系。只记录“查过文献”不足以解释生成员为何得到某条证据；只记录模型最后答案又无法知道它是否真的使用了外部资料。Draft 和工具轨迹提供更长的回声，Idea 只接收经过角色整理的结构化结论。

工具错误也有传播级别。一个可选工具失败，角色可以在没有它的情况下继续；一个必需工具失败，阶段处理器可以把 Session 置为 ERROR。配置和角色定义决定边界，编排器不能为了追求成功率把所有工具错误都吞掉。

## 第一百零六章　等待并不等于没有人工作

AWAITING_FEEDBACK 的房间里可能没有模型调用，却有外层驾驶员、离线反馈文件和持久化 Session 在工作。状态写入以后，运行器可以退出，应用界面可以断开，下一次请求再把反馈带回来。等待被设计成可持续的事实，而不是内存里的 sleep。

一个人工反馈可以只写一句话，也可以是一组针对多个 Idea 的意见。接口把它们追加到 feedback_history，并记录目标、轮次和时间。外层看到状态从 waiting 变成 reflecting，再调用 resume；状态变化和反馈写入是两个可观察事件，便于诊断“意见已经到达但会话没有继续”的问题。

如果没有 feedback，自动驾驶员不应反复调用 run_session 让同一个状态空转。它可以等待、报告当前状态，或在有 offline_feedback 时读取一次。重复空转会制造日志噪声，也可能把状态回调和工具调用误当成新的研究进展。

方法阶段也可能经过等待。用户可以在看过方法草案后指出实验成本或安全约束，再让反思和精炼继续。这样，反馈插槽不仅服务早期想法，也服务已经接近执行的方案；它是人类判断进入自动流程的固定门。

## 第一百零七章　排序不是投票大会

排序器收到的是当前迭代的一批候选，不是整个历史。它按小批次请求评分，校验每个返回项的身份、总体分数、标准分项和理由，再把各批次合并。批次之间的评分解释可以拼接，但候选的最终排序必须基于结构化分数。

返回数据如果是 JSON 字符串，解析器会尝试还原；解析失败时，不能把原字符串当作已经评分的列表。缺少必要字段的条目被过滤并记录，避免一条格式错误的回复污染所有候选。排序阶段的严格性来自它是流程闸门：它决定哪些卡片进入方法和实验。

可选的 distinct 策略按 parent_id 分组，只保留每个父家族的最高分代表，再选 top N。它的目的不是奖惩某个父节点，而是让候选空间保留多样性。默认策略可能不启用这一规则，读者必须以当前角色配置为准，不能把故事中的“每家只留一个”写成永久法则。

排序结果写回每个 Idea 的 score 和 scores，也写回 Session 的 top_ideas。未入选的 Idea 仍然保留，它们可能在历史图谱中发挥作用，也可能在人工反馈后被重新检视。删除落选卡片会使“为什么它没有被选中”变得不可回答。

## 第一百零八章　方法开发不是扩写作文

方法开发员要回答五个不同问题：方案叫什么，标题如何让人定位，描述要改变什么，核心陈述是什么，具体方法如何执行。它不是把 Idea 的段落扩成更长的段落，而是把形容词变成动作，把“提升鲁棒性”翻译成数据、步骤、对照和评价。

证据上下文会从 Idea 的 evidence 或父 Idea 沿谱系取得，再按标题、内容和相关性整理。没有证据的候选可以先请求 ScholarAgent；有证据的候选不必重复检索。这个条件避免每个阶段都从零搜索，也让方法卡知道自己依赖了哪些资料。

方法开发失败时，编排器会留下一个以失败标记开头的名称，把错误写入 statement 和 method。它看起来不如一张成功卡片整齐，却让后续读者看到“候选方向存在，但方法翻译失败”。精炼阶段会识别空方法并跳过，避免让一团错误文字进入实验工作台。

## 第一百零九章　精炼阶段的克制

精炼员只在方法细节存在且非空时调用。它接收目标、当前方法和 refine_evidence，尝试改进步骤、对照、限制和预期结果。返回的 refined_method 被写回 Idea；如果模型调用失败但提供了原方法，编排器可以保留原方法并标明错误，避免一次服务故障让全部研究材料消失。

精炼不是第二次方法开发。方法开发解决“有没有可执行的协议”，精炼解决“协议内部是否一致、证据是否支撑、步骤是否遗漏”。两者的批评字段分开，资料桶也分开，后续实验可以知道自己拿的是初稿还是已经经过精炼的版本。

如果 top_ideas 为空，精炼阶段可以直接完成；如果没有 refinement Agent，也可以以 warning 后完成。这体现了收束器的可选性：Discovery 的完成需要有一个可解释的结果，不要求每个可选增强都成功。

## 第一百一十章　一个错误如何穿过多个房间

假设模型返回的候选缺少文本。生成员可能仍然创建一张空 Idea，反思员会发现无法构造有效 hypothesis，资料员会拒绝搜索，排序阶段最终没有可评分条目。这个错误若只在生成日志里写一行 warning，后来者会看到一个“没有想法的错误状态”，难以定位真正的入口问题。

更稳妥的路径是在结构化结果验证处标记缺失，保留原始响应片段的可审计记录，让编排器决定是过滤该候选、继续其他候选，还是让 Session 进入 ERROR。错误传播范围必须与数据归属一致：一张卡片坏了，不应连带所有卡片；流程没有任何有效卡片时，排序闸门才需要停止整条走廊。

另一个例子是文献搜索失败。若一个 Idea 的搜索任务可以局部隔离，其他 Idea 仍可获得证据并进入演化；若当前实现把 task exception 在 gather 后整体抛出，整个外部数据阶段就会进入 ERROR。全景书不能把“理想的局部隔离”当成实现事实，而应指出真实的失败边界和它的后果。

## 第一百一十一章　写日志的人也有责任

日志不是越多越好。启动日志要记录任务、类型、路径、后端、轮数和模式；阶段日志要记录 Session、状态、候选数量和失败身份；实验日志要记录工作台、GPU、后端、运行目录和性能来源；错误日志要包含异常和可定位的上下文。重复打印同一大段 prompt 只会淹没真正的转折。

日志级别帮助不同读者筛选。info 告诉操作者流程走到了哪里，warning 告诉操作者某个增强或资料缺失但可能继续，error 告诉操作者某个阶段无法完成。不要用 warning 掩盖会导致错误恢复的持久化失败，也不要把一个单候选的可接受失败写成全局 error。

日志和结构化产物要互相照应。日志里的“Round 2 completed”应能在摘要的 rounds 中找到对应记录；日志说发现最佳候选，应能在结果列表和工作台中找到性能字段；日志说跳过经验生成，应能说明没有实验或长期记忆不可用。彼此矛盾的日志比缺日志更危险，因为它会让复盘者相信错误的故事。

## 第一百一十二章　把一整次运行画成六条线

第一条线是输入线：任务目录或准备草稿，经过保存、转换、revision 和 Launch 快照，形成 Task。第二条线是状态线：INITIAL、GENERATING、REFLECTING、EXTERNAL_DATA、EVOLVING、RANKING、AWAITING_FEEDBACK，再进入方法阶段和 COMPLETED 或 ERROR。

第三条线是候选线：Idea 从文本和理由开始，经过批评、证据、父子演化、评分、方法和精炼，成为实验委托单。第四条线是代码线：原始 baseline 进入候选工作台，`run_0` 保存零点，`run_N` 产生修改，最佳结果可能被复制回下一轮的 baseline。

第五条线是观察线：状态回调、Draft、日志、Session JSON、轮次记录和公共 artifact 把发生过的动作分层保存。第六条线是记忆线：Task Memory、IdeaGraph、在线记忆、经验库和提示演化把过去带进未来，但不改变当前任务的身份。

六条线相互交叉却不应互相替代。状态线可以告诉你正在实验，不能告诉你指标是多少；代码线可以告诉你使用了哪个基线，不能告诉你 Idea 为什么被选；观察线可以让你回放，不能把失败变成成功；记忆线可以提供指导，不能替任务下决定。理解这些分工，就不容易再把 Discovery 写成一段模型调用。

# 第十二幕　给不同读者的同一座工坊

## 第一百一十三章　给研究者：问它是否值得信

研究者最关心的不是系统用了多少个类，而是某个结论是否有可靠的来路。阅读一个候选时，可以先看它的 Idea 文本和 rationale，再看批评、证据和父节点；进入方法时，查看 method_details 与 refine_evidence；进入实验时，确认工作台的 `run_0` 与最近有效运行；最后从 performance 回到原始 final_info。

如果这条链断在某处，研究者不必立即否定全部结果，但应标记结论的可信等级。例如有方法没有证据，它可以是一个值得讨论的提案；有证据没有实验，它可以是一个有文献支持的方案；有实验但没有共同指标，它只能说明执行发生过，不能说明性能改变。

研究者还应该把负结果当成研究材料。一个候选在不同轮次反复失败，可能说明假设本身不适合任务，也可能说明执行器没有满足某个约束。Long memory 和 IdeaGraph 可以帮助区分“同一失败模式”与“不同原因的表面相似”，但最终判断仍需回到工作台和日志。

## 第一百一十四章　给工程师：问它是否能恢复

工程师要问的是：进程被杀、机器重启、外部服务超时以后，系统能不能从磁盘继续，而不是从零生成一个看似相同的运行。答案散落在几个位置：Launch 快照、Session JSON、轮次摘要、运行器标记、Draft 和候选工作台。

工程师可以故意制造中断：在等待反馈时停止进程，在实验后端写完 `run_1` 但尚未写摘要时杀掉 worker，在并发实验中让一个 future 抛异常。恢复后检查已完成的轮次、Session 状态、候选工作台、错误字段和下一步动作。只有当系统能区分“已完成”“正在等待”“只写了一半”和“不可恢复错误”，恢复才不是一句口号。

工程师还要检查配置边界。恢复默认不改变旧轮次，但可以在明确配置下延长总轮数；model catalog 和 discovery preferences 读取 Launch 快照；新的全局设置不会偷换旧运行。测试应覆盖这些组合，而不是只覆盖“没有任何中断”的绿灯路径。

## 第一百一十五章　给运维者：问它是否会把资源用完

运维者看到的是模型额度、GPU、磁盘、线程和外部搜索服务。每层都有自己的上限：MAS 阶段限制 LLM 并发，资料阶段限制搜索并发，ExperimentRunner 限制工作台并行和 GPU 份额，后端自身还有最大运行次数和超时。

资源告警要与研究结果分开。一个实验因为 GPU 不足没有开始，不应进入经验库的“方法失败”；一个实验在 CPU 上完成但指标下降，也不应被归因于调度故障。结果对象的 error、gpu_ids、folder_name 和 performance 让运维者有机会做这种区分。

磁盘管理也必须尊重历史。候选工作台、run 目录和 Draft 可能很大，但它们承载失败和重放证据；共享经验库和来源 blob 还可能被多个 Launch 引用。清理策略应按引用和终态设计，不能用“删除最旧目录”这种粗糙规则破坏恢复链。

## 第一百一十六章　给前端：问它应该显示什么

前端只需要显示服务器确认过的状态、阶段、进度、允许动作和公开产物。它不应从日志字符串猜阶段，不应从本地缓存决定停止按钮是否可用，也不应直接拼接服务器绝对路径去读取文件。

一个友好的运行台可以把状态解释成故事：“正在生成候选”“等待反馈”“正在验证 3/5”“本轮已完成，正在整理经验”。这些句子是观察层的翻译，不是新的事实。底层仍保留原始状态、Session ID、轮次和错误，用户展开详情时可以回到证据。

前端断线重连后应重新查询服务器权威观察，并沿用 Launch ID 和事件游标。它不应把重连前最后一帧当作当前状态。若服务器已经对账到 completed，恢复按钮应该消失；若服务器发现 runner 失败，错误和只读产物应该出现，而不是继续显示“运行中”。

## 第一百一十七章　给审计者：问谁改变了什么

审计者沿着时间线看六类事件：输入被保存或转换，Launch 被创建，Session 状态改变，Idea 字段写回，工作台和 run 目录产生，摘要与记忆更新。每类事件都应有来源身份和时间，必要时还要有请求指纹、模型目录或后端名称。

审计不需要把每个 token 公开。它需要知道某个候选为什么进入实验、实验使用什么基线、指标从哪个文件读取、下一轮为什么采用某条代码。Draft 可以保留更细的过程，但公共审计报告可以只提供证据索引和摘要。

如果一个字段没有清楚的写入者，审计者应把它视为待确认，而不是把最接近的日志当成来源。例如 `top_ideas` 由排序结果写入，不能用报告中的候选顺序代替；`overall_improvement_rate` 由性能计算器写入，不能用模型说“有提升”代替。

## 第一百一十八章　给测试者：问边界能否重复触发

测试者不只运行一条 happy path。要重复点击开始，重复停止，重复恢复，使用相同幂等键提交不同 revision，读取不存在的 artifact，读取 `../` 路径，创建没有 prompt 的普通任务，创建没有 checklist 的科学任务，让当前运行配置与恢复摘要冲突。

每个边界都要有预期的状态和错误类型。无效输入在启动前拒绝，未知后端在候选执行时失败，单 Idea 的实验异常不应吞掉其他结果，终态不允许改变，公共观察不泄露内部路径。测试名称最好直接说出这些不变量，以便未来修改者理解为什么断言存在。

## 第一百一十九章　给后来要扩展系统的人

新增一个 Agent 时，要确定它需要什么上下文、返回什么结构、失败影响哪一层、结果写回 Idea 还是 Draft。新增一个实验后端时，要遵守工作台、日志、GPU、成功标志、性能和错误的结果合同。新增一种任务类型时，要在输入标准化、代码基线、输出目录和摘要字段上写清楚它与 auto、sci 的差别。

扩展不能只增加一个 if 分支。分支会穿过入口、配置、运行时、AgentFactory、ExperimentRunner、结果统计、恢复扫描、公共观察和测试。深模块的做法是把差异封装在边界内，再让外层继续消费同一份合同；否则故事会越来越像一份互相覆盖的例外清单。

## 第一百二十章　一次人工复盘的节奏

复盘者可以先读本书的总地图，再打开某个 Launch 的摘要；按轮次挑出成功和失败最多的一轮；进入该轮 Session 观察 Idea 如何从生成走到排序；进入一个成功候选看工作台、run_0、run_N 和性能；再进入一个失败候选对照错误路径。最后回到 prompt 备份、经验库和 baseline 更新，理解下一轮为什么不再是原来的起点。

这条复盘顺序先看宏观，再看局部，再看前后两轮的差异。它避免一开始被模型长文本或外部日志淹没，也避免只看最终成功而忽略被淘汰的路线。对于科学任务，还要把 checklist 和 report 纳入复盘，因为它们描述了“任务完成”比代码返回更宽的含义。

复盘的终点不是为每个候选写一个漂亮评价，而是找出系统可以改进的地方：哪种反馈最能改变候选质量，哪类失败在记忆库中重复出现，哪个并发上限造成排队，哪条状态转移缺少可读观察，哪份产物不够支持恢复。全景机制的价值在于让这些问题有位置可放。

## 第一百二十一章　一个短小但完整的叙事伪流程

可以把一次 Discovery 用一段非代码式的口述记住：先确认研究问题已经签字，给它建立 Launch 和快照；再让 Session 召集角色，提出方向，逐张批评、查证、演化和排序；等人类意见或自动反馈回来，把最有希望的方向写成方法；为每个方法复制房间，留下 `run_0`，让后端在自己的房间里试验；读取最近有效的结果，与基线做可解释的比较；把成功和失败都记回账本；如果还有下一轮，按模式决定是否前移基线；如果没有，封存摘要。

这段话已经包含真正的控制流：签字失败不启动，角色缺失会停在编排，单候选失败可以隔离，指标缺失不等于零改善，反馈可以让状态从等待回到反思，增量前移必须携带代码和指标，摘要只在完成轮次后写。它没有列出每个参数，却没有丢掉关键决定。

## 第一百二十二章　另一个短小但完整的失败流程

研究问题签字后，Launch 成功创建；模型运行时启动，但生成员返回的候选没有文本。编排器把无效候选记在观察中，其他候选仍然继续反思。排序时发现仍有有效候选，于是流程继续；实验阶段一个候选的后端超时，工作台留下 traceback，另一个候选完成并写出指标；增量选择跳过失败者，摘要同时记录两种结果。

如果所有候选都无效，排序闸门把 Session 置为 ERROR，外层记录失败轮次，不会创建没有 Idea 的实验目录。恢复时，用户可以修订 prompt 或模型配置，选择重新运行新的 Launch；旧 Launch 保持失败证据。这个流程展示了“局部错误隔离”和“没有任何有效输入时停止”同时存在，并不矛盾。

## 第一百二十三章　这一套机制为何适合故事化说明

代码天然按文件和函数切割，读者却常常按因果和时间理解系统。把 `WorkflowSession` 说成一间有门牌的房间，把 `Idea` 说成一张会变厚的卡，把 `run_0` 说成测量的零点，能让字段之间的关系先在脑中建立，再回到真实对象验证。

故事化不是降低严谨性。故事中的门槛必须对应输入校验，房间必须对应状态，账本必须对应持久化对象，工作台必须对应复制目录，接力棒必须对应基线更新。只要每个比喻都能落回一个可检查的事实，通俗语言反而能减少“模型提出想法、系统做实验”这类过于粗粒度的黑箱句子。

故事也允许呈现失败和犹豫。一个资料员找不到文献，一个候选没有指标，一个恢复请求发现配置已变，这些不是主流程之外的尴尬，而是科研系统真正需要处理的日常。读者跟随人物走过这些岔路，才能理解为什么状态、日志和产物必须同时存在。

## 第一百二十四章　全书的终点不是代码的终点

本书写到 `discovery_summary.json`，并不意味着仓库里的 Discovery 只有这么多文件；它意味着故事的边界已经完成。读者如果要继续深入，可以以摘要为索引，沿着 Session、Idea、工作台、run 目录、Draft 和记忆库逐层展开。每一层都有更细的实现细节，但不会改变前面这条因果链。

后续实现可以加入新的模型适配器、新的外部后端、新的实验指标、新的公共观察字段，只要它们遵守输入、状态、隔离、证据、恢复和安全这几条骨架，整个系统仍然可以被同一种方式讲清楚。真正的全景不是把所有名称罗列一遍，而是让新名称有地方落座。

尾声里，书记员把最后一页摘要夹进 Launch 的账本。她没有写“这个答案就是对的”，只写下任务、轮次、候选、结果、失败和路径。队长关掉实验室，门没有锁死：下一次运行可以从经验库取走失败的教训，另一位研究者可以打开报告和工作台，审计者可以沿着字段血缘追问。Discovery 的价值，正是在关门以后仍然允许别人知道屋里发生过什么。

# 附录 A　十二张机制卡：把复杂流程折成可复述的动作

## 机制卡一：输入确认

故事里，接待员不问模型“你觉得这是什么任务”，只检查任务目录、文件存在性和已保存版本。普通任务找到 prompt，科学任务找到 task_info；应用入口还要确认准备已保存、转换成功、revision 仍然匹配。任何事实不成立，研究留在门外。卡片的关键句是：先确认你手里拿的东西，再决定往哪条路走。

## 机制卡二：Launch 隔离

故事里，书记员给每一次运行分配一间有名字的房间，把本次 prompt 和配置拍成照片。共享记忆放在公共仓库，当前运行的 Session 和实验放在房间里。卡片的关键句是：历史可以共享，运行不能互相覆盖。

## 机制卡三：状态推进

故事里，门牌只允许有限的房间，当前门牌决定下一位角色。没有处理者就停在错误房间；进入新房间时记忆和观察同时更新。卡片的关键句是：状态不是进度条文字，而是决定谁有资格行动的合同。

## 机制卡四：候选加厚

故事里，Idea 从一张薄卡片开始，批评、证据、父子谱系、评分和方法细节逐层贴上去。没有发生过的阶段不填假材料，发生但失败的阶段留下失败标记。卡片的关键句是：字段的缺席和字段的空值各有故事。

## 机制卡五：工具循环

故事里，模型每次想请外部工人帮忙，都要说清工具和参数；工人返回结果或错误，模型再决定下一步。循环有次数上限，结束原因必须留下。卡片的关键句是：工具是带权限和失败可能的行动，不是模型记忆的延长线。

## 机制卡六：方法翻译

故事里，方法员把“值得研究”翻译成“可以执行”：它写出名称、目标、步骤、对照、证据和限制。方法开发失败不会生成漂亮的空文本，而是留下可见的失败卡。卡片的关键句是：科学叙事必须在某个时刻变成动作序列。

## 机制卡七：工作台复制

故事里，每个候选得到自己的房间，根目录可被修改，`run_0` 保存零点。候选之间不能共享正在修改的 code，原始任务也不能被污染。卡片的关键句是：没有隔离，就没有公平比较。

## 机制卡八：指标比较

故事里，测量员从零点和最近有效运行读取共同指标，逐项计算变化，再汇总成总体改善率。缺失指标不是零，基线为零时不做相对比较。卡片的关键句是：数字必须有共同来源，正号也必须有语义。

## 机制卡九：增量接力

故事里，队长只从成功且有可比较证据的候选中选接力棒；复制时代码、指标、科学输出和报告一起前移。卡片的关键句是：下一轮的昨天必须是一整个可运行状态，而不是一条孤立数字。

## 机制卡十：恢复与对账

故事里，重启后的值班员先读摘要、Session、标记和目录，再决定从哪一轮继续；服务器观察会与运行器状态对账。卡片的关键句是：恢复不是复活内存，而是重新确认文件和进程留下的事实。

## 机制卡十一：公共观察

故事里，窗口只展示允许观看的产物和相对路径，不把源代码字节、内部日志和绝对路径带到街上；路径穿越和符号链接逃逸都被挡住。卡片的关键句是：透明要有边界，安全也要有证据。

## 机制卡十二：经验回流

故事里，轮末书记员只在真的有实验时提炼经验，把成功与失败对照后写进库；提示演化先备份再替换。卡片的关键句是：过去可以指导未来，但不能篡改过去。

# 附录 B　术语表：把工坊的口语和仓库的名字对齐

**Discovery**：研究发现主流程。它从已确认的任务输入出发，完成候选生成、验证、实验和经验沉淀，终点是发现摘要及其证据目录。

**Launch**：一次外层运行的隔离边界。它拥有自己的输入快照、配置快照、Session、实验结果和摘要，也有可以被公共观察层引用的身份。

**Task**：结构化研究任务。它承载描述、领域、背景、约束和参考代码路径，来源可以是普通 prompt，也可以是科学任务标准化结果。

**Session**：一次 MAS 内部会话。它管理当前状态、Idea 列表、反馈、迭代计数、top ideas、时间和错误，是内层恢复的最小骨架。

**WorkflowState**：有限的状态门牌。INITIAL、GENERATING、REFLECTING、EXTERNAL_DATA、EVOLVING、RANKING、AWAITING_FEEDBACK、METHOD_DEVELOPMENT、REFINING、COMPLETED 和 ERROR 各自表示一组合法的行动边界。

**Idea**：研究候选的持久化卡片。它可以从纯文本逐渐加厚为含证据、评分、方法和精炼结果的执行协议。

**parent_id**：演化谱系中的父节点身份。它让子 Idea 的来源可追踪，也让多样性排序和失败模式聚类有依据。

**critique**：对候选方向或方法的审查意见。早期意见存入普通批评字段，方法阶段意见存入方法批评字段。

**evidence**：支持研究方向的资料记录。它通常来自早期 ScholarAgent 查询，服务于演化和排序。

**refine_evidence**：针对具体方法步骤的资料记录。它通常在方法阶段重新查询，服务于精炼。

**top ideas**：排序器选择的候选身份集合。它决定哪些方向进入方法开发或实验，但不删除落选 Idea。

**method_details**：方法开发阶段生成的执行草案。它包含名称、标题、描述、核心陈述和方法步骤等语义。

**refined_method_details**：经过方法反思、精炼证据和 RefinementAgent 处理后的方案。它是实验委托单最优先使用的来源。

**feedback_history**：外部意见的时间序列。记录文字、时间、轮次、作用范围和目标 Idea，供后续角色裁剪使用。

**VegapunkInterface**：MAS 外部驾驶员的门面。它创建、运行、恢复会话，查询状态并注入反馈，不绕过 Session 状态机直接改卡片。

**UnifiedModelRuntime**：统一模型能力边界。它负责根据冻结目录选择适配器，提供文本、结构化输出、图像和嵌入等能力。

**AgentFactory**：角色装配器。它把角色名称、配置和统一运行时绑定成可执行 Agent，拒绝未知角色或不完整配置。

**ModelToolLoop**：受上限控制的模型—工具往返。它负责校验工具请求、执行工具、回填结果和记录终止原因。

**ResearchDraft**：只追加的观察带。它承载较长的轨迹、工具事件和运行叙述，不替代结构化 Session 或最终摘要。

**MemoryManager**：会话级持久化接口。它保存和加载 Session、Task 与 Idea，让暂停、错误和完成都能落盘。

**FileSystemMemoryManager**：以文件系统为后端的会话记忆实现。它把任务、会话和候选写入可恢复的 JSON 结构。

**Task Memory**：跨任务的相似案例检索层。它通过关键词、嵌入或混合策略把过去的成功和失败带给当前角色。

**IdeaGraph**：历史 Idea 的关系图。它负责节点、相似关系和聚类，不直接替 RankingAgent 决定 top ideas。

**PromptEvolver**：提示演化器。它读取经验库，在明确周期内备份并生成新 prompt，失败时沿用旧版本。

**ExperienceGenerator**：经验提炼器。它从实验和轨迹中比较成功失败模式，再把经验以新增、更新、删除或不变操作合入库。

**Round**：外层完整循环。它通常包含一次候选生成、方法准备、实验或报告、轮次封存和可选的经验生成。

**Iteration**：Session 内部候选加工循环。它不等同于 Round，也不等同于实验的 run 编号。

**baseline**：比较的起点状态。它同时包含代码、运行脚本、指标、数据路径以及科学任务可能需要的输出和报告结构。

**run_0**：候选工作台中基线的固定影子。它保存比较零点，不表示候选已经尝试失败。

**run_N**：外部后端的一次真实尝试。它可能成功、失败、超时或只留下部分材料；最近有效的最终信息才参与性能计算。

**final_info.json**：实验器读取的最终指标载体。它连接运行目录与性能计算，缺失或不可解析时不能假装有改善。

**performance**：结构化的比较结果。包括基线指标、当前指标、逐指标改善率和总体改善率。

**overall_improvement_rate**：共同可比较指标的平均变化率。它是外层选择最佳结果的参考，不自动代表科学意义上的“更好”。

**ExperimentRunner**：实验编排器。它创建工作台、选择后端、分配 GPU、管理日志、回收结果和计算性能。

**Codex backend**：可调用 Codex CLI 或对应适配器的实验后端。它可以接收统一运行时、任务类型上下文、最大运行次数和超时。

**OpenHands backend**：依赖挂载目录和 URI 配置的实验后端。它仍然需要遵守工作台、日志和结果合同。

**Qwen Code backend**：另一种外部实验执行路径。后端差异被 ExperimentRunner 屏蔽，外层只消费共同结果。

**GPU allocator**：实验资源分配器。它通过信号量和环境变量为单个工作台分配设备，避免并行数直接超出硬件容量。

**MCTS mode**：某些后端支持的搜索式实验模式。它改变后端内部探索策略，不改变 Discovery 的目录和结果边界。

**fresh mode**：每轮回到原始任务代码的循环模式。长期记忆仍可存在，代码基线不自动继承上一轮。

**incremental mode**：每轮尝试从已选最佳结果的代码与指标开始。成功候选才有资格成为接力棒。

**Launch snapshot**：输入、配置、模型目录和偏好的冻结副本。恢复时优先读取它，防止全局设置漂移。

**revision**：准备区转换并保存后的执行输入版本。它绑定准备指纹，是应用启动 Launch 的合法身份。

**idempotency key**：一次外部动作的重试身份。与请求指纹一起使用，防止网络重试创建重复 Launch 或重复恢复。

**request fingerprint**：根据动作不可变输入计算出的指纹。它帮助系统区分“同一次重试”和“复用同一键做另一件事”。

**observation**：服务器对内部运行事实的安全投影。它为前端和 API 提供状态、动作、时间线和公开错误。

**artifact**：可以被列出、预览或读取的产物。公共列表使用相对路径并绑定 Launch 根目录，内部日志和源文件可能被限制。

**path traversal**：通过 `../`、绝对路径或符号链接逃出选定 Launch 根目录的读取尝试。Discovery 应拒绝它。

**reconcile**：把磁盘、运行器标记和服务器索引重新对账的过程。它让状态观察不会永久停留在旧内存。

**PaperOrchestra boundary**：Discovery 与论文编排之间的边界。论文模块可以消费发现摘要，但本书不把它作为 Discovery 内部机制展开。

# 附录 C　源代码地图：想回到仓库时从哪里开始

如果读者要从本书回到代码，入口可以先看 `launch_discovery.py`。任务分流、科学任务标准化、恢复扫描、最佳实验选择、增量基线更新、轮末经验生成和外层 `_main` 都在这里形成第一条主线。阅读顺序建议从入口函数的阶段注释开始，再跳到它调用的辅助函数，不要一上来把六百行当成一个整体。

MAS 侧从 `vegapunk/stage.py` 的 `IdeaGenerator` 和 `ExperimentRunner` 看起。前者负责 Interface、IdeaGraph、Session 输出和候选对齐，后者负责候选工作台、后端选择、GPU、运行器、性能和结果回收。它们共享一个从外层延迟构造并注入的 model runtime，这是理解“模型能力为什么在两阶段一致”的关键。

状态机与角色在 `vegapunk/mas/workflow/orchestration_agent.py`、相邻的 Task、Idea、WorkflowSession 定义和各个 Agent 模块中。先读状态转移和上下文组装，再读某个角色的提示和 schema；如果反过来只看角色提示，很容易把角色内部的自然语言当成全局流程。

统一模型入口在 `vegapunk/mas/models/unified_runtime.py`，工具回路在 `vegapunk/mas/agents/tool_loop.py`，观察草稿在 `vegapunk/research_draft.py`，会话文件记忆在 `vegapunk/mas/memory/memory_manager.py`。这几处分别对应能力、外部动作、长观察和恢复骨架。

应用层的准备、Launch、状态、产物和安全边界在 `desktop/openworker/upstream/coworker/server` 下的 Discovery 相关模块。Facade 是动作门面，LaunchStore 是持久化和对账中心，artifact 模块负责相对路径与预览。测试目录中 Discovery acceptance、artifact、observation、durable resume 和 research draft 相关文件，则是这些边界的可执行注释。

读代码时可以使用五个问题作导航：这个对象从哪里来？它被谁调用？它写回什么？失败传播到哪里？重启后凭什么重新得到它？只要每个关键对象都能回答这五问，代码细节就不会变成散乱的名字。

# 附录 D　终稿验收清单

长度方面，正文与附录合计应达到至少十万中文字符或等量字符规模；章节扫描应覆盖入口、任务规范化、外层循环、Session 状态、角色、运行时、工具、Draft、实验、指标、失败、恢复、记忆、观察、产物、测试和术语表。书中不再使用大段 Python 代码块，伪代码含义通过故事骨架、条件关系和字段血缘表达。

边界方面，PaperOrchestra 只作为可插拔的后续消费者被提及，不展开其编排、TeX、PDF 和论文审查逻辑；Discovery 的叙事终点固定为摘要与发现证据目录。任何章节若把论文输出当成 Discovery 必然产物，都应回到这一边界修订。

事实方面，应检查默认配置的叙述没有把数字写成永久定律，检查 fresh 与 incremental 的差异，检查实验 `run_0`、最近有效 `run_N` 和性能计算的关系，检查科学任务的 outputs 与 report 是否在增量更新中一起移动，检查失败候选是否保留而非被改写成成功。

可读性方面，每章先给情境，再给机制，再给对象和产物；避免连续堆叠三层以上标题，避免把参数清单当作叙事。对象名只用于定位，真正的解释围绕谁在何时做什么、状态如何改变、证据落在哪里展开。

EPUB 方面，应把终稿 Markdown 转成 XHTML，保留中文标题层级、表格、行内代码和段落顺序；生成 `mimetype`、OPF、导航和唯一元数据，校验 ZIP 可读、manifest 完整、spine 顺序稳定；最终文件与 Markdown 放在同一 docs 目录，文件名保持对应关系。

# 附录 E　不把故事误读成的十件事

第一，故事中的队长不是一个新的 Agent，而是外层编排逻辑的叙事称呼。第二，书记员不是另一套数据库，而是对持久化、日志和摘要职责的直觉化说法。第三，资料员不拥有科学真理，它只返回可供角色评估的外部证据。

第四，门牌不是 UI 标签，而是 WorkflowState 的状态合同。第五，工作台不是容器产品的专名，而是每个候选独立复制的代码目录。第六，接力棒不是一个神秘分数，而是最佳结果经过代码、指标和必要产物同步更新后的 baseline。

第七，等待反馈不是线程睡眠，而是可以被持久化、查询和恢复的状态。第八，经验不是模型的一句总结，而是有实验材料、来源和合并操作的长期记忆。第九，摘要不是论文结论，而是下一次恢复和人工审计可以共同读取的事实横截面。

第十，所谓“伪代码层面的颗粒度”不是让读者看到更多括号、参数和方法签名，而是让读者在不打开源代码的情况下仍能回答：哪个条件改变了路径，哪份数据成为了依据，哪个失败被隔离，哪种状态允许恢复，哪条证据最终写进了摘要。

# 后记　把一条流水线还给它的时间

最初的任务信只有一页，最后的证据却有许多层。它们不是因为系统喜欢复杂，而是因为研究问题会在运行中变成不同的东西：一份输入、一张卡片、一段批评、一条引用、一套方法、一间工作台、几个运行目录、一组指标、一条失败轨迹、一份经验和一张摘要。

如果只看最终答案，这些层似乎都可以省掉；如果要让别人相信答案、复现过程、解释失败、恢复中断，层与层之间的关系就不能省掉。本书选择故事化，是为了把关系放回时间里，让读者跟着任务一起走，而不是在一张参数表前停住。

愿下一位打开 Launch 目录的人，不必猜测哪一份文件是起点；愿下一位研究者看到失败时，知道它没有被抹掉；愿下一位工程师修改代码时，知道哪些边界是可扩展的，哪些不变量不能让步。Discovery 的全景，不是把系统说得更玄，而是把每一次选择、每一次等待、每一次复制和每一次落盘都说得足够清楚。

# 附录 F　事件剧场：同一套机制在不同天气里如何行动

## 剧场一：用户只上传了一张图

准备区收到研究文字和一张图片。保存动作可以成功，转换动作却发现 Execution Input 仍然缺少目标领域或约束。系统不会因为附件存在就启动 Launch；图片被保存为来源 blob，草稿保持可编辑，用户可以补全文字后重新转换。这个场景提醒我们，附件是输入的一部分，却不是任务定义的替代品。

## 剧场二：用户连续点击两次开始

两个 HTTP 请求带着同一个幂等键抵达。第一个请求通过 revision 校验并创建 Launch，第二个请求在锁内发现同一键和同一指纹，返回第一个响应。前端可能看到两次按钮反馈，后台只有一条运行。若第二个请求携带另一个 revision，系统返回冲突，迫使调用者换一个键明确表达新意图。

## 剧场三：转换成功后准备内容被修改

用户先得到 revision A，随后编辑研究文字但没有保存。启动请求仍指向 revision A，却发现当前准备 fingerprint 已经变化，于是被拒绝。旧 revision 可以继续被查看，新的草稿可以另存为 revision B。系统宁愿让用户多一次确认，也不把“页面上最新的一句话”和“后台使用的旧版本”混在一起。

## 剧场四：模型凭据在报告模式不可用

Launch 已经拥有 Session 和 Idea 文件，用户只想生成报告。外层延迟构造模型运行时，ReportWriter 直接消费已有候选，报告可以成功写出；如果用户选择实验模式，运行时才会在需要时构造并因凭据缺失而失败。只读的已完成材料因此不被新环境的凭据问题锁死。

## 剧场五：调查工具返回一篇不相关的论文

ScholarAgent 收到论文结果后仍要做相关性评估。它可以把论文留在搜索轨迹中，却不把它作为高相关 evidence 写入 Idea。方法阶段的 `paper_context` 只包含被角色整理过的证据。这个场景说明“搜到”与“采用”是两个动作，外部数据不会自动变成科学事实。

## 剧场六：反思员对一张卡片超时

并发任务中，Idea A 的反思返回，Idea B 的模型请求超时，Idea C 继续完成。实现若按单卡隔离，会给 B 写空批评或失败记录，按原列表顺序把 A、B、C 写回；其余候选继续演化。如果超时发生在共享模型服务初始化阶段，影响范围可能扩大到整批，日志要明确这是资源级失败而非单卡内容问题。

## 剧场七：演化员产生了孩子但没有写 changes

EvolutionAgent 返回子候选、改进说明和整体 changes。编排器把子候选文本、理由、轮次和 parent_id 写入 Idea，而把更长的 changes 留在轨迹中。未来读者想知道“孩子改了什么”，需要沿父子谱系和演化观察查看；不能假设所有响应字段都会自动进入卡片。

## 剧场八：排序服务把列表包成字符串

RankingAgent 返回的 scored_hypotheses 是一段 JSON 字符串。解析器先尝试解码，再校验每个候选的身份、分数、分项和理由。若字符串被截断，整个批次可以失败或被过滤，剩余批次仍可能成功；排序器不会把字符串的首尾字符当成候选内容。结构化输出的外观变化不会改变验证责任。

## 剧场九：方法卡的名称为空

方法角色返回 description 和 method，却没有 name。编排器可以用 Idea 文本的短前缀作为可读回退，并在字段中保留缺失事实；实验工作台因此仍有门牌，报告也能生成。回退名称不等于方法完整，审计者仍应看到 schema 缺失或 warning。

## 剧场十：实验后端在第二次运行前崩溃

候选工作台已有 `run_0` 和成功的 `run_1`，后端准备启动 `run_2` 时进程崩溃。结果对象记录失败，性能计算器仍可读取 `run_1` 的有效指标；若后端成功标志以最终整体状态为准，候选可能被标成失败，即使它有一条可比较的中间结果。两种信息都保留，外层不会把“曾经有结果”自动等同于“本次执行成功”。

## 剧场十一：最新运行指标为零

基线某指标为零，当前运行也为零。性能计算器跳过这个指标的相对改善率，而不是报告百分之零或无穷。其他非零基线的指标仍可比较，总体值只平均那些真正可计算的字段。读者看到性能对象为空或只含部分指标时，应把它理解为测量定义的边界。

## 剧场十二：并行候选写入同名文件

每个候选在自己的工作台中拥有独立的 `notes.txt`、日志和 run 目录，因此同名文件不会互相覆盖。公共结果列表按完成顺序追加，但每一条包含完整工作台路径。即使两个线程同时写出“final_info”，它们也写在不同根目录下；资源并发和文件归属被分成两道锁。

## 剧场十三：增量更新中途复制失败

最佳运行的 `final_info.json` 已经写入新的 `run_0`，但复制 code 目录时磁盘空间不足。更新函数记录失败，外层保留旧的 best_code_path，不把这份半更新目录作为下一轮 baseline。恢复者可以清理空间后重试，也可以用旧基线继续；摘要不会说一条尚未完成的接力已经交棒。

## 剧场十四：应用服务在等待反馈时重启

服务重启后，内存里的 waiting 事件消失，但 Session JSON 和 Launch 状态仍在。新的状态查询从磁盘加载并对账，公共观察继续显示等待反馈；用户提交 feedback 后，Interface 追加历史并恢复。没有任何 live await 被假定仍然存在，等待状态靠持久化事实重建。

## 剧场十五：用户读取一个符号链接产物

候选目录里有一个看似普通的链接，实际指向 Launch 根目录之外的秘密文件。artifact resolver 先规范化路径并检查真实目标是否位于允许根目录，发现逃逸后拒绝读取。列表也不应把链接目标的绝对位置返回给用户。产物浏览器的安全边界在解析阶段，而不是在页面显示阶段。

# 附录 G　常见追问：读者可以用这些问题检查自己是否真的理解

**为什么不直接把原始 prompt 每轮重新读取？** 因为任务目录可能被编辑，Launch 需要冻结本次输入；明确的提示演化有备份和周期，隐式重读没有。

**为什么普通任务没有 task_info 仍然可以运行？** 因为 auto 分支的最小输入合同是 prompt 和代码目录；入口通过文件存在性分流，不要求所有任务共享科学材料。

**为什么科学任务要生成合成 prompt？** 因为 MAS 角色消费统一 Task 结构，合成过程把数据项和 checklist 约束翻译到同一个上下文，而不改变原始任务文件。

**为什么 `run_0` 要复制到每个候选里？** 因为每个候选可能来自不同的增量代码起点，比较必须在候选自己的工作台内拥有明确零点。

**为什么不拿最后一个 `run_N` 直接比较？** 最后一个运行可能没有最终指标或在写结果前崩溃，最近有效运行才是可解释的当前测量。

**为什么性能对象允许为空？** 因为执行成功和指标可用是两层事实；空性能提醒读者测量链断开，不把缺失伪装为零。

**为什么总改善率只是平均值？** 当前实现需要一个跨候选的简单比较键，平均共同指标是它的结构化选择；真正的科学权重和“越小越好”语义仍属于任务定义。

**为什么失败候选不从 IdeaGraph 删除？** 因为失败是搜索历史的一部分，删除会让下一轮重复探索同一条路。

**为什么 feedback 不直接修改 Task？** 任务是签字后的研究问题，反馈是之后的意见；两者冲突时应可见地重新修订输入，而不是静默改变实验命题。

**为什么等待反馈也要写状态？** 因为进程可以退出、应用可以重启，只有持久化状态才能让外部意见在未来继续同一条走廊。

**为什么回调失败不改变 Session 状态？** 回调属于观察层，研究流程属于事实层；把旁观者的故障传回主流程会让 UI 问题变成研究失败。

**为什么长观察写 Draft，结构化状态写 JSON？** Draft 适合保留过程和轨迹，JSON 适合恢复和条件判断；一份文件无法同时满足两种形态而不变得笨重或模糊。

**为什么统一运行时要延迟构造？** 报告和只读恢复可能不需要模型凭据；延迟让已完成材料在受限环境中仍然可查看。

**为什么运行时要共享？** 生成与实验若各自选择模型，会让同一 Launch 的两阶段不再拥有同一能力边界，也难以审计。

**为什么搜索和模型要有不同并发限制？** 两者瓶颈不同，搜索服务的配额不等于模型 provider 的配额；分开控制才能准确调节。

**为什么并行结果可以按完成顺序收集？** 因为结果的身份不由列表位置决定，候选名称、工作台和性能字段才是归属；强行按提交顺序排序反而可能隐藏真实完成时序。

**为什么科学任务更新 baseline 时要搬 report？** 报告和图表是科学运行状态的一部分，脱离代码会让下一轮缺少上下文或引用旧文件。

**为什么 `loop_rounds` 可以在恢复时延长？** 恢复摘要只告诉系统已经完成到哪，当前配置可以明确要求继续做更多轮；旧轮次不会被重跑。

**为什么恢复不从最后一个目录名推断完成？** 目录可能只创建到一半，只有摘要、结果和可验证产物能证明轮次完成。

**为什么公共 artifact 不暴露 runner.log？** 运行器日志常含内部命令、路径和调试数据；用户需要的报告与摘要可以公开，内部诊断材料应保留在受控边界。

**为什么 artifact 读取必须绑定 Launch？** 同名任务和候选可能存在于多个运行，先绑定根目录才能防止跨 Launch 读取。

**为什么要拒绝非有限数字？** 无限或 NaN 会破坏 JSON 消费、排序和 UI 显示，不能成为研究指标。

**为什么启动请求只接受 preparation_id 和 revision_id？** 让用户先保存并转换输入，避免临时字段绕过准备和校验边界。

**为什么同一个幂等键不能换 revision？** 因为这会把一次重试身份变成一个任意命令通道，无法判断是重试还是新运行。

**为什么来源文件用 content_ref 而不是直接放字节？** 内容寻址能复用相同来源、保护公共快照不暴露私有字节，并让恢复检查内容是否仍然存在。

**为什么来源物化失败要清理孤儿 blob？** 半成品 Launch 不应留下没有引用、无法解释的私有输入；清理在锁内进行以避免误删其他 Launch 使用的内容。

**为什么终态不允许停止或恢复？** 完成或失败已经是历史事实，动作只能改变运行而不能改写历史；只读访问仍然开放。

**为什么报告生成成功不代表科学成功？** 报告只是把候选写成文本，未必有实验或有效指标；它的成功字段应和实验性能分开解读。

**为什么 PaperOrchestra 不在书里展开？** 它是发现结果的后续消费者，不是 Discovery 状态、实验和摘要闭环的必要齿轮。

**为什么本书仍然保留真实对象名？** 便于读者回到仓库核对，而不是要求读者记住一套完全虚构的人物系统。

**为什么不把每个 Python 参数列出来？** 因为参数清单能告诉人名字，却不一定告诉人因果、边界和失败；本书的颗粒度在机制关系。

**为什么故事需要写失败？** 失败决定恢复、基线、经验和科学结论的可信度；只写成功会把流程误解成一条没有分叉的流水线。

**为什么要把测试写进全景？** 测试把输入、恢复、安全、产物和运行时的边界变成可重复的契约，是系统机制的一部分。

**为什么一份摘要不能包含所有日志？** 摘要承担恢复和横截面统计，完整日志承担过程观察；混在一起会让两者都难以使用。

**为什么字段血缘值得单独讲？** 因为最终数字和最终状态若没有来源，读者无法判断它们是模型产物、代码结果、人工反馈还是默认值。

# 附录 H　把终稿转换成电子书时应保留的阅读节奏

Markdown 转 EPUB 时，书名、卷标题、章标题应进入导航目录；章节之间保留自然换页，但不要把每一段拆成一个独立页面。正文的引用、行内代码和表格需要使用适合中文排版的字体和行距，避免技术对象名被拆在奇怪的行尾。

每一幕适合作为导航的二级节点，每一章作为三级节点，附录保持独立节点。目录过深会重新制造技术报告式的嵌套，目录过浅又会让十万字文本难以定位；幕、章、附录三层已经足够。

电子书中应保留 `discovery_summary.json`、`run_0`、`AWAITING_FEEDBACK` 等行内代码的等宽效果，但不应把整段机制重新排成代码块。这样，读者能知道对象名是仓库中的真实索引，同时仍然以故事段落理解系统。

如果阅读器不支持中文表格的自动换行，字段字典可以降级为段落列表；内容不能被截断。EPUB 的 manifest、spine、nav 和 XHTML 必须经过 ZIP 完整性检查，`mimetype` 保持未压缩并位于压缩包首项，所有内部链接指向存在的章节文件。

## 电子书中的两种阅读路径

第一种是连续阅读：从任务信开始，跟随工坊经过输入、Session、实验、恢复和封存，适合第一次理解 Discovery。第二种是索引阅读：从术语表或字段字典进入，再跳回对应章节查看故事，适合已经熟悉仓库、只想核对某一机制的读者。

电子书不应把附录隐藏在正文之后的无名页面里。机制卡帮助快速复述，术语表帮助定位，源代码地图帮助回仓库，问答帮助确认理解，验收清单帮助检查交付。它们共同把一部长篇叙事变成可以反复使用的研究工具。

# 附录 I　关键机制链：每一行都是一条可以追问的因果

任务名 → 任务目录 → 任务类型：目录身份先被统一，再由 `task_info.json` 的存在性决定 auto 或 sci，后续所有分支都从这一事实出发。

任务类型 → prompt 来源：auto 复制原 prompt，sci 由 task_info 和 checklist 生成合成 prompt，缺输入时在门口失败，不让模型猜。

Launch 参数 → 输出目录：已有 launch 复用、恢复回旧目录、新运行创建时间目录，三条路都要留下本次输入快照。

输入快照 → Task：任务描述、领域、背景、约束和参考代码被统一包装，Agent 不再关心材料最初来自哪个文件。

配置 → 计数器：外层 loop rounds、内部 max iterations、top ideas 数量和实验 max runs 各自进入自己的时钟，不能互相借义。

恢复摘要 → start round：只把真正有完成证据的轮次算入已完成，半成品目录和没有结果的 Session 不会偷走下一次起点。

Launch 快照 → 模型目录：运行时读取冻结的能力身份，避免恢复时全局模型设置改变同一个 Launch 的能力边界。

统一运行时 → Agent：角色只声明需要文本、结构化输出、搜索或嵌入，适配器和 provider 选择在运行时内部完成。

AgentFactory → 角色注册表：未知角色在装配期暴露，已知角色获得自己的提示、工具和配置，编排器消费共同的 execute 合同。

execute 门禁 → 结构化结果：角色先检查上下文，再调用模型，最后验证 schema；自然语言的完整感不能替代字段合同。

工具请求 → 工具执行 → 工具结果：循环器保留名称、输入、输出和错误，模型可以继续调查，但上限和终止原因必须记录。

Session 创建 → MemoryManager：任务卡、会话卡和起始状态先落盘，后续每个阶段才能有可靠的恢复身份。

INITIAL → GENERATING：状态变化是一个可观察事件，不是一个 UI 进度条；失败时要写 error，不用空 Idea 伪装继续。

生成上下文 → hypotheses：目标、反馈、轮次和可选论文被交给生成员，返回的文本和理由成为第一版 Idea。

Idea → 反思：反思员只拿到合适的候选快照和作用范围正确的反馈，输出普通批评或方法批评，不混写两个阶段。

Idea → ScholarAgent：资料员根据目标和候选生成查询，外部证据经过相关性评估后才进入 evidence 或 refine_evidence。

critique + evidence → EvolutionAgent：父卡片的批评和证据形成子卡片的上下文，parent_id 保留谱系，失败只隔离对应分支。

候选批次 → RankingAgent：排序器逐批返回分项和理由，解析、校验、合并、排序之后才写 top_ideas。

top_ideas → MethodAgent：只有被选中的候选进入方法开发，方法字段把研究方向翻译成执行步骤和评价方式。

METHOD_DEVELOPMENT → method_phase：一旦进入方法阶段，后续反思、搜索和精炼写入独立字段，早期证据仍然保留。

AWAITING_FEEDBACK → feedback_history：等待是持久化插槽，人工或离线文件注入意见，再由 Interface 触发恢复。

method_details → RefinementAgent：精炼只接收非空方法，失败可保留原方法并附错误，空卡片不进入实验。

Idea → refined_method_details：精炼后的方法优先作为实验委托单，缺失时才退回较早字段，并保留回退事实。

委托单 → ExperimentRunner：候选名称、描述和方法进入独立工作台，Session ID 负责把实验结果接回正确会话。

base_dir → candidate folder：复制基线而不是直接修改原目录，确保外部后端的代码、输出和失败日志不会污染其他候选。

candidate folder → run_0：复制实验脚本和 final_info，形成当前候选自己的比较零点，避免不同起点互相借用指标。

run_0 + run_N → performance：读取共同数值字段，跳过不可转换和零分母，产生逐指标改善率和总体值。

后端成功 + 无指标 → success 与 performance 分离：命令完成不等于测量完成，空性能保留断裂证据，不写假零值。

GPU allocator → backend：先分配资源再启动后端，环境变量和信号量一起保护并行实验不超卖设备。

后端异常 → result.error：单候选异常写入自己的结果和工作台，外层仍可统计其他候选；共享资源失败则记录更大影响范围。

成功结果 → online memory：实验完成后才保存 Idea、结果和轨迹，记忆失败不回滚工作台，但会留下 warning。

Round results → experience generation：先封存轮次事实，再让经验生成器读取 ideas、notes 和指标，避免记忆读到半成品。

successful results → best result：只在成功候选中比较总体改善率，没有有效候选就保持原基线。

best run → updated baseline：代码、run_0 指标、run_0/code 以及科学任务的 outputs、report 一起前移。

fresh → original task code：长期记忆可继续存在，但下一轮代码不继承上一轮工作台，便于做独立重复。

incremental → previous best code：代码起点前移，prompt 和任务身份仍由 Launch 快照管理，研究命题不随复制悄悄改变。

rounds + sessions + results → discovery_summary：摘要保存可恢复横截面，不把全部 Draft 和日志复制成巨型文件。

Preparation → revision：保存、转换、指纹和当前性检查构成启动资格，未保存编辑不能通过 API 偷渡。

revision + idempotency key → Launch admission：同键同指纹重放，同键不同指纹冲突，网络重试不会制造重复运行。

source blob → content_ref：来源字节留在私有内容寻址区域，公开快照只保留引用和描述，恢复时重新确认存在。

LaunchStore → observation：磁盘、运行器标记和索引经过对账后投影成公共状态，不把旧内存当作权威。

artifact list → relative path：文件先绑定 Launch 根目录，再允许预览；绝对路径、`../` 和符号链接逃逸被拒绝。

completed 或 failed → read-only history：终态保留摘要、错误和产物，停止与恢复动作关闭，历史不能被重写。

ResearchDraft.append → immutable block：并发追加保持块完整，过程叙述可继续增长，原来的观察不被覆盖。

tests → invariants：测试把启动校验、共享运行时、失败保留、产物安全、幂等和恢复从口头约定变成可重复契约。

字段血缘 → 审计问题：任何最终值都应能回答谁写入、何时写入、依据什么、能否由另一个产物复核。

# 附录 J　交付前的最后一页

在把这本书交给读者前，先确认终稿文件确实是当前版本，章节编号连续，正文和附录的标题能被 Markdown 解析器识别，表格闭合，行内代码没有被错误转义，全文没有遗留的大段 Python 伪代码块。若某章仍像接口文档，应优先改写因果和故事，而不是继续增加字段列表。

再确认覆盖范围：从任务输入开始，读者能找到普通与科学任务分流、Launch 建立、prompt 和配置快照、模型运行时、AgentFactory、工具循环、Session 状态、Idea 谱系、反馈插槽、方法开发、实验工作台、run_0 与 run_N、指标、资源、失败、增量基线、长期记忆、公共观察、产物安全、恢复、测试和摘要终点。

最后确认电子书转换不会重新把正文变成技术手册。EPUB 只改变容器和导航，不改变本书的叙事语气；对象名继续作为索引，机制继续以故事、条件、状态和证据解释。读者可以在地铁上连续读，也可以在仓库旁边按术语跳读，两种路径都应得到同一套 Discovery 因果链。

当这三页都被勾上，书记员才把文件名从“草稿”改成“终稿”。她知道终稿仍可以被未来的代码变化修订，但这一版至少没有把代码行数误当成机制颗粒度，也没有用小说的抒情掩盖输入、状态、失败和恢复的硬边界。

# 附录 K　研究工坊值班手册：十二次交接时应该说清楚的话

## 交接一：我接到的是什么任务

值班者不要只说“这是一个分类任务”或“这是一个科学复现”。应说明任务目录、任务名称、任务类型如何判断，普通任务是否有 prompt 和 code，科学任务是否有 task_info、数据和 checklist。下一位接班人首先要知道自己拿到的是哪一个输入事实，而不是哪一个模糊主题。

## 交接二：这次 Launch 看见了什么

说清 prompt 快照的位置、配置快照的位置、模型目录的规范身份、loop rounds、loop mode、实验后端和输出目录。若提示曾经演化，还要指出备份文件和发生轮次。没有这些信息，后续读者会把当前全局设置误认为这次运行的设置。

## 交接三：已经完成到哪一轮

不要只看最大的轮次目录名。检查摘要的 rounds、每条结果的成功和失败、Session JSON 的状态、摘要时间和轮次是否完整。若恢复要从 Round 3 开始，必须能指出 Round 1 和 Round 2 的完成证据，以及 Round 3 为什么没有被算入已完成。

## 交接四：Session 现在站在哪扇门前

说清 Session ID、WorkflowState、iterations_completed、max_iterations、top_ideas、method_phase、feedback_history 是否为空，以及最后一次状态变化的原因。若是 AWAITING_FEEDBACK，说明它等待的是全局意见、局部意见还是离线文件；若是 ERROR，说明错误是否可重试。

## 交接五：哪些 Idea 仍然活着

列出当前迭代的候选数量、top IDs、父子关系和各自证据。不要只报一个“有五个候选”，还要说其中几张只有方向、几张有方法、几张已经有精炼结果。候选的成熟度决定下一步是继续反思、请求资料、开发方法还是进入实验。

## 交接六：实验工作台的边界在哪里

给出每个候选的工作台路径、notes、run_0、最近有效 run、后端、GPU 信息和日志位置。若使用并行，说明结果列表是按完成顺序还是按提交顺序收集。接班人应能从路径直接找到“这张卡试图验证什么”和“它实际改了什么”。

## 交接七：性能数字从哪里来

说明 baseline final_info 和当前 final_info 的路径，列出共同指标、被跳过的指标、基线为零的指标以及总体改善率的计算依据。不要只说“提升了 3%”，要说是哪些字段平均出 3%，是否存在损失方向相反、清单未完成或输出缺失的情况。

## 交接八：最佳接力棒是否真的交出

如果是 incremental，说明被选中的候选、选择时的总体改善率、代码复制是否完成、run_0 指标是否更新、科学任务的 outputs 和 report 是否同步。若复制途中失败，明确下一轮仍使用哪个旧路径。接力棒的名字不如接力动作的完成证据重要。

## 交接九：长期记忆是否介入

说明 Task Memory、IdeaGraph、online memory、经验库和 PromptEvolver 是否可用，历史加载了多少 Idea 和实验，最近一轮是否生成新经验，下一轮是否计划提示演化。记忆不可用时，主流程是否降级继续也要写清；未来读者才能判断候选差异来自任务，还是来自历史指导。

## 交接十：公共观察允许别人看到什么

列出可见状态、允许动作、可读报告和摘要，不要把内部 runner.log、绝对路径、源文件字节或私有来源 blob 当作公共产物。若用户报告读取失败，先检查 Launch 绑定和相对路径，再检查文件是否存在，不要建议用户直接拼服务器路径。

## 交接十一：如果机器现在断电，回来从哪里接

给出恢复命令或 Launch resume 身份，说明最后可靠的摘要、Session JSON 和运行器标记位置。指出哪些工作台已经完成，哪些可能只留下半截 run，哪些动作可以安全重试。恢复交接的核心不是“再跑一次”，而是“知道哪些事情已经发生过”。

## 交接十二：下一位最应该问的一个问题

每次值班结束，留下一个尚未解决但有证据的问题：某个候选为什么没有指标，某条反馈是否改变了生成分布，某个科学清单项为何缺失，某个并发限制是否造成超时，某份经验是否应该更新。问题要指向文件、字段或阶段，而不是泛泛地写“继续观察”。这样，下一次 Discovery 才会从理解过的历史出发，而不是从一片无名的日志里重新猜。

值班手册的最后一句仍然是本书最重要的提醒：系统可以自动推进，但不能自动制造已经发生的事实。每一次交接都把事实、证据、未知和下一步分开说清，故事才不会变成传说。

# 附录 L　从一个工作台读懂一整个候选

打开候选工作台，第一眼看到的通常是一个带时间和名称的目录。不要急着进入最深处。先看 `notes.txt`：它告诉你候选的名字、标题、描述和方法，也告诉你这是从哪个研究想法翻译过来的。如果 notes 缺失或内容为空，后续所有运行文件都需要谨慎解读，因为你可能只看见了一间没有门牌的房子。

接着看根目录的代码和实验脚本。它们代表外部后端开始修改以前的候选状态；若这个目录来自 incremental，代码可能已经不是原任务的原始版本，但应该能沿着上一轮的最佳路径回溯。根目录不是最终结果，它只是“当前候选可以被改变成什么样”的起点。

进入 `run_0`，读取实验脚本和 `final_info.json`。这两个文件回答“比较的零点是什么”。如果 `run_0` 只有指标没有代码，或者代码与基线脚本不一致，性能数字就需要额外解释；规范的工作台会把零点的代码和指标一起保存，以便重新运行和审计。

再按时间或编号查看 `run_1`、`run_2` 等目录。每个目录可能有修改后的 code、日志、最终信息和异常记录。最新并不自动等于有效；先找到最近一个完整的 `final_info.json`，再把它与运行日志中的最后一次成功动作对应起来。若最后一次尝试失败，仍然保留它，因为失败说明后端走到过哪里。

如果候选是科学任务，还要进入 `outputs/` 和 `report/`。图、表、数据摘要和报告不是“实验完成后顺手生成的附件”，而是任务是否满足约束的证据。一个性能数字改善但报告缺少关键图表的候选，可能在研究指标上成功、在任务验收上失败；这两个结论应同时记录，而不是互相覆盖。

然后看 log 和 Draft。日志提供阶段、后端、GPU、超时和错误，Draft 提供模型与工具的长观察。它们解释为什么代码变成当前样子，但不应被直接当作指标来源。指标仍应回到 final_info，状态仍应回到 Session 和摘要，过程材料负责连接因果。

如果候选结果标记为成功，继续追踪 performance：基线指标、当前指标、逐指标改善率和总体值是否齐全？如果标记为失败，先读 error 和 traceback，再看是否有部分有效 run。成功字段与性能字段分离，正是为了让你能在同一工作台里看到“执行发生过”和“测量是否成立”两件事。

最后回到 Session 目录，确认这张卡在 Idea 列表中的身份、评分、父节点、反馈和证据。工作台是代码和实验的近景，Session 是候选在研究流程中的中景，Launch 摘要是整个运行的远景。三层拼起来，才是一张完整的候选肖像。

如果你需要把候选交给另一位研究者，最小交接包应包含：Launch ID、Session ID、Idea ID 或名称、工作台路径、基线和当前指标来源、成功或失败原因、相关 prompt 版本、关键反馈以及需要人工确认的问题。只传一段方法文字，会让对方失去实验和输入上下文；只传一个结果数字，会让对方无法判断它是否可复现。

一间好的工作台不会替你作出科学判断，却会让判断有地方落脚。你可以不同意候选的方法，可以质疑指标的方向，可以认为报告不完整；但你不必再猜测它从哪里来、改了什么、相对于什么比较、失败在哪一层。这正是隔离目录、状态机和证据链共同提供的价值。

# 附录 M　交叉检查：当两个边界同时发生变化

## 输入变化和代码变化同时发生

用户可能在上一轮实验后修改研究文字，同时最佳代码也已经被增量模式前移。下一次启动不能只问“代码从哪里来”，还要问“任务问题是否还是同一个”。代码路径由 baseline 逻辑决定，研究文字由 revision 和 prompt 快照决定；若两者的任务指纹不再匹配，最安全的动作是建立新的 Launch，而不是把新问题套在旧代码上。

这类交叉变化在人工工作中很常见：研究者看见第一轮结果后改变约束，工程师同时修复了数据加载。系统若只保存最终代码，会让未来读者以为第二轮仍然在验证第一轮的问题；系统若只保存新 prompt，又会让第二轮的改善率失去旧代码的参照。输入快照和 baseline 快照必须各自完整，才能在复盘时把两条变化线分开。

## 模型变化和提示变化同时发生

PromptEvolver 可能在某一轮替换提示，Launch 恢复又可能发现全局模型设置已经改变。模型目录和 prompt 备份应当分别记录：提示告诉我们“问题怎样被提问”，模型目录告诉我们“谁来回答”。两者同时改变时，摘要和日志要能说明发生的轮次与原因。

如果恢复使用了旧 prompt 却切换到新模型，结果仍可能有意义，但不能和原运行被当作完全同分布的重复。科学上是否允许这种替换，要由任务和实验设计决定；系统层面至少要把替换事实暴露出来，让人有机会重新评估。

## 反馈和经验同时进入下一轮

轮末经验生成会把实验失败转成检索线索，外部反馈又可能要求下一轮优先考虑另一条约束。生成上下文同时包含 feedback_history 和从长期记忆检索到的 guidance，但二者的来源必须分开。反馈是本次运行的人类意见，经验是过去多次运行的概括；如果把它们拼成一段没有来源的文字，角色无法判断哪条是硬约束、哪条只是参考。

经验库更新也不能覆盖当前反馈。即使旧经验说某方法通常有效，本轮用户也可以要求暂时不采用它；即使旧经验说某方向失败，本轮新证据也可以让它重新进入讨论。记忆提供偏置，反馈提供当前意图，任务约束仍然位于两者之上。

## 并行执行和人工观察同时发生

用户可能在并行实验还未全部结束时打开运行台。公共观察应显示已完成、运行中、失败和等待中的候选分布，而不是等整轮结束才返回一张静态结果。服务器对账时要避免把“尚未出现 final_info”误当作失败，也要避免把已退出的进程继续显示为运行中。

前端的进度文案可以说“3 个候选已回收，2 个仍在运行”，但摘要只有在轮次封存后才写最终成功数。中间观察和最终摘要的粒度不同，却都来自同一组工作台事实。用户如果在中途刷新，看到的数字可能变化；这不是不一致，而是生命周期不同。

## 科学清单和性能指标同时变化

一个科学候选可能提高总体性能，却没有完成 checklist 中的一项图表；另一个候选性能略降，却满足了所有复现要求。Discovery 不替任务决定如何权衡这两种结果，而是把 performance、report 和 checklist 证据并列保存。排序器可以在早期使用配置的评分标准，人工复盘可以在最终验收时采用更严格的科学判断。

如果把清单是否通过直接折叠成一个 success 布尔值，下一轮的经验会失去“指标改善但验收失败”的模式。更好的叙事是：执行成功、测量可用、任务验收三个层次同时存在，任何一个层次都可以成为下一轮需要修正的线索。

## 共享记忆和 Launch 隔离同时发生

两个 Launch 处理同一任务时，可以共享历史 Idea 和经验库，却不能共享正在写入的 Session 或候选工作台。IdeaGraph 扫描历史文件时要容忍旧格式和重复节点，当前 Launch 写入时则要使用自己的目录和身份。共享是为了学习，隔离是为了归属；把两者都放在一个平面目录里会让“来自过去”和“正在发生”混成一团。

经验生成在轮末读取共享目录时，还要确认它读到的是已经封存的结果，而不是另一个同时运行的 Launch 的半成品。目录命名、Session ID 和轮次摘要共同提供过滤依据；如果无法确认文件属于哪次运行，宁可跳过也不要把它写成当前经验。

## 失败重试和幂等恢复同时发生

外部后端可能在一次运行失败后被自动重试，应用层也可能因为网络重试发送 Resume。两种重试的对象不同：后端重试可以产生新的 `run_N`，Resume 重试应该指向同一个 Launch 状态。日志和结果要能区分“同一动作被重新请求”和“候选在同一工作台里进行了新的实验尝试”。

如果一个恢复请求触发了第二个外部进程，而第一个进程其实仍然在运行，两个进程可能同时修改同一工作台。LaunchStore 的幂等和运行器标记必须在恢复入口挡住这个竞态；工作台内部的 run 编号不能替代 Launch 层的动作锁。

## 旧目录格式和新恢复逻辑同时存在

IdeaGraph、MemoryManager 和恢复扫描都可能遇到历史 Launch 的旧结构，例如 `session_*/ideas.json`、旧的 `ideas_*.json` 或不同的字典键。兼容读取可以接受多种输入形状，但写出时应选择当前稳定格式，并在日志中标明发生了兼容回退。

兼容不是无限期地猜。若旧文件缺少身份、轮次和时间，系统可以补一个可追踪的临时 ID，但不能把缺失的科学结论补出来；若旧摘要与当前目录互相矛盾，恢复应停在需要人工确认的边界。迁移的目标是延长证据寿命，不是让所有损坏文件都看起来完整。

## 公共产物和内部诊断同时需要同一文件

`summary.json` 可能需要对用户开放，`runner.log` 可能需要工程师诊断。最稳妥的方式不是复制两套互相漂移的文件，而是在读取层定义不同的视图：公共视图只返回允许字段和相对路径，内部视图可以在受控权限下读取更详细的日志。两种视图都指向同一个 Launch 根目录和同一份事实。

如果公共视图把内部错误文字完全删掉，用户可能只看到“失败”；如果把内部命令和绝对路径全部公开，又会扩大安全边界。可以公开错误的类别、阶段、候选和建议动作，把敏感细节留给内部日志。透明度的目标是帮助用户采取下一步，而不是让所有内部字节都变成公共资料。

## 版本升级和旧摘要同时存在

当代码升级了字段名或状态枚举，旧 Launch 仍然可能被读取。向后兼容层可以把旧字段映射到当前对象，再按新格式写出，但必须保留原始身份和版本线索。恢复成功不代表旧状态与新状态完全等价，摘要和日志应显示发生过兼容转换。

如果状态枚举从一个房间拆成两个房间，旧摘要可能只能定位到较粗的门牌。系统可以从 Session JSON、Draft 和目录产物推断更细位置，但推断出来的部分应标为恢复观察，而不是伪装成旧运行曾经写下的事实。版本迁移越诚实，未来审计越容易。

## 交叉检查的结论

复杂系统的难点往往不在单个模块，而在两个模块同时改变时谁拥有解释权。输入与代码、模型与提示、反馈与经验、并发与观察、指标与清单、记忆与隔离、重试与恢复、旧格式与新逻辑、公共视图与内部诊断、版本升级与历史摘要，都是会产生这种交叉的地方。

全景写作的任务，就是为每一个交叉点画出边界：哪些事实必须来自快照，哪些动作必须幂等，哪些结果可以局部失败，哪些字段只能被一个角色写入，哪些产物可以公开，哪些变化必须被明确标注。边界画得越细，故事越容易讲，系统也越容易被修改而不失去自己的形状。

# 最后一页　给未来版本的作者

未来的作者也许会为 Discovery 增加新的阶段、新的外部执行器，或者把长期记忆迁移到另一种存储。开始修改以前，请先问三个问题。这个新东西属于输入、状态、能力、实验、记忆还是观察？它需要建立哪一个新的事实边界？它失败时应该隔离一张卡、一轮、一个 Launch，还是整个服务？

如果答案清楚，就给它一个能被恢复和审计的身份，写明输入从哪里来、产物写到哪里、哪些字段允许为空、哪些状态可以转移、哪些动作需要幂等。不要只在成功路径里接入新组件，也不要把异常全部交给一个总 catch。一个新组件只有在失败、重试、并发和重启时仍然有清楚的行为，才真正成为 Discovery 的一部分。

也请保留这本书的写法。把代码对象作为路标，把系统行为转译成研究工坊里的人、门、卡片、工作台和账本；用故事解释因果，用结构化产物证明事实。不要重新堆出一串难以呼吸的参数表，也不要为了通俗而删掉状态、异常和恢复。严谨与易懂并不是两条互斥的路，它们在机制边界处可以相遇。

每一版终稿都应重新检查字数、章节、关键词、PaperOrchestra 边界和 EPUB 结构；也应重新对照代码与测试，确认没有把旧实现当成新事实。书是系统的镜子，镜子可以有叙事的光线，却不能把门牌照成别的名字。

当未来的运行结束，新的摘要写下最后一行，新的作者也许会在旧 Launch 旁边再建一间房。那时，愿这本书仍能让他知道从哪一扇门进入，为什么要留下 `run_0`，哪些失败不该被删除，哪一条反馈曾经改变了方向，以及在所有模型回答之外，什么才是 Discovery 真正留下的证据。

## 终稿自检的叙事版本

把书摊在桌上，先问任务信有没有被接住；如果没有，入口章节还不够清楚。再问队伍有没有被组织起来；如果没有，Session、状态和角色章节还在说概念。再问候选有没有走到代码房间；如果没有，方法开发、工作台和 `run_0` 章节还缺桥。再问数字有没有来源；如果没有，性能和字段血缘还不够具体。再问失败能不能被找到；如果不能，错误、恢复和测试章节还不完整。最后问读者能不能在没有源代码的情况下复述整条流程；如果不能，叙事还需要变得更顺。

这份自检不要求每一章都出现同样的对象名，也不要求每个函数都有对应段落。它要求的是覆盖关系：输入会变成什么，状态会推动谁，候选会在哪些房间变厚，实验会以什么为零点，结果会被谁选择，失败会被写到哪里，恢复会从什么证据开始，下一轮会继承什么而不继承什么。只要关系完整，文字就可以自由而通俗。

在 EPUB 里再做一次同样的自检：章节能否顺序阅读，附录能否从导航进入，表格是否没有丢行，行内代码是否仍然可辨，中文标点和英文对象名是否没有粘连。电子书不是一个压缩后的文件夹，而是另一种阅读现场；它应该让人继续感到自己站在工坊里，而不是落进一份失去呼吸的导出报告。

此刻，工坊里的灯已经全部亮过一遍。接待台确认输入，状态门牌引导队伍，资料员和反思员围着 Idea，方法员把方向翻成步骤，实验员守着 `run_0`，测量员读出性能，书记员封存轮次，值班者为下一轮交接。故事结束，机制仍在运行；正因为机制可以被重新走过，故事才值得写下。

如果读者只记住一张纸，可以记住这张纸上的六个箭头：输入 → Session，Session → Idea，Idea → 工作台，工作台 → 指标，指标 → 基线，基线 → 下一轮。每个箭头旁边再写三个词：条件、产物、失败。输入在什么条件下进入 Session，Session 产生什么 Idea，Idea 如何成为工作台，工作台留下什么指标，指标怎样改变基线，基线如何影响下一轮；每一步失败时，谁停下，谁继续，什么被保留。

这六个箭头覆盖了书中看似分散的对象。prompt、Task 和 revision 属于输入；WorkflowSession、WorkflowState 和 Interface 属于 Session；Idea、evidence、score、method_details 属于候选；ExperimentRunner、candidate folder、run_0 和 backend 属于工作台；final_info、performance 和 notes 属于指标证据；fresh、incremental、memory 和 prompt evolution 属于下一轮。读者可以用它检查任何新增模块应该落在哪个边界。

而故事里的最后一盏灯，照见的是边界之外的谦逊：Discovery 能把研究过程组织得更清楚，却不能替研究者决定哪个指标最重要；能保留成功和失败，却不能把失败解释成必然的理论；能让外部模型和工具更有效率，却不能把模型的回答升级成事实。系统留下的不是权威，而是足够完整的证据，让人有资格做判断。

所以，本书的终稿并不以一句“系统完成”收尾，而以一份可继续工作的交接收尾。下一轮、下一位研究者、下一次模型升级，都可以沿着这些箭头重新进入；它们会看到输入的来源、状态的门牌、候选的谱系、工作台的零点、指标的血缘、失败的痕迹和恢复的路径。故事被保存下来，流程便不再只属于运行它的那一刻。

愿这份交接在电子书中仍然完整，在 Markdown 中仍然可检索，在仓库里仍然能对应真实对象；愿读者无需逐句翻译代码，也能在每一次分叉前知道为什么，在每一次失败后知道怎么办，在每一次恢复时知道凭什么。到这里，十万字的容量不只是长度证明，也是一种承诺：系统的细节值得被耐心讲完。

如果有一天读者合上书，仍能复述“输入被确认、状态被推进、候选被加厚、实验被隔离、指标被比较、基线被选择、证据被封存”，那么本书已经完成了它最重要的工作。其余的对象名、目录名和配置名，都可以沿着这条主线回到代码中逐一核对。

而这条主线之所以可靠，是因为它同时容纳了顺利和不顺利的时刻：有的任务在入口被拒绝，有的候选在反思后消失，有的实验没有指标，有的恢复找回了半途状态，有的经验来自一次失败。故事没有把这些岔路剪掉，系统也没有。读者看到的不是一条被美化的直线，而是一座仍然允许真实研究发生的工坊。

于是，终稿的最后一个事实也被写下：Discovery 的可理解性，不来自删去复杂，而来自为复杂安排清楚的位置。

输入有入口的位置，状态有门牌的位置，候选有卡片的位置，实验有工作台的位置，失败有档案的位置，恢复有证据的位置，摘要有封存的位置。读者沿着位置前进，就能把一座庞大的系统读成一段有因果的故事。

这便是本次修订希望交付的阅读体验：细节没有被省略，只是被安排进了故事。

故事至此闭合，机制仍然开放。

读者可以从任何一扇门重新进入。

门牌、账本、工作台和摘要会把他带回同一条因果链。

这条链可以被验证，也可以被继续书写。

终稿的旅程到此交付，但它不是把读者送到一扇锁死的门前。它把钥匙留在输入快照、状态门牌、Idea 卡片、实验工作台、失败档案、恢复摘要和经验库里。读者可以从任意一处重新进入，也可以把新的实现、新的实验和新的问题接到这条因果链上。只要这些位置仍然清楚，Discovery 就仍然是一座可以被理解、被复核、被修订的研究工坊。
