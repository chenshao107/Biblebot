import requests
from sentence_transformers import SentenceTransformer
from typing import List, Dict, Any
import numpy as np
from loguru import logger
from app.core.config import settings
import re
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

    def embed_dense(self, text: str) -> List[float]:
        """Generates a dense vector."""
        if self.use_api:
            return self._embed_dense_api(text)
        
        embedding = self.dense_model.encode(text)
        return embedding.tolist()

    def _embed_dense_api(self, text: str) -> List[float]:
        """Calls Cloud API for dense embedding."""
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
            response = requests.post(settings.EMBEDDING_API_URL, json=payload, headers=headers)
            response.raise_for_status()
            return response.json()["data"][0]["embedding"]
        except Exception as e:
            logger.error(f"Error calling Embedding API: {e}")
            raise e

    def embed_sparse(self, text: str) -> Dict[str, Any]:
        """
        Generates a sparse vector using a simplified hashing approach.
        In a production environment, you might use SPLADE or a real BM25 tokenizer.
        """
        tokens = self._tokenize(text)
        counts = Counter(tokens)
        
        indices = []
        values = []
        
        for token, count in counts.items():
            # Simple hashing to map tokens to a fixed index space
            idx = hash(token) % self.sparse_vocab_size
            indices.append(idx)
            values.append(float(count))
            
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
            # Common dimensions: BGE-M3 (1024), OpenAI (1536)
            # You can also make this a config
            return 1024 if "bge-m3" in settings.EMBEDDING_MODEL_NAME.lower() else 768
        return self.dense_model.get_sentence_embedding_dimension()
