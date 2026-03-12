#!/usr/bin/env python3
"""
测试 RAG 的 category_filter 功能
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from app.agent.tools.rag_tool import RAGTool


def test_rag_filter():
    """测试 RAG 过滤功能"""
    print("=" * 60)
    print("测试 RAG category_filter 功能")
    print("=" * 60)
    
    tool = RAGTool()
    
    test_cases = [
        {
            "name": "不加 filter（全局搜索）",
            "query": "U-Boot 编译",
            "top_k": 3,
            "category_filter": None
        },
        {
            "name": "filter='RK3506'（只搜 RK3506）",
            "query": "U-Boot 编译",
            "top_k": 3,
            "category_filter": "RK3506"
        },
        {
            "name": "filter='SSD212'（只搜 SSD212）",
            "query": "U-Boot 编译",
            "top_k": 3,
            "category_filter": "SSD212"
        },
        {
            "name": "filter='公司规章制度'（只搜规章制度）",
            "query": "报销",
            "top_k": 3,
            "category_filter": "公司规章制度"
        },
        {
            "name": "filter='RK3506/uboot'（子目录过滤）",
            "query": "编译步骤",
            "top_k": 3,
            "category_filter": "RK3506/uboot"
        },
    ]
    
    for case in test_cases:
        print(f"\n{'='*60}")
        print(f"测试: {case['name']}")
        print(f"查询: {case['query']}")
        print(f"Filter: {case['category_filter']}")
        print("-" * 60)
        
        result = tool.execute(
            query=case['query'],
            top_k=case['top_k'],
            category_filter=case['category_filter']
        )
        
        if result.success:
            # 只显示前 800 字符
            output = result.output[:800] + "..." if len(result.output) > 800 else result.output
            print(output)
        else:
            print(f"❌ 错误: {result.error}")


if __name__ == "__main__":
    test_rag_filter()
