"""Run Parameter Registry: schema, validation, and persistence (ADR-0157).

One Pydantic model tree carries every run parameter of the main config with
its type, description, and validation rule. The same schema drives server
side validation and the structured forms in the Admin Console. Saving
writes the config file (the single source of truth); edits only affect
Launches that start afterwards because a Launch reads its own snapshot.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field


class _Section(BaseModel):
    model_config = ConfigDict(extra="allow")


class SystemConfig(_Section):
    debug: bool = Field(False, description="启用调试行为（更详细的内部检查与输出）")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        "INFO", description="全局日志级别"
    )


class ContextMemoryConfig(_Section):
    backend: str = Field("file_system", description="上下文记忆的存储后端")
    file_dir: str = Field("results", description="上下文记忆文件目录")


class TaskMemoryConfig(_Section):
    enabled: bool = Field(True, description="启用任务记忆（从过往实验学习的短期记忆）")
    memory_dir: str = Field("./config/mem_store", description="任务记忆存储目录")
    top_k: int = Field(5, ge=1, le=100, description="检索相似记录的数量")
    alpha: float = Field(0.5, ge=0, le=1, description="混合检索权重（关键词 vs 语义）")
    include_details: bool = Field(True, description="检索结果是否包含细节")
    embedding_mode: Literal["title", "description", "method", "full"] = Field(
        "description", description="用于嵌入的记录字段"
    )


class OnlineMemoryConfig(_Section):
    enabled: bool = Field(True, description="每次运行后自动保存实验结果")
    aggregation: Literal["best", "avg", "last"] = Field(
        "best", description="多次运行结果的聚合方式"
    )


class IdeaGraphConfig(_Section):
    similarity_threshold: float = Field(
        0.7, ge=0, le=1, description="IdeaGraph 建边的最小相似度"
    )


class PromptEvolverConfig(_Section):
    enabled: bool = Field(True, description="启用基于经验库的自动 prompt 演化")
    evolution_interval: int = Field(
        1, ge=1, description="每 N 个 Discovery 轮次演化一次 prompt"
    )


class LongMemoryConfig(_Section):
    enabled: bool = Field(True, description="启用长期记忆（IdeaGraph + 经验库）")
    idea_graph: IdeaGraphConfig = Field(
        default_factory=IdeaGraphConfig, description="IdeaGraph 设置"
    )
    prompt_evolver: PromptEvolverConfig = Field(
        default_factory=PromptEvolverConfig, description="PromptEvolver 设置"
    )


class MemoryConfig(_Section):
    context_memory: ContextMemoryConfig = Field(
        default_factory=ContextMemoryConfig, description="上下文记忆（会话历史与工作记忆）"
    )
    task_memory: TaskMemoryConfig = Field(
        default_factory=TaskMemoryConfig, description="任务记忆（带正负标签的实验记录）"
    )
    online_memory: OnlineMemoryConfig = Field(
        default_factory=OnlineMemoryConfig, description="在线记忆（运行后自动保存）"
    )
    long_memory: LongMemoryConfig = Field(
        default_factory=LongMemoryConfig, description="长期记忆（历史想法追踪与 prompt 演化）"
    )


class SciToolsConfig(_Section):
    local: bool = Field(False, description="启用本地 Sci 工具")
    remote: list[dict[str, Any]] | None = Field(
        None, description="远程 MCP 工具端点列表（id/url/headers）"
    )


class WebSearchConfig(_Section):
    max_results: int = Field(10, ge=1, le=100, description="网页搜索返回的最大结果数")


class LiteratureSearchConfig(_Section):
    timeout: int = Field(30, ge=1, description="文献检索请求超时（秒）")
    api_keys: dict[str, str] = Field(
        default_factory=dict, description="文献源 API key（如 semantic_scholar）"
    )
    kg_papers: dict[str, Any] = Field(
        default_factory=dict, description="知识图谱论文检索（api_url 等）"
    )


class ToolsConfig(_Section):
    web_search: WebSearchConfig = Field(
        default_factory=WebSearchConfig, description="网页搜索工具"
    )
    literature_search: LiteratureSearchConfig = Field(
        default_factory=LiteratureSearchConfig, description="文献检索工具"
    )


class GenerationAgentConfig(_Section):
    generation_count: int = Field(15, ge=1, description="每轮生成的想法数量")
    creativity: float = Field(0.7, ge=0, le=1, description="生成创造性（0 保守，1 激进）")
    do_survey: bool = Field(True, description="生成前是否做文献综述")
    use_memory: bool = Field(True, description="生成时启用记忆系统")
    filter_failed_ideas: bool = Field(True, description="过滤与失败尝试相似的想法")
    failed_similarity_threshold: float = Field(
        0.7, ge=0, le=1, description="判定与失败尝试相似的阈值"
    )
    max_regeneration_attempts: int = Field(2, ge=0, description="被过滤想法的最大重新生成次数")


class ReflectionAgentConfig(_Section):
    count: int = Field(3, ge=0, description="每个想法的反思轮数")
    detail_level: Literal["low", "medium", "high"] = Field(
        "medium", description="反思的详细程度"
    )


class EvolutionAgentConfig(_Section):
    evolution_count: int = Field(2, ge=0, description="每轮演化产生的变体数量")
    creativity_level: float = Field(0.6, ge=0, le=1, description="演化创造性")
    temperature: float = Field(0.7, ge=0, le=2, description="演化模型采样温度")
    use_memory: bool = Field(True, description="演化时启用记忆系统")
    filter_failed_ideas: bool = Field(True, description="过滤与失败尝试相似的演化结果")
    failed_similarity_threshold: float = Field(0.7, ge=0, le=1, description="相似度阈值")
    max_regeneration_attempts: int = Field(2, ge=0, description="最大重新生成次数")


class RankingAgentConfig(_Section):
    criteria: dict[str, float] = Field(
        default_factory=dict, description="排序标准权重（novelty/plausibility/testability/alignment）"
    )
    strategy: str = Field("default", description="排序策略")


class ScholarAgentConfig(_Section):
    search_depth: Literal["shallow", "moderate", "deep"] = Field(
        "moderate", description="检索深度"
    )
    sources: list[str] = Field(default_factory=list, description="检索来源列表")


class SurveyAgentConfig(_Section):
    max_papers: int = Field(50, ge=1, description="综述纳入的最大论文数")
    sources: list[str] = Field(default_factory=list, description="综述来源列表")


class DrAgentConfig(_Section):
    enabled: bool = Field(True, description="启用 Deep Research 背景调研")
    mode: str = Field("simple", description="Deep Research 模式")


class ExpAnalyzeAgentConfig(_Section):
    temperature: float = Field(0.7, ge=0, le=2, description="实验分析模型采样温度")
    reasoning: dict[str, Any] = Field(
        default_factory=dict, description="分析推理上下文设置"
    )
    timeout: int = Field(120, ge=1, description="分析超时（秒）")
    use_llm_for_metric_direction: bool = Field(
        True, description="用模型判断指标优化方向"
    )
    use_llm_for_primary_metric: bool = Field(True, description="用模型选择主指标")


class AgentsConfig(_Section):
    generation: GenerationAgentConfig = Field(
        default_factory=GenerationAgentConfig, description="想法生成 agent"
    )
    reflection: ReflectionAgentConfig = Field(
        default_factory=ReflectionAgentConfig, description="反思 agent"
    )
    evolution: EvolutionAgentConfig = Field(
        default_factory=EvolutionAgentConfig, description="演化 agent"
    )
    method_development: dict[str, Any] | None = Field(
        None, description="方法开发 agent（当前无独立参数）"
    )
    refinement: dict[str, Any] | None = Field(
        None, description="方法精炼 agent（当前无独立参数）"
    )
    ranking: RankingAgentConfig = Field(
        default_factory=RankingAgentConfig, description="排序 agent"
    )
    scholar: ScholarAgentConfig = Field(
        default_factory=ScholarAgentConfig, description="学术检索 agent"
    )
    survey: SurveyAgentConfig = Field(
        default_factory=SurveyAgentConfig, description="综述 agent"
    )
    dr: DrAgentConfig = Field(default_factory=DrAgentConfig, description="Deep Research agent")
    exp_analyze: ExpAnalyzeAgentConfig = Field(
        default_factory=ExpAnalyzeAgentConfig, description="实验结果分析 agent（在线记忆）"
    )


class WorkflowConfig(_Section):
    max_iterations: int = Field(4, ge=1, description="MAS 想法演化的最大迭代次数")
    top_ideas_count: int = Field(5, ge=1, description="进入实验阶段的想法数量")
    top_ideas_evo: bool = Field(True, description="top ideas 是否参与演化")
    max_concurrent_tasks: int = Field(5, ge=1, description="MAS 内最大并发任务数")
    loop_rounds: int = Field(10, ge=1, description="Discovery 外层最大轮数")
    loop_mode: Literal["fresh", "incremental"] = Field(
        "incremental", description="轮间模式：fresh 每轮从基线开始，incremental 从最优结果开始"
    )


class SciTaskConfig(_Section):
    evaluation_mode: Literal["llm_judge", "none"] = Field(
        "llm_judge", description="sci 任务评估模式"
    )
    default_launcher: str = Field(
        "python code/experiment.py", description="默认 launcher 命令"
    )


class ExperimentConfig(_Section):
    model: str = Field(..., description="实验后端（coding agent）使用的模型标识")
    use_mcts: bool = Field(False, description="实验阶段使用 MCTS 搜索而非普通 run/修错循环")
    max_runs: int = Field(2, ge=1, description="每个候选的最大实验运行次数（run_0 为基线）")
    max_parallel_experiments: int = Field(4, ge=1, description="并行实验数量上限")
    gpu_per_experiment: float = Field(1.0, gt=0, description="每个实验的 GPU 配额（支持小数）")


class RunParameters(_Section):
    """The full run parameter tree of the main Vegapunk config file."""

    version: str = Field("2.0.0", description="配置文件版本号")
    model_catalog_path: str = Field(
        "config/model_catalog.yaml", description="统一模型目录文件路径"
    )
    system: SystemConfig = Field(default_factory=SystemConfig, description="系统级设置")
    memory: MemoryConfig = Field(default_factory=MemoryConfig, description="记忆系统配置")
    sci_tools: SciToolsConfig = Field(
        default_factory=SciToolsConfig, description="Sci 工具（MCP）配置"
    )
    tools: ToolsConfig = Field(default_factory=ToolsConfig, description="内置工具配置")
    agents: AgentsConfig = Field(default_factory=AgentsConfig, description="各 agent 配置")
    workflow: WorkflowConfig = Field(
        default_factory=WorkflowConfig, description="Discovery 工作流配置"
    )
    sci_task: SciTaskConfig = Field(
        default_factory=SciTaskConfig, description="论文复现任务配置"
    )
    experiment: ExperimentConfig = Field(..., description="实验执行配置")


def parameter_catalog() -> list[dict]:
    """Derive the flat catalog (path, description, type, constraints) from the schema."""
    entries: list[dict] = []

    def walk(model: type[BaseModel], prefix: str) -> None:
        for name, field in model.model_fields.items():
            path = f"{prefix}{name}"
            annotation = field.annotation
            if isinstance(annotation, type) and issubclass(annotation, BaseModel):
                walk(annotation, f"{path}.")
                continue
            metadata = {}
            for constraint in field.metadata:
                for attr in ("ge", "le", "gt", "lt"):
                    if hasattr(constraint, attr):
                        metadata[attr] = getattr(constraint, attr)
            entries.append(
                {
                    "path": path,
                    "description": field.description or "",
                    "type": str(annotation),
                    **metadata,
                }
            )

    walk(RunParameters, "")
    return entries


def load_values(config_path: Path) -> dict:
    return yaml.safe_load(config_path.read_text()) or {}


def validate_values(values: dict) -> RunParameters:
    return RunParameters.model_validate(values)


def save_values(config_path: Path, parameters: RunParameters) -> None:
    payload = parameters.model_dump(exclude_none=False)
    config_path.write_text(
        "# Managed by the Admin Console Run Parameter Registry.\n"
        "# Field documentation lives in the registry schema (admin_console/parameters.py).\n"
        + yaml.safe_dump(payload, allow_unicode=True, sort_keys=False)
    )
