from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Literal
import json
import time
import uuid
import asyncio
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict
from loguru import logger
from app.agent import Agent, AgentResponse, get_default_tools
from app.services.rag.retriever import RAGEngine
from app.core.config import settings

router = APIRouter()

# 线程池配置 - 从配置文件读取
_executor = ThreadPoolExecutor(
    max_workers=settings.THREAD_POOL_MAX_WORKERS, 
    thread_name_prefix="agent_worker"
)

# 对话历史存储（内存中，按 session_id 分组）
# 格式: {session_id: [{"role": "user"/"assistant", "content": "..."}, ...]}
_conversation_history: Dict[str, List[Dict[str, str]]] = defaultdict(list)

# ============== Agent 模式（主推） ==============

class AgentRequest(BaseModel):
    query: str
    context: Optional[str] = None
    stream: bool = False
    session_id: Optional[str] = None  # 对话会话 ID，用于维护上下文

class AgentStepResponse(BaseModel):
    type: str  # thinking, tool_call, tool_result, final_answer
    content: str
    tool_name: Optional[str] = None
    tool_args: Optional[Dict[str, Any]] = None

class AgentFullResponse(BaseModel):
    answer: str
    steps: List[Dict[str, Any]]

# 懒加载 Agent
_agent: Optional[Agent] = None

def get_agent() -> Agent:
    global _agent
    if _agent is None:
        logger.info("初始化 Agent...")
        _agent = Agent(tools=get_default_tools())
    return _agent

def _get_conversation_context(session_id: Optional[str]) -> str:
    """获取对话历史作为上下文"""
    if not session_id or session_id not in _conversation_history:
        return ""
    
    history = _conversation_history[session_id]
    if not history:
        return ""
    
    max_history = settings.CONVERSATION_MAX_HISTORY
    max_length = settings.CONVERSATION_MAX_MESSAGE_LENGTH
    
    # 构建对话历史文本
    context_parts = ["=== 对话历史 ==="]
    for msg in history[-max_history * 2:]:  # 只取最近的消息（一轮=2条消息）
        role = "用户" if msg["role"] == "user" else "助手"
        content = msg["content"][:max_length]  # 限制单条消息长度
        if len(msg["content"]) > max_length:
            content += "..."
        context_parts.append(f"{role}: {content}")
    
    context_parts.append("=== 当前问题 ===")
    return "\n".join(context_parts)


def _add_to_history(session_id: Optional[str], role: str, content: str):
    """添加消息到对话历史"""
    if not session_id:
        return
    
    max_history = settings.CONVERSATION_MAX_HISTORY
    
    _conversation_history[session_id].append({
        "role": role,
        "content": content,
        "timestamp": time.time()
    })
    
    # 限制历史长度，保留最近的消息（一轮=2条消息，所以乘以2）
    max_messages = max_history * 2
    if len(_conversation_history[session_id]) > max_messages:
        _conversation_history[session_id] = _conversation_history[session_id][-max_messages:]


