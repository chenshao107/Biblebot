import requests
from sentence_transformers import SentenceTransformer
from typing import List, Dict, Any
import numpy as np
from loguru import logger
from app.core.config import settings
import re
import json
import time
from pathlib import Path
from collections import Counter

class HybridEmbedder:
    def __init__(self):
        self.use_api = settings.USE_EMBEDDING_API
        if not self.use_api:
            logger.info(f"Loading local dense embedding model: {settings.EMBEDDING_MODEL_NAME}")
            self.dense_model = SentenceTransformer(settings.EMBEDDING_MODEL_NAME)
        else:
            logger.info(f"Using Cloud API for embeddings: {settings.EMBEDDING_API_URL}")
        
        # Vocabulary for sparse encoding (simplified)
        self.sparse_vocab_size = 10000
        
        # API速率限制：记录上次调用时间
        self._last_api_call_time = 0
        self._min_call_interval = 0.1  # 每次API调用间隔至少100ms

    def embed_dense(self, text: str) -> List[float]:
        """Generates a dense vector."""
        if self.use_api:
            # API速率限制
            elapsed = time.time() - self._last_api_call_time
            if elapsed < self._min_call_interval:
                time.sleep(self._min_call_interval - elapsed)
            
            result = self._embed_dense_api(text)
            self._last_api_call_time = time.time()
            return result
        
        embedding = self.dense_model.encode(text)
        return embedding.tolist()

    def _embed_dense_api(self, text: str) -> List[float]:
        """Calls Cloud API for dense embedding with retry mechanism."""
        max_retries = 3
        retry_delay = 2  # 秒
        
        for attempt in range(max_retries):
            try:
                headers = {
                    "Authorization": f"Bearer {settings.EMBEDDING_API_KEY}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": settings.EMBEDDING_MODEL_NAME,
                    "input": text,
                    "encoding_format": "float"
                }
                response = requests.post(
                    settings.EMBEDDING_API_URL, 
                    json=payload, 
                    headers=headers,
                    timeout=30  # 添加超时设置
                )
                response.raise_for_status()
                return response.json()["data"][0]["embedding"]
                
            except requests.exceptions.RequestException as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Embedding API调用失败 (尝试 {attempt + 1}/{max_retries}): {e}")
                    logger.info(f"等待 {retry_delay} 秒后重试...")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # 指数退避
                else:
                    logger.error(f"Embedding API调用失败，已达最大重试次数: {e}")
                    raise e

    def embed_sparse(self, text: str) -> Dict[str, Any]:
        """
        Generates a sparse vector using a simplified hashing approach.
        In a production environment, you might use SPLADE or a real BM25 tokenizer.
        """
        tokens = self._tokenize(text)
        counts = Counter(tokens)
        
        # 使用字典来处理哈希冲突，合并相同index的值
        index_value_map = {}
        
        for token, count in counts.items():
            # Simple hashing to map tokens to a fixed index space
            idx = hash(token) % self.sparse_vocab_size
            # 如果index已存在，累加值（处理哈希冲突）
            if idx in index_value_map:
                index_value_map[idx] += float(count)
            else:
                index_value_map[idx] = float(count)
        
        # 转换为排序的列表（Qdrant要求indices有序）
        sorted_items = sorted(index_value_map.items())
        indices = [idx for idx, _ in sorted_items]
        values = [val for _, val in sorted_items]
            
        return {
            "indices": indices,
            "values": values
        }

    def _tokenize(self, text: str) -> List[str]:
        # Simple regex tokenizer
        text = text.lower()
        tokens = re.findall(r'\w+', text)
        # Filter short tokens
        return [t for t in tokens if len(t) > 1]

    def get_dim(self) -> int:
        if self.use_api:
            return settings.EMBEDDING_DIM
        return self.dense_model.get_sentence_embedding_dimension()

    def save_embedding_metadata(self, doc_id: str, chunks_embeddings: List[Dict[str, Any]]):
        """
        Saves embedding metadata for tuning reference.
        chunks_embeddings: List of {chunk_index, dense_dim, sparse_indices_count, content_preview}
        """
        if not settings.SAVE_INTERMEDIATE_FILES:
            return
            
        output_dir = Path(settings.DATA_EMBEDDINGS_DIR)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        output_path = output_dir / f"{Path(doc_id).stem}_embeddings.json"
        
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump({
                "doc_id": doc_id,
                "embedding_model": settings.EMBEDDING_MODEL_NAME,
                "use_api": self.use_api,
                "dense_dim": self.get_dim(),
                "sparse_vocab_size": self.sparse_vocab_size,
                "total_chunks": len(chunks_embeddings),
                "chunks": chunks_embeddings
            }, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Saved embedding metadata to {output_path}")
        return output_path
