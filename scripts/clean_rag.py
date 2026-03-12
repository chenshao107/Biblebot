#!/usr/bin/env python3
"""
RAG 数据清理脚本

清理内容：
  1. Qdrant 向量数据库中的 collection（整个 collection 或指定文档）
  2. data/canonical_md  — 转换后的 Markdown 中间文件
  3. data/chunks        — 分块中间文件
  4. data/embeddings    — 嵌入向量元数据

用法：
  # 清理全部数据（collection + 所有中间文件）
  python3 scripts/clean_rag.py --all

  # 仅清理 Qdrant collection（保留中间文件）
  python3 scripts/clean_rag.py --qdrant

  # 仅清理中间文件（保留 Qdrant 数据）
  python3 scripts/clean_rag.py --files

  # 按文档路径删除（支持模糊匹配，同时清理 Qdrant 和中间文件）
  python3 scripts/clean_rag.py --doc "RK3506/uboot/README.md"
  python3 scripts/clean_rag.py --doc "RK3506"   # 删除该 category 下所有文档

  # 列出 Qdrant 中已有的文档
  python3 scripts/clean_rag.py --list

  # 预览将要删除的内容（不实际删除）
  python3 scripts/clean_rag.py --all --dry-run
"""

import os
import sys
import shutil
import argparse
from pathlib import Path
from loguru import logger

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from app.core.config import settings
from app.services.storage.qdrant_client import QdrantStorage
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels


# ─────────────────────────── 辅助函数 ───────────────────────────

def get_qdrant_client() -> QdrantClient:
    return QdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)


def collection_exists(client: QdrantClient) -> bool:
    collections = client.get_collections().collections
    return any(c.name == settings.QDRANT_COLLECTION_NAME for c in collections)


def get_intermediate_dirs() -> list[Path]:
    """返回所有中间文件目录"""
    return [
        Path(settings.DATA_CANONICAL_DIR),
        Path(settings.DATA_CHUNKS_DIR),
        Path(settings.DATA_EMBEDDINGS_DIR),
    ]


# ─────────────────────────── 清理函数 ───────────────────────────

def clean_qdrant_collection(dry_run: bool = False):
    """删除整个 Qdrant collection"""
    client = get_qdrant_client()

    if not collection_exists(client):
        logger.info(f"Collection '{settings.QDRANT_COLLECTION_NAME}' 不存在，跳过。")
        return

    if dry_run:
        logger.info(f"[DRY-RUN] 将删除 Qdrant collection: {settings.QDRANT_COLLECTION_NAME}")
        return

    client.delete_collection(settings.QDRANT_COLLECTION_NAME)
    logger.success(f"已删除 Qdrant collection: {settings.QDRANT_COLLECTION_NAME}")


def clean_intermediate_files(dry_run: bool = False):
    """删除所有中间文件目录"""
    dirs = get_intermediate_dirs()
    for d in dirs:
        if not d.exists():
            logger.info(f"目录不存在，跳过: {d}")
            continue
        if dry_run:
            file_count = sum(1 for _ in d.rglob("*") if _.is_file())
            logger.info(f"[DRY-RUN] 将删除目录: {d}  ({file_count} 个文件)")
        else:
            shutil.rmtree(d)
            logger.success(f"已删除目录: {d}")


def list_documents():
    """列出 Qdrant 中所有已索引文档的路径"""
    client = get_qdrant_client()

    if not collection_exists(client):
        logger.warning(f"Collection '{settings.QDRANT_COLLECTION_NAME}' 不存在。")
        return

    # 滚动读取所有点，收集唯一的 source_file
    doc_set: set[str] = set()
    offset = None
    batch_size = 500

    while True:
        result, next_offset = client.scroll(
            collection_name=settings.QDRANT_COLLECTION_NAME,
            limit=batch_size,
            offset=offset,
            with_payload=["source_file"],
            with_vectors=False,
        )
        for point in result:
            src = point.payload.get("source_file", "")
            if src:
                doc_set.add(src)
        if next_offset is None:
            break
        offset = next_offset

    if not doc_set:
        logger.info("Collection 中没有文档。")
        return

    docs = sorted(doc_set)
    logger.info(f"共找到 {len(docs)} 个文档：")
    for doc in docs:
        print(f"  {doc}")


