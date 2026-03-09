from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Literal
import json
import time
import uuid
from loguru import logger
from app.agent import Agent, AgentResponse, get_default_tools
from app.services.rag.retriever import RAGEngine

router = APIRouter()

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
    """
    agent = get_agent()
    
    if request.stream:
        # 流式响应
        async def generate():
            for step in agent.run_stream(request.query, request.context):
                yield f"data: {json.dumps(step, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        
        return StreamingResponse(
            generate(),
            media_type="text/event-stream"
        )
    else:
        # 非流式响应
        try:
            response = AgentResponse()
            for step in agent.run_stream(request.query, request.context):
                response.add_step(step)
            return response.to_dict()
        except Exception as e:
            logger.error(f"Agent 执行失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))


# ============== OpenAI 兼容接口（供 LobeChat 等使用） ==============

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatCompletionRequest(BaseModel):
    model: str = "agent-knowledge"
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
    """
    # 提取用户最后一条消息作为查询
    user_messages = [m for m in request.messages if m.role == "user"]
    if not user_messages:
        raise HTTPException(status_code=400, detail="No user message found")
    
    query = user_messages[-1].content
    agent = get_agent()
    
    if request.stream:
        # 流式响应
        async def generate():
            response_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
            created = int(time.time())
            
            # 发送开始标记
            yield f"data: {json.dumps({'id': response_id, 'object': 'chat.completion.chunk', 'created': created, 'model': request.model, 'choices': [{'index': 0, 'delta': {'role': 'assistant'}, 'finish_reason': None}]}, ensure_ascii=False)}\n\n"
            
            # 收集完整回答
            full_content = ""
            for step in agent.run_stream(query):
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
                    # 如果前面没有步骤，直接发送答案
                    if not full_content:
                        yield f"data: {json.dumps({'id': response_id, 'object': 'chat.completion.chunk', 'created': created, 'model': request.model, 'choices': [{'index': 0, 'delta': {'content': content}, 'finish_reason': None}]}, ensure_ascii=False)}\n\n"
                    else:
                        # 前面有步骤，发送分隔线和答案
                        separator = "\n" + "="*50 + "\n\n📋 **最终答案**：\n\n"
                        yield f"data: {json.dumps({'id': response_id, 'object': 'chat.completion.chunk', 'created': created, 'model': request.model, 'choices': [{'index': 0, 'delta': {'content': separator}, 'finish_reason': None}]}, ensure_ascii=False)}\n\n"
                        yield f"data: {json.dumps({'id': response_id, 'object': 'chat.completion.chunk', 'created': created, 'model': request.model, 'choices': [{'index': 0, 'delta': {'content': content}, 'finish_reason': None}]}, ensure_ascii=False)}\n\n"
            
            # 发送结束标记
            yield f"data: {json.dumps({'id': response_id, 'object': 'chat.completion.chunk', 'created': created, 'model': request.model, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        
        return StreamingResponse(generate(), media_type="text/event-stream")
    
    else:
        # 非流式响应
        try:
            response = AgentResponse()
            for step in agent.run_stream(query):
                response.add_step(step)
            
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
                "id": "agent-knowledge",
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