@router.post("/agent")
async def agent_query(request: AgentRequest):
    """
    Agent 查询接口 - 智能体自主探索并回答问题
    
    - 非流式: 返回完整的执行过程和最终答案
    - 流式: 返回 SSE 流，逐步输出执行过程
    - 支持 session_id 维护对话上下文
    
    使用线程池支持并发请求，多个用户可以同时访问。
    """
    agent = get_agent()
    
    # 获取对话历史并构建上下文
    history_context = _get_conversation_context(request.session_id)
    if history_context:
        if request.context:
            full_context = f"{history_context}\n\n额外背景：\n{request.context}"
        else:
            full_context = history_context
    else:
        full_context = request.context
    
    # 记录用户消息到历史
    _add_to_history(request.session_id, "user", request.query)
    
    if request.stream:
        # 流式响应 - 使用 asyncio.Queue 实现跨线程数据传递
        queue: asyncio.Queue = asyncio.Queue()
        main_loop = asyncio.get_event_loop()  # 获取主线程的 event loop
        
        def run_in_thread():
            """在线程中执行 agent，将结果放入队列"""
            try:
                for step in agent.run_stream(request.query, full_context):
                    # 将结果放入队列（线程安全），等待完成
                    future = asyncio.run_coroutine_threadsafe(
                        queue.put(("step", step)), 
                        main_loop
                    )
                    future.result()  # 等待放入完成
                # 标记完成
                future = asyncio.run_coroutine_threadsafe(
                    queue.put(("done", None)), 
                    main_loop
                )
                future.result()
            except Exception as e:
                future = asyncio.run_coroutine_threadsafe(
                    queue.put(("error", str(e))), 
                    main_loop
                )
                future.result()
        
        async def generate():
            """异步生成器，从队列中读取数据"""
            # 启动线程执行
            loop = asyncio.get_event_loop()
            future = loop.run_in_executor(_executor, run_in_thread)
            
            final_answer = ""
            try:
                while True:
                    # 检查客户端是否断开（通过取消任务）
                    if asyncio.current_task().cancelled():
                        logger.info("客户端断开连接，停止 Agent")
                        agent.stop()
                        break
                    
                    try:
                        msg_type, data = await asyncio.wait_for(queue.get(), timeout=0.5)
                    except asyncio.TimeoutError:
                        # 超时后继续循环，检查取消状态
                        continue
                    
                    if msg_type == "done":
                        break
                    elif msg_type == "error":
                        yield f"data: {json.dumps({'type': 'error', 'content': data}, ensure_ascii=False)}\n\n"
                        break
                    else:
                        if data.get("type") == "final_answer":
                            final_answer = data.get("content", "")
                        elif data.get("type") == "stopped":
                            # Agent 被停止
                            yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
                            break
                        yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
                
                # 记录助手回复到历史
                if final_answer and request.session_id:
                    _add_to_history(request.session_id, "assistant", final_answer)
                
                yield "data: [DONE]\n\n"
            except asyncio.CancelledError:
                # 客户端断开连接
                logger.info("客户端断开连接（CancelledError），停止 Agent")
                agent.stop()
                raise
            except Exception as e:
                logger.error(f"流式响应错误: {e}")
                yield f"data: {json.dumps({'type': 'error', 'content': str(e)}, ensure_ascii=False)}\n\n"
        
        return StreamingResponse(
            generate(),
            media_type="text/event-stream"
        )
    else:
        # 非流式响应 - 在线程池中执行
        def run_agent():
            response = AgentResponse()
            for step in agent.run_stream(request.query, full_context):
                response.add_step(step)
            return response
        
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(_executor, run_agent)
            
            # 记录助手回复到历史
            if response.final_answer and request.session_id:
                _add_to_history(request.session_id, "assistant", response.final_answer)
            
            return response.to_dict()
        except Exception as e:
            logger.error(f"Agent 执行失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))


# ============== OpenAI 兼容接口（供 LobeChat 等使用） ==============

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatCompletionRequest(BaseModel):
    model: str = "biblebot"
    messages: List[ChatMessage]
    stream: bool = False
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = None

class ChatCompletionChoice(BaseModel):
    index: int
    message: Optional[ChatMessage] = None
    delta: Optional[ChatMessage] = None
    finish_reason: Optional[str] = None

class ChatCompletionResponse(BaseModel):
    id: str
    object: str
    created: int
    model: str
    choices: List[ChatCompletionChoice]

@router.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
    """
    OpenAI 兼容的聊天完成接口
    供 LobeChat、ChatGPT-Next-Web 等客户端使用
    
    支持完整的对话上下文，使用 messages 中的历史记录。
    使用线程池支持并发请求。
    """
    # 提取用户最后一条消息作为查询
    user_messages = [m for m in request.messages if m.role == "user"]
    if not user_messages:
        raise HTTPException(status_code=400, detail="No user message found")
    
    query = user_messages[-1].content
    
    # 构建对话历史上下文（排除最后一条用户消息，因为它作为当前查询）
    conversation_parts = []
    for msg in request.messages[:-1]:  # 排除最后一条
        role = "用户" if msg.role == "user" else "助手"
        content = msg.content[:1000]  # 限制长度
        conversation_parts.append(f"{role}: {content}")
    
    context = ""
    if conversation_parts:
        context = "=== 对话历史 ===\n" + "\n".join(conversation_parts[-10:])  # 最近10轮
    
    agent = get_agent()
    
    if request.stream:
        # 流式响应 - 使用 asyncio.Queue 实现跨线程数据传递
        queue: asyncio.Queue = asyncio.Queue()
        response_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
        created = int(time.time())
        main_loop = asyncio.get_event_loop()  # 获取主线程的 event loop
        
        def run_in_thread():
            """在线程中执行 agent，将结果放入队列"""
            try:
                for step in agent.run_stream(query, context):
                    future = asyncio.run_coroutine_threadsafe(
                        queue.put(("step", step)), 
                        main_loop
                    )
                    future.result()
                future = asyncio.run_coroutine_threadsafe(
                    queue.put(("done", None)), 
                    main_loop
                )
                future.result()
            except Exception as e:
                future = asyncio.run_coroutine_threadsafe(
                    queue.put(("error", str(e))), 
                    main_loop
                )
                future.result()
        
        async def generate():
            """异步生成器，从队列中读取数据并格式化为 OpenAI 流式格式"""
            # 启动线程执行
            loop = asyncio.get_event_loop()
            future = loop.run_in_executor(_executor, run_in_thread)
            
            # 发送开始标记
            yield f"data: {json.dumps({'id': response_id, 'object': 'chat.completion.chunk', 'created': created, 'model': request.model, 'choices': [{'index': 0, 'delta': {'role': 'assistant'}, 'finish_reason': None}]}, ensure_ascii=False)}\n\n"
            
            full_content = ""
            try:
                while True:
                    # 检查客户端是否断开（通过取消任务）
                    if asyncio.current_task().cancelled():
                        logger.info("客户端断开连接，停止 Agent")
                        agent.stop()
                        break
                    
                    try:
                        msg_type, data = await asyncio.wait_for(queue.get(), timeout=0.5)
                    except asyncio.TimeoutError:
                        # 超时后继续循环，检查取消状态
                        continue
                    
                    if msg_type == "done":
                        break
                    elif msg_type == "error":
                        yield f"data: {json.dumps({'id': response_id, 'object': 'chat.completion.chunk', 'created': created, 'model': request.model, 'choices': [{'index': 0, 'delta': {'content': f'错误: {data}'}, 'finish_reason': None}]}, ensure_ascii=False)}\n\n"
                        break
                    else:
                        step = data
                        if step["type"] == "stopped":
                            # Agent 被停止
                            yield f"data: {json.dumps({'id': response_id, 'object': 'chat.completion.chunk', 'created': created, 'model': request.model, 'choices': [{'index': 0, 'delta': {'content': '[已停止]'}, 'finish_reason': 'stop'}]}, ensure_ascii=False)}\n\n"
                            break
                        elif step["type"] == "thinking":
                            content = f"💭 {step['content']}\n\n"
                            full_content += content
                            yield f"data: {json.dumps({'id': response_id, 'object': 'chat.completion.chunk', 'created': created, 'model': request.model, 'choices': [{'index': 0, 'delta': {'content': content}, 'finish_reason': None}]}, ensure_ascii=False)}\n\n"
                        
                        elif step["type"] == "tool_call":
                            content = f"🔧 调用工具: {step['tool_name']}\n\n"
                            full_content += content
                            yield f"data: {json.dumps({'id': response_id, 'object': 'chat.completion.chunk', 'created': created, 'model': request.model, 'choices': [{'index': 0, 'delta': {'content': content}, 'finish_reason': None}]}, ensure_ascii=False)}\n\n"
                        
                        elif step["type"] == "tool_result":
                            content = f"✅ 工具返回结果\n\n"
                            full_content += content
                            yield f"data: {json.dumps({'id': response_id, 'object': 'chat.completion.chunk', 'created': created, 'model': request.model, 'choices': [{'index': 0, 'delta': {'content': content}, 'finish_reason': None}]}, ensure_ascii=False)}\n\n"
                        
                        elif step["type"] == "final_answer":
                            content = step["content"]
                            if not full_content:
                                yield f"data: {json.dumps({'id': response_id, 'object': 'chat.completion.chunk', 'created': created, 'model': request.model, 'choices': [{'index': 0, 'delta': {'content': content}, 'finish_reason': None}]}, ensure_ascii=False)}\n\n"
                            else:
                                separator = "\n" + "="*50 + "\n\n📋 **最终答案**：\n\n"
                                yield f"data: {json.dumps({'id': response_id, 'object': 'chat.completion.chunk', 'created': created, 'model': request.model, 'choices': [{'index': 0, 'delta': {'content': separator}, 'finish_reason': None}]}, ensure_ascii=False)}\n\n"
                                yield f"data: {json.dumps({'id': response_id, 'object': 'chat.completion.chunk', 'created': created, 'model': request.model, 'choices': [{'index': 0, 'delta': {'content': content}, 'finish_reason': None}]}, ensure_ascii=False)}\n\n"
                
                # 发送结束标记
                yield f"data: {json.dumps({'id': response_id, 'object': 'chat.completion.chunk', 'created': created, 'model': request.model, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]}, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
            except asyncio.CancelledError:
                # 客户端断开连接
                logger.info("客户端断开连接（CancelledError），停止 Agent")
                agent.stop()
                raise
            except Exception as e:
                logger.error(f"流式响应错误: {e}")
                yield f"data: {json.dumps({'id': response_id, 'object': 'chat.completion.chunk', 'created': created, 'model': request.model, 'choices': [{'index': 0, 'delta': {'content': f'错误: {e}'}, 'finish_reason': 'stop'}]}, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
        
        return StreamingResponse(generate(), media_type="text/event-stream")
    
    else:
        # 非流式响应 - 在线程池中执行
        def run_agent():
            response = AgentResponse()
            for step in agent.run_stream(query, context):
                response.add_step(step)
            return response
        
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(_executor, run_agent)
            
            return ChatCompletionResponse(
                id=f"chatcmpl-{uuid.uuid4().hex[:12]}",
                object="chat.completion",
                created=int(time.time()),
                model=request.model,
                choices=[
                    ChatCompletionChoice(
                        index=0,
                        message=ChatMessage(role="assistant", content=response.final_answer),
                        finish_reason="stop"
                    )
                ]
            )
        except Exception as e:
            logger.error(f"Agent 执行失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))

@router.get("/v1/models")
async def list_models():
    """
    OpenAI 兼容的模型列表接口
    """
    return {
        "object": "list",
        "data": [
            {
                "id": "biblebot",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "knowledge-agent"
            }
        ]
    }


# ============== RAG 模式（保留兼容） ==============

class QueryRequest(BaseModel):
    query: str
    top_k: int = 5

class QueryResponse(BaseModel):
    results: List[Dict[str, Any]]

# 懒加载 RAG 引擎
_rag_engine: Optional[RAGEngine] = None

def get_rag_engine() -> RAGEngine:
    global _rag_engine
    if _rag_engine is None:
        logger.info("初始化 RAG 引擎...")
        _rag_engine = RAGEngine()
    return _rag_engine

@router.post("/query", response_model=QueryResponse)
async def query_rag(request: QueryRequest):
    """
    RAG 检索接口 - 纯向量检索，不调用 Agent
    保留此接口用于快速检索场景
    注意：只要检索结果超过 top_k 就会自动 rerank
    """
    try:
        rag_engine = get_rag_engine()
        results = rag_engine.search(request.query, top_k=request.top_k)
        return QueryResponse(results=results)
    except Exception as e:
        logger.error(f"RAG 检索失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
