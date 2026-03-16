"""
Agent MCP 服务器
将 Agent 包装为 MCP 服务，支持 stdio 和 HTTP/SSE 两种模式
"""
import asyncio
import json
import sys
import os
from typing import Any, Dict, List, Optional
from loguru import logger

# 配置日志
logger.remove()
logger.add(sys.stderr, level="INFO")


class AgentMCPServer:
    """
    Agent MCP 服务器基类
    只暴露一个工具：ask_agent - 向 Agent 提问获取知识库回答
    """
    
    def __init__(self):
        self.agent = None
        self._initialized = False
    
    async def _init_agent(self):
        """初始化 Agent"""
        if self.agent is not None:
            return
        
        try:
            # 延迟导入，避免循环依赖
            from app.agent import Agent, get_default_tools
            
            logger.info("🤖 正在初始化 Agent...")
            tools = get_default_tools()
            self.agent = Agent(tools=tools)
            logger.info("✅ Agent 初始化完成")
        except Exception as e:
            logger.error(f"❌ Agent 初始化失败: {e}")
            raise
    
    def get_tools_schema(self) -> List[Dict[str, Any]]:
        """获取工具列表定义"""
        return [
            {
                "name": "ask_agent",
                "description": "向知识库 Agent 提问，获取智能回答。Agent 会自动探索知识库并返回答案。",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "question": {
                            "type": "string",
                            "description": "要问的问题，可以是关于知识库内容的任何问题"
                        },
                        "context": {
                            "type": "string",
                            "description": "可选的上下文信息，用于提供额外背景"
                        }
                    },
                    "required": ["question"]
                }
            }
        ]
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """调用工具"""
        if tool_name != "ask_agent":
            return {
                "error": {
                    "code": -32601,
                    "message": f"未知工具: {tool_name}"
                }
            }
        
        # 确保 Agent 已初始化
        await self._init_agent()
        
        question = arguments.get("question", "")
        context = arguments.get("context", "")
        
        if not question:
            return {
                "error": {
                    "code": -32602,
                    "message": "缺少必要参数: question"
                }
            }
        
        try:
            # 运行 Agent 获取答案
            logger.info(f"🤔 处理问题: {question[:50]}...")
            answer = self.agent.run(question, context if context else None)
            logger.info("✅ 回答生成完成")
            
            return {
                "content": [
                    {
                        "type": "text",
                        "text": answer
                    }
                ]
            }
        except Exception as e:
            logger.error(f"❌ Agent 执行失败: {e}")
            return {
                "error": {
                    "code": -32603,
                    "message": f"Agent 执行失败: {str(e)}"
                }
            }


class StdioMCPServer(AgentMCPServer):
    """基于 stdio 的 MCP 服务器（本地使用）"""
    
    def __init__(self):
        super().__init__()
        self._request_id = 0
    
    def _send_response(self, response: Dict[str, Any]):
        """发送 JSON-RPC 响应到 stdout"""
        response_line = json.dumps(response) + "\n"
        sys.stdout.write(response_line)
        sys.stdout.flush()
    
    def _send_error(self, request_id: Any, code: int, message: str):
        """发送错误响应"""
        self._send_response({
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": code,
                "message": message
            }
        })
    
    def _handle_initialize(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """处理初始化请求"""
        params = request.get("params", {})
        protocol_version = params.get("protocolVersion", "2024-11-05")
        
        logger.info(f"📡 收到初始化请求，协议版本: {protocol_version}")
        
        self._initialized = True
        
        return {
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {}
                },
                "serverInfo": {
                    "name": "biblebot-agent-mcp-server",
                    "version": "1.0.0"
                }
            }
        }
    
    def _handle_tools_list(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """处理工具列表请求"""
        logger.info("📋 收到工具列表请求")
        
        return {
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "result": {
                "tools": self.get_tools_schema()
            }
        }
    
    async def _handle_tools_call(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """处理工具调用请求"""
        params = request.get("params", {})
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        
        logger.info(f"🔧 收到工具调用请求: {tool_name}")
        
        result = await self.call_tool(tool_name, arguments)
        
        if "error" in result:
            return {
                "jsonrpc": "2.0",
                "id": request.get("id"),
                "error": result["error"]
            }
        
        return {
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "result": result
        }
    
    async def handle_request(self, request: Dict[str, Any]):
        """处理单个请求"""
        method = request.get("method")
        request_id = request.get("id")
        
        try:
            if method == "initialize":
                response = self._handle_initialize(request)
            elif method == "tools/list":
                response = self._handle_tools_list(request)
            elif method == "tools/call":
                response = await self._handle_tools_call(request)
            elif method == "notifications/initialized":
                logger.info("✅ MCP 客户端已初始化")
                return
            else:
                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32601,
                        "message": f"未知方法: {method}"
                    }
                }
            
            self._send_response(response)
            
        except Exception as e:
            logger.error(f"处理请求时出错: {e}")
            self._send_error(request_id, -32603, f"内部错误: {str(e)}")
    
    async def run(self):
        """运行 MCP 服务器，从 stdin 读取请求"""
        logger.info("🚀 Agent MCP 服务器启动 (stdio 模式)")
        logger.info("📡 等待客户端连接...")
        
        try:
            while True:
                line = await asyncio.get_event_loop().run_in_executor(
                    None, sys.stdin.readline
                )
                
                if not line:
                    logger.info("👋 客户端断开连接")
                    break
                
                line = line.strip()
                if not line:
                    continue
                
                try:
                    request = json.loads(line)
                    await self.handle_request(request)
                except json.JSONDecodeError as e:
                    logger.error(f"JSON 解析失败: {e}")
                    self._send_error(None, -32700, f"Parse error: {str(e)}")
                    
        except KeyboardInterrupt:
            logger.info("👋 收到中断信号，服务器关闭")
        except Exception as e:
            logger.error(f"服务器运行错误: {e}")
        finally:
            logger.info("🛑 MCP 服务器已停止")


