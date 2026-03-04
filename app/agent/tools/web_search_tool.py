"""
网络搜索工具 - 进行互联网信息检索
注意：需要配置搜索引擎 API（如 Serper、Google Custom Search 等）
"""
import requests
from typing import Any, Dict
from loguru import logger
from app.agent.tools.base import BaseTool, ToolResult
from app.core.config import settings


class WebSearchTool(BaseTool):
    """网络搜索工具"""
    
    def __init__(self, api_key: str = None, search_engine: str = "serper"):
        """
        初始化网络搜索工具
        
        Args:
            api_key: 搜索引擎 API 密钥，默认从环境变量读取 SERPER_API_KEY
            search_engine: 搜索引擎类型，目前支持 serper
        """
        self.api_key = api_key or getattr(settings, 'SERPER_API_KEY', None)
        self.search_engine = search_engine
        self.base_url = "https://google.serper.dev/search" if search_engine == "serper" else None
    
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
    
    def execute(self, query: str, num_results: int = 5) -> ToolResult:
        """执行网络搜索"""
        if not self.api_key:
            return ToolResult(
                success=False,
                output="",
                error="未配置搜索引擎 API 密钥。请在 .env 文件中设置 SERPER_API_KEY"
            )
        
        try:
            logger.info(f"网络搜索：{query}")
            
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
