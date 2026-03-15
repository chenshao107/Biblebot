"""
Artifact 检索工具 - 让 LLM 按需获取存储的工具结果
"""
from typing import Any, Dict
from loguru import logger
from app.agent.tools.base import BaseTool, ToolResult
from app.agent.artifact_store import get_artifact_store


class ArtifactRetrievalTool(BaseTool):
    """
    检索已存储的 Artifact 内容
    
    当 LLM 需要查看之前工具调用的完整结果时使用
    """
    
    @property
    def name(self) -> str:
        return "retrieve_artifact"
    
    @property
    def description(self) -> str:
        return """检索之前工具调用存储的完整结果。

使用场景：
1. 当你看到 "artifact_id: xxx" 且需要查看完整内容时
2. 当轻量级引用中的信息不足以回答问题时
3. 当你需要验证或深入分析之前的工具结果时

注意：
- 只检索你确实需要的内容
- 避免重复检索相同的 artifact
- 如果信息已足够，不要调用此工具"""
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "artifact_id": {
                    "type": "string",
                    "description": "要检索的 artifact ID，例如 'art_a1b2c3d4e5f6'"
                },
                "max_length": {
                    "type": "integer",
                    "description": "最大返回长度（字符数），默认 5000。如果只需要部分内容，可以设置较小值",
                    "default": 5000
                },
                "offset": {
                    "type": "integer",
                    "description": "起始偏移量，用于分页获取，默认 0",
                    "default": 0
                }
            },
            "required": ["artifact_id"]
        }
    
    def execute(self, artifact_id: str, max_length: int = 5000, 
                offset: int = 0) -> ToolResult:
        """执行检索"""
        try:
            store = get_artifact_store()
            artifact = store.get(artifact_id)
            
            if not artifact:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"找不到 artifact: {artifact_id}"
                )
            
            content = artifact.content
            total_length = len(content)
            
            # 分页获取
            if offset > 0:
                content = content[offset:]
            
            # 截断
            truncated = False
            if len(content) > max_length:
                content = content[:max_length]
                truncated = True
            
            # 构建输出
            output_parts = [
                f"【Artifact 检索结果】",
                f"artifact_id: {artifact_id}",
                f"工具: {artifact.metadata.get('tool_name', 'unknown')}",
                f"信息需求: {artifact.metadata.get('information_need', '未记录')}",
                f"",
                f"内容 ({offset}-{offset + len(content)}/{total_length} 字符):",
                f"---",
                content,
            ]
            
            if truncated:
                remaining = total_length - offset - len(content)
                output_parts.append(f"\n---\n[还有 {remaining} 字符，使用 offset={offset + len(content)} 继续获取]")
            
            logger.info(f"📖 Artifact 检索: {artifact_id} ({len(content)} 字符)")
            
            return ToolResult(
                success=True,
                output="\n".join(output_parts)
            )
            
        except Exception as e:
            logger.error(f"Artifact 检索失败: {e}")
            return ToolResult(
                success=False,
                output="",
                error=f"检索失败: {str(e)}"
            )


class ArtifactListTool(BaseTool):
    """
    列出所有可用的 Artifact
    
    帮助 LLM 了解有哪些存储的工具结果可用
    """
    
    @property
    def name(self) -> str:
        return "list_artifacts"
    
    @property
    def description(self) -> str:
        return """列出当前任务中所有已存储的 Artifact。

使用场景：
1. 当你不确定有哪些之前的工具结果可用时
2. 当你需要查找特定信息但不知道在哪个 artifact 中时
3. 任务开始时了解已收集的信息"""
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "required": []
        }
    
    def execute(self) -> ToolResult:
        """列出所有 artifact"""
        try:
            store = get_artifact_store()
            stats = store.get_stats()
            
            if stats["count"] == 0:
                return ToolResult(
                    success=True,
                    output="当前没有存储的 Artifact"
                )
            
            output_parts = [
                f"【Artifact 列表】",
                f"总计: {stats['count']} 个",
                f"",
            ]
            
            # 遍历所有 artifact
            for artifact_id, artifact in store._store.items():
                meta = artifact.metadata
                info_need = meta.get('information_need', '未记录')[:60]
                output_parts.append(
                    f"- {artifact_id}: {meta.get('tool_name', 'unknown')} "
                    f"({artifact.token_count} tokens) | 需求: {info_need}..."
                )
            
            return ToolResult(
                success=True,
                output="\n".join(output_parts)
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"列出 artifact 失败: {str(e)}"
            )
