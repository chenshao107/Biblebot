import requests
from flashrank import Ranker, RerankRequest
from typing import List, Dict, Any
from loguru import logger
from app.core.config import settings

class HybridReranker:
    def __init__(self):
        self.use_api = settings.USE_RERANK_API
        self.enabled = settings.USE_RERANK_API  # 当 False 时完全跳过 rerank
        
        if not self.enabled:
            logger.info("Rerank 已禁用，将直接返回向量检索结果")
            return
        
        if self.use_api:
            logger.info(f"Using Cloud API for Rerank: {settings.RERANK_API_URL}")
        else:
            logger.info(f"Loading local Reranker model: {settings.RERANK_MODEL_NAME}")
            # FlashRank will download the model automatically
            self.ranker = Ranker(model_name=settings.RERANK_MODEL_NAME, cache_dir="./models")

    def rerank(self, query: str, passages: List[Dict[str, Any]], top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Reranks the retrieved passages based on the query.
        """
        if not passages:
            return []
        
        # 如果 rerank 被禁用，直接返回原结果
        if not self.enabled:
            logger.debug("Rerank 已禁用，跳过重排序")
            return passages[:top_k]

        if self.use_api:
            return self._rerank_api(query, passages, top_k)

        # Prepare passages for FlashRank
        flash_passages = [
            {
                "id": p.get("id", i),
                "text": p["payload"].get("content", ""),
                "meta": p["payload"]
            }
            for i, p in enumerate(passages)
        ]

        rerank_request = RerankRequest(query=query, passages=flash_passages)
        results = self.ranker.rerank(rerank_request)

        # FlashRank returns a list of results with scores
        logger.info(f"Reranked {len(passages)} passages down to {top_k} (Local)")
        return results[:top_k]

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
