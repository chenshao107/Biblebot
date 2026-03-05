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

def get_relative_path(file_path: Path, base_dir: Path) -> str:
    """获取相对于 base_dir 的路径"""
    try:
        return str(file_path.relative_to(base_dir))
    except ValueError:
        return file_path.name

def extract_category_from_path(rel_path: str) -> dict:
    """
    从相对路径提取分类信息
    例如: RK3506/uboot/README.md -> 
    {
        "category": "RK3506",
        "subcategory": "uboot",
        "full_path": "RK3506/uboot/README.md"
    }
    """
    parts = rel_path.split('/')
    
    if len(parts) == 1:
        # 根目录下的文件
        return {
            "category": "root",
            "subcategory": "",
            "full_path": rel_path
        }
    else:
        # 子目录中的文件
        return {
            "category": parts[0],
            "subcategory": '/'.join(parts[1:-1]) if len(parts) > 2 else "",
            "full_path": rel_path
        }

def process_file(file_path: Path, raw_dir: Path, converter, chunker, embedder, storage):
    """处理单个文件"""
    try:
        # 获取相对路径作为 doc_id
        rel_path = get_relative_path(file_path, raw_dir)
        path_info = extract_category_from_path(rel_path)
        
        logger.info(f"Processing: {rel_path} (category: {path_info['category']})")
        
        # 1. Convert
        md_content = converter.convert(file_path)
        converter.save_canonical(md_content, rel_path)  # 使用相对路径保存
        
        # 2. Chunk - 传递完整的分类信息
        chunks = chunker.chunk(md_content, rel_path, path_info)
        chunker.save_chunks(chunks, rel_path)
        
        # 3. Embed & Prepare Points
        points = []
        embedding_metadata = []
        for i, chunk in enumerate(chunks):
            content = chunk["content"]
            dense_vec = embedder.embed_dense(content)
            sparse_vec = embedder.embed_sparse(content)
            
            embedding_metadata.append({
                "chunk_index": i,
                "dense_dim": len(dense_vec),
                "sparse_indices_count": len(sparse_vec["indices"]),
                "content_length": len(content),
                "content_preview": content[:200] + "..." if len(content) > 200 else content
            })
            
            points.append(models.PointStruct(
                id=hash(f"{rel_path}_{i}") & 0xFFFFFFFFFFFFFFFF,
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
        embedder.save_embedding_metadata(rel_path, embedding_metadata)
        
        # 5. Upsert
        storage.upsert_chunks(points)
        logger.info(f"Successfully ingested {rel_path}")
        
    except Exception as e:
        logger.error(f"Failed to process {file_path}: {e}")

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

    # 递归遍历所有文件（包括子目录）
    files = list(raw_dir.rglob("*"))
    doc_files = [f for f in files if f.is_file()]
    
    if not doc_files:
        logger.warning(f"No files found in {raw_dir}")
        return

    logger.info(f"Found {len(doc_files)} files to process")

    for file_path in doc_files:
        process_file(file_path, raw_dir, converter, chunker, embedder, storage)

if __name__ == "__main__":
    main()
