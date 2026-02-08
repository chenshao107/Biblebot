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
        4. RRF / Fusion (Handled by Qdrant/Retriever)
        5. Reranking
        """
        logger.info(f"Starting RAG search for: {query}")
        
        # 1. Expand query
        expanded_queries = self.rewriter.rewrite(query)
        
        all_hits = []
        # 2 & 3. For each variation, do hybrid search
        for q in expanded_queries:
            dense_vec = self.embedder.embed_dense(q)
            sparse_vec = self.embedder.embed_sparse(q)
            
            hits = self.storage.search_hybrid(dense_vec, sparse_vec, limit=20)
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
                
        # 4. Rerank the unique hits
        reranked_results = self.reranker.rerank(query, unique_hits, top_k=top_k)
        
        return reranked_results
