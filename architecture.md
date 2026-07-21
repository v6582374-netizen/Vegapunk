# Vegapunk 项目流程架构

本文档基于当前代码图谱和源码实现整理，重点覆盖启动入口、发现实验主循环、多智能体编排、深度研究 QA、模型/工具/记忆、实验执行、MCTS 和任务目录结构。

## 总览架构图

```mermaid
flowchart TB
    User["用户 / CLI"] --> Launch["launch.py::main<br/>按 --mode 分发"]
    Launch --> QA["launch_qa.py::main<br/>一次性研究问答"]
    Launch --> Discovery["launch_discovery.py::main<br/>自主发现实验流水线"]

    subgraph Config["配置与运行参数"]
        DefaultCfg["config/default_config.yaml<br/>memory / agents / workflow / experiment"]
        Catalog["config/model_catalog.yaml<br/>providers / bindings / capabilities"]
        Env[".env<br/>API keys 和兼容端点"]
        Prompt["tasks/*/prompt.json 或 sci_task 归一化 prompt.json"]
    end

    subgraph MAS["Vegapunk MAS 核心"]
        Interface["VegapunkInterface<br/>系统生命周期与会话接口"]
        AgentFactory["AgentFactory<br/>创建并缓存业务 agent"]
        ModelRuntime["UnifiedModelRuntime<br/>解析 Catalog 并执行请求"]
        Orchestrator["OrchestrationAgent<br/>WorkflowSession 状态机"]
        DataTypes["data_type.py<br/>WorkflowState / Task / Idea / WorkflowSession"]
    end

    subgraph Agents["顶层业务 Agent"]
        Generation["GenerationAgent<br/>生成 hypotheses"]
        Survey["SurveyAgent<br/>初始文献/网页调研"]
        Reflection["ReflectionAgent<br/>批评 idea 或 method"]
        Scholar["ScholarAgent<br/>检索证据与引用"]
        Evolution["EvolutionAgent<br/>进化 hypotheses"]
        Ranking["RankingAgent<br/>多标准评分选 Top ideas"]
        MethodDev["MethodDevelopmentAgent<br/>idea -> method_details"]
        Refinement["RefinementAgent<br/>method -> refined_method"]
        DRAgent["DRAgent<br/>深度研究 workflow 适配"]
        Experience["ExperienceAgent / PromptGeneratorAgent<br/>经验总结与 prompt 演化"]
    end

    subgraph Infra["模型、工具与记忆基础设施"]
        Models["BaseModel / Runtime-bound model / embedding binding"]
        Tools["vegapunk.mas.tools<br/>literature_search / web_search / memory_retrieval / MCP"]
        Memory["memory<br/>MemoryManager / TaskMemoryLayer / OnlineMemorySaver / MemoryModule / IdeaGraph"]
    end

    subgraph Execution["实验与产物"]
        Stage["stage.py<br/>IdeaGenerator / ExperimentRunner / ReportWriter"]
        Backends["experiments_utils_*<br/>claudecode / iflow / openhands"]
        MCTS["mcts_experiments_utils_* + mcts_node.py<br/>可选 MCTS 搜索"]
        Tasks["tasks/Auto* 与 sci_tasks<br/>code / launcher.sh / final_info.json"]
        Outputs["results/<task>/<launch_id>/<session_id><br/>ideas.json / traj.json / run_* / reports / discovery_summary.json"]
    end

    QA --> DRAgent
    Discovery --> DefaultCfg
    Discovery --> Prompt
    Discovery --> Stage
    Stage --> Interface
    Interface --> AgentFactory
    Interface --> ModelRuntime
    Interface --> Memory
    Interface --> Orchestrator
    Orchestrator --> DataTypes
    Orchestrator --> Generation
    Orchestrator --> Reflection
    Orchestrator --> Scholar
    Orchestrator --> Evolution
    Orchestrator --> Ranking
    Orchestrator --> MethodDev
    Orchestrator --> Refinement
    Generation --> Survey
    Agents --> Models
    Agents --> Tools
    Agents --> Memory
    Stage --> Backends
    Stage --> MCTS
    Backends --> Tasks
    MCTS --> Tasks
    Stage --> Outputs
    Memory --> Outputs
```

## 发现实验主流程

