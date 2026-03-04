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
                }
            },
            "required": ["query"]
        }
    
    def execute(self, query: str, top_k: int = 5) -> ToolResult:
        """执行 RAG 检索"""
        try:
            logger.info(f"RAG 检索: {query}, top_k={top_k}")
            results = self.rag_engine.search(query, top_k=top_k)
            
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
                
                doc_id = meta.get("doc_id", "未知")
                section = meta.get("section", "")
                
                output_parts.append(
                    f"[{i}] 来源: {doc_id} | {section}\n"
                    f"相关度: {score:.3f}\n"
                    f"内容:\n{content}\n"
                )
            
            output = "\n---\n".join(output_parts)
            
            return ToolResult(
                success=True,
                output=f"找到 {len(results)} 条相关结果:\n\n{output}"
            )
            
        except Exception as e:
            logger.error(f"RAG 检索失败: {e}")
            return ToolResult(
                success=False,
                output="",
                error=f"检索失败: {str(e)}"
            )
