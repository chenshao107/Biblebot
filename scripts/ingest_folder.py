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

# 尝试导入 tqdm，如果没有则提供一个简单的替代
try:
    from tqdm import tqdm
except ImportError:
    class tqdm:
        def __init__(self, iterable=None, total=None, desc=None, **kwargs):
            self.iterable = iterable
            self.total = total
            self.desc = desc
            self.n = 0
            if desc:
                logger.info(f"{desc} (tqdm not installed)")
        
        def __iter__(self):
            for item in self.iterable:
                yield item
                self.n += 1
        
        def __enter__(self):
            return self
        
        def __exit__(self, *args):
            pass
        
        def update(self, n=1):
            self.n += n
        
        def set_postfix(self, **kwargs):
            pass
        
        def close(self):
            pass

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

def process_file(file_path: Path, raw_dir: Path, converter, chunker, embedder, storage, pbar=None):
    """处理单个文件，返回 (是否成功, 生成的chunks数量)"""
    try:
        # 获取相对路径作为 doc_id
        rel_path = get_relative_path(file_path, raw_dir)
        path_info = extract_category_from_path(rel_path)
        
        if pbar:
            pbar.set_postfix(file=rel_path[:40] + "..." if len(rel_path) > 40 else rel_path)
        
        # 1. Convert
        md_content = converter.convert(file_path)
        converter.save_canonical(md_content, rel_path)
        
        # 2. Chunk - 传递完整的分类信息
        chunks = chunker.chunk(md_content, rel_path, path_info)
        chunker.save_chunks(chunks, rel_path)
        
        # 3. Embed & Prepare Points
        points = []
        embedding_metadata = []
        chunk_contents = [chunk["content"] for chunk in chunks]
        
        # 批量获取dense embedding（带进度条）
        dense_vectors = embedder.embed_dense_batch(
            chunk_contents, 
            batch_size=32,
            show_progress=True,
            desc=f"Embedding ({len(chunks)} chunks)"
        )
        
        # 处理每个chunk
        for i, (chunk, dense_vec) in enumerate(zip(chunks, dense_vectors)):
            content = chunk["content"]
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
        
        return True, len(chunks)
        
    except Exception as e:
        logger.error(f"Failed to process {file_path}: {e}")
        return False, 0

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
    
    # 统计
    success_count = 0
    failed_count = 0
    total_chunks = 0
    
    # 使用进度条处理文件（position=0 确保在最底部显示）
    with tqdm(total=len(doc_files), desc="📁 Files", unit="file", position=0, leave=True, ncols=100) as pbar:
        for file_path in doc_files:
            success, chunks_count = process_file(file_path, raw_dir, converter, chunker, embedder, storage, pbar)
            
            if success:
                success_count += 1
                total_chunks += chunks_count
            else:
                failed_count += 1
            
            pbar.update(1)
            pbar.set_postfix_str(
                f"✓{success_count} ✗{failed_count} chunks={total_chunks}"
            )
    
    # 最终统计
    logger.info("=" * 60)
    logger.info(f"Processing complete!")
    logger.info(f"  Total files: {len(doc_files)}")
    logger.info(f"  Successful:  {success_count}")
    logger.info(f"  Failed:      {failed_count}")
    logger.info(f"  Total chunks: {total_chunks}")
    logger.info("=" * 60)

if __name__ == "__main__":
    main()
