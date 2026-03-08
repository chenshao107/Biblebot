import requests
from typing import List, Dict, Any
from loguru import logger
from app.core.config import settings

class HybridReranker:
    def __init__(self):
        # 强制使用 API 模式，不加载本地模型
        logger.info(f"Using Cloud API for Rerank: {settings.RERANK_API_URL}")

    def rerank(self, query: str, passages: List[Dict[str, Any]], top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Reranks the retrieved passages based on the query via API.
        """
        if not passages:
            return []

        return self._rerank_api(query, passages, top_k)

    def _rerank_api(self, query: str, passages: List[Dict[str, Any]], top_k: int) -> List[Dict[str, Any]]:
        """Calls Cloud API for reranking."""
        try:
            headers = {
                "Authorization": f"Bearer {settings.RERANK_API_KEY}",
                "Content-Type": "application/json"
            }
            # SiliconFlow rerank format
            payload = {
                "model": settings.RERANK_MODEL_NAME,
                "query": query,
                "documents": [p["payload"].get("content", "") for p in passages],
                "top_n": top_k
            }
            response = requests.post(settings.RERANK_API_URL, json=payload, headers=headers)
            response.raise_for_status()
            
            api_results = response.json()["results"]
            
            # Map back to our format
            final_results = []
            for res in api_results:
                idx = res["index"]
                original_p = passages[idx]
                final_results.append({
                    "id": original_p.get("id"),
                    "text": original_p["payload"].get("content", ""),
                    "score": res["relevance_score"],
                    "meta": original_p["payload"]
                })
            
            logger.info(f"Reranked {len(passages)} passages down to {top_k} (API)")
            return final_results
            
        except Exception as e:
            logger.error(f"Error calling Rerank API: {e}")
            # Fallback to simple slice if API fails
            return passages[:top_k]
