#!/usr/bin/env python3
"""
验证数据路径一致性测试
检查所有组件是否都使用 canonical_md 路径
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from app.core.config import settings


def check_paths():
    """检查所有相关路径配置"""
    print("=" * 60)
    print("数据路径一致性检查")
    print("=" * 60)
    
    print("\n📁 配置路径:")
    print(f"  DATA_RAW_DIR:       {settings.DATA_RAW_DIR}")
    print(f"  DATA_CANONICAL_DIR: {settings.DATA_CANONICAL_DIR}")
    print(f"  DATA_CHUNKS_DIR:    {settings.DATA_CHUNKS_DIR}")
    
    print("\n📂 实际目录状态:")
    paths = {
        "raw": Path(settings.DATA_RAW_DIR),
        "canonical_md": Path(settings.DATA_CANONICAL_DIR),
        "chunks": Path(settings.DATA_CHUNKS_DIR),
    }
    
    for name, path in paths.items():
        exists = "✅ 存在" if path.exists() else "❌ 不存在"
        file_count = len(list(path.rglob("*"))) if path.exists() else 0
        print(f"  {name:12} {exists:8} ({file_count} 个文件/目录)")
    
    print("\n📄 canonical_md 中的文件:")
    canonical_path = Path(settings.DATA_CANONICAL_DIR)
    if canonical_path.exists():
        md_files = list(canonical_path.rglob("*.md"))
        for f in md_files[:10]:  # 只显示前10个
            rel_path = f.relative_to(canonical_path)
            print(f"  - {rel_path}")
        if len(md_files) > 10:
            print(f"  ... 还有 {len(md_files) - 10} 个文件")
    
    print("\n🔍 路径一致性验证:")
    # 检查 chunk 文件中的路径
    chunks_path = Path(settings.DATA_CHUNKS_DIR)
    if chunks_path.exists():
        chunk_files = list(chunks_path.glob("*_chunks.json"))
        if chunk_files:
            import json
            with open(chunk_files[0], 'r') as f:
                data = json.load(f)
            doc_id = data.get('doc_id', 'N/A')
            print(f"  Chunk 文件示例 doc_id: {doc_id}")
            if doc_id.endswith('.md'):
                print("  ✅ doc_id 使用 .md 扩展名")
            else:
                print("  ⚠️  doc_id 未使用 .md 扩展名")


def verify_no_pdf_exposure():
    """验证 AI 不会接触到 PDF 路径"""
    print("\n" + "=" * 60)
    print("PDF 隔离验证")
    print("=" * 60)
    
    # 检查 chunk 元数据
    chunks_path = Path(settings.DATA_CHUNKS_DIR)
    if not chunks_path.exists():
        print("  无 chunk 文件，请先运行 ingest_folder.py")
        return
    
    chunk_files = list(chunks_path.glob("*_chunks.json"))
    if not chunk_files:
        print("  无 chunk 文件")
        return
    
    import json
    
    pdf_found = False
    for chunk_file in chunk_files[:5]:  # 检查前5个文件
        with open(chunk_file, 'r') as f:
            data = json.load(f)
        
        doc_id = data.get('doc_id', '')
        full_path = data.get('chunks', [{}])[0].get('metadata', {}).get('full_path', '')
        
        if '.pdf' in doc_id.lower() or '.pdf' in full_path.lower():
            print(f"  ❌ 发现 PDF 路径: {doc_id}")
            pdf_found = True
    
    if not pdf_found:
        print("  ✅ 未在 chunk 元数据中发现 PDF 路径")
        print("  ✅ AI 只会看到 .md 文件路径")


def test_section_index():
    """测试章节索引"""
    print("\n" + "=" * 60)
    print("章节索引验证")
    print("=" * 60)
    
    index_path = Path(settings.DATA_CANONICAL_DIR) / "section_index.json"
    
    if not index_path.exists():
        print(f"  ❌ 章节索引不存在: {index_path}")
        print("  请先运行 ingest_folder.py 构建索引")
        return
    
    import json
    with open(index_path, 'r') as f:
        index = json.load(f)
    
    total_files = index.get('total_files', 0)
    files = index.get('files', {})
    
    print(f"  ✅ 索引文件存在: {index_path}")
    print(f"  📊 索引文件数: {total_files}")
    
    # 检查索引中的文件路径
    pdf_in_index = False
    for file_path in list(files.keys())[:5]:
        print(f"  - {file_path}")
        if '.pdf' in file_path.lower():
            pdf_in_index = True
    
    if pdf_in_index:
        print("  ⚠️  索引中发现 PDF 路径")
    else:
        print("  ✅ 索引中无 PDF 路径")


if __name__ == "__main__":
    check_paths()
    verify_no_pdf_exposure()
    test_section_index()
    
    print("\n" + "=" * 60)
    print("检查完成")
    print("=" * 60)
