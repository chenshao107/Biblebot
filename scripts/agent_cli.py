#!/usr/bin/env python3
"""
Agent CLI - 命令行交互式测试
"""
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.agent import Agent, get_default_tools
from loguru import logger


def main():
    print("=" * 60)
    print("Knowledge Agent CLI")
    print("=" * 60)
    print("\n可用工具:")
    print("  - search_knowledge: RAG 知识库检索")
    print("  - run_bash: 执行 bash 命令探索文件")
    print("  - run_python: 执行 Python 代码")
    print("  - web_search: 互联网搜索（需配置 API key）")
    print("  - calculator: 数学计算器")
    print("\n输入 'quit' 或 'exit' 退出\n")
    
    # 初始化 Agent
    logger.info("初始化 Agent...")
    agent = Agent(tools=get_default_tools())
    logger.info("Agent 初始化完成")
    
    print("-" * 60)
    
    while True:
        try:
            query = input("\n你: ").strip()
            
            if not query:
                continue
            
            if query.lower() in ("quit", "exit", "q"):
                print("再见！")
                break
            
            print("\nAgent 正在思考...\n")
            
            # 运行 Agent 并打印每一步
            for step in agent.run_stream(query):
                step_type = step["type"]
                content = step["content"]
                
                if step_type == "thinking":
                    print(f"\n🤔 [思考] {content}")
                elif step_type == "tool_call":
                    tool_name = step.get("tool_name", "")
                    tool_args = step.get("tool_args", {})
                    print(f"\n📞 [调用工具] {tool_name}")
                    print(f"  参数：{tool_args}")
                elif step_type == "tool_result":
                    # 截断过长的输出
                    if len(content) > 500:
                        content = content[:500] + "...(截断)"
                    print(f"\n✅ [工具结果]\n{content}")
                elif step_type == "final_answer":
                    print(f"\n{'='*40}")
                    print(f"💡 [最终答案]\n{content}")
                    print(f"{'='*40}")
            
        except KeyboardInterrupt:
            print("\n\n收到中断信号，退出...")
            break
        except Exception as e:
            print(f"\n错误: {e}")
            logger.exception("Agent 执行出错")


if __name__ == "__main__":
    main()
