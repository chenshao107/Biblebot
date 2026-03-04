"""
LLM 调用封装 - 支持 function calling
"""
import requests
import json
from typing import List, Dict, Any, Optional
from loguru import logger
from app.core.config import settings


class LLMClient:
    """LLM 客户端，支持 function calling"""
    
    def __init__(self):
        self.api_key = settings.LLM_API_KEY
        self.base_url = settings.LLM_BASE_URL
        self.model = settings.LLM_MODEL
    
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
            
            return {
                "content": message.get("content"),
                "tool_calls": message.get("tool_calls"),
                "finish_reason": choice.get("finish_reason")
            }
            
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
