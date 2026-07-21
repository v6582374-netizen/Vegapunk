from abc import ABC, abstractmethod
from typing import Dict, Any, List

from vegapunk.mas.models.runtime import ModelRunRequest, ModelRunResult


class BaseModel(ABC):
    """
    模型基类
    """
    
    @abstractmethod
    def generate(self, prompt: str, **kwargs) -> str:
        """
        生成文本响应
        
        Args:
            prompt: 输入提示词
            **kwargs: 其他参数
            
        Returns:
            生成的文本响应
        """
        pass
    
    def run(self, request: ModelRunRequest) -> ModelRunResult:
        """Execute a project-native Runtime request when the provider supports it."""
        raise NotImplementedError(
            f"{self.__class__.__name__} does not implement the Vegapunk Runtime"
        )

    def generate_with_tools(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]], **kwargs) -> Dict[str, Any]:
        """
        使用工具调用生成响应
        
        Args:
            messages: 消息列表
            tools: 工具定义列表
            **kwargs: 其他参数
            
        Returns:
            包含工具调用的响应
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support legacy Chat tool calls"
        )
