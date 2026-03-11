"""
MCP 工具包装器
将 MCP 工具包装为 BiboBot 的 BaseTool 接口
"""
from typing import Any, Dict, Optional
from loguru import logger

from app.agent.tools.base import BaseTool, ToolResult
from app.agent.tools.mcp_client import MCPClientManager, get_mcp_manager, MCPTool


class MCPToolWrapper(BaseTool):
    """
    MCP 工具包装器
    将外部 MCP 服务器的工具包装为 BiboBot 可用的工具
    """
    
    def __init__(self, mcp_tool: MCPTool, manager: MCPClientManager):
        """
        初始化 MCP 工具包装器
        
        Args:
            mcp_tool: MCP 工具定义
            manager: MCP 客户端管理器
        """
        self._mcp_tool = mcp_tool
        self._manager = manager
        self._server_name = mcp_tool.server_name
        self._tool_name = mcp_tool.name
    
    @property
    def name(self) -> str:
        """工具名称（添加服务器前缀避免冲突）"""
        return f"{self._server_name}_{self._tool_name}"
    
    @property
    def description(self) -> str:
        """工具描述"""
        return self._mcp_tool.description
    
    @property
    def parameters(self) -> Dict[str, Any]:
        """工具参数 Schema"""
        return self._mcp_tool.parameters
    
    def execute(self, **kwargs) -> ToolResult:
        """
        执行 MCP 工具
        
        注意：这是一个同步方法，但 MCP 调用是异步的
        我们使用 asyncio.run 来运行异步调用
        """
        import asyncio
        
        try:
            # 运行异步调用
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(
                self._manager.call_tool(self._server_name, self._tool_name, kwargs)
            )
            loop.close()
            
            # 处理结果
            if "error" in result:
                return ToolResult(
                    success=False,
                    output="",
                    error=str(result["error"])
                )
            
            # MCP 工具返回的是 content 列表
            content = result.get("content", [])
            output_parts = []
            for item in content:
                if item.get("type") == "text":
                    output_parts.append(item.get("text", ""))
                elif item.get("type") == "image":
                    output_parts.append(f"[Image: {item.get('mimeType', 'unknown')}]")
                elif item.get("type") == "resource":
                    resource = item.get("resource", {})
                    output_parts.append(f"[Resource: {resource.get('uri', '')}]")
            
            return ToolResult(
                success=True,
                output="\n".join(output_parts) if output_parts else str(result)
            )
            
        except Exception as e:
            logger.error(f"MCP 工具 {self.name} 执行失败: {e}")
            return ToolResult(
                success=False,
                output="",
                error=str(e)
            )


class MCPToolFactory:
    """
    MCP 工具工厂
    用于从配置动态创建 MCP 工具包装器
    """
    
    @staticmethod
    def create_tools_from_config(configs: Dict[str, Dict[str, Any]]) -> list:
        """
        从配置创建 MCP 工具
        
        Args:
            configs: MCP 服务器配置字典
                {
                    "filesystem": {
                        "command": "npx",
                        "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/dir"],
                        "env": {}
                    },
                    "fetch": {
                        "command": "uvx",
                        "args": ["mcp-server-fetch"]
                    }
                }
        
        Returns:
            BaseTool 实例列表
        """
        import asyncio
        
        manager = get_mcp_manager()
        tools = []
        
        # 注册所有服务器
        for server_name, server_config in configs.items():
            if not server_config.get("command"):
                logger.warning(f"MCP 服务器 {server_name} 未配置命令，跳过")
                continue
            
            manager.register_server(
                name=server_name,
                command=server_config["command"],
                args=server_config.get("args", []),
                env=server_config.get("env")
            )
            logger.info(f"📝 已注册 MCP 服务器: {server_name}")
        
        # 初始化所有服务器并获取工具
        if manager.clients:
            try:
                # 检查是否已经在事件循环中
                try:
                    loop = asyncio.get_running_loop()
                    # 如果在运行中的事件循环中，使用 nest_asyncio 来允许嵌套
                    import nest_asyncio
                    nest_asyncio.apply()
                    results = asyncio.get_event_loop().run_until_complete(manager.initialize_all())
                except RuntimeError:
                    # 没有运行中的事件循环，正常创建
                    results = asyncio.run(manager.initialize_all())
                
                # 检查初始化结果
                for server_name, success in results.items():
                    if success:
                        client = manager.clients[server_name]
                        mcp_tools = client.get_tools()
                        for mcp_tool in mcp_tools:
                            wrapper = MCPToolWrapper(mcp_tool, manager)
                            tools.append(wrapper)
                            logger.info(f"  ✅ 加载工具: {wrapper.name}")
                    else:
                        logger.warning(f"  ❌ MCP 服务器 {server_name} 初始化失败")
                
            except Exception as e:
                logger.error(f"初始化 MCP 工具失败: {e}")
        
        logger.info(f"🎉 共加载 {len(tools)} 个 MCP 工具")
        return tools


# 预定义的常用 MCP 服务器配置
COMMON_MCP_SERVERS = {
    "filesystem": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem"],
        "description": "文件系统操作（需要配置路径参数）"
    },
    "fetch": {
        "command": "uvx",
        "args": ["mcp-server-fetch"],
        "description": "网页内容获取"
    },
    "sqlite": {
        "command": "uvx",
        "args": ["mcp-server-sqlite", "--db-path", "/path/to/db.sqlite"],
        "description": "SQLite 数据库操作（需要配置数据库路径）"
    },
    "git": {
        "command": "uvx",
        "args": ["mcp-server-git"],
        "description": "Git 操作"
    },
    "github": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-github"],
        "description": "GitHub API 操作（需要 GITHUB_PERSONAL_ACCESS_TOKEN 环境变量）"
    },
    "brave_search": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-brave-search"],
        "description": "Brave 搜索（需要 BRAVE_API_KEY 环境变量）"
    },
    "puppeteer": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-puppeteer"],
        "description": "浏览器自动化（Puppeteer）"
    },
    "redis": {
        "command": "uvx",
        "args": ["mcp-server-redis"],
        "description": "Redis 操作"
    },
}


def get_common_server_help() -> str:
    """获取常用 MCP 服务器的帮助信息"""
    help_text = "常用 MCP 服务器:\n"
    for name, config in COMMON_MCP_SERVERS.items():
        help_text += f"  - {name}: {config['description']}\n"
        help_text += f"    命令: {config['command']} {' '.join(config['args'])}\n"
    return help_text
