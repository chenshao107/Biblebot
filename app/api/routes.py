from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Literal
import json
import time
import uuid
import asyncio
from concurrent.futures import ThreadPoolExecutor
from loguru import logger
from app.agent import Agent, AgentResponse, get_default_tools
from app.services.rag.retriever import RAGEngine

router = APIRouter()

# 线程池配置
_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="agent_worker")

# ============== Agent 模式（主推） ==============

class AgentRequest(BaseModel):
    query: str
    context: Optional[str] = None
    stream: bool = False

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

@router.post("/agent")
async def agent_query(request: AgentRequest):
    """
    Agent 查询接口 - 智能体自主探索并回答问题
    
    - 非流式: 返回完整的执行过程和最终答案
    - 流式: 返回 SSE 流，逐步输出执行过程
    
    使用线程池支持并发请求，多个用户可以同时访问。
    """
    agent = get_agent()
    
    if request.stream:
        # 流式响应 - 使用 asyncio.Queue 实现跨线程数据传递
        queue: asyncio.Queue = asyncio.Queue()
        
        def run_in_thread():
            """在线程中执行 agent，将结果放入队列"""
            try:
                for step in agent.run_stream(request.query, request.context):
                    # 将结果放入队列（线程安全）
                    asyncio.run_coroutine_threadsafe(
                        queue.put(("step", step)), 
                        asyncio.get_event_loop()
                    )
                # 标记完成
                asyncio.run_coroutine_threadsafe(
                    queue.put(("done", None)), 
                    asyncio.get_event_loop()
                )
            except Exception as e:
                asyncio.run_coroutine_threadsafe(
                    queue.put(("error", str(e))), 
                    asyncio.get_event_loop()
                )
        
        async def generate():
            """异步生成器，从队列中读取数据"""
            # 启动线程执行
            loop = asyncio.get_event_loop()
            future = loop.run_in_executor(_executor, run_in_thread)
            
            try:
                while True:
                    msg_type, data = await queue.get()
                    if msg_type == "done":
                        break
                    elif msg_type == "error":
                        yield f"data: {json.dumps({'type': 'error', 'content': data}, ensure_ascii=False)}\n\n"
                        break
                    else:
                        yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
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
            for step in agent.run_stream(request.query, request.context):
                response.add_step(step)
            return response.to_dict()
        
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(_executor, run_agent)
            return result
        except Exception as e:
            logger.error(f"Agent 执行失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))


# ============== OpenAI 兼容接口（供 LobeChat 等使用） ==============

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatCompletionRequest(BaseModel):
    model: str = "bibobot"
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
    
    使用线程池支持并发请求。
    """
    # 提取用户最后一条消息作为查询
    user_messages = [m for m in request.messages if m.role == "user"]
    if not user_messages:
        raise HTTPException(status_code=400, detail="No user message found")
    
    query = user_messages[-1].content
    agent = get_agent()
    
    if request.stream:
        # 流式响应 - 使用 asyncio.Queue 实现跨线程数据传递
        queue: asyncio.Queue = asyncio.Queue()
        response_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
        created = int(time.time())
        
        def run_in_thread():
            """在线程中执行 agent，将结果放入队列"""
            try:
                for step in agent.run_stream(query):
                    asyncio.run_coroutine_threadsafe(
                        queue.put(("step", step)), 
                        asyncio.get_event_loop()
                    )
                asyncio.run_coroutine_threadsafe(
                    queue.put(("done", None)), 
                    asyncio.get_event_loop()
                )
            except Exception as e:
                asyncio.run_coroutine_threadsafe(
                    queue.put(("error", str(e))), 
                    asyncio.get_event_loop()
                )
        
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
                    msg_type, data = await queue.get()
                    if msg_type == "done":
                        break
                    elif msg_type == "error":
                        yield f"data: {json.dumps({'id': response_id, 'object': 'chat.completion.chunk', 'created': created, 'model': request.model, 'choices': [{'index': 0, 'delta': {'content': f'错误: {data}'}, 'finish_reason': None}]}, ensure_ascii=False)}\n\n"
                        break
                    else:
                        step = data
                        if step["type"] == "thinking":
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
            except Exception as e:
                logger.error(f"流式响应错误: {e}")
                yield f"data: {json.dumps({'id': response_id, 'object': 'chat.completion.chunk', 'created': created, 'model': request.model, 'choices': [{'index': 0, 'delta': {'content': f'错误: {e}'}, 'finish_reason': 'stop'}]}, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
        
        return StreamingResponse(generate(), media_type="text/event-stream")
    
    else:
        # 非流式响应 - 在线程池中执行
        def run_agent():
            response = AgentResponse()
            for step in agent.run_stream(query):
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
                "id": "bibobot",
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
