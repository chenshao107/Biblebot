"""
LLM 调用封装 - 支持 function calling
"""
import requests
import json
import os
from datetime import datetime
from typing import List, Dict, Any, Optional
from loguru import logger
from app.core.config import settings


class LLMClient:
    """LLM 客户端，支持 function calling"""
    
    def __init__(self):
        self.api_key = settings.LLM_API_KEY
        self.base_url = settings.LLM_BASE_URL
        self.model = settings.LLM_MODEL
        self.debug_llm = settings.DEBUG_LLM_API
        self.debug_log_dir = settings.DEBUG_LLM_LOG_DIR
        self._call_count = 0
    
    def _save_debug_log(self, payload: dict, response: dict):
        """保存 LLM API 调用日志到文件"""
        if not self.debug_llm:
            return
        
        try:
            # 创建日志目录
            os.makedirs(self.debug_log_dir, exist_ok=True)
            
            self._call_count += 1
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{self.debug_log_dir}/llm_call_{timestamp}_{self._call_count:03d}.json"
            
            log_data = {
                "timestamp": datetime.now().isoformat(),
                "call_count": self._call_count,
                "model": self.model,
                "request": payload,
                "response": response
            }
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(log_data, f, ensure_ascii=False, indent=2)
            
            logger.debug(f"LLM 调试日志已保存: {filename}")
        except Exception as e:
            logger.warning(f"保存 LLM 调试日志失败: {e}")
    
    def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.7
    ) -> Dict[str, Any]:
        """
        调用 LLM，支持工具调用
        
        Args:
            messages: 对话历史
            tools: 可用工具列表（OpenAI function calling 格式）
            temperature: 温度参数
            
        Returns:
            LLM 响应，包含 content 或 tool_calls
        """
        if not self.api_key or self.api_key.startswith("sk-XXXX"):
            raise ValueError("LLM_API_KEY 未配置，请在 .env 文件中设置")
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        
        # 添加工具（如果有）
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        
        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers,
                timeout=120
            )
            response.raise_for_status()
            
            result = response.json()
            choice = result["choices"][0]
            message = choice["message"]
            
            # 提取 usage 信息（真实 token 统计）
            usage = result.get("usage", {})
            
            response_data = {
                "content": message.get("content"),
                "tool_calls": message.get("tool_calls"),
                "finish_reason": choice.get("finish_reason"),
                # Token 统计（来自 LLM API 真实值）
                "usage": {
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0),
                    "cached_tokens": usage.get("prompt_tokens_details", {}).get("cached_tokens", 0),
                    "cache_miss_tokens": usage.get("prompt_cache_miss_tokens", usage.get("prompt_tokens", 0))
                }
            }
            
            # 保存调试日志
            self._save_debug_log(payload, result)
            
            return response_data
            
        except requests.exceptions.RequestException as e:
            logger.error(f"LLM API 调用失败: {e}")
            raise
    
    def parse_tool_calls(self, tool_calls: List[Dict]) -> List[Dict[str, Any]]:
        """解析工具调用"""
        parsed = []
        for tc in tool_calls:
            parsed.append({
                "id": tc["id"],
                "name": tc["function"]["name"],
                "arguments": json.loads(tc["function"]["arguments"])
            })
        return parsed
