from typing import List, Dict, Any
from loguru import logger
from app.services.rag.embedder import HybridEmbedder
from app.services.rag.query_rewriter import QueryRewriter
from app.services.rag.reranker import HybridReranker
from app.services.storage.qdrant_client import QdrantStorage

class RAGEngine:
    def __init__(self):
        self.embedder = HybridEmbedder()
        self.rewriter = QueryRewriter()
        self.reranker = HybridReranker()
        self.storage = QdrantStorage()
        
        # Initialize storage collection on startup
        self.storage.init_collection(dense_dim=self.embedder.get_dim())

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Complete RAG retrieval pipeline:
        1. Query Rewriting (Expansion)
        2. Multi-query Embedding (Dense + Sparse)
        3. Hybrid Search in Qdrant
        4. Reranking (只要截断就 rerank)
        
        Args:
            query: 查询字符串
            top_k: 返回结果数量
        """
        logger.info(f"Starting RAG search for: {query} (top_k={top_k})")
        
        # 1. Expand query
        expanded_queries = self.rewriter.rewrite(query)
        
        all_hits = []
        # 2 & 3. For each variation, do hybrid search
        # 扩大搜索范围，确保有足够候选给 rerank
        search_limit = max(top_k * 4, 20)
        
        for q in expanded_queries:
            dense_vec = self.embedder.embed_dense(q)
            sparse_vec = self.embedder.embed_sparse(q)
            
            hits = self.storage.search_hybrid(dense_vec, sparse_vec, limit=search_limit)
            # Convert Qdrant objects to dict for consistency
            all_hits.extend([
                {
                    "id": h.id,
                    "payload": h.payload,
                    "score": h.score
                }
                for h in hits
            ])
            
        # De-duplicate hits based on content or ID
        seen_ids = set()
        unique_hits = []
        for h in all_hits:
            if h["id"] not in seen_ids:
                unique_hits.append(h)
                seen_ids.add(h["id"])
        
        logger.info(f"Retrieved {len(unique_hits)} unique hits from {len(expanded_queries)} query variations")
        
        # 4. Rerank (核心原则：只要截断就要 rerank)
        # 只有一种情况不 rerank：hits <= top_k（没有丢东西）
        if len(unique_hits) > top_k:
            logger.info(f"Reranking {len(unique_hits)} hits down to {top_k}")
            results = self.reranker.rerank(query, unique_hits, top_k=top_k)
        else:
            logger.info(f"Skipping rerank (hits {len(unique_hits)} <= top_k {top_k}, no truncation)")
            results = unique_hits[:top_k]
        
        return results
