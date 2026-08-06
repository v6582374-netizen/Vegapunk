"""
Agent Factory for Vegapunk

This module provides functionality for registering and creating specialized
agent instances based on configuration.
"""
import logging
from collections.abc import Mapping
from typing import Dict, Any, Type

from ..models.unified_runtime import UnifiedModelRuntime
from .base_agent import BaseAgent
from vegapunk.research_draft import attach_research_draft_hook

from .survey_agent import SurveyAgent
from .scholar_agent import ScholarAgent
from .connector_agent import ConnectorAgent
from .web_evidence_agent import WebEvidenceAgent

from .generation_agent import GenerationAgent
from .evolution_agent import EvolutionAgent

from .reflection_agent import ReflectionAgent
from .ranking_agent import RankingAgent

from .method_development_agent import MethodDevelopmentAgent
from .refinement_agent import RefinementAgent

from .dr_agent import DRAgent

from .prompt_generator_agent import PromptGeneratorAgent
from .experience_agent import ExperienceAgent
logger = logging.getLogger(__name__)


class AgentInitializationError(RuntimeError):
    """Raised when one or more configured agents cannot be initialized.

    Agent construction happens at process startup. Returning a partial registry from
    that boundary makes the workflow appear healthy until a later phase dereferences
    the missing role, which turns the original configuration error into a misleading
    session failure. Keep the individual failures available for callers and logs.
    """

    def __init__(self, failures: Mapping[str, BaseException]) -> None:
        self.failures = dict(failures)
        details = "; ".join(
            f"{agent_type}: {type(error).__name__}: {error}"
            for agent_type, error in self.failures.items()
        )
        super().__init__(f"Failed to initialize configured agents: {details}")


