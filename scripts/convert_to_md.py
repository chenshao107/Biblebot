"""
convert_to_md.py — 仅将 data/raw/ 中的文件转换为 Markdown，保存至 data/canonical_md/

用途：在有 GPU / 高性能 CPU 的机器上单独跑 Docling 转换，
     生成好的 data/canonical_md/ 目录后搬回本机，
     再用 ingest_folder.py 跳过转换直接做 chunk + embed + upsert。
"""

import sys
import gc
from pathlib import Path
from loguru import logger

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from app.services.ingestion.converter import DoclingConverter
from app.core.config import settings

# 尝试导入 tqdm
try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False
    class tqdm:
        def __init__(self, iterable=None, total=None, desc=None, **kwargs):
            self.iterable = iterable
            self.n = 0
            if desc:
                logger.info(f"{desc} (tqdm not installed)")
        def __iter__(self):
            for item in self.iterable:
                yield item
                self.n += 1
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def update(self, n=1): self.n += n
        def set_postfix_str(self, s): pass
        def close(self): pass


def get_relative_path(file_path: Path, base_dir: Path) -> str:
    try:
        return str(file_path.relative_to(base_dir))
    except ValueError:
        return file_path.name


def is_already_converted(raw_rel_path: str) -> bool:
    """检查 canonical_md 中对应的 .md 文件是否已存在"""
    canonical_rel_path = str(Path(raw_rel_path).with_suffix('.md'))
    output_path = Path(settings.DATA_CANONICAL_DIR) / canonical_rel_path
    return output_path.exists()


def main():
    converter = DoclingConverter()

    raw_dir = Path(settings.DATA_RAW_DIR)
    if not raw_dir.exists():
        logger.error(f"Raw directory not found: {raw_dir}")
        return

    doc_files = [f for f in raw_dir.rglob("*") if f.is_file()]
    if not doc_files:
        logger.warning(f"No files found in {raw_dir}")
        return

    logger.info(f"Found {len(doc_files)} files in {raw_dir}")

    success_count = 0
    skipped_count = 0
    failed_count = 0

    with tqdm(total=len(doc_files), desc="📄 Converting", unit="file", ncols=100) as pbar:
        for file_path in doc_files:
            raw_rel_path = get_relative_path(file_path, raw_dir)
            suffix = Path(raw_rel_path).suffix.lower()

            # 跳过二进制文件
            if suffix in DoclingConverter.BINARY_SUFFIXES:
                skipped_count += 1
                pbar.update(1)
                pbar.set_postfix_str(f"✓{success_count} ◦{skipped_count} ✗{failed_count}")
                continue

            # 断点续传：已转换则跳过
            if is_already_converted(raw_rel_path):
                skipped_count += 1
                pbar.update(1)
                pbar.set_postfix_str(f"✓{success_count} ◦{skipped_count}(skip) ✗{failed_count}")
                continue

            try:
                md_content = converter.convert(file_path)
                if md_content is None:
                    # 格式不支持（Docling 拒绝）
                    skipped_count += 1
                else:
                    converter.save_canonical(md_content, raw_rel_path)
                    success_count += 1
                    del md_content
                    gc.collect()
            except Exception as e:
                logger.error(f"Failed to convert {raw_rel_path}: {e}")
                failed_count += 1

            pbar.update(1)
            pbar.set_postfix_str(f"✓{success_count} ◦{skipped_count} ✗{failed_count}")

    logger.info("=" * 60)
    logger.info("Conversion complete!")
    logger.info(f"  Total files : {len(doc_files)}")
    logger.info(f"  Converted   : {success_count}")
    logger.info(f"  Skipped     : {skipped_count}  (already done / binary / unsupported)")
    logger.info(f"  Failed      : {failed_count}")
    logger.info(f"  Output dir  : {settings.DATA_CANONICAL_DIR}")
    logger.info("=" * 60)
    logger.info("Next step: copy data/canonical_md/ to the target machine,")
    logger.info("then run:  python scripts/ingest_folder.py")


if __name__ == "__main__":
    main()