def clean_by_doc(doc_prefix: str, dry_run: bool = False):
    """
    按文档路径前缀删除：
    - 从 Qdrant 删除匹配的 points
    - 删除对应的中间文件（canonical_md / chunks / embeddings）
    """
    client = get_qdrant_client()

    # ── 1. 删除 Qdrant points ──
    if not collection_exists(client):
        logger.warning(f"Collection '{settings.QDRANT_COLLECTION_NAME}' 不存在，跳过 Qdrant 清理。")
    else:
        # 先统计匹配的点数
        count_result = client.count(
            collection_name=settings.QDRANT_COLLECTION_NAME,
            count_filter=qmodels.Filter(
                must=[
                    qmodels.FieldCondition(
                        key="source_file",
                        match=qmodels.MatchText(text=doc_prefix),
                    )
                ]
            ),
            exact=True,
        )
        matched = count_result.count

        if matched == 0:
            logger.info(f"Qdrant 中没有匹配 '{doc_prefix}' 的文档。")
        else:
            if dry_run:
                logger.info(f"[DRY-RUN] 将从 Qdrant 删除 {matched} 个 points（匹配前缀: '{doc_prefix}'）")
            else:
                client.delete(
                    collection_name=settings.QDRANT_COLLECTION_NAME,
                    points_selector=qmodels.FilterSelector(
                        filter=qmodels.Filter(
                            must=[
                                qmodels.FieldCondition(
                                    key="source_file",
                                    match=qmodels.MatchText(text=doc_prefix),
                                )
                            ]
                        )
                    ),
                )
                logger.success(f"已从 Qdrant 删除 {matched} 个 points（匹配: '{doc_prefix}'）")

    # ── 2. 删除中间文件 ──
    norm_prefix = doc_prefix.strip("/")
    dirs = get_intermediate_dirs()
    deleted_any = False

    for base_dir in dirs:
        if not base_dir.exists():
            continue
        # 精确路径匹配：直接删除对应条目
        target = base_dir / norm_prefix
        # 也处理 .md / .json 后缀的情况
        candidates = [target]
        # 对于 canonical_md，文件名带 .md；chunks/embeddings 带 .json
        for suffix in [".md", ".json"]:
            candidates.append(Path(str(target) + suffix))
            # 如果 norm_prefix 本身没后缀，也尝试把最后一节加后缀
            stem = target.stem
            candidates.append(target.with_suffix(suffix))

        for candidate in candidates:
            if candidate.exists():
                if dry_run:
                    logger.info(f"[DRY-RUN] 将删除: {candidate}")
                else:
                    if candidate.is_dir():
                        shutil.rmtree(candidate)
                    else:
                        candidate.unlink()
                    logger.success(f"已删除: {candidate}")
                deleted_any = True

        # 还可能是同名目录（如 category 目录）
        if target.is_dir() and target not in candidates:
            if dry_run:
                file_count = sum(1 for _ in target.rglob("*") if _.is_file())
                logger.info(f"[DRY-RUN] 将删除目录: {target}  ({file_count} 个文件)")
            else:
                shutil.rmtree(target)
                logger.success(f"已删除目录: {target}")
            deleted_any = True

    if not deleted_any:
        logger.info(f"没有找到匹配 '{doc_prefix}' 的中间文件。")


# ─────────────────────────── 主程序 ───────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="RAG 数据清理工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all",    action="store_true", help="清理全部（Qdrant + 所有中间文件）")
    group.add_argument("--qdrant", action="store_true", help="仅清理 Qdrant collection")
    group.add_argument("--files",  action="store_true", help="仅清理本地中间文件")
    group.add_argument("--doc",    metavar="PATH_PREFIX",
                       help="按文档路径前缀删除（如 'RK3506' 或 'RK3506/uboot/README.md'）")
    group.add_argument("--list",   action="store_true", help="列出 Qdrant 中已有的文档")

    parser.add_argument(
        "--dry-run", action="store_true",
        help="预览将要删除的内容，不实际执行删除",
    )
    return parser


def confirm(prompt: str) -> bool:
    """交互确认，非 TTY 环境直接返回 True（方便脚本调用）"""
    if not sys.stdin.isatty():
        return True
    answer = input(f"{prompt} [y/N] ").strip().lower()
    return answer in ("y", "yes")


def main():
    parser = build_parser()
    args = parser.parse_args()

    dry_run = args.dry_run
    if dry_run:
        logger.info("── DRY-RUN 模式，不会实际删除任何数据 ──")

    if args.list:
        list_documents()
        return

    if args.all:
        logger.info("将清理：Qdrant collection + 所有中间文件")
        if not dry_run and not confirm("确认要删除全部 RAG 数据？"):
            logger.info("已取消。")
            return
        clean_qdrant_collection(dry_run)
        clean_intermediate_files(dry_run)

    elif args.qdrant:
        logger.info(f"将清理：Qdrant collection '{settings.QDRANT_COLLECTION_NAME}'")
        if not dry_run and not confirm("确认要删除 Qdrant collection？"):
            logger.info("已取消。")
            return
        clean_qdrant_collection(dry_run)

    elif args.files:
        logger.info("将清理：data/canonical_md、data/chunks、data/embeddings")
        if not dry_run and not confirm("确认要删除所有中间文件？"):
            logger.info("已取消。")
            return
        clean_intermediate_files(dry_run)

    elif args.doc:
        logger.info(f"将清理文档：'{args.doc}'")
        if not dry_run and not confirm(f"确认要删除文档 '{args.doc}' 的所有数据？"):
            logger.info("已取消。")
            return
        clean_by_doc(args.doc, dry_run)

    if not dry_run:
        logger.success("清理完成。")


if __name__ == "__main__":
    main()