# 这里集中维护“角色名 -> 代理类”的映射。上层状态机只说要哪个角色，
# 不直接 import 具体实现，因此新增角色时主要改这一处注册表。
class AgentFactory:
    """
    Factory for creating agent instances based on configuration.
    
    This factory maintains a registry of available agent types
    and creates properly configured instances as needed.
    """
    
    # Registry of agent types
    _agent_registry: Dict[str, Type[BaseAgent]] = {
        "generation": GenerationAgent,
        "reflection": ReflectionAgent,
        "evolution": EvolutionAgent,
        "method_development": MethodDevelopmentAgent,
        "refinement": RefinementAgent,
        "ranking": RankingAgent,
        "survey": SurveyAgent,
        "scholar": ScholarAgent,
        "connector": ConnectorAgent,
        "web_evidence": WebEvidenceAgent,
        "dr": DRAgent,
        'prompt_evolver':PromptGeneratorAgent,
        'experience':ExperienceAgent
    }
    
    # 同一类角色和同一模型配置通常可以复用，缓存能减少重复初始化模型客户端。
    _agent_cache: Dict[str, BaseAgent] = {}
    
    @classmethod
    def register_agent_type(cls, agent_type: str, agent_class: Type[BaseAgent]) -> None:
        """
        Register a new agent type.
        
        Args:
            agent_type: Type identifier for the agent
            agent_class: Agent class to register
        """
        if agent_type in cls._agent_registry:
            logger.warning(f"Overriding existing agent type: {agent_type}")
            
        cls._agent_registry[agent_type] = agent_class
        logger.info(f"Registered agent type: {agent_type}")
    
    @classmethod
    def create_agent(cls, 
                  agent_type: str, 
                  config: Dict[str, Any],
                  model_runtime: 'UnifiedModelRuntime') -> BaseAgent:
        """
        Create an agent instance of the specified type.
        
        Args:
            agent_type: Type of agent to create
            config: Configuration for the agent
            model_runtime: Process-owned UnifiedModelRuntime instance
            
        Returns:
            Configured agent instance
            
        Raises:
            ValueError: If the agent type is not registered
        """
        # Check if agent type is registered
        if agent_type not in cls._agent_registry:
            raise ValueError(f"Agent type not registered: {agent_type}")
        
        # 缓存粒度按角色和模型提供方划分；这能复用连接，又避免不同模型配置混在一起。
        cache_key = cls._create_cache_key(agent_type, config)
        
        # Check if we have a cached instance
        if cache_key in cls._agent_cache:
            logger.debug(f"Using cached agent instance for {agent_type}")
            return cls._agent_cache[cache_key]
        
        # Get the agent class
        agent_class = cls._agent_registry[agent_type]
        
        try:
            model = model_runtime.create_model_for_agent(agent_type, config)
            
            # Create the agent instance
            agent = agent_class(model, config)
            attach_research_draft_hook(agent)
            
            # Cache the instance
            cls._agent_cache[cache_key] = agent
            
            logger.info(f"Created agent instance of type: {agent_type}")
            return agent
        except Exception as e:
            logger.error(f"Error creating agent {agent_type}: {e}")
            raise
    
    @classmethod
    def create_all_agents(cls, 
                       config: Dict[str, Any],
                       model_runtime: 'UnifiedModelRuntime') -> Dict[str, BaseAgent]:
        """
        Create all configured agent instances.
        
        Args:
            config: Configuration dictionary with agent configurations
            model_runtime: Process-owned UnifiedModelRuntime instance
            
        Returns:
            Dictionary mapping agent types to agent instances
        """
        agents = {}
        agent_configs = config.get("agents") or {}
        if not isinstance(agent_configs, Mapping):
            raise TypeError(
                "The 'agents' configuration must be a mapping of agent type to settings"
            )

        failures: Dict[str, BaseException] = {}
        for agent_type, agent_config in agent_configs.items():
            if agent_type in cls._agent_registry:
                try:
                    if agent_config is None:
                        # YAML uses a null value for roles that rely entirely on
                        # defaults (for example method_development/refinement).
                        merged_config = {}
                    elif isinstance(agent_config, Mapping):
                        # Create a merged config with agent-specific settings without
                        # mutating the caller's parsed configuration tree.
                        merged_config = dict(agent_config)
                    else:
                        raise TypeError(
                            f"configuration must be a mapping or null, got "
                            f"{type(agent_config).__name__}"
                        )

                    # 单个角色配置会带上全局上下文，这样代理可以读取记忆、工具和模型等公共设置。
                    merged_config["_global_config"] = config
                    # Keep the process-owned runtime on the role config as well.
                    # Some agents (notably DeepResearch) consume it directly, and
                    # the cache key must describe the runtime that owns the model.
                    merged_config["_runtime"] = model_runtime

                    # Add global memory configuration for agents that use task memory
                    if "memory" in config:
                        merged_config["memory"] = config["memory"]

                    agents[agent_type] = cls.create_agent(
                        agent_type=agent_type,
                        config=merged_config,
                        model_runtime=model_runtime
                    )
                except Exception as e:
                    failures[agent_type] = e
                    logger.exception("Error creating agent %s", agent_type)

        if failures:
            raise AgentInitializationError(failures) from next(iter(failures.values()))

        return agents
    
    @classmethod
    def get_available_agent_types(cls) -> Dict[str, str]:
        """
        Get available agent types.
        
        Returns:
            Dictionary mapping agent types to their class names
        """
        return {agent_type: agent_class.__name__ 
                for agent_type, agent_class in cls._agent_registry.items()}
    
    @classmethod
    def clear_cache(cls) -> None:
        """Clear the agent cache."""
        cls._agent_cache.clear()
        logger.info("Agent cache cleared")
    
    @staticmethod
    def _create_cache_key(agent_type: str, config: Dict[str, Any]) -> str:
        """
        Create a cache key for an agent configuration.
        
        Args:
            agent_type: Type of agent
            config: Agent configuration
            
        Returns:
            Cache key string
        """
        runtime = config.get("_runtime")
        model_id = (
            runtime.catalog.active_text_model
            if isinstance(runtime, UnifiedModelRuntime)
            else "unbound"
        )
        return f"{agent_type}_{model_id}"
