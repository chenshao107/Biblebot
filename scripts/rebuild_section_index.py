#!/usr/bin/env python3
"""
重建章节索引 - 只重建 section_index.json，不重新生成嵌入向量
用于修复章节标题格式问题后快速重建索引
"""
import os
import sys
from pathlib import Path
from loguru import logger

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from app.services.ingestion.section_indexer import SectionIndexer
from app.core.config import settings


def main():
    """重建章节索引"""
    logger.info("=" * 60)
    logger.info("重建章节索引")
    logger.info("=" * 60)
    
    indexer = SectionIndexer()
    
    # 查找所有 canonical_md 中的 .md 文件
    canonical_dir = Path(settings.DATA_CANONICAL_DIR)
    if not canonical_dir.exists():
        logger.error(f"Canonical directory not found: {canonical_dir}")
        return
    
    md_files = list(canonical_dir.rglob("*.md"))
    
    if not md_files:
        logger.warning(f"No markdown files found in {canonical_dir}")
        return
    
    logger.info(f"Found {len(md_files)} markdown files to index")
    
    # 处理每个文件
    success_count = 0
    failed_count = 0
    
    for md_path in md_files:
        try:
            # 计算相对于 canonical_dir 的路径
            rel_path = md_path.relative_to(canonical_dir)
            
            # 读取文件内容
            with open(md_path, 'r', encoding='utf-8') as f:
                md_content = f.read()
            
            # 构建索引
            indexer.index_file(md_content, str(rel_path))
            success_count += 1
            
        except Exception as e:
            logger.error(f"Failed to index {md_path}: {e}")
            failed_count += 1
    
    # 保存索引
    output_path = indexer.save_index()
    
    # 统计
    logger.info("=" * 60)
    logger.info("章节索引重建完成!")
    logger.info(f"  成功: {success_count}")
    logger.info(f"  失败: {failed_count}")
    logger.info(f"  索引文件: {output_path}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
