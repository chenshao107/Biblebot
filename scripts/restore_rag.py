#!/usr/bin/env python3
"""
RAG 数据恢复脚本 - 导入 Qdrant 向量数据 + 本地文件

功能：
  1. 从 snapshot 恢复 Qdrant collection
  2. 解压本地数据文件到正确位置
  3. 支持完整备份和单独恢复

用法：
  # 从完整备份恢复（Qdrant + 本地文件）
  python3 scripts/restore_rag.py --input ./backups/rag_backup_20240101_120000.tar.gz

  # 仅从 snapshot 恢复 Qdrant
  python3 scripts/restore_rag.py --input ./backups/qdrant.snapshot --qdrant-only

  # 仅从本地文件恢复
  python3 scripts/restore_rag.py --input ./backups/local_files.tar.gz --files-only

  # 恢复前预览（不实际执行）
  python3 scripts/restore_rag.py --input ./backups/rag_backup.tar.gz --dry-run

  # 强制恢复（删除现有数据）
  python3 scripts/restore_rag.py --input ./backups/rag_backup.tar.gz --force
"""

import os
import sys
import argparse
import tarfile
import tempfile
import shutil
from pathlib import Path
from loguru import logger

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from app.core.config import settings
from qdrant_client import QdrantClient


def get_qdrant_client():
    """获取 Qdrant 客户端"""
    return QdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)


def check_collection_exists() -> bool:
    """检查 collection 是否存在"""
    client = get_qdrant_client()
    collections = client.get_collections().collections
    return any(c.name == settings.QDRANT_COLLECTION_NAME for c in collections)


def get_collection_info():
    """获取当前 collection 信息"""
    if not check_collection_exists():
        return None
    
    client = get_qdrant_client()
    try:
        points_count = client.count(settings.QDRANT_COLLECTION_NAME).count
        return {"points_count": points_count}
    except Exception:
        return None


def restore_qdrant_snapshot(snapshot_path: str, force: bool = False, dry_run: bool = False):
    """
    从 snapshot 恢复 Qdrant collection
    
    Args:
        snapshot_path: snapshot 文件路径
        force: 如果 collection 已存在，是否删除后重建
        dry_run: 仅预览，不实际执行
    """
    client = get_qdrant_client()
    snapshot_path = Path(snapshot_path)
    
    if not snapshot_path.exists():
        raise FileNotFoundError(f"Snapshot 文件不存在: {snapshot_path}")
    
    # 检查现有 collection
    exists = check_collection_exists()
    if exists:
        current_info = get_collection_info()
        logger.warning(f"Collection '{settings.QDRANT_COLLECTION_NAME}' 已存在")
        logger.warning(f"  - 当前向量数量: {current_info['points_count']}")
        
        if not force:
            logger.error("使用 --force 强制覆盖现有 collection，或手动删除后重试")
            raise RuntimeError("Collection 已存在，请使用 --force 强制恢复")
        
        if dry_run:
            logger.info("[DRY-RUN] 将删除现有 collection 并从 snapshot 恢复")
        else:
            logger.info("正在删除现有 collection...")
            client.delete_collection(settings.QDRANT_COLLECTION_NAME)
            logger.info("现有 collection 已删除")
    
    if dry_run:
        logger.info(f"[DRY-RUN] 将从 snapshot 恢复: {snapshot_path}")
        logger.info(f"[DRY-RUN] Snapshot 大小: {snapshot_path.stat().st_size / 1024 / 1024:.2f} MB")
        return
    
    # 上传并恢复 snapshot
    logger.info(f"正在上传 snapshot: {snapshot_path}")
    
    try:
        import time
        
        # 使用 Qdrant Python 客户端的 recover_snapshot 方法
        # 这是最简单可靠的方式
        
        logger.info("正在恢复 snapshot（使用客户端 API）...")
        
        # 方法1: 使用 recover_snapshot 方法从本地文件恢复
        # 这个方法会在服务器上创建 collection 并恢复数据
        client.recover_snapshot(
            collection_name=settings.QDRANT_COLLECTION_NAME,
            location=str(snapshot_path),
            wait=True  # 等待恢复完成
        )
        
        logger.info("Snapshot 恢复命令已发送，等待完成...")
        time.sleep(3)  # 给服务器一些时间处理
        
        # 验证恢复结果
        max_retries = 10
        for i in range(max_retries):
            try:
                new_info = get_collection_info()
                if new_info and new_info['points_count'] > 0:
                    logger.info(f"Qdrant 恢复完成！")
                    logger.info(f"  - 恢复后向量数量: {new_info['points_count']}")
                    break
            except Exception as e:
                logger.debug(f"等待恢复完成... ({i+1}/{max_retries})")
                time.sleep(1)
        else:
            logger.warning("无法验证恢复结果，请手动检查")
        
    except Exception as e:
        logger.error(f"恢复 Qdrant snapshot 失败: {e}")
        # 尝试备选方法：使用 HTTP API
        logger.info("尝试使用备选方法恢复...")
        try:
            import requests
            
            # 备选方法：上传 snapshot 文件并恢复
            upload_url = f"http://{settings.QDRANT_HOST}:{settings.QDRANT_PORT}/collections/{settings.QDRANT_COLLECTION_NAME}/snapshots/upload"
            
            with open(snapshot_path, 'rb') as f:
                response = requests.post(upload_url, files={'snapshot': f}, timeout=300)
                response.raise_for_status()
            
            logger.info("Snapshot 上传成功")
            logger.warning("请手动在 Qdrant Dashboard 或使用以下命令恢复:")
            logger.warning(f"  PUT http://{settings.QDRANT_HOST}:{settings.QDRANT_PORT}/collections/{settings.QDRANT_COLLECTION_NAME}/snapshots/recover")
            logger.warning(f"  Body: {{\"location\": \"{snapshot_path.name}\"}}")
            
        except Exception as e2:
            logger.error(f"备选方法也失败: {e2}")
            raise e


