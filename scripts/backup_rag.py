#!/usr/bin/env python3
"""
RAG 数据备份脚本 - 导出 Qdrant 向量数据 + 本地文件

功能：
  1. 创建 Qdrant collection snapshot
  2. 打包本地数据文件（canonical_md, chunks, embeddings）
  3. 生成统一的备份文件

用法：
  # 创建完整备份（Qdrant snapshot + 本地文件）
  python3 scripts/backup_rag.py --output ./backups/rag_backup_$(date +%Y%m%d_%H%M%S).tar.gz

  # 仅备份 Qdrant snapshot
  python3 scripts/backup_rag.py --qdrant-only --output ./backups/qdrant_snapshot.snapshot

  # 仅备份本地文件
  python3 scripts/backup_rag.py --files-only --output ./backups/rag_files_$(date +%Y%m%d_%H%M%S).tar.gz

  # 查看 Qdrant collection 信息
  python3 scripts/backup_rag.py --info
"""

import os
import sys
import argparse
import tarfile
import tempfile
from pathlib import Path
from datetime import datetime
from loguru import logger

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from app.core.config import settings
from qdrant_client import QdrantClient


def get_qdrant_client():
    """获取 Qdrant 客户端"""
    return QdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)


def get_collection_info():
    """获取 collection 信息"""
    client = get_qdrant_client()
    
    try:
        collections = client.get_collections().collections
        collection_names = [c.name for c in collections]
        
        if settings.QDRANT_COLLECTION_NAME not in collection_names:
            logger.warning(f"Collection '{settings.QDRANT_COLLECTION_NAME}' 不存在")
            return None
        
        # 获取 collection 统计信息
        collection_info = client.get_collection(settings.QDRANT_COLLECTION_NAME)
        points_count = client.count(settings.QDRANT_COLLECTION_NAME).count
        
        return {
            "name": settings.QDRANT_COLLECTION_NAME,
            "vectors_config": collection_info.config.params.vectors,
            "sparse_vectors_config": collection_info.config.params.sparse_vectors,
            "points_count": points_count,
        }
    except Exception as e:
        logger.error(f"获取 collection 信息失败: {e}")
        return None


def create_qdrant_snapshot(output_path: str = None) -> str:
    """
    创建 Qdrant collection snapshot
    
    Args:
        output_path: 输出路径，如果为 None 则使用临时目录
    
    Returns:
        snapshot 文件路径
    """
    client = get_qdrant_client()
    
    try:
        # 创建 snapshot
        logger.info(f"正在创建 Qdrant collection '{settings.QDRANT_COLLECTION_NAME}' 的 snapshot...")
        snapshot_info = client.create_snapshot(
            collection_name=settings.QDRANT_COLLECTION_NAME
        )
        
        snapshot_name = snapshot_info.name
        logger.info(f"Snapshot 创建成功: {snapshot_name}")
        
        # 下载 snapshot 文件
        # Qdrant 的 snapshot 存储在服务器上，需要通过 HTTP API 下载
        import requests
        
        snapshot_url = f"http://{settings.QDRANT_HOST}:{settings.QDRANT_PORT}/collections/{settings.QDRANT_COLLECTION_NAME}/snapshots/{snapshot_name}"
        
        if output_path is None:
            output_path = f"./{snapshot_name}"
        
        logger.info(f"正在下载 snapshot 到: {output_path}")
        response = requests.get(snapshot_url, stream=True)
        response.raise_for_status()
        
        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        logger.info(f"Snapshot 下载完成: {output_path}")
        
        # 删除服务器上的 snapshot（可选）
        try:
            client.delete_snapshot(
                collection_name=settings.QDRANT_COLLECTION_NAME,
                snapshot_name=snapshot_name
            )
            logger.info(f"已清理服务器上的 snapshot: {snapshot_name}")
        except Exception as e:
            logger.warning(f"清理服务器 snapshot 失败（可忽略）: {e}")
        
        return output_path
        
    except Exception as e:
        logger.error(f"创建 snapshot 失败: {e}")
        raise


