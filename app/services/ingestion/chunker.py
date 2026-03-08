from typing import List, Dict, Any
from markdown_it import MarkdownIt
from loguru import logger
from pathlib import Path
import re
import json
from app.core.config import settings

class MarkdownChunker:
    def __init__(self, chunk_size: int = 1500, chunk_overlap: int = 100):
        self.md = MarkdownIt()
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk(self, md_content: str, doc_id: str, path_info: dict = None) -> List[Dict[str, Any]]:
        """
        Chunks markdown content based on headers and size.
        
        Args:
            md_content: Markdown 内容
            doc_id: 文档 ID（使用相对路径，如 RK3506/uboot/README.md）
            path_info: 路径信息字典，包含 category, subcategory, full_path
        """
        logger.info(f"Chunking document {doc_id}...")
        
        # 使用路径信息或从 doc_id 解析
        if path_info is None:
            path_info = self._extract_path_info(doc_id)
        
        # Normalize markdown first
        content = self._normalize_md(md_content)
        
        # Split by headers (simplistic version for now)
        sections = self._split_by_headers(content)
        
        chunks = []
        for section in sections:
            section_content = section['content']
            section_title = section['title']
            
            # 构建元数据
            metadata = {
                "doc_id": doc_id,
                "category": path_info.get("category", "unknown"),
                "subcategory": path_info.get("subcategory", ""),
                "full_path": path_info.get("full_path", doc_id),
                "section": section_title,
                "chunk_index": len(chunks),
            }
            
            # If section is too large, sub-chunk it
            if len(section_content) > self.chunk_size:
                sub_chunks = self._sliding_window(section_content, self.chunk_size, self.chunk_overlap)
                for i, sub in enumerate(sub_chunks):
                    # 只在第一个子分片添加标题，避免重复
                    content = f"{section_title}\n{sub}" if i == 0 else sub
                    chunks.append({
                        "content": content,
                        "metadata": {
                            **metadata,
                            "chunk_index": len(chunks),
                            "is_subchunk": True,
                            "subchunk_index": i
                        }
                    })
            else:
                chunks.append({
                    "content": section_content,
                    "metadata": {
                        **metadata,
                        "chunk_index": len(chunks),
                        "is_subchunk": False
                    }
                })
        
        logger.info(f"Created {len(chunks)} chunks for {doc_id} (category: {path_info.get('category', 'unknown')})")
        return chunks
    
    def _extract_path_info(self, doc_id: str) -> dict:
        """从 doc_id (相对路径) 提取路径信息"""
        parts = doc_id.split('/')
        
        if len(parts) == 1:
            return {
                "category": "root",
                "subcategory": "",
                "full_path": doc_id
            }
        else:
            return {
                "category": parts[0],
                "subcategory": '/'.join(parts[1:-1]) if len(parts) > 2 else "",
                "full_path": doc_id
            }

    def save_chunks(self, chunks: List[Dict[str, Any]], doc_id: str):
        """
        Saves the chunks to JSON file for tuning reference.
        """
        if not settings.SAVE_INTERMEDIATE_FILES:
            return
            
        output_dir = Path(settings.DATA_CHUNKS_DIR)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        output_path = output_dir / f"{Path(doc_id).stem}_chunks.json"
        
        # Save with pretty formatting for readability
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump({
                "doc_id": doc_id,
                "total_chunks": len(chunks),
                "chunk_size": self.chunk_size,
                "chunk_overlap": self.chunk_overlap,
                "chunks": chunks
            }, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Saved {len(chunks)} chunks to {output_path}")
        return output_path

    def _normalize_md(self, md: str) -> str:
        # Flatten deep headers to h4
        md = re.sub(r"^#{5,6}\s+", "#### ", md, flags=re.MULTILINE)
        # Remove excessive empty lines
        md = re.sub(r"\n{3,}", "\n\n", md)
        
        # 合并Docling产生的碎片化段落
        md = self._merge_fragmented_paragraphs(md)
        
        # 过滤掉纯目录部分（密集的链接列表）
        md = self._filter_toc_section(md)
        
        return md
    
    def _merge_fragmented_paragraphs(self, md: str) -> str:
        """
        合并Docling转换产生的碎片化段落。
        Docling会把一段连续的文本按行分割，中间插入空行，导致：
        "The first step...\n\nis to create...\n\na configuration."
        需要合并成：
        "The first step is to create a configuration."
        """
        lines = md.split('\n')
        result_lines = []
        i = 0
        
        while i < len(lines):
            line = lines[i]
            
            # 如果是空行，跳过
            if not line.strip():
                i += 1
                continue
            
            # 如果是代码块标记、标题、列表项，直接保留
            if line.strip().startswith('```') or line.strip().startswith('#') or \
               line.strip().startswith('- ') or line.strip().startswith('* ') or \
               re.match(r'^\d+\.', line.strip()):
                result_lines.append(line)
                i += 1
                continue
            
            # 否则，尝试合并连续的短行（句子片段）
            merged = line
            i += 1
            
            # 向后看：如果下一行是空行，再下一行是短文本行（不是特殊格式），则合并
            while i < len(lines):
                # 跳过空行
                if i < len(lines) and not lines[i].strip():
                    i += 1
                    continue
                
                # 检查下一行内容
                if i < len(lines):
                    next_line = lines[i]
                    # 如果下一行是特殊格式，停止合并
                    if next_line.strip().startswith('```') or \
                       next_line.strip().startswith('#') or \
                       next_line.strip().startswith('- ') or \
                       next_line.strip().startswith('* ') or \
                       re.match(r'^\d+\.', next_line.strip()) or \
                       next_line.strip().startswith('[') or \
                       next_line.strip().startswith('!['):
                        break
                    
                    # 合并条件：
                    # 1. 当前行没有结束标点（说明句子未完）
                    # 2. 下一行不是以大写字母开头（排除新句子）
                    # 3. 合并后总长度不超过300字符
                    if not merged.endswith('.') and not merged.endswith('?') and not merged.endswith('!') and \
                       not merged.endswith(')') and \
                       not next_line[0].isupper() and \
                       len(merged) + len(next_line) < 300:
                        merged = merged + ' ' + next_line
                        i += 1
                    else:
                        break
                else:
                    break
            
            result_lines.append(merged)
        
        return '\n\n'.join(result_lines)
    
    def _filter_toc_section(self, md: str) -> str:
        """
        检测并过滤掉纯目录部分（Table of Contents）
        判断标准：连续多行都是链接，且链接密度超过80%
        """
        lines = md.split('\n')
        filtered_lines = []
        in_toc = False
        consecutive_link_lines = 0
        
        for i, line in enumerate(lines):
            # 检测是否是目录标识行
            if 'table of contents' in line.lower() or '**table of contents**' in line.lower():
                in_toc = True
                continue
            
            # 计算当前行的链接密度
            if line.strip():
                link_count = line.count('](http')
                line_length = len(line)
                
                if link_count > 3 and line_length > 100:
                    consecutive_link_lines += 1
                else:
                    consecutive_link_lines = 0
                    
                # 如果连续10行都是密集链接，判定为目录区域
                if consecutive_link_lines >= 10:
                    in_toc = True
                elif consecutive_link_lines == 0 and in_toc:
                    # 遇到非链接行，目录区域结束
                    in_toc = False
            
            # 非目录部分保留
            if not in_toc:
                filtered_lines.append(line)
        
        return '\n'.join(filtered_lines)

    def _split_by_headers(self, md: str) -> List[Dict[str, str]]:
        # Regex to match headers (h1-h3, skip h4 to avoid over-splitting)
        header_pattern = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)
        
        matches = list(header_pattern.finditer(md))
        if not matches:
            return [{"title": "Root", "content": md}]
            
        sections = []
        last_pos = 0
        current_title = "Root"
        
        for match in matches:
            # Content before this header belongs to the previous header
            content = md[last_pos:match.start()].strip()
            if content:
                sections.append({"title": current_title, "content": content})
            
            current_title = match.group(0).strip()
            last_pos = match.start()
            
        # Add the last section
        sections.append({"title": current_title, "content": md[last_pos:].strip()})
        
        return sections

    def _sliding_window(self, text: str, size: int, overlap: int) -> List[str]:
        if not text:
            return []
        
        # 检测是否包含代码块
        has_code_blocks = '```' in text
        
        if not has_code_blocks:
            # 无代码块，使用原逻辑
            return self._simple_sliding_window(text, size, overlap)
        
        # 有代码块，需要智能切分
        return self._smart_split_with_code_blocks(text, size, overlap)
    
    def _simple_sliding_window(self, text: str, size: int, overlap: int) -> List[str]:
        """简单的滑动窗口切分，添加最小长度过滤"""
        chunks = []
        start = 0
        min_chunk_size = 50  # 最小分片长度，过滤太短的碎片
        
        while start < len(text):
            end = start + size
            chunk = text[start:end]
            # 最后一片如果太短，合并到前一片
            if end >= len(text) and len(chunk) < min_chunk_size and chunks:
                chunks[-1] = chunks[-1] + chunk
            else:
                chunks.append(chunk)
            start += size - overlap
            if end >= len(text):
                break
        return chunks
    
    def _smart_split_with_code_blocks(self, text: str, size: int, overlap: int) -> List[str]:
        """
        智能切分：保证代码块不被截断
        策略：如果代码块大小超过chunk_size，则单独保留整个代码块
        """
        chunks = []
        code_block_pattern = re.compile(r'```[\s\S]*?```', re.MULTILINE)
        
        # 找到所有代码块的位置
        code_blocks = []
        for match in code_block_pattern.finditer(text):
            code_blocks.append((match.start(), match.end()))
        
        if not code_blocks:
            return self._simple_sliding_window(text, size, overlap)
        
        # 按照代码块边界切分
        current_pos = 0
        
        for code_start, code_end in code_blocks:
            # 处理代码块之前的文本
            if code_start > current_pos:
                before_text = text[current_pos:code_start]
                if len(before_text) > size:
                    chunks.extend(self._simple_sliding_window(before_text, size, overlap))
                elif before_text.strip():
                    chunks.append(before_text)
            
            # 处理代码块：即使超过size也保留完整
            code_block = text[code_start:code_end]
            chunks.append(code_block)
            
            current_pos = code_end
        
        # 处理最后一个代码块之后的文本
        if current_pos < len(text):
            after_text = text[current_pos:]
            if len(after_text) > size:
                chunks.extend(self._simple_sliding_window(after_text, size, overlap))
            elif after_text.strip():
                chunks.append(after_text)
        
        return chunks