def restore_local_files(backup_path: str, dry_run: bool = False):
    """
    恢复本地数据文件
    
    Args:
        backup_path: 备份文件路径（tar.gz）
        dry_run: 仅预览，不实际执行
    """
    backup_path = Path(backup_path)
    base_dir = Path(settings.BASE_DIR)
    
    if not backup_path.exists():
        raise FileNotFoundError(f"备份文件不存在: {backup_path}")
    
    logger.info(f"正在恢复本地文件: {backup_path}")
    
    if dry_run:
        logger.info("[DRY-RUN] 将解压以下内容:")
    
    with tarfile.open(backup_path, "r:gz") as tar:
        # 列出所有成员
        members = tar.getmembers()
        
        for member in members:
            if dry_run:
                logger.info(f"  - {member.name}")
                continue
            
            # 确定目标路径
            if member.name.startswith("canonical_md/"):
                target = base_dir / settings.DATA_CANONICAL_DIR / member.name[13:]  # 去掉 "canonical_md/" 前缀
            elif member.name.startswith("chunks/"):
                target = base_dir / settings.DATA_CHUNKS_DIR / member.name[7:]  # 去掉 "chunks/" 前缀
            elif member.name.startswith("embeddings/"):
                target = base_dir / settings.DATA_EMBEDDINGS_DIR / member.name[11:]  # 去掉 "embeddings/" 前缀
            else:
                logger.warning(f"  - 跳过未知文件: {member.name}")
                continue
            
            # 解压文件
            if member.isfile():
                target.parent.mkdir(parents=True, exist_ok=True)
                with tar.extractfile(member) as src, open(target, 'wb') as dst:
                    shutil.copyfileobj(src, dst)
                logger.debug(f"  - 恢复: {target}")
    
    if not dry_run:
        logger.info("本地文件恢复完成")


def restore_full_backup(backup_path: str, force: bool = False, dry_run: bool = False):
    """
    从完整备份恢复
    
    Args:
        backup_path: 完整备份文件路径
        force: 是否强制覆盖
        dry_run: 仅预览
    """
    backup_path = Path(backup_path)
    
    if not backup_path.exists():
        raise FileNotFoundError(f"备份文件不存在: {backup_path}")
    
    logger.info(f"正在从完整备份恢复: {backup_path}")
    
    # 创建临时目录
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # 解压备份
        logger.info("正在解压备份文件...")
        with tarfile.open(backup_path, "r:gz") as tar:
            tar.extractall(temp_path)
        
        # 检查备份内容
        snapshot_file = temp_path / "qdrant.snapshot"
        files_backup = temp_path / "local_files.tar.gz"
        info_file = temp_path / "BACKUP_INFO.txt"
        
        if info_file.exists():
            logger.info("备份信息:")
            print("\n" + info_file.read_text() + "\n")
        
        # 恢复 Qdrant
        if snapshot_file.exists():
            restore_qdrant_snapshot(str(snapshot_file), force=force, dry_run=dry_run)
        else:
            logger.warning("备份中未找到 Qdrant snapshot")
        
        # 恢复本地文件
        if files_backup.exists():
            restore_local_files(str(files_backup), dry_run=dry_run)
        else:
            logger.warning("备份中未找到本地文件")
    
    logger.info("完整备份恢复完成！")


def main():
    parser = argparse.ArgumentParser(
        description="RAG 数据恢复脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python3 scripts/restore_rag.py --input ./backups/rag_backup.tar.gz
  python3 scripts/restore_rag.py --input ./backups/qdrant.snapshot --qdrant-only
  python3 scripts/restore_rag.py --input ./backups/local_files.tar.gz --files-only
  python3 scripts/restore_rag.py --input ./backups/rag_backup.tar.gz --dry-run
  python3 scripts/restore_rag.py --input ./backups/rag_backup.tar.gz --force
        """
    )
    
    parser.add_argument(
        "--input", "-i",
        required=True,
        help="备份文件路径"
    )
    parser.add_argument(
        "--qdrant-only",
        action="store_true",
        help="仅恢复 Qdrant（输入必须是 .snapshot 文件）"
    )
    parser.add_argument(
        "--files-only",
        action="store_true",
        help="仅恢复本地文件"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="强制覆盖现有数据"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="预览恢复操作，不实际执行"
    )
    
    args = parser.parse_args()
    
    try:
        if args.qdrant_only:
            # 仅恢复 Qdrant
            restore_qdrant_snapshot(args.input, force=args.force, dry_run=args.dry_run)
        elif args.files_only:
            # 仅恢复本地文件
            restore_local_files(args.input, dry_run=args.dry_run)
        else:
            # 完整恢复
            restore_full_backup(args.input, force=args.force, dry_run=args.dry_run)
        
        if args.dry_run:
            logger.info("\n[DRY-RUN] 预览完成，未实际执行任何操作")
        else:
            logger.info("\n恢复完成！")
        
    except Exception as e:
        logger.error(f"恢复失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
