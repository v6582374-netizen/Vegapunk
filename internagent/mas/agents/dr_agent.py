"""
DR Agent for InternAgent

This module implements the DR (Discovery Research) Agent, which interfaces with
the DR workflow system to execute complex discovery research tasks.
"""

import logging
import asyncio
import sys
import os
import copy
from typing import Any, Dict, Tuple

from .base_agent import BaseAgent, AgentExecutionError

logger = logging.getLogger(__name__)

# 这一层只是适配器：外部把它当作普通代理使用，内部再去调更重的调研工作流。
# 延迟导入能避免普通多代理启动时被调研子系统的路径和依赖问题卡住。
_workflow_class = None
_load_config_func = None
_get_config_func = None


def _merge_workflow_config(
    base: Dict[str, Any], override: Dict[str, Any]
) -> Dict[str, Any]:
    """Recursively merge DR mappings while replacing all other values."""

    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(merged.get(key), dict) and isinstance(value, dict):
            merged[key] = _merge_workflow_config(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _effective_dr_model_names(model_config: Dict[str, Any]) -> Tuple[str, ...]:
    """Resolve the model names that the DR workflow will actually use."""

    from .dr_agents.utils.config_loader import resolve_dr_model_roles

    resolved = resolve_dr_model_roles(model_config)
    return tuple(dict.fromkeys(resolved.values()))


def _probe_dr_model(
    model_name: str, runtime_config: Dict[str, Any]
) -> None:
    """Make one small real request through the selected DR provider."""

    from .dr_agents.models import get_model

    model = get_model(
        model_name,
        runtime_config=runtime_config,
        agent_role="dr_availability_probe",
        reasoning_context="current_turn",
        reasoning_mode="standard",
        background=False,
    )
    try:
        probe = getattr(model, "probe", None)
        if not callable(probe):
            raise ValueError(
                f"DeepResearch model {model_name!r} does not support "
                "availability probing"
            )
        probe()
    finally:
        close = getattr(model, "close", None)
        if callable(close):
            close()


def _get_workflow_class():
    """Lazy import of Workflow class to avoid import errors at module load time."""
    global _workflow_class
    if _workflow_class is not None:
        return _workflow_class
    current_dir = os.path.dirname(os.path.abspath(__file__))
    dr_agents_path = os.path.join(current_dir, "dr_agents")
    if dr_agents_path not in sys.path:
        sys.path.insert(0, dr_agents_path)
    try:
        from workflow.main import Workflow
        _workflow_class = Workflow
        return _workflow_class
    except ImportError as e:
        logger.error(f"Failed to import Workflow from dr_agents: {e}")
        return None


def _get_config_loaders():
    """Lazy import of config loader functions."""
    global _load_config_func, _get_config_func
    if _load_config_func is not None and _get_config_func is not None:
        return _load_config_func, _get_config_func
    current_dir = os.path.dirname(os.path.abspath(__file__))
    dr_agents_path = os.path.join(current_dir, "dr_agents")
    if dr_agents_path not in sys.path:
        sys.path.insert(0, dr_agents_path)
    try:
        from utils.config_loader import load_config, get_config
        _load_config_func, _get_config_func = load_config, get_config
        return _load_config_func, _get_config_func
    except ImportError as e:
        logger.error(f"Failed to import config loaders from dr_agents: {e}")
        return None, None


class DRAgent(BaseAgent):
    """
    DR Agent executes discovery research tasks using the DR workflow system.

    This agent serves as an interface between the InternAgent multi-agent system
    and the specialized DR (Discovery Research) workflow, enabling complex
    research discovery tasks to be executed within the broader agent framework.
    """
    
    def __init__(self, model, config: Dict[str, Any]):
        """
        Initialize the DR agent.
        
        Args:
            model: Language model to use
            config: Configuration dictionary containing DR-specific settings
        """
        super().__init__(model, config)

        self.workflow = None
        if not config.get("enabled", True):
            self.workflow_config = {}
            logger.info("DR workflow is disabled")
            return
        
        # 不同使用场景读取不同配置；问答、简单调研和复杂调研共享同一层适配逻辑。
        self.mode = config.get("mode", "simple")
        
        # Load DR workflow configuration from config.yaml
        self.workflow_config = self._load_dr_config(config)
        
        # 工作流初始化失败时保留一个可创建的代理对象，调用方仍能拿到降级提示。
        Workflow = _get_workflow_class()
        if Workflow is not None:
            for model_name in _effective_dr_model_names(
                self.workflow_config["model"]
            ):
                _probe_dr_model(
                    model_name,
                    self.workflow_config.get("runtime_model", {}),
                )
                logger.info("DR model availability confirmed: %s", model_name)
            try:
                self.workflow = Workflow(config=self.workflow_config)
                logger.info("DR workflow initialized successfully")
            except Exception as e:
                logger.warning(f"Failed to initialize DR workflow: {str(e)}, DR agent will work in limited mode")
                # Don't raise the exception, allow the agent to be created
        else:
            logger.warning("Workflow class not available - import failed, DR agent will work in limited mode")
            # Create a placeholder to avoid failures
            # The agent can still be initialized but won't be able to execute
    
    def _load_dr_config(self, agent_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Load DR workflow configuration from config.yaml file.
        
        Args:
            agent_config: Agent-specific configuration (can contain overrides)
        
        Returns:
            Merged configuration dictionary
        """
        # First, try to load from config.yaml in dr_agents folder
        workflow_config = None
        
        # Get config loader functions via lazy import
        load_config, get_config = _get_config_loaders()
        
        if load_config is not None:
            try:
                # Get the path to config.yaml in dr_agents folder
                current_dir = os.path.dirname(os.path.abspath(__file__))
                config_path = os.path.join(current_dir, "dr_agents", f"config_{self.mode}.yaml")
                
                if os.path.exists(config_path):
                    workflow_config = load_config(config_path)
                    logger.info(f"Loaded DR workflow config from: {config_path}")
                elif get_config is not None:
                    workflow_config = get_config()
                    logger.info("Using default DR workflow config")
            except Exception as e:
                logger.warning(f"Failed to load DR config.yaml: {e}")
        
        # If loading failed, use empty config or fallback
        if workflow_config is None:
            workflow_config = {}
            logger.warning("Using empty DR workflow config")
        
        # 外部配置可以只覆盖少量字段，不必复制整份调研工作流配置。
        if "workflow_config" in agent_config:
            workflow_config = _merge_workflow_config(
                workflow_config,
                agent_config["workflow_config"],
            )
            logger.info("Applied agent config overrides to DR workflow config")

        _effective_dr_model_names(workflow_config.get("model", {}))

        # DR is a synchronous orchestration layer, but it inherits the exact root
        # provider policy instead of maintaining a second OpenAI configuration.
        global_config = agent_config.get("_global_config", {})
        models_config = global_config.get("models", {})
        provider_config = copy.deepcopy(models_config.get("openai", {}))
        provider_config["provider"] = "openai"
        workflow_config["runtime_model"] = provider_config

        return workflow_config
    
    async def execute(self, context: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute discovery research task using the DR workflow.
        
        Args:
            context: Dictionary containing:
                - task: The research task description
                - file_path: Optional file path for additional context
                - goal: Research goal information (optional)
                - iteration: Current iteration number (optional)
            params: Dictionary containing optional configuration overrides
                
        Returns:
            The workflow execution result (format depends on the workflow)
        """
        # Extract task information from context
        task = context.get("task", "")
        if not task:
            # Try alternative keys
            task = context.get("description", "") or context.get("goal", {}).get("description", "")
        
        if not task:
            raise AgentExecutionError("Task description is required for DR agent execution")
        
        # Extract optional file path
        file_path = context.get("file_path", None)
        
        # 如果调研子系统不可用，返回可读的降级结果，而不是让整个问答或发现流程崩掉。
        if self.workflow is None:
            logger.error("DR workflow is not initialized - cannot execute task")
            # Return a simple fallback response
            return f"Background research needed for: {task}\n\nNote: DR workflow is not available. Please provide background context manually."
        
        try:
            logger.info(f"DR Agent executing task: {task}")
            
            # 这里跨过了多代理主流程，直接让调研工作流完成背景搜索和答案合成。
            result = await asyncio.to_thread(
                self.workflow.execute,
                task=task,
                file_path=file_path,
            )
            
            logger.info("DR workflow execution completed successfully")
            
            # Return the result directly (user has modified return format)
            return result
            
        except Exception as e:
            logger.error(f"Error during DR workflow execution: {str(e)}")
            # Return a fallback response instead of raising error
            return f"Background research for: {task}\n\nNote: DR workflow execution failed. Please provide background context manually."
