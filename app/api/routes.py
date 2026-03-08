from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import json
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
