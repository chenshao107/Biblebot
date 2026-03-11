"""
MCP (Model Context Protocol) 客户端
用于连接和调用外部 MCP 服务器
"""
import asyncio
import json
import subprocess
import threading
import time
from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass
from loguru import logger


@dataclass
class MCPTool:
    """MCP 工具定义"""
    name: str
    description: str
    parameters: Dict[str, Any]
    server_name: str


class MCPClient:
    """
    MCP 客户端基类
    支持通过 stdio 或 SSE 连接 MCP 服务器
    """
    
    def __init__(self, server_name: str, command: Optional[str] = None, 
                 args: Optional[List[str]] = None, env: Optional[Dict[str, str]] = None):
        """
        初始化 MCP 客户端
        
        Args:
            server_name: 服务器名称标识
            command: 启动命令（如 'npx', 'uvx', 'python' 等）
            args: 命令参数
            env: 环境变量
        """
        self.server_name = server_name
        self.command = command
        self.args = args or []
        self.env = env or {}
        self.process: Optional[subprocess.Popen] = None
        self._tools: List[MCPTool] = []
        self._initialized = False
        self._request_id = 0
        self._lock = threading.Lock()
    
    async def initialize(self) -> bool:
        """
        初始化 MCP 服务器连接
        返回是否成功
        """
        if self._initialized:
            return True
            
        if not self.command:
            logger.warning(f"MCP 服务器 {self.server_name} 未配置命令")
            return False
        
        try:
            # 启动 MCP 服务器进程
            env = {**os.environ, **self.env} if self.env else None
            self.process = subprocess.Popen(
                [self.command] + self.args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env
            )
            
            # 发送初始化请求
            init_request = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "biblebot-mcp-client", "version": "1.0.0"}
                }
            }
            
            response = await self._send_request(init_request)
            if response and "result" in response:
                self._initialized = True
                logger.info(f"✅ MCP 服务器 {self.server_name} 初始化成功")
                # 获取工具列表
                await self._fetch_tools()
                return True
            else:
                logger.error(f"❌ MCP 服务器 {self.server_name} 初始化失败: {response}")
                return False
                
        except Exception as e:
            logger.error(f"❌ MCP 服务器 {self.server_name} 启动失败: {e}")
            return False
    
    def _get_next_request_id(self) -> int:
        """获取下一个请求 ID（线程安全）"""
        with self._lock:
            self._request_id += 1
            return self._request_id
    
    async def _send_request(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """发送 JSON-RPC 请求并获取响应"""
        if not self.process or self.process.poll() is not None:
            logger.error(f"MCP 服务器 {self.server_name} 进程未运行")
            return None
        
        try:
            # 发送请求（加锁保证并发安全）
            request_line = json.dumps(request) + "\n"
            
            with self._lock:
                # 检查进程仍然存活
                if self.process.poll() is not None:
                    logger.error(f"MCP 服务器 {self.server_name} 进程已退出")
                    return None
                
                self.process.stdin.write(request_line)
                self.process.stdin.flush()
                
                # 读取响应，带超时重试
                max_retries = 3
                for attempt in range(max_retries):
                    # 使用 asyncio.wait_for 实现超时
                    import asyncio
                    try:
                        response_line = await asyncio.wait_for(
                            asyncio.get_event_loop().run_in_executor(
                                None, self.process.stdout.readline
                            ),
                            timeout=30.0  # 30秒超时
                        )
                        break
                    except asyncio.TimeoutError:
                        if attempt < max_retries - 1:
                            logger.warning(f"MCP 请求超时，重试 {attempt + 1}/{max_retries}")
                            continue
                        else:
                            logger.error(f"MCP 请求超时，已重试 {max_retries} 次")
                            return None
                else:
                    return None
            
            # 解析响应（在锁外进行）
            if not response_line:
                # 读取 stderr 获取错误信息
                stderr_data = ""
                try:
                    # 非阻塞读取 stderr
                    import select
                    if select.select([self.process.stderr], [], [], 0.1)[0]:
                        stderr_data = self.process.stderr.readline()
                except:
                    pass
                
                if stderr_data:
                    logger.error(f"MCP 服务器 {self.server_name} stderr: {stderr_data}")
                else:
                    logger.error(f"MCP 服务器 {self.server_name} 返回空响应")
                return None
            
            try:
                return json.loads(response_line)
            except json.JSONDecodeError as e:
                logger.error(f"MCP 响应 JSON 解析失败: {e}, 原始数据: {response_line[:200]}")
                return None
            
        except Exception as e:
            logger.error(f"发送 MCP 请求失败: {e}")
            return None
    
    async def _fetch_tools(self):
        """获取 MCP 服务器提供的工具列表"""
        request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list"
        }
        
        response = await self._send_request(request)
        if response and "result" in response:
            tools_data = response["result"].get("tools", [])
            self._tools = []
            for tool_data in tools_data:
                mcp_tool = MCPTool(
                    name=tool_data["name"],
                    description=tool_data.get("description", ""),
                    parameters=tool_data.get("inputSchema", {"type": "object", "properties": {}}),
                    server_name=self.server_name
                )
                self._tools.append(mcp_tool)
            logger.info(f"📦 MCP 服务器 {self.server_name} 提供 {len(self._tools)} 个工具")
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        调用 MCP 工具
        
        Args:
            tool_name: 工具名称
            arguments: 工具参数
            
        Returns:
            工具执行结果
        """
        if not self._initialized:
            success = await self.initialize()
            if not success:
                return {"error": f"MCP 服务器 {self.server_name} 未初始化"}
        
        request = {
            "jsonrpc": "2.0",
            "id": self._get_next_request_id(),
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }
        
        response = await self._send_request(request)
        if response:
            if "result" in response:
                return response["result"]
            elif "error" in response:
                return {"error": response["error"]}
        
        return {"error": "调用 MCP 工具失败"}
    
    def get_tools(self) -> List[MCPTool]:
        """获取所有可用工具"""
        return self._tools
    
    def close(self):
        """关闭 MCP 服务器连接"""
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None
            self._initialized = False
            logger.info(f"🔌 MCP 服务器 {self.server_name} 已关闭")


class MCPClientManager:
    """
    MCP 客户端管理器
    管理多个 MCP 服务器连接
    """
    
    def __init__(self):
        self.clients: Dict[str, MCPClient] = {}
    
    def register_server(self, name: str, command: str, args: List[str], 
                       env: Optional[Dict[str, str]] = None) -> MCPClient:
        """注册 MCP 服务器"""
        client = MCPClient(name, command, args, env)
        self.clients[name] = client
        return client
    
    async def initialize_all(self) -> Dict[str, bool]:
        """初始化所有 MCP 服务器"""
        results = {}
        for name, client in self.clients.items():
            results[name] = await client.initialize()
        return results
    
    def get_all_tools(self) -> List[MCPTool]:
        """获取所有服务器的工具"""
        all_tools = []
        for client in self.clients.values():
            all_tools.extend(client.get_tools())
        return all_tools
    
    async def call_tool(self, server_name: str, tool_name: str, 
                       arguments: Dict[str, Any]) -> Dict[str, Any]:
        """调用指定服务器的工具"""
        if server_name not in self.clients:
            return {"error": f"未知的 MCP 服务器: {server_name}"}
        
        client = self.clients[server_name]
        return await client.call_tool(tool_name, arguments)
    
    def close_all(self):
        """关闭所有连接"""
        for client in self.clients.values():
            client.close()


# 导入 os 用于环境变量
import os

# 全局管理器实例
_mcp_manager: Optional[MCPClientManager] = None


def get_mcp_manager() -> MCPClientManager:
    """获取全局 MCP 管理器实例"""
    global _mcp_manager
    if _mcp_manager is None:
        _mcp_manager = MCPClientManager()
    return _mcp_manager
