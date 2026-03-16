"""
章节索引工具 - 高效浏览和读取文档章节
"""
from typing import Any, Dict
from pathlib import Path
from loguru import logger
from app.agent.tools.base import BaseTool, ToolResult
from app.services.ingestion.section_indexer import get_indexer
from app.core.config import settings


class ListSectionsTool(BaseTool):
    """列出文档的所有章节"""
    
    @property
    def name(self) -> str:
        return "list_sections"
    
    @property
    def description(self) -> str:
        return """列出指定 Markdown 文档的所有章节结构。

用途：
- 快速了解文档结构
- 定位感兴趣的章节
- 为 read_section 提供章节标题

示例：
- list_sections("RK3506/uboot/编译指南.md")
- list_sections("公司规章制度/人事部/考勤制度.md")

返回：章节列表（包含标题、层级、行号范围）"""
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "文档路径（相对于 data/canonical_md），如 'RK3506/uboot/编译指南.md'"
                }
            },
            "required": ["file_path"]
        }
    
    def execute(self, file_path: str) -> ToolResult:
        """执行章节列表查询"""
        try:
            indexer = get_indexer()
            sections = indexer.list_sections(file_path)
            
            if not sections:
                return ToolResult(
                    success=True,
                    output=f"文档 '{file_path}' 没有章节索引，或文档不存在。"
                )
            
            # 格式化输出
            output_parts = [f"📄 {file_path}\n", "=" * 50]
            
            for i, section in enumerate(sections, 1):
                level = section['level']
                title = section['title']
                start = section['start_line']
                end = section['end_line']
                
                # 根据层级缩进
                indent = "  " * (level - 1)
                output_parts.append(
                    f"{i}. {indent}{title} (lines {start}-{end})"
                )
            
            output_parts.append("\n💡 使用 read_section 工具读取特定章节内容")
            
            return ToolResult(
                success=True,
                output="\n".join(output_parts)
            )
            
        except Exception as e:
            logger.error(f"List sections failed: {e}")
            return ToolResult(
                success=False,
                output="",
                error=f"查询章节失败: {str(e)}"
            )


class ReadSectionTool(BaseTool):
    """读取指定章节的内容"""
    
    @property
    def name(self) -> str:
        return "read_section"
    
    @property
    def description(self) -> str:
        return """读取 Markdown 文档中指定章节的内容。

用途：
- 精准读取感兴趣的章节
- 避免加载整个大文档
- 提高阅读效率

示例：
- read_section("RK3506/uboot/编译指南.md", "## 编译步骤")
- read_section("公司规章制度/人事部/考勤制度.md", "## 请假流程")

注意：
- section_title 可以是完整标题或部分匹配
- 工具可能有bug，如果遇到问题，请使用bash命令查看md文件
- 如果不指定 section_title，则返回整个文档"""
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "文档路径（相对于 data/canonical_md），如 'RK3506/uboot/编译指南.md'"
                },
                "section_title": {
                    "type": "string",
                    "description": "章节标题（如 '## 编译步骤'），可选。不指定则读取整个文档",
                    "default": None
                }
            },
            "required": ["file_path"]
        }
    
    def execute(self, file_path: str, section_title: str = None) -> ToolResult:
        """执行章节读取"""
        try:
            # 构建完整路径
            full_path = Path(settings.DATA_CANONICAL_DIR) / file_path
            
            if not full_path.exists():
                return ToolResult(
                    success=False,
                    output="",
                    error=f"文件不存在: {file_path}"
                )
            
            # 读取文件内容
            with open(full_path, 'r', encoding='utf-8') as f:
                md_content = f.read()
            
            # 如果没有指定章节，返回整个文档
            if not section_title:
                lines = md_content.split('\n')
                return ToolResult(
                    success=True,
                    output=f"📄 {file_path} (共 {len(lines)} 行)\n\n{md_content[:5000]}"
                )
            
            # 获取指定章节
            indexer = get_indexer()
            result = indexer.get_section_content(file_path, section_title, md_content)
            
            if not result:
                # 章节未找到，列出所有可用章节
                sections = indexer.list_sections(file_path)
                available = "\n".join([f"  - {s['title']}" for s in sections])
                return ToolResult(
                    success=False,
                    output="",
                    error=f"章节 '{section_title}' 未找到。\n\n可用章节 ({len(sections)} 个):\n{available}\n\n请从以上列表中选择正确的章节标题重试。或者工具出现错误，请使用bash命令查看md文件。"
                )
            
            # 格式化输出
            output = (
                f"📄 {file_path}\n"
                f"📌 {result['title']} (lines {result['start_line']}-{result['end_line']})\n"
                f"{'=' * 50}\n\n"
                f"{result['content']}"
            )
            
            return ToolResult(
                success=True,
                output=output
            )
            
        except Exception as e:
            logger.error(f"Read section failed: {e}")
            return ToolResult(
                success=False,
                output="",
                error=f"读取章节失败: {str(e)}"
            )
