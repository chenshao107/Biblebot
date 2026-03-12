import os
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from pathlib import Path
from loguru import logger
from app.core.config import settings

class DoclingConverter:
    def __init__(self):
        # 设置 CPU 线程数
        os.environ["OMP_NUM_THREADS"] = str(settings.DOCLING_OCR_THREADS)

        pipeline_options = PdfPipelineOptions(do_ocr=settings.DOCLING_DO_OCR)
        self.converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
            }
        )
        logger.info(
            f"DoclingConverter initialized: do_ocr={settings.DOCLING_DO_OCR}, "
            f"ocr_threads={settings.DOCLING_OCR_THREADS}"
        )

    # Docling 不支持的格式，直接读取为纯文本
    PLAIN_TEXT_SUFFIXES = {".txt", ".text", ".log", ".ini", ".cfg", ".conf", ".yaml", ".yml", ".toml", ".sh", ".bat"}

    def _read_as_plain_text(self, input_path: Path) -> str:
        """
        将文件作为纯文本读取，并包装为 markdown 格式。
        """
        logger.info(f"Reading as plain text: {input_path.name}")
        try:
            with open(input_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            # 包裹成 markdown 代码块，保留原始格式
            return f"# {Path(input_path).stem}\n\n```\n{content}\n```\n"
        except Exception as e:
            logger.error(f"Error reading plain text file {input_path}: {e}")
            raise e

    def convert(self, input_path: Path) -> str:
        """
        Converts a document to Markdown string.
        优先尝试使用 Docling 转换，如果失败则降级为纯文本读取。
        """
        suffix = Path(input_path).suffix.lower()
        
        # 1. 对于已知的纯文本格式，直接读取（优化性能）
        if suffix in self.PLAIN_TEXT_SUFFIXES:
            return self._read_as_plain_text(input_path)
        
        # 2. 尝试用 Docling 转换
        try:
            logger.info(f"Converting {input_path.name} to Markdown...")
            result = self.converter.convert(str(input_path))
            md_content = result.document.export_to_markdown()
            return md_content
        except Exception as e:
            # Docling 转换失败，尝试作为纯文本读取
            logger.warning(f"Docling failed to convert {input_path.name}: {e}. Falling back to plain text...")
            return self._read_as_plain_text(input_path)

    def save_canonical(self, content: str, original_name: str):
        """
        Saves the converted content to the canonical_md directory.
        Preserves the directory structure from data/raw.
        
        Args:
            content: Markdown content
            original_name: Original file path (can be relative path like RK3506/uboot/README.md)
        """
        output_dir = Path(settings.DATA_CANONICAL_DIR)
        
        # 处理相对路径，保留目录结构
        original_path = Path(original_name)
        output_path = output_dir / original_path.parent / f"{original_path.stem}.md"
        
        # 创建必要的子目录
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info(f"Saved canonical markdown to {output_path}")
        return output_path
