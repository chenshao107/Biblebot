from docling.document_converter import DocumentConverter
from pathlib import Path
from loguru import logger
from app.core.config import settings

class DoclingConverter:
    def __init__(self):
        self.converter = DocumentConverter()

    def convert(self, input_path: Path) -> str:
        """
        Converts a document to Markdown string.
        """
        try:
            logger.info(f"Converting {input_path.name} to Markdown...")
            result = self.converter.convert(str(input_path))
            md_content = result.document.export_to_markdown()
            return md_content
        except Exception as e:
            logger.error(f"Error converting {input_path}: {e}")
            raise e

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
