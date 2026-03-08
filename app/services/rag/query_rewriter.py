import requests
from typing import List
from loguru import logger
from app.core.config import settings

class QueryRewriter:
    def __init__(self):
        self.api_key = settings.LLM_API_KEY
        self.base_url = settings.LLM_BASE_URL
        self.model = settings.LLM_MODEL

    def rewrite(self, query: str) -> List[str]:
        """
        Uses LLM to expand/rewrite the query into multiple variations.
        If API key is missing, returns the original query as a list.
        """
        if not self.api_key or self.api_key == "your_api_key_here":
            logger.warning("LLM_API_KEY not configured. Skipping query rewriting.")
            return [query]

        prompt = f"""你是一个搜索专家。请将用户查询改写为4个不同的搜索变体，以提高在英文技术文档中的召回率。

改写策略：
1. 保留原查询的中文表达
2. 生成英文关键词（技术文档通常是英文）
3. 提取核心命令/术语（如 menuconfig, make, config）
4. 生成同义词/相关术语

请直接输出改写后的内容，每行一个，不要包含序号、解释或多余内容。

用户查询: {query}
"""
        
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3
            }
            
            response = requests.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
            response.raise_for_status()
            
            content = response.json()['choices'][0]['message']['content']
            variations = [v.strip() for v in content.split('\n') if v.strip()]
            
            # Ensure the original query is included
            if query not in variations:
                variations.append(query)
                
            logger.info(f"Query expanded into: {variations}")
            return variations
            
        except Exception as e:
            logger.error(f"Error during query rewriting: {e}")
            return [query]
