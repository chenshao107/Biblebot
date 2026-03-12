"""
RAG 检索工具 - 复用现有的 RAG 引擎
"""
from typing import Any, Dict
from loguru import logger
from app.agent.tools.base import BaseTool, ToolResult
from app.services.rag.retriever import RAGEngine


class RAGTool(BaseTool):
    """RAG 知识库检索工具"""
    
    def __init__(self):
        self._rag_engine = None
    
    @property
    def rag_engine(self) -> RAGEngine:
        """懒加载 RAG 引擎"""
        if self._rag_engine is None:
            logger.info("初始化 RAG 引擎...")
            self._rag_engine = RAGEngine()
        return self._rag_engine
    
    @property
    def name(self) -> str:
        return "search_knowledge"
    
    @property
    def description(self) -> str:
        return """在知识库中进行语义搜索。适用于：
- 查询特定主题的知识
- 寻找相关文档或片段
- 快速获取事实性信息
返回与查询语义相关的知识片段，按相关性排序。"""
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索查询，可以是问题或关键词"
                },
                "top_k": {
                    "type": "integer",
                    "description": "返回结果数量，默认 5",
                    "default": 5
                },
                "category_filter": {
                    "type": "string",
                    "description": "按文件夹路径过滤，只搜索指定目录下的内容。'category'对应第一级文件夹名。示例：'RK3506'表示只搜RK3506文件夹下的文档；'RK3506/uboot'表示只搜RK3506/uboot子目录。当问题明确涉及特定分类时使用。",
                    "default": None
                }
            },
            "required": ["query"]
        }
    
    def execute(self, query: str, top_k: int = 5, category_filter: str = None) -> ToolResult:
        """执行 RAG 检索"""
        try:
            logger.info(f"RAG 检索: {query}, top_k={top_k}, category_filter={category_filter}")
            results = self.rag_engine.search(query, top_k=top_k, category_filter=category_filter)
            
            if not results:
                return ToolResult(
                    success=True,
                    output="知识库中未找到相关内容。"
                )
            
            # 格式化输出
            output_parts = []
            for i, r in enumerate(results, 1):
                # 兼容不同的结果格式
                if isinstance(r, dict):
                    content = r.get("text") or r.get("payload", {}).get("content", "")
                    score = r.get("score", 0)
                    meta = r.get("meta", r.get("payload", {}))
                else:
                    content = getattr(r, "text", str(r))
                    score = getattr(r, "score", 0)
                    meta = getattr(r, "meta", {})
                
                # 提取元数据
                doc_id = meta.get("doc_id", "未知")
                category = meta.get("category", "")
                subcategory = meta.get("subcategory", "")
                full_path = meta.get("full_path", doc_id)
                section = meta.get("section", "")
                start_line = meta.get("start_line", 0)
                end_line = meta.get("end_line", 0)
                
                # 构建来源信息
                source_info = f"📁 {full_path}"
                if category and category != "root":
                    source_info += f" | 分类: {category}"
                    if subcategory:
                        source_info += f"/{subcategory}"
                if section and section != "Root":
                    source_info += f" | 章节: {section}"
                
                # 添加行号信息（相对于转换后的 Markdown，仅供参考）
                line_info = f"lines: {start_line}-{end_line} (参考)" if start_line != end_line else f"line: {start_line} (参考)"
                
                output_parts.append(
                    f"[{i}] {source_info}\n"
                    f"   相关度: {score:.3f} | {line_info}\n"
                    f"   内容:\n{content}\n"
                )
            
            output = "\n---\n".join(output_parts)
            
            # 添加分类统计
            categories = set()
            for r in results:
                if isinstance(r, dict):
                    meta = r.get("payload", {})
                else:
                    meta = getattr(r, "meta", {})
                cat = meta.get("category", "")
                if cat and cat != "root":
                    categories.add(cat)
            
            category_hint = ""
            if categories:
                category_hint = f"\n📊 涉及分类: {', '.join(sorted(categories))}\n"
            
            return ToolResult(
                success=True,
                output=f"找到 {len(results)} 条相关结果:{category_hint}\n{output}"
            )
            
        except Exception as e:
            logger.error(f"RAG 检索失败: {e}")
            return ToolResult(
                success=False,
                output="",
                error=f"检索失败: {str(e)}"
            )