```mermaid
flowchart TD
    A["launch_discovery.main()"] --> B["setup_logging() / parse_arguments()"]
    B --> C{"--resume ?"}
    C -- 是 --> C1["load_resume_state()<br/>恢复 completed_rounds / sessions / best_code_path"]
    C -- 否 --> C2["新建 results/<task>/<timestamp>_launch"]
    C1 --> D["解析 task_dir / task_name"]
    C2 --> D
    D --> E["detect_task_type()<br/>auto: prompt.json<br/>sci: task_info.json"]
    E --> F["准备 ref_code_path 与 prompt_path<br/>sci 通过 normalize_sci_task() 生成 prompt"]
    F --> G["加载 config/default_config.yaml"]
    G --> H["读取 workflow.loop_rounds / loop_mode<br/>skip_idea_generation 时强制单轮"]
    H --> I["初始化 Long Memory<br/>MemoryModule 加载历史 ideas 和 experiment notes"]
    I --> J["for round_num in start_round..loop_rounds"]

    J --> K{"incremental 且已有 best_code_path ?"}
    K -- 是 --> K1["base_code_dir = 上轮最优代码目录"]
    K -- 否 --> K2["base_code_dir = 原始任务目录"]
    K1 --> L{"跳过 idea 生成 ?"}
    K2 --> L

    L -- 是 --> L1["从 --idea_path 读取已有 ideas"]
    L -- 否 --> L2["IdeaGenerator.generate_ideas()<br/>驱动 MAS 会话直到 completed"]
    L2 --> L3["保存 session/ideas.json<br/>复制 traj.json<br/>生成 ideas_visualization.pdf"]
    L1 --> M{"--mode report ?"}
    L3 --> M

    M -- 是 --> N["ReportWriter.generate_reports()<br/>按 idea 生成 markdown 报告"]
    M -- 否 --> O["ExperimentRunner.run_experiments()<br/>顺序或 ThreadPool 并行执行"]
    O --> P["run_claude_experiment / run_iflow_experiment / run_openhands_experiment"]
    P --> Q["计算 final_info 指标提升<br/>OnlineMemorySaver.save_idea_result()"]
    N --> R["记录 round_result"]
    Q --> R
    R --> S["MemoryModule + ExperienceGenerator<br/>每轮后生成经验库"]
    S --> T{"还有下一轮 ?"}
    T -- 是 --> U{"loop_mode == incremental ?"}
    U -- 是 --> U1["_find_best_experiment_result()<br/>_update_baseline_for_incremental()"]
    U -- 否 --> J
    U1 --> J
    T -- 否 --> V["聚合全局统计<br/>写 discovery_summary.json"]
```

## MAS 会话状态机

```mermaid
stateDiagram-v2
    [*] --> initial
    initial --> generating: _update_session_state()

    generating --> reflecting: _run_generation_phase()
    reflecting --> external_data: _run_reflection_phase()
    external_data --> evolving: _run_external_data_phase(method_phase=false)
    evolving --> ranking: _run_evolution_phase()

    ranking --> awaiting_feedback: 未达 max_iterations
    awaiting_feedback --> reflecting: add_feedback() 后继续
    ranking --> method_development: iterations_completed >= max_iterations

    method_development --> reflecting: _run_method_development_phase()
    reflecting --> external_data: 方法批评
    external_data --> refining: _run_external_data_phase(method_phase=true)
    refining --> completed: _run_refinement_phase()

    generating --> error: agent 异常
    reflecting --> error: agent 异常
    external_data --> error: 检索异常
    evolving --> error: agent 异常
    ranking --> error: 无 ideas 或评分异常
    method_development --> error: 方法开发异常
```

## OrchestrationAgent 阶段实现图

```mermaid
flowchart LR
    Start["OrchestrationAgent.run_session()"] --> Get["加载/获取 WorkflowSession"]
    Get --> Dispatch["_execute_current_phase()<br/>按 WorkflowState 分发"]

    Dispatch --> Gen["_run_generation_phase<br/>GenerationAgent.execute()<br/>可选 SurveyAgent.execute()"]
    Gen --> IdeaObj["创建 Idea(text, rationale, baseline_summary, iteration)"]
    IdeaObj --> Reflect["_run_reflection_phase<br/>并发 ReflectionAgent.execute()<br/>写 critiques 或 method_critiques"]
    Reflect --> External["_run_external_data_phase<br/>并发 ScholarAgent.execute()<br/>写 evidence / references / refine_evidence"]
    External --> Evo{"method_phase ?"}
    Evo -- 否 --> Evolve["_run_evolution_phase<br/>并发 EvolutionAgent.execute()<br/>生成子 Idea(parent_id)"]
    Evolve --> Rank["_run_ranking_phase<br/>RankingAgent.execute()<br/>写 score / scores / top_ideas"]
    Rank --> Loop{"达到 max_iterations ?"}
    Loop -- 否 --> Await["_run_awaiting_feedback_phase<br/>等待离线或人工 feedback"]
    Await --> Reflect
    Loop -- 是 --> Method["_run_method_development_phase<br/>MethodDevelopmentAgent.execute()<br/>idea.method_details"]
    Method --> Reflect
    Evo -- 是 --> Refine["_run_refinement_phase<br/>RefinementAgent.execute()<br/>idea.refined_method_details"]
    Refine --> Done["WorkflowState.COMPLETED"]

    Dispatch --> Err["WorkflowState.ERROR"]
```

