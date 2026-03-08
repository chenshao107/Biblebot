from qdrant_client import QdrantClient
from qdrant_client.http import models
from loguru import logger
from app.core.config import settings

class QdrantStorage:
    def __init__(self):
        self.client = QdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)
        self.collection_name = settings.QDRANT_COLLECTION_NAME

    def init_collection(self, dense_dim: int = 768):
        """
        Initializes the Qdrant collection with both dense and sparse vector configurations.
        """
        try:
            collections = self.client.get_collections().collections
            exists = any(c.name == self.collection_name for c in collections)
            
            if exists:
                logger.info(f"Collection {self.collection_name} already exists. Skipping creation.")
                return

            logger.info(f"Creating collection {self.collection_name} with Hybrid Search support...")
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config={
                    "dense": models.VectorParams(
                        size=dense_dim,
                        distance=models.Distance.COSINE
                    )
                },
                sparse_vectors_config={
                    "sparse": models.SparseVectorParams(
                        index=models.SparseIndexParams(
                            on_disk=False,
                        )
                    )
                }
            )
            logger.info(f"Collection {self.collection_name} created successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize Qdrant collection: {e}")
            raise e

    def upsert_chunks(self, points: list, batch_size: int = 100):
        """
        Upserts points (chunks) into Qdrant with batching to avoid payload size limits.
        Each point should have dense and sparse vectors in the 'vectors' dict.
        
        Args:
            points: List of PointStruct to upsert
            batch_size: Number of points per batch (default: 100)
        """
        try:
            total_points = len(points)
            for i in range(0, total_points, batch_size):
                batch = points[i:i + batch_size]
                self.client.upsert(
                    collection_name=self.collection_name,
                    points=batch
                )
                logger.info(f"Upserted batch {i//batch_size + 1}/{(total_points + batch_size - 1)//batch_size}, "
                           f"{len(batch)} points to {self.collection_name}")
            
            logger.info(f"Successfully upserted {total_points} points total to {self.collection_name}")
        except Exception as e:
            logger.error(f"Error during upsert: {e}")
            raise e

    def search_hybrid(self, dense_vector: list, sparse_vector: dict, limit: int = 10):
        """
        Performs a hybrid search combining dense and sparse results.
        """
        try:
            prefetch = [
                models.Prefetch(
                    query=dense_vector,
                    using="dense",
                    limit=limit * 2,
                ),
                models.Prefetch(
                    query=models.SparseVector(
                        indices=sparse_vector["indices"],
                        values=sparse_vector["values"]
                    ),
                    using="sparse",
                    limit=limit * 2,
                ),
            ]
            
            # Using RRF or Simple Fusion (Qdrant handles fusion in Query API)
            results = self.client.query_points(
                collection_name=self.collection_name,
                prefetch=prefetch,
                query=models.FusionQuery(fusion=models.Fusion.RRF),
                limit=limit,
            ).points
            
            return results
        except Exception as e:
            logger.error(f"Error during hybrid search: {e}")
            raise e
