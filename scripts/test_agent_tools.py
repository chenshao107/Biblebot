#!/usr/bin/env python3
"""
测试 Agent 工具（Bash、Python、Section 等）
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from app.agent.tools import get_default_tools, get_tool_by_name


def test_bash_tool():
    """测试 Bash 工具"""
    print("=" * 60)
    print("测试 Bash 工具")
    print("=" * 60)
    
    try:
        tool = get_tool_by_name("bash")
        
        # 测试列出目录
        print("\n1. 列出 canonical_md 目录:")
        result = tool.execute("ls -la")
        print(result.output[:500] if result.success else result.error)
        
        # 测试搜索 markdown 文件
        print("\n2. 搜索 Markdown 文件:")
        result = tool.execute('find . -name "*.md" | head -10')
        print(result.output if result.success else result.error)
        
        # 测试读取文件
        print("\n3. 读取测试文件:")
        result = tool.execute("head -20 RK3506/uboot/编译指南.md")
        print(result.output if result.success else result.error)
        
    except Exception as e:
        print(f"❌ Bash 工具测试失败: {e}")


def test_python_tool():
    """测试 Python 工具"""
    print("\n" + "=" * 60)
    print("测试 Python 工具")
    print("=" * 60)
    
    try:
        tool = get_tool_by_name("python")
        
        # 测试读取文件
        print("\n1. 读取并解析 Markdown 文件:")
        code = """
from pathlib import Path

# 读取文件
file_path = Path("RK3506/uboot/编译指南.md")
if file_path.exists():
    content = file_path.read_text(encoding='utf-8')
    lines = content.split('\\n')
    print(f"文件: {file_path}")
    print(f"总行数: {len(lines)}")
    print(f"前5行:")
    for i, line in enumerate(lines[:5], 1):
        print(f"  {i}: {line}")
else:
    print(f"文件不存在: {file_path}")
"""
        result = tool.execute(code)
        print(result.output if result.success else result.error)
        
        # 测试数据分析
        print("\n2. 简单数据分析:")
        code = """
import json

# 模拟数据分析
data = {"files": ["a.md", "b.md", "c.md"], "count": 3}
print(f"文件数量: {data['count']}")
print(f"文件列表: {', '.join(data['files'])}")
"""
        result = tool.execute(code)
        print(result.output if result.success else result.error)
        
    except Exception as e:
        print(f"❌ Python 工具测试失败: {e}")


def test_section_tools():
    """测试章节工具"""
    print("\n" + "=" * 60)
    print("测试 Section 工具")
    print("=" * 60)
    
    try:
        # 测试 list_sections
        print("\n1. list_sections 工具:")
        tool = get_tool_by_name("list_sections")
        result = tool.execute("RK3506/uboot/编译指南.md")
        print(result.output if result.success else result.error)
        
        # 测试 read_section
        print("\n2. read_section 工具:")
        tool = get_tool_by_name("read_section")
        result = tool.execute("RK3506/uboot/编译指南.md", "## 编译步骤")
        output = result.output[:600] + "..." if len(result.output) > 600 else result.output
        print(output if result.success else result.error)
        
    except Exception as e:
        print(f"❌ Section 工具测试失败: {e}")


def test_rag_tool():
    """测试 RAG 工具"""
    print("\n" + "=" * 60)
    print("测试 RAG 工具")
    print("=" * 60)
    
    try:
        tool = get_tool_by_name("rag")
        
        print("\n1. 基本搜索:")
        result = tool.execute("U-Boot 编译", top_k=2)
        output = result.output[:600] + "..." if len(result.output) > 600 else result.output
        print(output if result.success else result.error)
        
        print("\n2. 带 filter 搜索:")
        result = tool.execute("U-Boot 编译", top_k=2, category_filter="RK3506")
        output = result.output[:600] + "..." if len(result.output) > 600 else result.output
        print(output if result.success else result.error)
        
    except Exception as e:
        print(f"❌ RAG 工具测试失败: {e}")


def list_all_tools():
    """列出所有可用工具"""
    print("=" * 60)
    print("所有可用工具")
    print("=" * 60)
    
    tools = get_default_tools()
    
    print(f"\n共 {len(tools)} 个工具:\n")
    
    for tool in tools:
        print(f"🔧 {tool.name}")
        print(f"   描述: {tool.description[:80]}...")
        print()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="测试 Agent 工具")
    parser.add_argument("--tool", choices=["bash", "python", "section", "rag", "all", "list"],
                       default="all", help="要测试的工具")
    args = parser.parse_args()
    
    if args.tool == "list":
        list_all_tools()
    elif args.tool == "bash":
        test_bash_tool()
    elif args.tool == "python":
        test_python_tool()
    elif args.tool == "section":
        test_section_tools()
    elif args.tool == "rag":
        test_rag_tool()
    else:
        list_all_tools()
        test_bash_tool()
        test_python_tool()
        test_section_tools()
        test_rag_tool()
