"""
工具注册模块 - 集中管理所有可用工具
支持 Docker 沙箱模式和原生模式自动切换
"""
from typing import List, Dict, Type
from loguru import logger
from app.agent.tools.base import BaseTool, ToolResult
from app.agent.tools.rag_tool import RAGTool
from app.agent.tools.web_search_tool import WebSearchTool
from app.agent.tools.calculator_tool import CalculatorTool
from app.core.config import settings

# 根据配置选择 Bash 和 Python 工具的实现
def _get_bash_tool_class():
    """获取 Bash 工具类（Docker 或原生）"""
    if settings.USE_DOCKER_SANDBOX:
        try:
            from app.agent.tools.docker_bash_tool import DockerBashTool
            logger.debug("使用 Docker Bash 工具")
            return DockerBashTool
        except ImportError as e:
            logger.warning(f"Docker Bash 工具不可用: {e}，回退到原生实现")
            from app.agent.tools.bash_tool import BashTool
            return BashTool
    else:
        from app.agent.tools.bash_tool import BashTool
        logger.debug("使用原生 Bash 工具")
        return BashTool

def _get_python_tool_class():
    """获取 Python 工具类（Docker 或原生）"""
    if settings.USE_DOCKER_SANDBOX:
        try:
            from app.agent.tools.docker_python_tool import DockerPythonTool
            logger.debug("使用 Docker Python 工具")
            return DockerPythonTool
        except ImportError as e:
            logger.warning(f"Docker Python 工具不可用: {e}，回退到原生实现")
            from app.agent.tools.python_tool import PythonTool
            return PythonTool
    else:
        from app.agent.tools.python_tool import PythonTool
        logger.debug("使用原生 Python 工具")
        return PythonTool

# 动态获取工具类
BashTool = _get_bash_tool_class()
PythonTool = _get_python_tool_class()

# 工具注册表
TOOL_REGISTRY: Dict[str, Type[BaseTool]] = {
    "rag": RAGTool,
    "bash": BashTool,
    "python": PythonTool,
    "web_search": WebSearchTool,
    "calculator": CalculatorTool,
}


def get_default_tools() -> List[BaseTool]:
    """获取默认的工具集（根据配置自动选择 Docker 或原生实现）"""
    tools = [
        RAGTool(),
        BashTool(),
        PythonTool(),
        CalculatorTool(),
    ]
    
    # WebSearchTool 需要 API key，单独处理
    try:
        web_tool = WebSearchTool()
        tools.append(web_tool)
    except Exception as e:
        logger.warning(f"WebSearchTool 初始化失败（可能未配置 API key）: {e}")
    
    # 记录使用的实现
    sandbox_mode = "Docker 沙箱" if settings.USE_DOCKER_SANDBOX else "原生"
    logger.info(f"已加载默认工具集（使用 {sandbox_mode} 模式）: {[t.name for t in tools]}")
    
    return tools


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
