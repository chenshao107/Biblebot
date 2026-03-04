#!/usr/bin/env python3
"""
Agent 架构验证脚本
检查所有组件是否正确配置和导入
"""
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def check_imports():
    """检查所有模块是否可以正常导入"""
    print("=" * 60)
    print("检查模块导入...")
    print("=" * 60)
    
    imports_to_check = [
        ("app.agent", "Agent"),
        ("app.agent", "get_default_tools"),
        ("app.agent.tools", "RAGTool"),
        ("app.agent.tools", "BashTool"),
        ("app.agent.tools", "PythonTool"),
        ("app.agent.tools", "WebSearchTool"),
        ("app.agent.tools", "CalculatorTool"),
        ("app.agent.tools", "register_tool"),
        ("app.core.config", "settings"),
    ]
    
    success_count = 0
    failed_count = 0
    
    for module_name, symbol in imports_to_check:
        try:
            module = __import__(module_name, fromlist=[symbol])
            getattr(module, symbol)
            print(f"✅ {module_name}.{symbol}")
            success_count += 1
        except Exception as e:
            print(f"❌ {module_name}.{symbol}: {e}")
            failed_count += 1
    
    print(f"\n导入检查：{success_count} 成功，{failed_count} 失败\n")
    return failed_count == 0


def check_tools():
    """检查工具是否可以实例化"""
    print("=" * 60)
    print("检查工具实例化...")
    print("=" * 60)
    
    from app.agent.tools import (
        RAGTool, BashTool, PythonTool, 
        WebSearchTool, CalculatorTool
    )
    
    tools_to_check = [
        ("RAGTool", RAGTool),
        ("BashTool", BashTool),
        ("PythonTool", PythonTool),
        ("WebSearchTool", WebSearchTool),
        ("CalculatorTool", CalculatorTool),
    ]
    
    success_count = 0
    failed_count = 0
    
    for name, tool_class in tools_to_check:
        try:
            tool = tool_class()
            print(f"✅ {name}: name='{tool.name}'")
            success_count += 1
        except Exception as e:
            print(f"❌ {name}: {e}")
            failed_count += 1
    
    print(f"\n工具检查：{success_count} 成功，{failed_count} 失败\n")
    return failed_count == 0


def check_config():
    """检查配置是否正确加载"""
    print("=" * 60)
    print("检查配置加载...")
    print("=" * 60)
    
    try:
        from app.core.config import settings
        
        config_items = [
            ("AGENT_MAX_ITERATIONS", settings.AGENT_MAX_ITERATIONS),
            ("BASH_TOOL_TIMEOUT", settings.BASH_TOOL_TIMEOUT),
            ("PYTHON_TOOL_TIMEOUT", settings.PYTHON_TOOL_TIMEOUT),
            ("LLM_MODEL", settings.LLM_MODEL),
        ]
        
        for name, value in config_items:
            print(f"✅ {name} = {value}")
        
        print("\n配置检查：成功\n")
        return True
        
    except Exception as e:
        print(f"❌ 配置加载失败：{e}")
        print("\n配置检查：失败\n")
        return False


def check_agent_creation():
    """检查 Agent 是否可以创建"""
    print("=" * 60)
    print("检查 Agent 创建...")
    print("=" * 60)
    
    try:
        from app.agent import Agent, get_default_tools
        
        tools = get_default_tools()
        agent = Agent(tools=tools)
        
        print(f"✅ Agent 创建成功")
        print(f"   - 工具数量：{len(agent.tools)}")
        print(f"   - 可用工具：{list(agent.tools.keys())}")
        print(f"   - 最大迭代次数：{agent.max_iterations}")
        print("\nAgent 检查：成功\n")
        return True
        
    except Exception as e:
        print(f"❌ Agent 创建失败：{e}")
        print("\nAgent 检查：失败\n")
        return False


def check_calculator():
    """测试计算器工具（快速功能验证）"""
    print("=" * 60)
    print("测试计算器工具（快速功能验证）...")
    print("=" * 60)
    
    try:
        from app.agent.tools import CalculatorTool
        
        tool = CalculatorTool()
        result = tool.execute(expression="2 + 3 * 4")
        
        if result.success and "14" in result.output:
            print(f"✅ 计算器测试通过：2 + 3 * 4 = 14")
            print("\n功能测试：成功\n")
            return True
        else:
            print(f"❌ 计算器测试结果异常：{result.output}")
            print("\n功能测试：失败\n")
            return False
            
    except Exception as e:
        print(f"❌ 计算器测试失败：{e}")
        print("\n功能测试：失败\n")
        return False


def main():
    """运行所有检查"""
    print("\n")
    print("╔" + "=" * 58 + "╗")
    print("║" + " " * 15 + "Agent 架构验证脚本" + " " * 15 + "║")
    print("╚" + "=" * 58 + "╝")
    print("\n")
    
    checks = [
        ("模块导入", check_imports),
        ("工具实例化", check_tools),
        ("配置加载", check_config),
        ("Agent 创建", check_agent_creation),
        ("功能测试", check_calculator),
    ]
    
    results = []
    for name, check_func in checks:
        try:
            result = check_func()
            results.append((name, result))
        except Exception as e:
            print(f"❌ {name} 检查过程中发生严重错误：{e}\n")
            results.append((name, False))
    
    # 汇总结果
    print("=" * 60)
    print("验证结果汇总")
    print("=" * 60)
    
    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{status} - {name}")
    
    all_passed = all(result for _, result in results)
    
    print("\n" + "=" * 60)
    if all_passed:
        print("🎉 所有检查通过！Agent 架构已正确配置。")
    else:
        print("⚠️  部分检查未通过，请查看上面的详细信息。")
    print("=" * 60)
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