## 顶层 Agent 模块实现

```mermaid
flowchart TB
    Factory["AgentFactory._agent_registry"] --> Gen["generation -> GenerationAgent"]
    Factory --> Ref["reflection -> ReflectionAgent"]
    Factory --> Evo["evolution -> EvolutionAgent"]
    Factory --> Meth["method_development -> MethodDevelopmentAgent"]
    Factory --> Refin["refinement -> RefinementAgent"]
    Factory --> Rank["ranking -> RankingAgent"]
    Factory --> Surv["survey -> SurveyAgent"]
    Factory --> Schol["scholar -> ScholarAgent"]
    Factory --> DR["dr -> DRAgent"]
    Factory --> Exp["experience -> ExperienceAgent"]
    Factory --> PE["prompt_evolver -> PromptGeneratorAgent"]

    Gen --> G1["构造 hypotheses JSON schema"]
    Gen --> G2["get_related_tools() + _call_model_with_tools()"]
    Gen --> G3["TaskMemoryRetriever guidance<br/>过滤失败相似 idea"]
    Gen --> G4["_call_model(schema)<br/>返回 hypotheses / reasoning / baseline_summary"]

    Ref --> R1["根据 method_details 选择 hypothesis 或 method critique schema"]
    Ref --> R2["_build_reflection_prompt()"]
    Ref --> R3["返回 critiques / strengths / suggestions"]

    Surv --> S1["web_search_query()"]
    Surv --> S2["advanced_query_paper()<br/>arxiv / crossref / web_search"]

    Schol --> C1["_generate_search_queries()"]
    Schol --> C2["_gather_literature_evidence()"]
    Schol --> C3["_generate_relevance_summary()"]

    Evo --> E1["构造 evolved_hypotheses schema"]
    Evo --> E2["_build_evolution_prompt()"]
    Evo --> E3["TaskMemoryRetriever 过滤失败相似 evolved idea"]

    Rank --> K1["按 SCORE_BATCH_SIZE=5 分批评分"]
    Rank --> K2["criteria: novelty / plausibility / testability / alignment"]
    Rank --> K3["strategy=distinct 时按 parent_id 去重后取 Top N"]

    Meth --> M1["method_details schema<br/>name/title/description/statement/method"]
    Meth --> M2["_build_method_development_prompt()"]

    Refin --> F1["refined_method schema"]
    Refin --> F2["失败时回退原 method_details"]

    DR --> D1["加载 DR workflow config"]
    DR --> D2["workflow.execute(task, file_path)"]

    Exp --> X1["对比实验结果"]
    Exp --> X2["更新 experience_library"]
    PE --> P1["从高置信经验生成新 task/background prompt"]
```

## 深度研究 QA 子系统

```mermaid
flowchart TD
    QA["launch_qa.py::main<br/>--question / --file / --output / --config"] --> DRA["DRAgent<br/>injected UnifiedModelRuntime"]
    DRA --> WF["dr_agents.workflow.main.Workflow.execute()"]

    WF --> GP["GlobalPlannerAgent.execute()<br/>自然语言任务 -> nodes/edges 有向图"]
    GP --> DAG["DirectedGraph<br/>检查环 / ready nodes / node status"]
    DAG --> GE["GlobalExecutionAgent.execute()<br/>逐层执行 ready nodes"]
    GE --> Layer["execute_graph()<br/>_execute_nodes_parallel()"]
    Layer --> Node["_execute_single_node()"]
    Node --> TW["TaskWorkflow.execute()<br/>节点级任务流程"]

    TW --> TP["PlannerAgent<br/>_plan_subtasks()"]
    TP --> TE["ExecutionAgent.execute()<br/>每个 subtask 的工具调用循环"]
    TE --> ToolLoop["execute_one_step()<br/>模型请求 tool_calls"]
    ToolLoop --> ToolCall["_execute_single_tool_call()<br/>function tool / MCP tool"]
    ToolCall --> TE
    TE --> Sum["_generate_subtask_response()<br/>JSON 解析 success/summary"]
    Sum --> TW
    TW --> GE

    GE --> Coord{"enable_coordinator ?"}
    Coord -- 是 --> CA["CoordinatorAgent.execute()<br/>修改执行图"]
    CA --> DAG
    Coord -- 否 --> Ans{"ready node 中有 answer ?"}
    Ans -- 否 --> DAG
    Ans -- 是 --> Syn["SynthesizerAgent.execute()"]
    Syn --> Final["_synthesize_answer()<br/>合成最终答案并附引用"]
    Final --> Output["stdout 或 --output 文件"]
```

