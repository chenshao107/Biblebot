"""
Artifact 语义摘要生成器
结合工具调用目的，生成有针对性的摘要
"""
from typing import Optional
from loguru import logger
from app.agent.llm import LLMClient


class ArtifactSummarizer:
    """
    为 Artifact 生成语义化摘要
    
    策略：
    1. 短内容 (< 1000 字符)：直接存，不生成摘要
    2. 长内容：用 LLM 生成针对性摘要，结合工具调用目的
    """
    
    # 阈值：超过这个长度才需要 LLM 摘要
    SUMMARIZE_THRESHOLD = 1000
    
    # 摘要最大长度
    MAX_SUMMARY_LENGTH = 800
    
    def __init__(self):
        self.llm = LLMClient()
    
    def should_summarize(self, content: str) -> bool:
        """判断是否需要生成摘要"""
        return len(content) > self.SUMMARIZE_THRESHOLD
    
    def generate_summary(self, content: str, tool_name: str, 
                         tool_purpose: str, user_query: str = "",
                         information_need: str = "") -> Optional[str]:
        """
        生成有针对性的语义摘要
        
        Args:
            content: 工具结果内容
            tool_name: 工具名称
            tool_purpose: 工具调用目的（为什么调用这个工具）
            user_query: 用户原始问题
            information_need: Agent 主动声明的信息需求（关键！）
            
        Returns:
            摘要文本，如果不需要摘要则返回 None
        """
        if not self.should_summarize(content):
            return None
        
        try:
            summary = self._call_llm_for_summary(
                content=content,
                tool_name=tool_name,
                tool_purpose=tool_purpose,
                user_query=user_query,
                information_need=information_need
            )
            logger.info(f"✅ 摘要生成完成: {len(content)} → {len(summary)} 字符")
            return summary
            
        except Exception as e:
            logger.warning(f"⚠️ 摘要生成失败: {e}，将使用截断")
            return None
    
    def _call_llm_for_summary(self, content: str, tool_name: str,
                               tool_purpose: str, user_query: str,
                               information_need: str = "") -> str:
        """调用 LLM 生成摘要"""
        
        # 构建针对性 prompt，强调信息需求
        system_prompt = """你是一个专门提取关键信息的助手。
你的任务是从工具结果中提取 Agent 需要的信息。

核心原则：
1. 聚焦【信息需求】中声明要获取的内容
2. 判断结果是否满足需求：是 / 部分 / 否
3. 提取关键信息
4. 保留具体的代码示例和命令
5. 如果信息不满足需求，明确指出"需要继续搜索"
6. 控制输出在 500 字以内
7. 使用 load_artifact('artifact_id') 获取完整内容(因为最后完整回答需要)。"""

        user_prompt = f"""【用户问题】
{user_query if user_query else "未提供"}

【工具调用目的】
{tool_purpose}

【信息需求 - Agent 期望获取的内容】
{information_need if information_need else "未明确声明，请根据上下文推断"}

【工具名称】
{tool_name}

【工具结果内容】
{content[:8000]}

请按以下格式生成摘要：

**需求满足度**: [完全满足/部分满足/未满足]

**关键发现**:
- [提取的关键信息1]
- [提取的关键信息2]
...

**相关性说明**:
[说明这些信息如何满足或未能满足信息需求]

**建议**:
[如果信息不完整，建议下一步如何获取]"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        response = self.llm.chat(messages, temperature=0.3)
        summary = response.get("content", "")
        
        # 截断到最大长度
        if len(summary) > self.MAX_SUMMARY_LENGTH:
            summary = summary[:self.MAX_SUMMARY_LENGTH] + "\n... [摘要已截断]"
        
        return summary


# 全局 summarizer 实例
_global_summarizer: Optional[ArtifactSummarizer] = None


def get_artifact_summarizer() -> ArtifactSummarizer:
    """获取全局 summarizer 实例"""
    global _global_summarizer
    if _global_summarizer is None:
        _global_summarizer = ArtifactSummarizer()
    return _global_summarizer
