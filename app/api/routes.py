from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from loguru import logger
from app.services.rag.retriever import RAGEngine
from app.core.config import settings

router = APIRouter()

# ============== RAG 检索接口 ==============

class QueryRequest(BaseModel):
    query: str
    top_k: int = 5
    category_filter: Optional[str] = None

class QueryResponse(BaseModel):
    results: List[Dict[str, Any]]
    query: str
    total: int

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
    RAG 语义检索接口

    返回候选文档的路径、分数和摘要（snippet），遵循"轻RAG + 强探索"原则：
    - RAG 只负责"定位"候选文档
    - Claude CLI Agent 负责"探索"获取精确答案

    返回格式: [{path, title, score, snippet}, ...]
    """
    try:
        rag = get_rag_engine()
        raw_results = rag.search(
            query=request.query,
            top_k=request.top_k,
            category_filter=request.category_filter,
        )

        # 转换为轻量定位格式
        results = []
        for r in raw_results:
            if isinstance(r, dict):
                payload = r.get("payload", {})
                score = r.get("score", 0)
            else:
                payload = getattr(r, "payload", {})
                score = getattr(r, "score", 0)

            canonical_path = payload.get("canonical_path", payload.get("doc_id", "unknown"))
            section = payload.get("section", "")
            content = payload.get("content", "")

            max_len = settings.RAG_SEARCH_MAX_SNIPPET_LEN
            snippet = content[:max_len]
            if len(content) > max_len:
                snippet += "..."

            results.append({
                "path": canonical_path,
                "title": section if section and section != "Root" else "",
                "score": score,
                "snippet": snippet,
            })

        return QueryResponse(
            results=results,
            query=request.query,
            total=len(results),
        )

    except Exception as e:
        logger.error(f"RAG 检索失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "ok", "version": "3.0.0"}
