#!/usr/bin/env python3
"""
测试 RAG 工具的 category_filter 参数效果
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))

from app.agent.tools.rag_tool import RAGTool

def test_filter():
    tool = RAGTool()
    
    print("=" * 60)
    print("测试 1: 不加 filter，搜索 'U-Boot 编译'")
    print("=" * 60)
    result1 = tool.execute(query="U-Boot 编译步骤", top_k=10)
    print(result1.output[:1500] if result1.success else result1.error)
    
    print("\n" + "=" * 60)
    print("测试 2: 加 filter='RK3506'，搜索 'U-Boot 编译'")
    print("=" * 60)
    result2 = tool.execute(query="U-Boot 编译步骤", top_k=10, category_filter="RK3506")
    print(result2.output[:1500] if result2.success else result2.error)
    
    print("\n" + "=" * 60)
    print("测试 3: 加 filter='SSD212'，搜索 'U-Boot 编译'")
    print("=" * 60)
    result3 = tool.execute(query="U-Boot 编译步骤", top_k=10, category_filter="SSD212")
    print(result3.output[:1500] if result3.success else result3.error)
    
    print("\n" + "=" * 60)
    print("测试 4: 加 filter='公司规章制度'，搜索 '报销'")
    print("=" * 60)
    result4 = tool.execute(query="报销流程", top_k=10, category_filter="公司规章制度")
    print(result4.output[:1500] if result4.success else result4.error)
    
    print("\n" + "=" * 60)
    print("测试 5: 加 filter='RK3506/uboot'，搜索 '编译'")
    print("=" * 60)
    result5 = tool.execute(query="编译步骤", top_k=10, category_filter="RK3506/uboot")
    print(result5.output[:1500] if result5.success else result5.error)

if __name__ == "__main__":
    test_filter()
