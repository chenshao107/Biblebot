#!/usr/bin/env python3
"""
Agent 调试脚本 - 用于 VSCode 单步调试

用法:
    python scripts/debug_agent.py "你的查询问题"
    
在 VSCode 中:
    1. 打开 Run and Debug 面板 (Ctrl+Shift+D)
    2. 选择 "Debug: 直接调试 Agent (推荐)"
    3. 按 F5 启动调试
    4. 在以下关键位置打断点:
       - app/agent/agent.py:run_stream() - Agent 主循环
       - app/agent/agent.py:_execute_tool() - 工具执行
       - app/agent/llm.py:chat() - LLM 调用
"""
import sys
import os
import json
from datetime import datetime

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agent import Agent, get_default_tools
from app.agent.llm import LLMClient


def print_json(title: str, data: dict, max_length: int = 5000):
    """打印格式化的 JSON 调试信息"""
    print(f"\n{'─'*60}")
    print(f"📋 {title}")
    print(f"{'─'*60}")
    json_str = json.dumps(data, ensure_ascii=False, indent=2)
    if len(json_str) > max_length:
        print(json_str[:max_length] + f"\n... (截断，共 {len(json_str)} 字符)")
    else:
        print(json_str)


def debug_agent(query: str):
    """
    调试 Agent 执行流程 - 打印完整调试信息
    """
    print(f"\n{'='*60}")
    print(f"🐛 调试 Agent - {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'='*60}")
    print(f"Query: {query}")
    print(f"{'='*60}\n")
    
    # 初始化 Agent
    tools = get_default_tools()
    agent = Agent(tools=tools)
    
    print(f"✅ 已加载工具: {[t.name for t in tools]}")
    print(f"   最大迭代次数: {agent.max_iterations}")
    
    # 收集完整调试日志
    debug_log = {
        "query": query,
        "tools": [t.name for t in tools],
        "iterations": []
    }
    
    # 逐步执行
    step_count = 0
    current_iteration = {"steps": []}
    
    for step in agent.run_stream(query):
        step_count += 1
        step_type = step['type']
        
        print(f"\n{'='*60}")
        print(f"🔄 Step {step_count} [{step_type}]")
        print(f"{'='*60}")
        
        if step_type == 'thinking':
            print(f"💭 AI 思考:\n{step['content']}")
            current_iteration['steps'].append({
                "type": "thinking",
                "content": step['content']
            })
            
        elif step_type == 'tool_call':
            print(f"🔧 工具调用:")
            print(f"   名称: {step['tool_name']}")
            print_json("参数", step['tool_args'])
            current_iteration['tool_call'] = {
                "name": step['tool_name'],
                "args": step['tool_args']
            }
            
        elif step_type == 'tool_result':
            print(f"✅ 工具结果:")
            print(f"   工具: {step['tool_name']}")
            content = step['content']
            print_json("返回内容", {"content": content[:2000] if len(content) > 2000 else content})
            current_iteration['tool_result'] = {
                "name": step['tool_name'],
                "content": content[:1000]  # 日志中截断
            }
            
        elif step_type == 'final_answer':
            print(f"💡 最终答案:\n{step['content']}")
            debug_log['final_answer'] = step['content']
            if current_iteration['steps']:
                debug_log['iterations'].append(current_iteration)
            current_iteration = {"steps": []}
    
    # 打印完整调试摘要
    print(f"\n{'='*60}")
    print(f"📊 调试摘要")
    print(f"{'='*60}")
    print(f"总步数: {step_count}")
    print(f"迭代轮数: {len(debug_log['iterations'])}")
    
    # 保存调试日志到文件
    log_file = f"debug_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(log_file, 'w', encoding='utf-8') as f:
        json.dump(debug_log, f, ensure_ascii=False, indent=2)
    print(f"\n💾 完整调试日志已保存: {log_file}")
    
    print(f"\n{'='*60}")
    print(f"✅ 调试完成")
    print(f"{'='*60}")


if __name__ == "__main__":
    # 从命令行获取查询
    query = sys.argv[1] if len(sys.argv) > 1 else "Buildroot 如何配置 menuconfig？"
    debug_agent(query)