## 模型、工具、记忆基础设施

```mermaid
flowchart TB
    subgraph ModelLayer["模型层"]
        MF["UnifiedModelRuntime.model_for()"]
        Provider["model_catalog.yaml<br/>relay / qwen / local embedding"]
        BM["BaseModel<br/>generate / generate_json / generate_with_messages / embed"]
        OM["Declared Responses / image / embedding adapters"]
        EM["EmbeddingModel<br/>local / openai / azure / custom"]
    end

    subgraph ToolLayer["工具层"]
        Init["init_tools() / init_mcp_tools()"]
        Registry["Tool Registry<br/>function tools + MCP tools"]
        Related["get_related_tools(query, tools)<br/>按 prompt 选择相关工具"]
        Lit["LiteratureSearch<br/>arxiv / semantic_scholar / crossref / core / kg_papers"]
        Web["WebSearch<br/>serper / wiki"]
        MemTool["memory_retrieval<br/>TaskMemoryRetriever / retrieve_task_memory()"]
        MCP["MCPManager / MCPManagerFastMCP<br/>远程 server 连接"]
    end

    subgraph MemoryLayer["记忆层"]
        MM["MemoryManager<br/>load/store/save/list session 与 hypothesis"]
        FSM["FileSystemMemoryManager<br/>results 目录 JSON 持久化"]
        TML["TaskMemoryLayer<br/>记录实验正负样本"]
        HR["HybridRetriever<br/>BM25 + vector + RRF"]
        OMS["OnlineMemorySaver<br/>实验成功后自动保存"]
        LM["MemoryModule<br/>加载历史 ideas/notes"]
        IG["IdeaGraph<br/>NetworkX + ChromaDB<br/>相似边与 Louvain 聚类"]
        EG["ExperienceGenerator<br/>从历史记忆生成经验"]
    end

    MF --> Provider
    Provider --> OM
    OM --> BM
    TML --> HR
    TML --> EM
    OMS --> TML
    LM --> IG
    LM --> EG
    Init --> Registry
    Registry --> Related
    Registry --> Lit
    Registry --> Web
    Registry --> MemTool
    Registry --> MCP
    Related --> AgentsUse["GenerationAgent / BaseAgent._call_model_with_tools()"]
    MemTool --> TML
```

## 实验执行与 MCTS

```mermaid
flowchart TD
    ER["ExperimentRunner.run_experiments()"] --> Mode{"max_parallel_experiments == 1<br/>且 gpu_per_experiment == 1 ?"}
    Mode -- 是 --> Seq["顺序 for idea"]
    Mode -- 否 --> Par["ThreadPoolExecutor<br/>并行提交 _run_single_experiment()"]
    Seq --> Single["_run_single_experiment()"]
    Par --> Single

    Single --> GPU["GPUAllocator.semaphore<br/>get_gpu_env()"]
    GPU --> Backend{"backend"}
    Backend -- claudecode --> Claude["run_claude_experiment()"]
    Backend -- iflow --> IFlow["run_iflow_experiment()"]
    Backend -- openhands --> OpenHands["run_openhands_experiment()"]

    Claude --> Setup["setup_sci_experiment_folder()<br/>或 setup_repo_experiment_folder()"]
    IFlow --> Setup
    OpenHands --> Setup
    Setup --> Log["setup_experiment_log()<br/>_start_progress_monitor()"]
    Log --> MCTSFlag{"experiment.use_mcts ?"}
    MCTSFlag -- 否 --> Normal["perform_experiments_claudecode / iflow<br/>生成 run_0..run_N"]
    MCTSFlag -- 是 --> MctsStart["perform_experiments_mcts()"]
    MctsStart --> Node["AiderMCTSNode<br/>workspace / metric / visits / children / UCT"]
    Node --> Step["ClaudeCodeMCTSSearch.step()"]
    Step --> Select["select()"]
    Select --> DraftOrImprove{"root ?"}
    DraftOrImprove -- 是 --> Draft["_draft()"]
    DraftOrImprove -- 否 --> Improve["_improve(parent)"]
    Draft --> Check["check_improvement()"]
    Improve --> Check
    Check --> Back["_backpropagate() / best_node 更新"]
    Back --> Step

    Normal --> Metrics["_calculate_experiment_performance()<br/>读取 final_info.json"]
    MctsStart --> Metrics
    Metrics --> Online["OnlineMemorySaver.save_idea_result()"]
    Online --> Result["返回 success / code_path / performance"]
```

