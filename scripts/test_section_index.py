#!/usr/bin/env python3
"""
测试章节索引功能
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from app.services.ingestion.section_indexer import get_indexer
from app.core.config import settings


def test_list_sections():
    """测试列出章节"""
    print("=" * 60)
    print("测试 list_sections")
    print("=" * 60)
    
    indexer = get_indexer()
    
    # 测试文件路径
    test_files = [
        "RK3506/uboot/编译指南.md",
        "公司规章制度/人事部/考勤制度.md",
    ]
    
    for file_path in test_files:
        print(f"\n📄 {file_path}")
        print("-" * 40)
        
        sections = indexer.list_sections(file_path)
        if not sections:
            print("  未找到章节索引")
            continue
        
        for i, section in enumerate(sections, 1):
            level = section['level']
            title = section['title']
            start = section['start_line']
            end = section['end_line']
            indent = "  " * (level - 1)
            print(f"  {i}. {indent}{title} (lines {start}-{end})")


def test_read_section():
    """测试读取章节内容"""
    print("\n" + "=" * 60)
    print("测试 read_section")
    print("=" * 60)
    
    indexer = get_indexer()
    
    # 测试读取特定章节
    test_cases = [
        ("RK3506/uboot/编译指南.md", "## 编译步骤"),
        ("公司规章制度/人事部/考勤制度.md", "## 请假流程"),
    ]
    
    for file_path, section_title in test_cases:
        print(f"\n📄 {file_path}")
        print(f"📌 {section_title}")
        print("-" * 40)
        
        # 读取完整文件内容
        full_path = Path(settings.DATA_CANONICAL_DIR) / file_path
        if not full_path.exists():
            print(f"  文件不存在: {file_path}")
            continue
        
        with open(full_path, 'r', encoding='utf-8') as f:
            md_content = f.read()
        
        # 获取章节内容
        result = indexer.get_section_content(file_path, section_title, md_content)
        if result:
            content = result['content'][:300] + "..." if len(result['content']) > 300 else result['content']
            print(f"  行号: {result['start_line']}-{result['end_line']}")
            print(f"  内容:\n{content}")
        else:
            print("  章节未找到")


def show_index_stats():
    """显示索引统计"""
    print("\n" + "=" * 60)
    print("章节索引统计")
    print("=" * 60)
    
    indexer = get_indexer()
    
    if not indexer.index:
        print("索引为空，请先运行 ingest_folder.py 构建索引")
        return
    
    print(f"总文件数: {len(indexer.index)}")
    print("\n文件列表:")
    
    for file_path, file_info in indexer.index.items():
        section_count = file_info.get('section_count', 0)
        total_lines = file_info.get('total_lines', 0)
        print(f"  - {file_path}: {section_count} 章节, {total_lines} 行")


if __name__ == "__main__":
    show_index_stats()
    test_list_sections()
    test_read_section()
