"""
工具注册模块 - 集中管理所有可用工具
"""
from typing import List, Dict, Type
from app.agent.tools.base import BaseTool, ToolResult
from app.agent.tools.rag_tool import RAGTool
from app.agent.tools.bash_tool import BashTool
from app.agent.tools.python_tool import PythonTool
from app.agent.tools.web_search_tool import WebSearchTool
from app.agent.tools.calculator_tool import CalculatorTool


# 工具注册表
TOOL_REGISTRY: Dict[str, Type[BaseTool]] = {
    "rag": RAGTool,
    "bash": BashTool,
    "python": PythonTool,
    "web_search": WebSearchTool,
    "calculator": CalculatorTool,
}


def get_default_tools() -> List[BaseTool]:
    """获取默认的工具集（包含所有工具）"""
    return [
        RAGTool(),
        BashTool(),
        PythonTool(),
        WebSearchTool(),  # 可选，如果未配置 API key 会自动禁用
        CalculatorTool(),
    ]


def get_tool_by_name(name: str) -> BaseTool:
    """根据名称获取工具实例"""
    if name not in TOOL_REGISTRY:
        raise ValueError(f"未知工具：{name}. 可用工具：{list(TOOL_REGISTRY.keys())}")
    return TOOL_REGISTRY[name]()


def get_available_tools() -> List[str]:
    """获取所有可用工具的名称"""
    return list(TOOL_REGISTRY.keys())


def register_tool(name: str, tool_class: Type[BaseTool]):
    """注册新工具"""
    TOOL_REGISTRY[name] = tool_class


__all__ = [
    "BaseTool",
    "ToolResult",
    "RAGTool",
    "BashTool",
    "PythonTool",
    "WebSearchTool",
    "CalculatorTool",
    "get_default_tools",
    "get_tool_by_name",
    "get_available_tools",
    "register_tool",
]
