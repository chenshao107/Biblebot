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
from app.agent.artifact_summarizer import get_artifact_summarizer
from app.core.config import settings


def estimate_tokens(text: str) -> int:
    """
    估算文本的 token 数量
    简化计算：3 字符 ≈ 1 token
    这个比例对中英文都比较接近实际情况
    """
    if not text:
        return 0
    return len(text) // 3


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
        
        # Artifact 存储和摘要
        self.artifact_store = get_artifact_store()
        self.artifact_builder = ArtifactMessageBuilder(self.artifact_store)
        self.artifact_summarizer = get_artifact_summarizer()
        
        # 工具调用目的追踪
        self._tool_call_purposes: Dict[str, str] = {}  # tool_call_id -> purpose
        
        # ============================================
        # Artifact 阈值配置（单位：tokens）
        # ============================================
        
        # Lazy Summarization 触发阈值
        # 当上下文总 token 数超过此值时，触发批量摘要压缩
        self.LAZY_SUMMARY_THRESHOLD = 20000  # tokens
        self._summary_triggered = False  # 是否已触发过总结
        
        # 工具结果处理策略阈值（均以 token 为单位）
        # 策略1: result_tokens < RAW_THRESHOLD → 直接 raw 进 context
        # 策略2: RAW_THRESHOLD <= result_tokens < ARTIFACT_THRESHOLD → raw + artifact 备份
        # 策略3: result_tokens >= ARTIFACT_THRESHOLD → artifact 化，只放引用
        self.RAW_THRESHOLD = 3000       # tokens, 约 9000 字符
        self.ARTIFACT_THRESHOLD = 5000  # tokens, 约 15000 字符
    
    def stop(self):
        """停止当前正在运行的 Agent 任务"""
        self._stop_event.set()
        logger.info("🛑 Agent 收到停止信号")
    
    def reset(self):
        """重置停止状态，准备新任务"""
        self._stop_event.clear()
    
    def _extract_tool_intent(self, tool_name: str, tool_args: Dict[str, Any], 
                              thinking: str) -> Dict[str, str]:
        """
        提取工具调用的完整意图
        
        包括：
        - purpose: 调用目的（为什么要调）
        - information_need: 信息需求（期望获取什么）
        
        从 LLM 的思考文本中提取，如果提取失败则使用启发式生成
        """
        import re
        
        result = {
            "purpose": "",
            "information_need": ""
        }
        
        if thinking:
            # 尝试提取调用目的（找包含工具名或"搜索/查找/获取"的句子）
            sentences = re.split(r'[。！？\n]', thinking)
            for sent in sentences:
                sent_clean = sent.strip()
                if not sent_clean:
                    continue
                    
                # 找包含工具名的句子
                if tool_name.replace('_', '') in sent_clean.replace('_', '').lower():
                    result["purpose"] = sent_clean[:200]
                    break
                # 或者找包含意图关键词的句子
                elif any(kw in sent_clean for kw in ['搜索', '查找', '获取', '查询', '需要', '想要', '找']):
                    result["purpose"] = sent_clean[:200]
                    break
            
            # 尝试提取信息需求（找包含"了解/知道/获取什么"的句子）
            for sent in sentences:
                sent_clean = sent.strip()
                if any(kw in sent_clean for kw in ['了解', '知道', '获取', '找出', '确定', '查看']):
                    # 提取"了解/知道..."后面的内容
                    match = re.search(r'(?:了解|知道|获取|找出|确定|查看)[^，。]*', sent_clean)
                    if match:
                        result["information_need"] = match.group(0)[:300]
                        break
        
        # 如果提取失败，使用默认生成
        if not result["purpose"]:
            arg_desc = ", ".join([f"{k}={v}" for k, v in list(tool_args.items())[:2]])
            result["purpose"] = f"使用 {tool_name} 查询 {arg_desc}"
        
        if not result["information_need"]:
            # 基于工具类型推断信息需求
            if "search" in tool_name.lower():
                result["information_need"] = f"搜索与 '{tool_args.get('query', '查询')}' 相关的文档和信息"
            elif "read" in tool_name.lower() or "open" in tool_name.lower():
                result["information_need"] = f"读取文件 '{tool_args.get('path', '指定路径')}' 的内容"
            else:
                result["information_need"] = f"获取 {tool_name} 的执行结果"
        
        return result
    
    def _get_available_artifact_ids(self) -> List[str]:
        """获取当前可用的 artifact ID 列表"""
        return list(self.artifact_store._store.keys())
    
    def _trigger_lazy_summary(self, messages: List[Dict[str, Any]], 
                              current_tokens: int) -> List[Dict[str, Any]]:
        """
        触发 Lazy Summarization
        
        当上下文超过阈值时：
        1. 大结果（已有 artifact）：生成摘要
        2. 中等结果（raw + artifact 备份）：替换为引用
        """
        if self._summary_triggered:
            return messages  # 已经触发过，避免重复
        
        logger.info(f"🔄 触发 Lazy Summarization (当前 {current_tokens} tokens > 阈值 {self.LAZY_SUMMARY_THRESHOLD})")
        
        # 统计处理数量
        summarized_count = 0
        compressed_count = 0
        
        # 遍历所有 tool 消息
        for i, msg in enumerate(messages):
            if msg.get("role") != "tool":
                continue
            
            art_id = msg.get("artifact_id")
            
            if not art_id:
                # 没有 artifact_id 的是小结果，跳过
                continue
            
            artifact = self.artifact_store.get(art_id)
            if not artifact:
                continue
            
            # 判断当前消息是 raw 还是引用
            content = msg.get("content", "")
            is_raw = len(content) > 500  # 引用消息通常很短
            
            if is_raw:
                # 中等结果：raw 内容，需要生成摘要并替换为引用
                if not artifact.summary:
                    # 先生成摘要
                    try:
                        meta = artifact.metadata
                        summary = self.artifact_summarizer.generate_summary(
                            content=artifact.content,
                            tool_name=meta.get("tool_name", "unknown"),
                            tool_purpose=meta.get("tool_purpose", ""),
                            user_query=self._current_user_query,
                            information_need=meta.get("information_need", "")
                        )
                        if summary:
                            artifact.summary = summary
                            logger.info(f"  ✅ {art_id}: 生成摘要 ({estimate_tokens(artifact.content)} → {estimate_tokens(summary)} tokens)")
                    except Exception as e:
                        logger.warning(f"  ⚠️ {art_id} 总结失败: {e}")
                        continue  # 总结失败，跳过
                
                # 替换为引用
                if artifact.summary:
                    tool_message = self.artifact_builder.build_tool_result_message(
                        tool_call_id=msg.get("tool_call_id"),
                        tool_name=artifact.metadata.get("tool_name", "unknown"),
                        artifact_id=art_id,
                        information_need=artifact.metadata.get("information_need", "")
                    )
                    messages[i] = tool_message
                    compressed_count += 1
                    logger.info(f"  📦 {art_id}: raw → 引用")
                    
            elif not artifact.summary:
                # 大结果：已经是引用，但还没有摘要，生成摘要
                try:
                    meta = artifact.metadata
                    summary = self.artifact_summarizer.generate_summary(
                        content=artifact.content,
                        tool_name=meta.get("tool_name", "unknown"),
                        tool_purpose=meta.get("tool_purpose", ""),
                        user_query=self._current_user_query,
                        information_need=meta.get("information_need", "")
                    )
                    if summary:
                        artifact.summary = summary
                        summarized_count += 1
                        logger.info(f"  ✅ {art_id}: 生成摘要")
                except Exception as e:
                    logger.warning(f"  ⚠️ {art_id} 总结失败: {e}")
        
        # 标记已触发
        self._summary_triggered = True
        
        # 添加系统提示
        if summarized_count > 0 or compressed_count > 0:
            summary_notice = (
                f"【系统提示】上下文已超过 {self.LAZY_SUMMARY_THRESHOLD} tokens，"
                f"已优化 {summarized_count} 个摘要，压缩 {compressed_count} 个工具结果。"
                f"如需查看完整内容，可使用 retrieve_artifact。"
            )
            messages.append({
                "role": "system",
                "content": summary_notice
            })
        
        return messages
    
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
        self._summary_triggered = False  # 重置 Lazy Summary 状态
        
        # 重置 ArtifactStore（每个任务独立）
        from app.agent.artifact_store import reset_artifact_store
        reset_artifact_store()
        self.artifact_store = get_artifact_store()
        self.artifact_builder = ArtifactMessageBuilder(self.artifact_store)
        self.artifact_summarizer = get_artifact_summarizer()
        self._tool_call_purposes = {}
        
        # 保存用户问题，用于生成针对性摘要
        self._current_user_query = query
        
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
            
            logger.info(f"📊 第 {iteration + 1} 轮上下文估算: {token_stats['total_tokens']} tokens (消息数: {token_stats['message_count']})")
            
            # 【Lazy Summarization】超过阈值触发批量总结
            if token_stats['total_tokens'] > self.LAZY_SUMMARY_THRESHOLD and not self._summary_triggered:
                messages = self._trigger_lazy_summary(messages, token_stats['total_tokens'])
                # 重新计算 token（因为添加了系统消息）
                token_stats = calculate_messages_tokens(messages)
            
            # 调用 LLM
            response = self.llm.chat(messages, tools=tools_schema)
            
            # 【关键】使用 LLM 返回的真实 token 统计更新
            real_usage = response.get("usage", {})
            real_prompt_tokens = real_usage.get("prompt_tokens", 0)
            real_completion_tokens = real_usage.get("completion_tokens", 0)
            real_total_tokens = real_usage.get("total_tokens", 0)
            cached_tokens = real_usage.get("cached_tokens", 0)
            cache_miss_tokens = real_usage.get("cache_miss_tokens", 0)
            
            # 更新统计历史（用真实值覆盖估算值）
            if self._token_stats_history:
                self._token_stats_history[-1]["real_prompt_tokens"] = real_prompt_tokens
                self._token_stats_history[-1]["real_completion_tokens"] = real_completion_tokens
                self._token_stats_history[-1]["cached_tokens"] = cached_tokens
                self._token_stats_history[-1]["cache_miss_tokens"] = cache_miss_tokens
            
            # 累计真实消耗
            self._total_tokens_consumed = real_total_tokens
            
            logger.info(f"📈 LLM 真实统计: prompt={real_prompt_tokens}, completion={real_completion_tokens}, cached={cached_tokens}, cache_miss={cache_miss_tokens}")
                    
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
                    
                    # 提取工具调用意图（目的 + 信息需求）
                    tool_intent = self._extract_tool_intent(
                        tool_name=tc["name"],
                        tool_args=tc["arguments"],
                        thinking=response.get("content", "")
                    )
                    tool_purpose = tool_intent["purpose"]
                    information_need = tool_intent["information_need"]
                    self._tool_call_purposes[tc["id"]] = tool_purpose
                    
                    logger.info(f"🎯 工具意图: {tool_purpose[:80]}...")
                    logger.info(f"📋 信息需求: {information_need[:80]}...")
                    
                    # 执行工具
                    result = self._execute_tool(tc["name"], tc["arguments"])
                    
                    # 构建结果内容
                    if result.success:
                        result_content = result.output
                        logger.info(f"✅ 工具返回成功，原始大小: {estimate_tokens(result_content)} tokens (~{len(result_content)} chars)")
                    else:
                        result_content = f"错误：{result.error}"
                        logger.warning(f"⚠️ 工具返回失败：{result.error}")
                    
                    # 【核心改进】根据 token 数决定处理策略
                    result_tokens = estimate_tokens(result_content)
                    
                    if result_tokens < self.RAW_THRESHOLD:
                        # 策略1：小结果 - 直接 raw，不存 artifact
                        tool_message = {
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": result_content
                        }
                        artifact_id = None
                        logger.info(f"📄 小结果直接进 context ({result_tokens} tokens, ~{len(result_content)} chars)")
                        
                    elif result_tokens < self.ARTIFACT_THRESHOLD:
                        # 策略2：中等结果 - raw 进 context + artifact 备份
                        artifact_id = self.artifact_store.save(
                            content=result_content,
                            artifact_type="tool_result",
                            metadata={
                                "tool_name": tc["name"],
                                "tool_args": tc["arguments"],
                                "tool_purpose": tool_purpose,
                                "information_need": information_need,
                                "success": result.success
                            }
                        )
                        # raw 进 context，但告知有 artifact 备份
                        tool_message = {
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": result_content,
                            "artifact_id": artifact_id  # 标记有备份
                        }
                        logger.info(f"📄 中等结果 raw + artifact 备份 ({result_tokens} tokens, ~{len(result_content)} chars, id: {artifact_id})")
                        
                    else:
                        # 策略3：大结果 - artifact + 轻量级引用
                        artifact_id = self.artifact_store.save(
                            content=result_content,
                            artifact_type="tool_result",
                            metadata={
                                "tool_name": tc["name"],
                                "tool_args": tc["arguments"],
                                "tool_purpose": tool_purpose,
                                "information_need": information_need,
                                "success": result.success
                            }
                        )
                        # 轻量级引用进 context
                        tool_message = self.artifact_builder.build_tool_result_message(
                            tool_call_id=tc["id"],
                            tool_name=tc["name"],
                            artifact_id=artifact_id,
                            information_need=information_need
                        )
                        logger.info(f"📦 大结果 artifact 化 ({result_tokens} tokens, ~{len(result_content)} chars → 引用, id: {artifact_id})")
                    
                    # 给前端显示用（仍显示原始内容）
                    yield {
                        "type": "tool_result",
                        "content": result_content,  # 前端仍显示完整内容
                        "tool_name": tc["name"],
                        "artifact_id": artifact_id  # 可能为 None（小结果）
                    }
                    
                    # 添加工具结果到消息
                    messages.append(tool_message)
                    
                    # 日志：显示处理结果
                    if artifact_id:
                        saved = estimate_tokens(result_content) - estimate_tokens(tool_message['content'])
                        if saved > 0:
                            logger.info(f"   💾 已节省 {saved} tokens ({saved/max(1,estimate_tokens(result_content))*100:.1f}%)")
            
            else:
                # 没有工具调用，说明 LLM 准备给出最终答案
                
                # 【关键】最后回答前，提示 LLM  retrieve 可能需要的 artifact
                artifact_ids = self._get_available_artifact_ids()
                if artifact_ids:
                    retrieval_hint = (
                        f"【系统提示】你即将给出最终答案。"
                        f"当前有 {len(artifact_ids)} 个已存储的工具结果可用：\n"
                        f"{', '.join(artifact_ids[:5])}{'...' if len(artifact_ids) > 5 else ''}\n\n"
                        f"如果你需要查看任何工具结果的完整内容来生成更准确的答案，"
                        f"请先调用 retrieve_artifact 获取，然后再给出最终答案。"
                    )
                    messages.append({"role": "system", "content": retrieval_hint})
                    
                    # 重新调用 LLM，让它有机会 retrieve
                    logger.info("🔄 注入 artifact 检索提示，重新调用 LLM...")
                    response = self.llm.chat(messages, tools=tools_schema)
                    
                    # 如果 LLM 选择 retrieve，继续循环
                    if response["tool_calls"]:
                        continue
                
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
