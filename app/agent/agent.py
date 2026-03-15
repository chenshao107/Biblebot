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
from app.agent.artifact_store import ArtifactStore, ArtifactMessageBuilder, get_artifact_store
from app.core.config import settings


def estimate_tokens(text: str) -> int:
    """
    估算文本的 token 数量
    中文：1 字 ≈ 1.5 tokens
    英文：1 词 ≈ 1.3 tokens
    简化计算：总字符数 / 2
    """
    if not text:
        return 0
    # 简单估算：平均每个字符约 0.5-1.5 tokens，取保守估计
    return int(len(text) * 0.6)


def calculate_messages_tokens(messages: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    计算 messages 列表的 token 统计信息
    
    Returns:
        {
            "total_tokens": 总 token 数,
            "message_count": 消息数量,
            "by_role": 按角色统计,
            "details": 每条消息的详情
        }
    """
    total_tokens = 0
    by_role = {}
    details = []
    
    for i, msg in enumerate(messages):
        # 提取内容
        content = ""
        if isinstance(msg.get("content"), str):
            content = msg["content"]
        elif msg.get("tool_calls"):
            # 工具调用消息
            for tc in msg["tool_calls"]:
                content += tc.get("function", {}).get("arguments", "")
        
        # 计算 token
        tokens = estimate_tokens(content)
        total_tokens += tokens
        
        role = msg.get("role", "unknown")
        by_role[role] = by_role.get(role, 0) + tokens
        
        # 记录详情
        content_preview = content[:100] + "..." if len(content) > 100 else content
        details.append({
            "index": i,
            "role": role,
            "tokens": tokens,
            "content_preview": content_preview
        })
    
    return {
        "total_tokens": total_tokens,
        "message_count": len(messages),
        "by_role": by_role,
        "details": details
    }


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
        
        # Token 统计相关
        self._token_stats_history = []  # 每轮的 token 统计
        self._total_tokens_consumed = 0  # 累计消耗的 token（估算）
        self._tool_results_tokens = 0  # 工具结果累计 token
        
        # Artifact 存储
        self.artifact_store = get_artifact_store()
        self.artifact_builder = ArtifactMessageBuilder(self.artifact_store)
    
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
        
        # 重置 token 统计
        self._token_stats_history = []
        self._total_tokens_consumed = 0
        self._tool_results_tokens = 0
        
        # 重置 ArtifactStore（每个任务独立）
        from app.agent.artifact_store import reset_artifact_store
        reset_artifact_store()
        self.artifact_store = get_artifact_store()
        self.artifact_builder = ArtifactMessageBuilder(self.artifact_store)
        
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
            
            # 动态注入迭代预警（方案1）
            remaining = self.max_iterations - iteration - 1
            if remaining <= 0:
                # 最后一次迭代：强制收敛警告
                warning_msg = (
                    f"⚠️ 【紧急】这是你的最后一次调用机会（{self.max_iterations}/{self.max_iterations}）。"
                    f"你必须立即停止所有工具调用，基于已收集的信息给出最终答案。"
                    f"如果继续调用工具，任务将失败且用户无法获得任何答案。"
                )
                messages.append({"role": "system", "content": warning_msg})
                logger.warning(f"🚨 注入强制收敛警告：最后一次迭代")
            elif remaining <= 2:
                # 剩余2次：强烈警告
                warning_msg = (
                    f"⏰ 【警告】你仅剩 {remaining} 次调用机会（当前第 {iteration + 1} 次，共 {self.max_iterations} 次）。"
                    f"请立即停止探索，整合已有信息准备给出最终答案。"
                    f"不要调用任何新工具，直接回答用户问题。"
                )
                messages.append({"role": "system", "content": warning_msg})
                logger.info(f"⚠️ 注入收敛提醒：剩余 {remaining} 次")
            elif remaining <= self.max_iterations * 0.3:
                # 剩余30%：温和提醒
                warning_msg = (
                    f"💡 【提醒】你还剩 {remaining} 次调用机会（共 {self.max_iterations} 次）。"
                    f"珍惜每一次调用机会，多调用点工具，评估是否已收集足够信息，如已足够请开始总结答案。"
                )
                messages.append({"role": "system", "content": warning_msg})
                logger.info(f"💡 注入迭代提醒：剩余 {remaining} 次")
                    
            # 计算并记录当前上下文 token 统计
            token_stats = calculate_messages_tokens(messages)
            self._token_stats_history.append({
                "iteration": iteration + 1,
                **token_stats
            })
            
            # 累计消耗（估算输入 token）
            self._total_tokens_consumed += token_stats['total_tokens']
            
            # 统计工具结果 token
            tool_tokens = token_stats['by_role'].get('tool', 0)
            self._tool_results_tokens += tool_tokens
            
            # 计算增长率
            growth_rate = 0
            if len(self._token_stats_history) > 1:
                prev_tokens = self._token_stats_history[-2]['total_tokens']
                if prev_tokens > 0:
                    growth_rate = ((token_stats['total_tokens'] - prev_tokens) / prev_tokens) * 100
            
            logger.info(f"📊 第 {iteration + 1} 轮上下文统计:")
            logger.info(f"   当前上下文: {token_stats['total_tokens']} tokens | 消息数: {token_stats['message_count']}")
            logger.info(f"   累计消耗: {self._total_tokens_consumed} tokens | 工具结果累计: {self._tool_results_tokens} tokens")
            logger.info(f"   增长率: {growth_rate:+.1f}% | 按角色: {token_stats['by_role']}")
            
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
                        logger.info(f"✅ 工具返回成功，原始大小: {len(result_content)} 字符")
                    else:
                        result_content = f"错误：{result.error}"
                        logger.warning(f"⚠️ 工具返回失败：{result.error}")
                    
                    # 【Artifact 模式】工具结果存入 ArtifactStore，messages 只放引用
                    artifact_id = self.artifact_store.save(
                        content=result_content,
                        artifact_type="tool_result",
                        metadata={
                            "tool_name": tc["name"],
                            "tool_args": tc["arguments"],
                            "success": result.success
                        }
                    )
                    
                    # 构建引用消息（大幅减小 token）
                    tool_message = self.artifact_builder.build_tool_result_message(
                        tool_call_id=tc["id"],
                        tool_name=tc["name"],
                        artifact_id=artifact_id
                    )
                    
                    # 给前端显示用（仍显示原始内容）
                    yield {
                        "type": "tool_result",
                        "content": result_content,  # 前端仍显示完整内容
                        "tool_name": tc["name"],
                        "artifact_id": artifact_id  # 附加 artifact_id
                    }
                    
                    # 添加工具结果到消息（使用 artifact 引用）
                    messages.append(tool_message)
                    
                    logger.info(f"📦 Artifact 已创建: {artifact_id}，消息大小从 {len(result_content)} 降至 {len(tool_message['content'])} 字符")
            
            else:
                # 没有工具调用，说明 LLM 准备给出最终答案
                final_answer = response["content"] or "我无法回答这个问题。"
                logger.info(f"💡 最终答案：{final_answer[:100]}...")
                
                # 输出最终 token 统计报告
                self._log_final_token_report()
                
                yield {
                    "type": "final_answer",
                    "content": final_answer
                }
                return
        
        # 达到最大迭代次数
        logger.warning(f"⚠️ 达到最大迭代次数 {self.max_iterations}")
        
        # 输出最终 token 统计报告
        self._log_final_token_report()
        
        yield {
            "type": "final_answer",
            "content": "抱歉，我在尝试多次后仍无法完成这个任务。请尝试简化你的问题。"
        }
    
    def _log_final_token_report(self):
        """输出最终 token 统计报告"""
        if not self._token_stats_history:
            return
        
        logger.info("=" * 60)
        logger.info("📈 Token 统计报告")
        logger.info("=" * 60)
        logger.info(f"总迭代轮数: {len(self._token_stats_history)}")
        logger.info(f"累计输入 Token: {self._total_tokens_consumed}")
        logger.info(f"工具结果累计 Token: {self._tool_results_tokens} ({self._tool_results_tokens/max(1,self._total_tokens_consumed)*100:.1f}%)")
        
        # Artifact 统计
        art_stats = self.artifact_store.get_stats()
        logger.info("-" * 60)
        logger.info(f"📦 Artifact 存储统计:")
        logger.info(f"   存储数量: {art_stats['count']} | 总 Token: {art_stats['total_tokens']} | 大小: {art_stats['total_size_mb']} MB")
        logger.info(f"   类型分布: {art_stats['by_type']}")
        
        # 估算节省的 token
        if art_stats['count'] > 0:
            # 假设每个 artifact 如果不压缩会全部进 messages
            saved_tokens = art_stats['total_tokens'] - (art_stats['count'] * 200)  # 200 是引用平均大小
            saved_pct = saved_tokens / max(1, self._total_tokens_consumed) * 100
            logger.info(f"   💡 估算节省: ~{saved_tokens} tokens ({saved_pct:.1f}%)")
        
        # 每轮详情
        logger.info("-" * 60)
        logger.info("每轮详情:")
        for stat in self._token_stats_history:
            tool_pct = stat['by_role'].get('tool', 0) / max(1, stat['total_tokens']) * 100
            logger.info(f"  轮次 {stat['iteration']}: {stat['total_tokens']:>6} tokens "
                       f"(工具占 {tool_pct:>5.1f}%) | 消息 {stat['message_count']} 条")
        
        # 趋势分析
        if len(self._token_stats_history) >= 2:
            first = self._token_stats_history[0]['total_tokens']
            last = self._token_stats_history[-1]['total_tokens']
            total_growth = ((last - first) / max(1, first)) * 100
            logger.info("-" * 60)
            logger.info(f"上下文膨胀: {first} → {last} tokens (+{total_growth:.1f}%)")
        
        logger.info("=" * 60)


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
