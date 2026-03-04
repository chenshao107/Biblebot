"""
Agent 核心 - LLM + 循环 + 工具调用
"""
import json
from typing import List, Dict, Any, Optional, Generator
from loguru import logger
from app.agent.llm import LLMClient
from app.agent.tools.base import BaseTool, ToolResult


SYSTEM_PROMPT = """你是一个智能知识助手，可以通过各种工具来回答用户的问题。

你有以下工具可用：
1. **search_knowledge**: 在知识库中进行语义搜索（RAG检索）
2. **run_bash**: 执行 bash 命令来探索文件（如 ls, cat, head, tail, grep, rg, find 等）
3. **run_python**: 执行 Python 代码进行数据分析或复杂处理

工作策略：
- 对于简单的知识查询，优先使用 search_knowledge 快速获取答案
- 对于需要探索文件结构、查找具体内容的任务，使用 run_bash
- 对于需要数据分析、格式转换的任务，使用 run_python
- 你可以组合使用多个工具来完成复杂任务
- 每次工具调用后，仔细分析结果，决定是否需要继续探索

请根据用户的问题，自主选择合适的工具，逐步探索并最终给出完整的答案。"""


class Agent:
    """Agent 核心类"""
    
    def __init__(self, tools: List[BaseTool], max_iterations: int = None):
        from app.core.config import settings
        self.llm = LLMClient()
        self.tools = {tool.name: tool for tool in tools}
        self.max_iterations = max_iterations or settings.AGENT_MAX_ITERATIONS
        
    def _get_tools_schema(self) -> List[Dict[str, Any]]:
        """获取所有工具的 OpenAI function calling schema"""
        return [tool.to_openai_function() for tool in self.tools.values()]
    
    def _execute_tool(self, name: str, arguments: Dict[str, Any]) -> ToolResult:
        """执行指定工具"""
        if name not in self.tools:
            return ToolResult(
                success=False,
                output="",
                error=f"未知工具：{name}"
            )
            
        tool = self.tools[name]
        try:
            logger.info(f"🔧 执行工具：{name}")
            logger.debug(f"参数：{arguments}")
            result = tool.execute(**arguments)
            logger.info(f"✅ 工具 {name} 执行完成：success={result.success}")
            return result
        except Exception as e:
            logger.error(f"❌ 工具 {name} 执行失败：{e}")
            return ToolResult(
                success=False,
                output="",
                error=str(e)
            )
    
    def run(self, query: str, context: Optional[str] = None) -> str:
        """
        运行 Agent，返回最终答案
        
        Args:
            query: 用户问题
            context: 可选的上下文信息
            
        Returns:
            最终答案
        """
        # 收集所有步骤，最后返回
        steps = list(self.run_stream(query, context))
        
        # 返回最后一个 final_answer
        for step in reversed(steps):
            if step["type"] == "final_answer":
                return step["content"]
        
        return "抱歉，我无法完成这个任务。"
    
    def run_stream(
        self, 
        query: str, 
        context: Optional[str] = None
    ) -> Generator[Dict[str, Any], None, None]:
        """
        流式运行 Agent，逐步返回执行过程
        
        Yields:
            {
                "type": "thinking" | "tool_call" | "tool_result" | "final_answer",
                "content": str,
                "tool_name": str (optional),
                "tool_args": dict (optional)
            }
        """
        # 构建初始消息
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]
        
        # 添加上下文（如果有）
        if context:
            messages.append({
                "role": "user", 
                "content": f"背景信息：\n{context}\n\n用户问题：{query}"
            })
        else:
            messages.append({"role": "user", "content": query})
        
        tools_schema = self._get_tools_schema()
        
        for iteration in range(self.max_iterations):
            logger.info(f"🤔 Agent 迭代 {iteration + 1}/{self.max_iterations}")
                    
            # 调用 LLM
            response = self.llm.chat(messages, tools=tools_schema)
                    
            # 检查是否有工具调用
            if response["tool_calls"]:
                tool_calls = self.llm.parse_tool_calls(response["tool_calls"])
                        
                # 如果 LLM 同时返回了文本，先输出
                if response["content"]:
                    yield {
                        "type": "thinking",
                        "content": response["content"]
                    }
                        
                # 添加 assistant 消息（包含工具调用）
                messages.append({
                    "role": "assistant",
                    "content": response["content"],
                    "tool_calls": response["tool_calls"]
                })
                        
                # 执行每个工具调用
                for tc in tool_calls:
                    logger.info(f"📞 调用工具：{tc['name']}")
                    yield {
                        "type": "tool_call",
                        "content": f"调用工具：{tc['name']}",
                        "tool_name": tc["name"],
                        "tool_args": tc["arguments"]
                    }
                    
                    # 执行工具
                    result = self._execute_tool(tc["name"], tc["arguments"])
                    
                    # 构建结果内容
                    if result.success:
                        result_content = result.output
                        logger.info(f"✅ 工具返回成功")
                    else:
                        result_content = f"错误：{result.error}"
                        logger.warning(f"⚠️ 工具返回失败：{result.error}")
                                        
                    yield {
                        "type": "tool_result",
                        "content": result_content,
                        "tool_name": tc["name"]
                    }
                    
                    # 添加工具结果到消息
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": result_content
                    })
            
            else:
                # 没有工具调用，说明 LLM 准备给出最终答案
                final_answer = response["content"] or "我无法回答这个问题。"
                logger.info(f"💡 最终答案：{final_answer[:100]}...")
                yield {
                    "type": "final_answer",
                    "content": final_answer
                }
                return
        
        # 达到最大迭代次数
        logger.warning(f"⚠️ 达到最大迭代次数 {self.max_iterations}")
        yield {
            "type": "final_answer",
            "content": "抱歉，我在尝试多次后仍无法完成这个任务。请尝试简化你的问题。"
        }


class AgentResponse:
    """Agent 响应封装，用于 API 返回"""
    
    def __init__(self):
        self.steps: List[Dict[str, Any]] = []
        self.final_answer: str = ""
    
    def add_step(self, step: Dict[str, Any]):
        self.steps.append(step)
        if step["type"] == "final_answer":
            self.final_answer = step["content"]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "answer": self.final_answer,
            "steps": self.steps
        }