def backup_local_files(output_path: str, include_canonical: bool = True, 
                       include_chunks: bool = True, include_embeddings: bool = True) -> str:
    """
    备份本地数据文件
    
    Args:
        output_path: 输出 tar.gz 文件路径
        include_canonical: 是否包含 canonical_md
        include_chunks: 是否包含 chunks
        include_embeddings: 是否包含 embeddings
    
    Returns:
        备份文件路径
    """
    base_dir = Path(settings.BASE_DIR)
    
    # 确保输出目录存在
    output_dir = Path(output_path).parent
    output_dir.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"正在备份本地数据文件到: {output_path}")
    
    with tarfile.open(output_path, "w:gz") as tar:
        # 备份 canonical_md
        if include_canonical:
            canonical_dir = base_dir / settings.DATA_CANONICAL_DIR
            if canonical_dir.exists():
                logger.info(f"  - 添加: {settings.DATA_CANONICAL_DIR}")
                tar.add(canonical_dir, arcname="canonical_md")
            else:
                logger.warning(f"  - 跳过（不存在）: {settings.DATA_CANONICAL_DIR}")
        
        # 备份 chunks
        if include_chunks:
            chunks_dir = base_dir / settings.DATA_CHUNKS_DIR
            if chunks_dir.exists():
                logger.info(f"  - 添加: {settings.DATA_CHUNKS_DIR}")
                tar.add(chunks_dir, arcname="chunks")
            else:
                logger.warning(f"  - 跳过（不存在）: {settings.DATA_CHUNKS_DIR}")
        
        # 备份 embeddings
        if include_embeddings:
            embeddings_dir = base_dir / settings.DATA_EMBEDDINGS_DIR
            if embeddings_dir.exists():
                logger.info(f"  - 添加: {settings.DATA_EMBEDDINGS_DIR}")
                tar.add(embeddings_dir, arcname="embeddings")
            else:
                logger.warning(f"  - 跳过（不存在）: {settings.DATA_EMBEDDINGS_DIR}")
    
    # 获取文件大小
    file_size = Path(output_path).stat().st_size
    logger.info(f"本地文件备份完成: {output_path} ({file_size / 1024 / 1024:.2f} MB)")
    
    return output_path


def create_full_backup(output_path: str) -> str:
    """
    创建完整备份（Qdrant snapshot + 本地文件）
    
    Args:
        output_path: 输出 tar.gz 文件路径
    
    Returns:
        备份文件路径
    """
    # 创建临时目录
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # 1. 创建 Qdrant snapshot
        snapshot_path = temp_path / "qdrant.snapshot"
        create_qdrant_snapshot(str(snapshot_path))
        
        # 2. 备份本地文件到临时目录
        files_backup_path = temp_path / "local_files.tar.gz"
        backup_local_files(str(files_backup_path))
        
        # 3. 打包成统一备份
        output_dir = Path(output_path).parent
        output_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"正在创建统一备份: {output_path}")
        with tarfile.open(output_path, "w:gz") as tar:
            tar.add(snapshot_path, arcname="qdrant.snapshot")
            tar.add(files_backup_path, arcname="local_files.tar.gz")
            
            # 添加备份信息文件
            info_content = f"""Backup Information
==================
Created: {datetime.now().isoformat()}
Collection: {settings.QDRANT_COLLECTION_NAME}
Qdrant Host: {settings.QDRANT_HOST}:{settings.QDRANT_PORT}

Contents:
  - qdrant.snapshot: Qdrant collection snapshot
  - local_files.tar.gz: Local data files (canonical_md, chunks, embeddings)
"""
            info_path = temp_path / "BACKUP_INFO.txt"
            info_path.write_text(info_content)
            tar.add(info_path, arcname="BACKUP_INFO.txt")
        
        file_size = Path(output_path).stat().st_size
        logger.info(f"完整备份创建完成: {output_path} ({file_size / 1024 / 1024:.2f} MB)")
        
    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="RAG 数据备份脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python3 scripts/backup_rag.py --output ./backups/rag_backup.tar.gz
  python3 scripts/backup_rag.py --qdrant-only --output ./backups/qdrant.snapshot
  python3 scripts/backup_rag.py --files-only --output ./backups/local_files.tar.gz
        """
    )
    
    parser.add_argument(
        "--output", "-o",
        help="备份输出路径"
    )
    parser.add_argument(
        "--qdrant-only",
        action="store_true",
        help="仅备份 Qdrant snapshot"
    )
    parser.add_argument(
        "--files-only",
        action="store_true",
        help="仅备份本地文件"
    )
    parser.add_argument(
        "--info",
        action="store_true",
        help="显示 collection 信息"
    )
    
    args = parser.parse_args()
    
    # 显示信息
    if args.info:
        info = get_collection_info()
        if info:
            print("\n" + "="*60)
            print("Qdrant Collection 信息")
            print("="*60)
            print(f"Collection 名称: {info['name']}")
            print(f"向量数量: {info['points_count']}")
            print(f"Dense 配置: {info['vectors_config']}")
            print(f"Sparse 配置: {info['sparse_vectors_config']}")
            print("="*60 + "\n")
        return
    
    # 检查输出路径
    if not args.output:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        args.output = f"./backups/rag_backup_{timestamp}.tar.gz"
    
    try:
        if args.qdrant_only:
            # 仅备份 Qdrant
            create_qdrant_snapshot(args.output)
        elif args.files_only:
            # 仅备份本地文件
            backup_local_files(args.output)
        else:
            # 完整备份
            create_full_backup(args.output)
        
        logger.info("备份完成！")
        
    except Exception as e:
        logger.error(f"备份失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
