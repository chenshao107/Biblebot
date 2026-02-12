import os
import sys
from pathlib import Path
from loguru import logger

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from app.services.ingestion.converter import DoclingConverter
from app.services.ingestion.chunker import MarkdownChunker
from app.services.rag.embedder import HybridEmbedder
from app.services.storage.qdrant_client import QdrantStorage
from qdrant_client.http import models

def main():
    converter = DoclingConverter()
    chunker = MarkdownChunker()
    embedder = HybridEmbedder()
    storage = QdrantStorage()

    # Init collection
    storage.init_collection(dense_dim=embedder.get_dim())

    raw_dir = Path("data/raw")
    if not raw_dir.exists():
        raw_dir.mkdir(parents=True)
        logger.info(f"Created {raw_dir}. Please put your documents there.")
        return

    files = list(raw_dir.iterdir())
    if not files:
        logger.warning(f"No files found in {raw_dir}")
        return

    for file_path in files:
        if file_path.is_dir():
            continue
            
        try:
            # 1. Convert
            md_content = converter.convert(file_path)
            converter.save_canonical(md_content, file_path.name)
            
            # 2. Chunk
            doc_id = file_path.name
            chunks = chunker.chunk(md_content, doc_id)
            chunker.save_chunks(chunks, doc_id)  # 保存切块中间文件
            
            # 3. Embed & Prepare Points
            points = []
            embedding_metadata = []  # 用于保存嵌入元数据
            for i, chunk in enumerate(chunks):
                content = chunk["content"]
                dense_vec = embedder.embed_dense(content)
                sparse_vec = embedder.embed_sparse(content)
                
                # 收集嵌入元数据
                embedding_metadata.append({
                    "chunk_index": i,
                    "dense_dim": len(dense_vec),
                    "sparse_indices_count": len(sparse_vec["indices"]),
                    "content_length": len(content),
                    "content_preview": content[:200] + "..." if len(content) > 200 else content
                })
                
                points.append(models.PointStruct(
                    id=hash(f"{doc_id}_{i}") & 0xFFFFFFFFFFFFFFFF, # Simple int64 hash
                    vector={
                        "dense": dense_vec,
                        "sparse": models.SparseVector(
                            indices=sparse_vec["indices"],
                            values=sparse_vec["values"]
                        )
                    },
                    payload={
                        **chunk["metadata"],
                        "content": content
                    }
                ))
            
            # 4. Save Embedding Metadata
            embedder.save_embedding_metadata(doc_id, embedding_metadata)
            
            # 5. Upsert
            storage.upsert_chunks(points)
            logger.info(f"Successfully ingested {file_path.name}")
            
        except Exception as e:
            logger.error(f"Failed to process {file_path.name}: {e}")

if __name__ == "__main__":
    main()
