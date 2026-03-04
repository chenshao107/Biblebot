"""
工具基类 - 定义统一的工具接口
"""
from abc import ABC, abstractmethod
from typing import Any, Dict
from pydantic import BaseModel


class ToolResult(BaseModel):
    """工具执行结果"""
    success: bool
    output: str
    error: str = ""


class BaseTool(ABC):
    """所有工具的基类"""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """工具名称，用于 LLM 调用"""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """工具描述，告诉 LLM 这个工具能做什么"""
        pass
    
    @property
    @abstractmethod
    def parameters(self) -> Dict[str, Any]:
        """工具参数的 JSON Schema，用于 LLM function calling"""
        pass
    
    @abstractmethod
    def execute(self, **kwargs) -> ToolResult:
        """执行工具"""
        pass
    
    def to_openai_function(self) -> Dict[str, Any]:
        """转换为 OpenAI function calling 格式"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters
            }
        }