## 任务目录与产物结构

```mermaid
flowchart LR
    TaskRoot["tasks/Auto*"] --> PromptJson["prompt.json<br/>domain / goal / background / constraints"]
    TaskRoot --> Code["code/<br/>baseline experiment implementation"]
    TaskRoot --> Launcher["launcher.sh<br/>执行任务实验"]
    TaskRoot --> Runs["run_0/<br/>baseline result"]
    Runs --> FinalInfo["final_info.json<br/>指标输出"]

    Sci["sci_tasks/tasks/*"] --> TaskInfo["task_info.json"]
    Sci --> Target["target_study/checklist.json"]
    TaskInfo --> Normalize["normalize_sci_task()<br/>生成 prompt.json"]
    Target --> Normalize

    LaunchOut["results/<task>/<launch_id>"] --> Session["session_<ts>"]
    Session --> Ideas["ideas.json"]
    Session --> Traj["traj.json"]
    Session --> Vis["ideas_visualization.pdf"]
    Session --> ExpRuns["<idea>/run_0..run_N"]
    ExpRuns --> Info["final_info.json"]
    LaunchOut --> Summary["discovery_summary.json"]
    LaunchOut --> ExpLib["experience_library / memory artifacts"]
```

## 模块实现清单

| 模块 | 关键文件/类/函数 | 实现职责 |
|---|---|---|
| 统一入口 | `launch.py::main` | 解析 `--mode`，把参数转交 `launch_qa.py` 或 `launch_discovery.py`。 |
| QA 入口 | `launch_qa.py::main` | 构造 `DRAgent`，执行 `agent.execute({'task', 'file_path'})`，打印或写出答案。 |
| 发现入口 | `launch_discovery.py::main` | 处理 resume、任务识别、配置、长记忆、多轮 discovery、实验/报告、incremental baseline、最终 summary。 |
| Idea 生成阶段 | `stage.py::IdeaGenerator.generate_ideas` | 启动 `VegapunkInterface` 会话，循环驱动状态机，处理 feedback，获取 top ideas，保存轨迹和可视化。 |
| MAS 接口 | `VegapunkInterface` | 加载配置、初始化模型工厂/记忆/agent/编排器、启动本地和 MCP 工具、提供 session API。 |
| 会话状态机 | `OrchestrationAgent` | 将 `WorkflowSession.state` 分发到生成、反思、证据、进化、排名、方法开发、精炼等阶段。 |
| 数据结构 | `WorkflowState`, `Task`, `Idea`, `WorkflowSession` | 保存任务、idea、证据、批评、分数、方法详情、top ideas、会话状态和迭代信息。 |
| Agent 工厂 | `AgentFactory` | 注册 11 类业务 agent，使用注入的 `UnifiedModelRuntime` 创建并缓存实例。 |
| Agent 基类 | `BaseAgent` | 统一模型调用、JSON schema 输出、重试、工具调用循环和工具执行。 |
| 生成 Agent | `GenerationAgent.execute` | 生成 hypotheses；使用工具上下文、历史记忆 guidance，并过滤失败相似方案。 |
| 反思 Agent | `ReflectionAgent.execute` | 对 hypothesis 或 method 生成结构化 critiques、strengths、suggestions。 |
| Survey Agent | `SurveyAgent.execute` | 在 idea 生成前做文献和网页调研，为生成阶段提供 `paper_lst`/`web_results`。 |
| Scholar Agent | `ScholarAgent.execute` | 为每个 idea 生成检索 query，收集 evidence/references，并生成 relevance summary。 |
| 进化 Agent | `EvolutionAgent.execute` | 基于 critiques/evidence/feedback 生成 `evolved_hypotheses`，可结合记忆过滤。 |
| 排名 Agent | `RankingAgent.execute` | 按 configured criteria 分批评分，排序并输出 `top_hypotheses`。 |
| 方法开发 Agent | `MethodDevelopmentAgent.execute` | 将 top idea 转成结构化 `method_details`。 |
| 精炼 Agent | `RefinementAgent.execute` | 用 method critiques 和 literature 生成 `refined_method`，失败时回退原方法。 |
| DR Agent | `DRAgent.execute` | 将 QA/背景研究任务转发给 DR workflow，失败时返回兜底背景说明。 |
| DR 全局 workflow | `dr_agents/workflow/main.py::Workflow.execute` | 全局规划、分层执行、可选协调、遇到 answer 节点后合成最终答案。 |
| DR 规划器 | `GlobalPlannerAgent.execute` | 通过 LLM 多轮生成 DAG，检查环并构造 `DirectedGraph`。 |
| DR 执行器 | `GlobalExecutionAgent.execute_graph` | 获取 ready nodes，并行执行一层节点，更新节点状态与结果。 |
| DR 节点 workflow | `TaskWorkflow.execute` | 规划节点内 subtasks，逐个执行并汇总节点结果。 |
| DR 工具执行 | `ExecutionAgent.execute` | 子任务级工具调用循环，维护 messages，解析最终 JSON summary。 |
| DR 合成器 | `SynthesizerAgent.execute` | 从执行图、answer 节点和引用管理器合成最终答案。 |
| 模型层 | `UnifiedModelRuntime`, `BaseModel`, `OpenAIModel` | 通过 Catalog 统一 text/json/messages/vision/image/embedding 接口。 |
| 工具层 | `literature_search.py`, `web_search.py`, `memory_retrieval.py`, `mcp_manager*.py` | 提供学术检索、网页检索、任务记忆检索和远程 MCP 工具接入。 |
| 上下文记忆 | `MemoryManager`, `FileSystemMemoryManager` | 持久化 session 与 hypothesis JSON。 |
| 任务记忆 | `TaskMemoryLayer`, `HybridRetriever` | 保存实验结果，计算正/负标签，BM25+向量检索相似记录，生成 guidance prompt。 |
| 在线记忆 | `OnlineMemorySaver` | 实验成功后自动把 idea 和 run 结果写入任务记忆。 |
| 长记忆 | `MemoryModule`, `IdeaGraph`, `ExperienceGenerator` | 加载历史 ideas/notes，构建相似图、聚类并生成经验。 |
| 实验执行 | `ExperimentRunner` | 为每个 idea 创建实验目录，分配 GPU，调用后端，计算性能，写 online memory。 |
| 报告生成 | `ReportWriter` | 基于 idea 生成 markdown 报告，报告模式不跑实验。 |
| MCTS 实验 | `ClaudeCodeMCTSSearch`, `IFlowMCTSSearch`, `AiderMCTSNode` | 可选搜索代码方案树，用 UCT 选择、draft/improve、指标回传和 best node 更新。 |
| 可视化 | `vis_tree.py`, `visualize_mcts*.py` | 将 MAS 轨迹或 MCTS 日志转成 PDF/HTML/Graphviz/ASCII 可视化。 |

## 关键运行路径

1. 发现实验：`launch.py --mode discovery` -> `launch_discovery.main()` -> `IdeaGenerator.generate_ideas()` -> `VegapunkInterface` -> `OrchestrationAgent` -> top ideas -> `ExperimentRunner.run_experiments()` -> `tasks/*/code` -> `final_info.json` -> `OnlineMemorySaver` -> `discovery_summary.json`。
2. QA：`launch.py --mode qa` 或 `launch_qa.py` -> `DRAgent.execute()` -> `Workflow.execute()` -> `GlobalPlannerAgent` -> `GlobalExecutionAgent` -> `TaskWorkflow`/`ExecutionAgent` -> `SynthesizerAgent` -> answer。
3. 增量多轮：每轮实验结束后，`_find_best_experiment_result()` 选择最优代码路径；下一轮在 `loop_mode=incremental` 时用该路径作为 baseline。
4. 记忆闭环：实验结果进入 `TaskMemoryLayer`；下一轮 `GenerationAgent` 和 `EvolutionAgent` 通过 memory guidance/failed-similarity filtering 避开失败方向并复用成功模式。
