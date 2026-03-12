"""
章节索引构建器 - 为 Markdown 文件构建章节索引
"""
import re
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from loguru import logger
from app.core.config import settings


class SectionIndexer:
    """Markdown 章节索引构建器"""
    
    def __init__(self):
        self.index = {}
    
    def parse_markdown(self, content: str, file_path: str) -> List[Dict[str, Any]]:
        """
        解析 Markdown 内容，提取章节结构
        
        Returns:
            List of {"title": str, "level": int, "start_line": int, "end_line": int}
        """
        lines = content.split('\n')
        sections = []
        
        # 正则匹配标题 (# ## ###)
        header_pattern = re.compile(r'^(#{1,6})\s+(.+)$')
        
        current_section = None
        
        for i, line in enumerate(lines):
            match = header_pattern.match(line)
            if match:
                # 保存上一个章节
                if current_section:
                    current_section['end_line'] = i - 1
                    sections.append(current_section)
                
                # 创建新章节
                level = len(match.group(1))
                title = match.group(0).strip()  # 包含 # 的完整标题
                current_section = {
                    'title': title,
                    'level': level,
                    'start_line': i,
                    'end_line': len(lines) - 1  # 临时，会被下一个章节覆盖
                }
        
        # 保存最后一个章节
        if current_section:
            current_section['end_line'] = len(lines) - 1
            sections.append(current_section)
        
        return sections
    
    def index_file(self, md_content: str, file_path: str) -> Dict[str, Any]:
        """
        为单个 Markdown 文件构建索引
        
        Args:
            md_content: Markdown 内容
            file_path: 文件路径（相对于 canonical_md）
        
        Returns:
            文件索引信息
        """
        sections = self.parse_markdown(md_content, file_path)
        lines = md_content.split('\n')
        
        file_index = {
            'file_path': file_path,
            'total_lines': len(lines),
            'section_count': len(sections),
            'sections': sections
        }
        
        self.index[file_path] = file_index
        logger.info(f"Indexed {file_path}: {len(sections)} sections, {len(lines)} lines")
        
        return file_index
    
    def save_index(self, output_dir: Optional[str] = None):
        """
        保存索引到 JSON 文件
        
        Args:
            output_dir: 输出目录，默认为 DATA_CANONICAL_DIR
        """
        output_dir = Path(output_dir or settings.DATA_CANONICAL_DIR)
        output_path = output_dir / 'section_index.json'
        
        index_data = {
            'total_files': len(self.index),
            'files': self.index
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(index_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Section index saved to {output_path}")
        return output_path
    
    def load_index(self, index_path: Optional[str] = None) -> Dict[str, Any]:
        """
        从 JSON 文件加载索引
        """
        if index_path:
            path = Path(index_path)
        else:
            path = Path(settings.DATA_CANONICAL_DIR) / 'section_index.json'
        
        if not path.exists():
            logger.warning(f"Section index not found: {path}")
            return {}
        
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        self.index = data.get('files', {})
        logger.info(f"Loaded section index: {len(self.index)} files")
        return self.index
    
    def list_sections(self, file_path: str) -> List[Dict[str, Any]]:
        """
        列出文件的所有章节
        
        Args:
            file_path: 文件路径（相对于 canonical_md）
        
        Returns:
            章节列表
        """
        if file_path not in self.index:
            # 尝试加载索引
            self.load_index()
        
        if file_path not in self.index:
            logger.warning(f"File not in index: {file_path}")
            return []
        
        return self.index[file_path]['sections']
    
    def get_section_content(self, file_path: str, section_title: str, 
                           md_content: str) -> Optional[Dict[str, Any]]:
        """
        获取指定章节的内容
        
        Args:
            file_path: 文件路径
            section_title: 章节标题（可以是部分匹配）
            md_content: 完整的 Markdown 内容
        
        Returns:
            章节内容和元数据
        """
        sections = self.list_sections(file_path)
        if not sections:
            return None
        
        # 精确匹配或部分匹配
        target_section = None
        for section in sections:
            if section_title in section['title'] or section['title'] in section_title:
                target_section = section
                break
        
        if not target_section:
            logger.warning(f"Section not found: {section_title} in {file_path}")
            return None
        
        # 提取内容
        lines = md_content.split('\n')
        start = target_section['start_line']
        end = target_section['end_line'] + 1
        content = '\n'.join(lines[start:end])
        
        return {
            'title': target_section['title'],
            'level': target_section['level'],
            'start_line': start,
            'end_line': end - 1,
            'content': content
        }


# 全局索引实例
_indexer_instance = None


def get_indexer() -> SectionIndexer:
    """获取全局索引实例"""
    global _indexer_instance
    if _indexer_instance is None:
        _indexer_instance = SectionIndexer()
        _indexer_instance.load_index()
    return _indexer_instance
