from typing import List, Dict, Any
from markdown_it import MarkdownIt
from loguru import logger
import re

class MarkdownChunker:
    def __init__(self, chunk_size: int = 600, chunk_overlap: int = 100):
        self.md = MarkdownIt()
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk(self, md_content: str, doc_id: str) -> List[Dict[str, Any]]:
        """
        Chunks markdown content based on headers and size.
        """
        logger.info(f"Chunking document {doc_id}...")
        
        # Normalize markdown first
        content = self._normalize_md(md_content)
        
        # Split by headers (simplistic version for now)
        sections = self._split_by_headers(content)
        
        chunks = []
        for section in sections:
            section_content = section['content']
            section_title = section['title']
            
            # If section is too large, sub-chunk it
            if len(section_content) > self.chunk_size:
                sub_chunks = self._sliding_window(section_content, self.chunk_size, self.chunk_overlap)
                for i, sub in enumerate(sub_chunks):
                    chunks.append({
                        "content": f"{section_title}\n{sub}",
                        "metadata": {
                            "doc_id": doc_id,
                            "section": section_title,
                            "chunk_index": len(chunks),
                            "is_subchunk": True
                        }
                    })
            else:
                chunks.append({
                    "content": section_content,
                    "metadata": {
                        "doc_id": doc_id,
                        "section": section_title,
                        "chunk_index": len(chunks),
                        "is_subchunk": False
                    }
                })
        
        return chunks

    def _normalize_md(self, md: str) -> str:
        # Flatten deep headers to h4
        md = re.sub(r"^#{5,6}\s+", "#### ", md, flags=re.MULTILINE)
        # Remove excessive empty lines
        md = re.sub(r"\n{3,}", "\n\n", md)
        return md

    def _split_by_headers(self, md: str) -> List[Dict[str, str]]:
        # Regex to match headers
        header_pattern = re.compile(r"^(#{1,4})\s+(.+)$", re.MULTILINE)
        
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
        chunks = []
        start = 0
        while start < len(text):
            end = start + size
            chunks.append(text[start:end])
            start += size - overlap
            if end >= len(text):
                break
        return chunks
