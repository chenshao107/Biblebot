"""
网络搜索工具 - 进行互联网信息检索
支持 Tavily（推荐，专为LLM优化）和 Serper
"""
import requests
from typing import Any, Dict, List
from loguru import logger
from app.agent.tools.base import BaseTool, ToolResult
from app.core.config import settings


class WebSearchTool(BaseTool):
    """网络搜索工具 - 默认使用 Tavily API"""
    
    def __init__(self, api_key: str = None, search_engine: str = None):
        """
        初始化网络搜索工具
        
        Args:
            api_key: 搜索引擎 API 密钥，优先从环境变量读取
            search_engine: 搜索引擎类型，支持 "tavily"（默认）或 "serper"
        """
        # 自动检测搜索引擎
        self.search_engine = search_engine or self._detect_search_engine()
        
        if self.search_engine == "tavily":
            self.api_key = api_key or getattr(settings, 'TAVILY_API_KEY', None)
            self.base_url = "https://api.tavily.com/search"
        else:  # serper
            self.api_key = api_key or getattr(settings, 'SERPER_API_KEY', None)
            self.base_url = "https://google.serper.dev/search"
    
    def _detect_search_engine(self) -> str:
        """根据配置的环境变量自动检测搜索引擎"""
        if getattr(settings, 'TAVILY_API_KEY', None):
            return "tavily"
        elif getattr(settings, 'SERPER_API_KEY', None):
            return "serper"
        return "tavily"  # 默认优先 Tavily
    
    @property
    def name(self) -> str:
        return "web_search"
    
    @property
    def description(self) -> str:
        return """在互联网上搜索最新信息。适用于：
- 查询新闻、时事
- 获取最新的研究成果或产品发布
- 验证事实信息
- 查找特定网站或资源

返回搜索结果摘要和链接。注意：需要配置 API 密钥才能使用。"""
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索查询词"
                },
                "num_results": {
                    "type": "integer",
                    "description": "返回结果数量，默认 5",
                    "default": 5
                }
            },
            "required": ["query"]
        }
    
    def _search_tavily(self, query: str, num_results: int) -> ToolResult:
        """使用 Tavily API 搜索 - 专为 LLM 优化"""
        headers = {
            "Content-Type": "application/json"
        }
        
        payload = {
            "api_key": self.api_key,
            "query": query,
            "max_results": num_results,
            "search_depth": "basic",  # basic 或 advanced
            "include_answer": True,   # 返回 AI 生成的答案摘要
            "include_images": False,
            "include_raw_content": False
        }
        
        response = requests.post(
            self.base_url,
            json=payload,
            headers=headers,
            timeout=15
        )
        response.raise_for_status()
        
        results = response.json()
        
        # Tavily 返回格式
        answer = results.get("answer", "")
        results_list = results.get("results", [])
        
        output_parts = []
        
        # 如果有 AI 生成的答案，放在最前面
        if answer:
            output_parts.append(f"📋 智能摘要：\n{answer}\n")
        
        # 详细结果
        if results_list:
            output_parts.append("📎 详细来源：")
            for i, r in enumerate(results_list[:num_results], 1):
                title = r.get("title", "")
                url = r.get("url", "")
                content = r.get("content", "")
                
                output_parts.append(
                    f"\n[{i}] {title}\n"
                    f"链接：{url}\n"
                    f"内容：{content[:300]}..."
                )
        
        if not output_parts:
            return ToolResult(
                success=True,
                output="未找到相关结果。"
            )
        
        return ToolResult(
            success=True,
            output="\n".join(output_parts)
        )
    
    def _search_serper(self, query: str, num_results: int) -> ToolResult:
        """使用 Serper API 搜索"""
        headers = {
            "X-API-KEY": self.api_key,
            "Content-Type": "application/json"
        }
        
        payload = {
            "q": query,
            "num": num_results
        }
        
        response = requests.post(
            self.base_url,
            json=payload,
            headers=headers,
            timeout=10
        )
        response.raise_for_status()
        
        results = response.json()
        
        # 格式化输出
        output_parts = []
        organic_results = results.get("organic", [])
        
        for i, r in enumerate(organic_results[:num_results], 1):
            title = r.get("title", "")
            link = r.get("link", "")
            snippet = r.get("snippet", "")
            
            output_parts.append(
                f"[{i}] {title}\n"
                f"链接：{link}\n"
                f"摘要：{snippet}\n"
            )
        
        if not organic_results:
            return ToolResult(
                success=True,
                output="未找到相关结果。"
            )
        
        output = "\n---\n".join(output_parts)
        
        return ToolResult(
            success=True,
            output=f"找到 {len(organic_results)} 条结果:\n\n{output}"
        )
    
    def execute(self, query: str, num_results: int = 5) -> ToolResult:
        """执行网络搜索"""
        if not self.api_key:
            return ToolResult(
                success=False,
                output="",
                error=f"未配置搜索引擎 API 密钥。请在 .env 文件中设置 {self.search_engine.upper()}_API_KEY"
            )
        
        try:
            logger.info(f"网络搜索 [{self.search_engine}]：{query}")
            
            if self.search_engine == "tavily":
                return self._search_tavily(query, num_results)
            else:
                return self._search_serper(query, num_results)
            
        except requests.exceptions.RequestException as e:
            logger.error(f"网络搜索失败：{e}")
            return ToolResult(
                success=False,
                output="",
                error=f"搜索请求失败：{str(e)}"
            )
        except Exception as e:
            logger.error(f"网络搜索异常：{e}")
            return ToolResult(
                success=False,
                output="",
                error=str(e)
            )
