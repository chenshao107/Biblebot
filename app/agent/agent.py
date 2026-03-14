"""
Agent 核心 - LLM + 循环 + 工具调用
"""
import json
import os
import subprocess
import threading
from typing import List, Dict, Any, Optional, Generator
from loguru import logger
from app.agent.llm import LLMClient
from app.agent.tools.base import BaseTool, ToolResult
from app.agent.prompt_manager import PromptManager
from app.core.config import settings


class Agent:
    """Agent 核心类"""
    
    def __init__(self, tools: List[BaseTool], max_iterations: int = None, knowledge_tree: str = ""):
        from app.core.config import settings
        self.llm = LLMClient()
        self.tools = {tool.name: tool for tool in tools}
        self.max_iterations = max_iterations or settings.AGENT_MAX_ITERATIONS
        self.knowledge_tree = knowledge_tree
        self.prompt_manager = PromptManager()
        self._stop_event = threading.Event()  # 用于取消当前任务
    
    def stop(self):
        """停止当前正在运行的 Agent 任务"""
        self._stop_event.set()
        logger.info("🛑 Agent 收到停止信号")
    
    def reset(self):
        """重置停止状态，准备新任务"""
        self._stop_event.clear()
    
    def _check_tree_command(self):
        """检查 tree 命令是否存在"""
        try:
            result = subprocess.run(
                ["tree", "--version"],
                capture_output=True,
                timeout=2
            )
            return result.returncode == 0
        except Exception:
            return False
    
    def _get_knowledge_tree(self) -> str:
        """获取知识库目录结构（2层）"""
        if self.knowledge_tree:
            return self.knowledge_tree
        
        # 检查 tree 命令是否存在
        if not self._check_tree_command():
            logger.error("❌ 'tree' 命令未安装，请执行: sudo apt-get install tree")
            raise RuntimeError(
                "tree 命令缺失。Agent 需要 tree 命令来获取知识库结构。\n"
                "请安装: sudo apt-get install tree 或 sudo yum install tree"
            )
        
        # 自动获取知识库结构
        try:
            data_dir = settings.DATA_CANONICAL_DIR
            if not os.path.exists(data_dir):
                return ""
            
            # 使用 tree -L 2 获取两层目录结构（基于 Docling 转换后的 Markdown）
            result = subprocess.run(
                ["tree", "-L", "2", data_dir],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                return result.stdout
        except Exception as e:
            logger.warning(f"获取知识库结构失败: {e}")
        
        return ""
        
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
                "type": "thinking" | "tool_call" | "tool_result" | "final_answer" | "stopped",
                "content": str,
                "tool_name": str (optional),
                "tool_args": dict (optional)
            }
        """
        # 重置停止状态
        self.reset()
        
        # 构建初始消息
        knowledge_tree = self._get_knowledge_tree()
        tools_list = list(self.tools.values())
        system_prompt = self.prompt_manager.build_system_prompt(
            tools=tools_list,
            knowledge_tree=knowledge_tree,
        )
        messages = [
            {"role": "system", "content": system_prompt}
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
            # 检查是否收到停止信号
            if self._stop_event.is_set():
                logger.info("🛑 Agent 迭代被用户停止")
                yield {
                    "type": "stopped",
                    "content": "用户已停止生成"
                }
                return
            
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
                    # 检查是否收到停止信号
                    if self._stop_event.is_set():
                        logger.info("🛑 Agent 工具调用被用户停止")
                        yield {
                            "type": "stopped",
                            "content": "用户已停止生成"
                        }
                        return
                    
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
