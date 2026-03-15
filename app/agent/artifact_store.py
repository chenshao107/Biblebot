"""
Artifact 存储 - 工具结果外部化存储
避免工具结果直接塞进 messages 导致上下文膨胀
"""
import uuid
import hashlib
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from loguru import logger


@dataclass
class Artifact:
    """Artifact 数据对象"""
    id: str
    type: str  # "tool_result", "file", "search_result" 等
    content: str
    summary: str  # LLM 生成的语义摘要
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def token_count(self) -> int:
        """估算 token 数量"""
        return int(len(self.content) * 0.6)
    
    @property
    def summary_token_count(self) -> int:
        """摘要的 token 数量"""
        return int(len(self.summary) * 0.6)
    
    @property
    def size(self) -> int:
        """内容字节数"""
        return len(self.content.encode('utf-8'))
    
    def get_display_content(self, use_summary: bool = True) -> str:
        """获取显示内容，优先使用摘要"""
        if use_summary and self.summary:
            return self.summary
        return self.content


class ArtifactStore:
    """
    Artifact 存储管理器
    
    核心思想：工具结果不直接进 messages，只存引用 ID
    需要时通过 ID 加载，支持按需检索和摘要
    """
    
    def __init__(self, max_artifacts: int = 100):
        self._store: Dict[str, Artifact] = {}
        self._max_artifacts = max_artifacts
        self._access_count: Dict[str, int] = {}  # 访问计数，用于 LRU
        
    def save(self, content: str, artifact_type: str = "tool_result", 
             metadata: Dict[str, Any] = None, summary: str = None) -> str:
        """
        保存内容到 ArtifactStore，返回 artifact_id
        
        Args:
            content: 内容文本
            artifact_type: 类型标记
            metadata: 元数据（如工具名、调用目的、调用时间等）
            summary: 预生成的语义摘要（可选）
            
        Returns:
            artifact_id: 唯一标识符
        """
        # 生成唯一 ID
        artifact_id = f"art_{uuid.uuid4().hex[:12]}"
        
        artifact = Artifact(
            id=artifact_id,
            type=artifact_type,
            content=content,
            summary=summary or "",  # 可能为空，需要后续生成
            metadata=metadata or {}
        )
        
        self._store[artifact_id] = artifact
        self._access_count[artifact_id] = 0
        
        # 清理旧 artifact
        self._cleanup_if_needed()
        
        logger.debug(f"Artifact 已保存: {artifact_id} (内容{artifact.token_count} tokens, 摘要{artifact.summary_token_count} tokens)")
        return artifact_id
    
    def get(self, artifact_id: str) -> Optional[Artifact]:
        """获取 artifact"""
        if artifact_id not in self._store:
            return None
        
        self._access_count[artifact_id] += 1
        return self._store[artifact_id]
    
    def get_content(self, artifact_id: str) -> Optional[str]:
        """获取 artifact 内容"""
        artifact = self.get(artifact_id)
        return artifact.content if artifact else None
    
    def get_summary(self, artifact_id: str, max_length: int = 500) -> str:
        """
        获取 artifact 摘要
        优先返回 LLM 生成的语义摘要，否则返回截断内容
        """
        artifact = self.get(artifact_id)
        if not artifact:
            return f"[Artifact {artifact_id} 不存在]"
        
        # 优先使用 LLM 生成的语义摘要
        if artifact.summary:
            return artifact.summary
        
        # 退化为截断摘要
        content = artifact.content
        if len(content) <= max_length:
            return content
        
        summary = content[:max_length]
        remaining = len(content) - max_length
        return f"{summary}\n... [还有 {remaining} 字符，使用 load_artifact('{artifact_id}') 获取完整内容]"
    
    def exists(self, artifact_id: str) -> bool:
        """检查 artifact 是否存在"""
        return artifact_id in self._store
    
    def get_stats(self) -> Dict[str, Any]:
        """获取存储统计"""
        total_tokens = sum(a.token_count for a in self._store.values())
        total_size = sum(a.size for a in self._store.values())
        
        return {
            "count": len(self._store),
            "total_tokens": total_tokens,
            "total_size_mb": round(total_size / 1024 / 1024, 2),
            "by_type": self._count_by_type()
        }
    
    def _count_by_type(self) -> Dict[str, int]:
        """按类型统计"""
        counts = {}
        for a in self._store.values():
            counts[a.type] = counts.get(a.type, 0) + 1
        return counts
    
    def _cleanup_if_needed(self):
        """如果超过限制，清理最少访问的 artifact"""
        if len(self._store) <= self._max_artifacts:
            return
        
        # 按访问次数排序，删除最少的
        sorted_ids = sorted(
            self._access_count.keys(),
            key=lambda x: self._access_count[x]
        )
        
        to_remove = len(self._store) - self._max_artifacts
        for artifact_id in sorted_ids[:to_remove]:
            del self._store[artifact_id]
            del self._access_count[artifact_id]
            logger.debug(f"Artifact 已清理: {artifact_id}")
    
    def clear(self):
        """清空所有 artifact"""
        self._store.clear()
        self._access_count.clear()
        logger.info("ArtifactStore 已清空")


class ArtifactMessageBuilder:
    """
    构建包含 artifact 引用的 messages
    替代直接塞 tool_result 到 messages
    """
    
    def __init__(self, artifact_store: ArtifactStore):
        self.store = artifact_store
    
    def build_tool_result_message(self, tool_call_id: str, tool_name: str, 
                                   artifact_id: str, information_need: str = "") -> Dict[str, Any]:
        """
        构建工具结果消息（轻量级引用）
        
        不塞摘要，只放 artifact_id 和元数据
        LLM 需要时可以通过 retrieve_artifact 获取
        """
        artifact = self.store.get(artifact_id)
        if not artifact:
            return {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": f"[错误：找不到 artifact {artifact_id}]"
            }
        
        # 轻量级引用格式 - 只包含关键元数据
        content_parts = [
            f"【工具结果已存储】",
            f"artifact_id: {artifact_id}",
            f"工具: {tool_name}",
        ]
        
        if information_need:
            content_parts.append(f"信息需求: {information_need[:100]}")
        
        content_parts.extend([
            f"大小: {artifact.token_count} tokens",
            f"",
            f"如需查看内容，请使用：retrieve_artifact('{artifact_id}')",
        ])
        
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": "\n".join(content_parts),
            "artifact_id": artifact_id,
            "information_need": information_need  # 保留信息需求，便于后续检索
        }
    
    def expand_artifact_in_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """
        如果需要，展开 message 中的 artifact 引用
        用于在关键节点给 LLM 看完整内容
        """
        content = message.get("content", "")
        
        # 检查是否包含 artifact 引用标记
        if "artifact_id:" in content:
            # 可以在这里实现自动展开逻辑
            pass
        
        return message


# 全局 artifact store（单例）
_global_artifact_store: Optional[ArtifactStore] = None


def get_artifact_store() -> ArtifactStore:
    """获取全局 artifact store"""
    global _global_artifact_store
    if _global_artifact_store is None:
        _global_artifact_store = ArtifactStore()
    return _global_artifact_store


def reset_artifact_store():
    """重置全局 artifact store"""
    global _global_artifact_store
    _global_artifact_store = ArtifactStore()
