from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any
from app.services.rag.retriever import RAGEngine

router = APIRouter()
rag_engine = RAGEngine()

class QueryRequest(BaseModel):
    query: str
    top_k: int = 5

class QueryResponse(BaseModel):
    results: List[Dict[str, Any]]

@router.post("/query", response_model=QueryResponse)
async def query_rag(request: QueryRequest):
    try:
        results = rag_engine.search(request.query, top_k=request.top_k)
        return QueryResponse(results=results)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
