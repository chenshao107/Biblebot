"""
Agent 核心 - LLM + 循环 + 工具调用
"""
import json
import os
import subprocess
from typing import List, Dict, Any, Optional, Generator
from loguru import logger
from app.agent.llm import LLMClient
from app.agent.tools.base import BaseTool, ToolResult
from app.core.config import settings


def get_system_prompt(knowledge_tree: str = "", tools: List[BaseTool] = None) -> str:
    """生成系统 Prompt，包含知识库结构信息和可用工具"""
    tree_info = f"\n知识库结构：\n{knowledge_tree}\n" if knowledge_tree else ""
    
    # 构建工具列表描述
    tools_list = []
    mcp_tools = []
    
    if tools:
        for tool in tools:
            tool_desc = f"- **{tool.name}**: {tool.description}"
            if tool.name.startswith(("filesystem_", "fetch_", "github_", "sqlite_", "git_", 
                                     "brave_search_", "puppeteer_", "redis_")):
                mcp_tools.append(tool_desc)
            else:
                tools_list.append(tool_desc)
    else:
        # 默认工具列表（向后兼容）
        tools_list = [
            "- **search_knowledge**: 在知识库中进行语义搜索（RAG检索）",
            "- **run_bash**: 执行 bash 命令来探索文件（如 ls, cat, head, tail, grep, rg, find 等）",
            "- **run_python**: 执行 Python 代码进行数据分析或复杂处理",
            "- **calculator**: 执行数学计算",
            "- **web_search**: 搜索互联网获取最新信息"
        ]
    
    # 构建工具说明
    tools_section = "\n".join(tools_list) if tools_list else ""
    mcp_section = ""
    if mcp_tools:
        mcp_section = "\n\n**MCP 扩展工具**（通过 Model Context Protocol 接入的外部工具）:\n" + "\n".join(mcp_tools)
    
    return f"""你是一个智能知识助手，类似于Claude Code、Cursor的AI助手，可以通过各种工具来回答用户的问题。
{tree_info}
你有以下工具可用，并且可以一次可以调用多个工具：
{tools_section}{mcp_section}

工作策略：
- 对于简单的知识查询，优先使用 search_knowledge 快速在现成的RAG知识库中粗略搜索。搜索的目的仅仅是初步定位与问题相关的内容的大致位置（我特地在RAG搜索结果里加入了当前片段出自于哪的信息，请你务必利用。）。为了更准确地获取答案，请通过bash命令或者python命令来查看原文的特定片段。
- 对于需要探索文件结构、查找具体内容的任务，使用 run_bash
- 对于需要数据分析、格式转换的任务，使用 run_python
- 对于需要获取网页内容的任务，可以使用 fetch_* 工具（如果可用）
- 对于需要文件系统操作的任务，可以使用 filesystem_* 工具（如果可用）
- 你可以组合使用多个工具来完成复杂任务
- 每次工具调用后，仔细分析结果，决定是否需要继续探索。当你能确定答案时，请立即给出最终答案。

工具使用建议（强烈建议但不强制）：
- search_knowledge: 建议最多 2-3 次，除非你认为当前知识库还有未挖掘的信息，或者查询不够、有必要延伸查找某些东西能完善回答
- run_bash: 建议最多 2-3 次，用于查看已定位的原文片段
- run_python: 仅在需要数据分析时使用
- MCP 工具: 根据具体任务需求使用

重要提醒：
- 如果已经获得足够信息能回答用户问题，请立即停止调用工具，直接给出最终答案
- 不要为了探索而探索，避免不必要的工具调用
- 简单问题通常 1-2 次 search_knowledge 就能解决

关于知识库覆盖范围：
- 当前知识库是有限的，只包含特定领域的技术文档
- 如果经过 2-3 次搜索仍未找到相关信息，很可能知识库中没有该内容
- 此时请直接告知用户"根据现有知识库无法找到答案"，而不是无限次尝试搜索
- 不要假设知识库中一定有答案，也不要因为搜不到而反复用不同关键词尝试

回答规范：
- 给出最终答案时，请简要标注信息来源（如：根据《Buildroot手册》第4章、或根据140服务器使用文档）
- 如果使用了多个来源，选择最主要的一两个标注即可
- 不需要详细引用，只需让用户知道复查方向

请根据用户的问题，自主选择合适的工具，逐步探索并最终给出完整的答案。"""


class Agent:
    """Agent 核心类"""
    
    def __init__(self, tools: List[BaseTool], max_iterations: int = None, knowledge_tree: str = ""):
        from app.core.config import settings
        self.llm = LLMClient()
        self.tools = {tool.name: tool for tool in tools}
        self.max_iterations = max_iterations or settings.AGENT_MAX_ITERATIONS
        self.knowledge_tree = knowledge_tree
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
            data_dir = settings.DATA_RAW_DIR
            if not os.path.exists(data_dir):
                return ""
            
            # 使用 tree -L 2 获取两层目录结构
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
        import threading
        
        # 重置停止状态
        self.reset()
        
        # 构建初始消息
        knowledge_tree = self._get_knowledge_tree()
        tools_list = list(self.tools.values())
        system_prompt = get_system_prompt(knowledge_tree, tools_list)
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