# ==================== HTTP/SSE 模式 ====================

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import AsyncGenerator
import uuid


class MCPInitializeRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: Optional[Any] = None
    method: str
    params: Optional[Dict[str, Any]] = None


class HTTPMCPServer:
    """基于 HTTP/SSE 的 MCP 服务器（远程访问）"""
    
    def __init__(self, agent_server: AgentMCPServer):
        self.agent = agent_server
        self.app = FastAPI(
            title="Agent MCP Server",
            description="基于 HTTP/SSE 的 Agent MCP 服务，支持内网共享访问",
            version="1.0.0"
        )
        self._setup_routes()
        self._setup_cors()
    
    def _setup_cors(self):
        """配置 CORS"""
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    
    def _setup_routes(self):
        """设置路由"""
        
        @self.app.get("/")
        async def root():
            """根路径，返回服务器信息"""
            return {
                "name": "Agent MCP Server",
                "version": "1.0.0",
                "protocol": "MCP 2024-11-05",
                "endpoints": {
                    "sse": "/sse - SSE 连接端点",
                    "message": "/message - 发送消息端点",
                    "tools": "/tools - 获取工具列表"
                }
            }
        
        @self.app.get("/tools")
        async def get_tools():
            """获取可用工具列表"""
            return {
                "tools": self.agent.get_tools_schema()
            }
        
        @self.app.get("/sse")
        async def sse_endpoint(request: Request):
            """SSE 连接端点"""
            session_id = str(uuid.uuid4())
            logger.info(f"📡 新的 SSE 连接: {session_id}")
            
            async def event_generator() -> AsyncGenerator[str, None]:
                # 发送初始化消息
                init_message = {
                    "jsonrpc": "2.0",
                    "id": 0,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {
                            "tools": {}
                        },
                        "serverInfo": {
                            "name": "biblebot-agent-mcp-server",
                            "version": "1.0.0"
                        },
                        "sessionId": session_id
                    }
                }
                yield f"data: {json.dumps(init_message)}\n\n"
                
                # 保持连接
                try:
                    while True:
                        # 检查客户端是否断开
                        if await request.is_disconnected():
                            logger.info(f"👋 SSE 连接断开: {session_id}")
                            break
                        await asyncio.sleep(1)
                except Exception as e:
                    logger.info(f"👋 SSE 连接异常: {session_id}, {e}")
            
            return StreamingResponse(
                event_generator(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                }
            )
        
        @self.app.post("/message")
        async def message_endpoint(request: Request):
            """接收客户端消息"""
            try:
                data = await request.json()
                logger.info(f"📨 收到消息: {data.get('method')}")
                
                method = data.get("method")
                request_id = data.get("id")
                
                if method == "tools/list":
                    return JSONResponse(content={
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "result": {
                            "tools": self.agent.get_tools_schema()
                        }
                    })
                
                elif method == "tools/call":
                    params = data.get("params", {})
                    tool_name = params.get("name")
                    arguments = params.get("arguments", {})
                    
                    logger.info(f"🔧 调用工具: {tool_name}")
                    result = await self.agent.call_tool(tool_name, arguments)
                    
                    if "error" in result:
                        return JSONResponse(content={
                            "jsonrpc": "2.0",
                            "id": request_id,
                            "error": result["error"]
                        })
                    
                    return JSONResponse(content={
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "result": result
                    })
                
                elif method == "initialize":
                    return JSONResponse(content={
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "result": {
                            "protocolVersion": "2024-11-05",
                            "capabilities": {
                                "tools": {}
                            },
                            "serverInfo": {
                                "name": "biblebot-agent-mcp-server",
                                "version": "1.0.0"
                            }
                        }
                    })
                
                else:
                    return JSONResponse(content={
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "error": {
                            "code": -32601,
                            "message": f"未知方法: {method}"
                        }
                    })
                    
            except Exception as e:
                logger.error(f"处理消息失败: {e}")
                raise HTTPException(status_code=500, detail=str(e))


def run_stdio_server():
    """运行 stdio 模式的 MCP 服务器"""
    # 添加项目根目录到 Python 路径
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    
    server = StdioMCPServer()
    asyncio.run(server.run())


def run_http_server(host: str = "0.0.0.0", port: int = 8001):
    """运行 HTTP/SSE 模式的 MCP 服务器"""
    import uvicorn
    
    # 添加项目根目录到 Python 路径
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    
    # 创建 Agent 服务器
    agent_server = AgentMCPServer()
    
    # 创建 HTTP 服务器
    http_server = HTTPMCPServer(agent_server)
    
    logger.info(f"🚀 启动 HTTP MCP 服务器: http://{host}:{port}")
    logger.info(f"📡 SSE 端点: http://{host}:{port}/sse")
    logger.info(f"📨 消息端点: http://{host}:{port}/message")
    
    uvicorn.run(http_server.app, host=host, port=port)


def main():
    """主入口 - 默认启动 stdio 模式"""
    run_stdio_server()


if __name__ == "__main__":
    main()
