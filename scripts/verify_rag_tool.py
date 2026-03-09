#!/usr/bin/env python3
"""
RAG工具验证脚本 - 全面检查RAG工具的各项功能
"""
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from loguru import logger
import json

def check_environment():
    """检查环境配置"""
    print("=" * 60)
    print("1. 环境配置检查")
    print("=" * 60)
    
    from app.core.config import settings
    
    checks = []
    
    # Qdrant配置
    print(f"\n📦 Qdrant配置:")
    print(f"   - Host: {settings.QDRANT_HOST}")
    print(f"   - Port: {settings.QDRANT_PORT}")
    print(f"   - Collection: {settings.QDRANT_COLLECTION_NAME}")
    
    # Embedding配置
    print(f"\n🔤 Embedding配置:")
    print(f"   - 使用API: {settings.USE_EMBEDDING_API}")
    print(f"   - 模型: {settings.EMBEDDING_MODEL_NAME}")
    print(f"   - 维度: {settings.EMBEDDING_DIM}")
    if settings.USE_EMBEDDING_API:
        has_key = settings.EMBEDDING_API_KEY and settings.EMBEDDING_API_KEY != "your_api_key_here"
        print(f"   - API Key: {'✅ 已配置' if has_key else '❌ 未配置'}")
        checks.append(("Embedding API Key", has_key))
        print(f"   - API URL: {settings.EMBEDDING_API_URL}")
    
    # Rerank配置
    print(f"\n🔄 Rerank配置:")
    print(f"   - 使用API: {settings.USE_RERANK_API}")
    print(f"   - 模型: {settings.RERANK_MODEL_NAME}")
    if settings.USE_RERANK_API:
        has_key = settings.RERANK_API_KEY and settings.RERANK_API_KEY != "your_api_key_here"
        print(f"   - API Key: {'✅ 已配置' if has_key else '❌ 未配置'}")
        checks.append(("Rerank API Key", has_key))
        print(f"   - API URL: {settings.RERANK_API_URL}")
    
    # LLM配置
    print(f"\n🤖 LLM配置:")
    has_llm_key = settings.LLM_API_KEY and settings.LLM_API_KEY != "your_api_key_here"
    print(f"   - API Key: {'✅ 已配置' if has_llm_key else '❌ 未配置'}")
    checks.append(("LLM API Key", has_llm_key))
    print(f"   - 模型: {settings.LLM_MODEL}")
    print(f"   - Base URL: {settings.LLM_BASE_URL}")
    
    return all(c[1] for c in checks)

def check_qdrant_connection():
    """检查Qdrant连接"""
    print("\n" + "=" * 60)
    print("2. Qdrant连接检查")
    print("=" * 60)
    
    try:
        from app.services.storage.qdrant_client import QdrantStorage
        storage = QdrantStorage()
        
        # 获取集合信息
        collections = storage.client.get_collections().collections
        collection_names = [c.name for c in collections]
        print(f"\n📊 可用集合: {collection_names}")
        
        from app.core.config import settings
        if settings.QDRANT_COLLECTION_NAME in collection_names:
            # 获取集合统计
            info = storage.client.get_collection(settings.QDRANT_COLLECTION_NAME)
            count = storage.client.count(settings.QDRANT_COLLECTION_NAME).count
            print(f"\n✅ 集合 '{settings.QDRANT_COLLECTION_NAME}' 存在")
            print(f"   - 向量维度: {info.config.params.vectors['dense'].size}")
            print(f"   - 文档数量: {count}")
            return True, count
        else:
            print(f"\n⚠️ 集合 '{settings.QDRANT_COLLECTION_NAME}' 不存在")
            print("   需要先运行数据摄取脚本: python scripts/ingest_folder.py")
            return False, 0
            
    except Exception as e:
        print(f"\n❌ Qdrant连接失败: {e}")
        print("   请检查:")
        print("   - Qdrant服务是否启动 (docker-compose up -d)")
        print("   - 配置中的QDRANT_HOST和QDRANT_PORT是否正确")
        return False, 0

def check_embedding():
    """检查Embedding功能"""
    print("\n" + "=" * 60)
    print("3. Embedding功能检查")
    print("=" * 60)
    
    try:
        from app.services.rag.embedder import HybridEmbedder
        embedder = HybridEmbedder()
        
        test_text = "这是一个测试文本"
        print(f"\n📝 测试文本: '{test_text}'")
        
        # 测试dense embedding
        print("\n   测试 Dense Embedding...")
        dense_vec = embedder.embed_dense(test_text)
        print(f"   ✅ Dense向量维度: {len(dense_vec)}")
        
        # 测试sparse embedding
        print("\n   测试 Sparse Embedding...")
        sparse_vec = embedder.embed_sparse(test_text)
        print(f"   ✅ Sparse向量 - 索引数: {len(sparse_vec['indices'])}, 值数: {len(sparse_vec['values'])}")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Embedding功能失败: {e}")
        return False

def check_query_rewriter():
    """检查查询改写功能"""
    print("\n" + "=" * 60)
    print("4. 查询改写功能检查")
    print("=" * 60)
    
    try:
        from app.services.rag.query_rewriter import QueryRewriter
        rewriter = QueryRewriter()
        
        test_query = "RK3506开发板调试方法"
        print(f"\n📝 测试查询: '{test_query}'")
        
        variations = rewriter.rewrite(test_query)
        print(f"\n✅ 查询改写结果 ({len(variations)} 个变体):")
        for i, v in enumerate(variations, 1):
            print(f"   {i}. {v}")
        
        return True
        
    except Exception as e:
        print(f"\n❌ 查询改写失败: {e}")
        return False

def check_reranker():
    """检查Rerank功能"""
    print("\n" + "=" * 60)
    print("5. Rerank功能检查")
    print("=" * 60)
    
    try:
        from app.services.rag.reranker import HybridReranker
        reranker = HybridReranker()
        
        test_query = "RK3506调试"
        test_passages = [
            {"id": 1, "payload": {"content": "RK3506是一款高性能处理器"}},
            {"id": 2, "payload": {"content": "调试RK3506需要使用JTAG接口"}},
            {"id": 3, "payload": {"content": "Linux内核编译方法"}}
        ]
        
        print(f"\n📝 测试查询: '{test_query}'")
        print(f"   测试文档数: {len(test_passages)}")
        
        results = reranker.rerank(test_query, test_passages, top_k=2)
        print(f"\n✅ Rerank结果 (Top 2):")
        for i, r in enumerate(results, 1):
            content = r.get("text", r.get("payload", {}).get("content", "N/A"))
            score = r.get("score", 0)
            print(f"   {i}. [得分: {score:.3f}] {content[:50]}...")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Rerank功能失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def check_rag_engine():
    """检查完整的RAG引擎"""
    print("\n" + "=" * 60)
    print("6. RAG引擎完整测试")
    print("=" * 60)
    
    try:
        from app.services.rag.retriever import RAGEngine
        
        print("\n🚀 初始化RAG引擎...")
        engine = RAGEngine()
        
        test_queries = [
            "RK3506调试方法",
            "服务器使用文档",
            "CMake使用指南"
        ]
        
        for query in test_queries:
            print(f"\n📝 测试查询: '{query}'")
            try:
                results = engine.search(query, top_k=3)
                print(f"   ✅ 返回 {len(results)} 条结果")
                for i, r in enumerate(results[:2], 1):
                    if isinstance(r, dict):
                        content = r.get("text", r.get("payload", {}).get("content", "N/A"))[:80]
                        score = r.get("score", 0)
                    else:
                        content = str(r)[:80]
                        score = 0
                    print(f"   {i}. [得分: {score:.3f}] {content}...")
            except Exception as e:
                print(f"   ❌ 查询失败: {e}")
        
        return True
        
    except Exception as e:
        print(f"\n❌ RAG引擎初始化失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def check_rag_tool():
    """检查RAG工具（Agent调用层）"""
    print("\n" + "=" * 60)
    print("7. RAG工具接口检查 (Agent层)")
    print("=" * 60)
    
    try:
        from app.agent.tools.rag_tool import RAGTool
        
        print("\n🚀 初始化RAG工具...")
        tool = RAGTool()
        
        print(f"\n📋 工具信息:")
        print(f"   - 名称: {tool.name}")
        print(f"   - 描述: {tool.description[:80]}...")
        
        test_query = "RK3506"
        print(f"\n📝 执行测试查询: '{test_query}'")
        
        result = tool.execute(query=test_query, top_k=3)
        
        print(f"\n✅ 执行结果:")
        print(f"   - 成功: {result.success}")
        if result.success:
            output_preview = result.output[:500] if len(result.output) > 500 else result.output
            print(f"   - 输出预览:\n{output_preview}")
            if len(result.output) > 500:
                print(f"   ... (共 {len(result.output)} 字符)")
        else:
            print(f"   - 错误: {result.error}")
        
        return result.success
        
    except Exception as e:
        print(f"\n❌ RAG工具执行失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def check_data_quality():
    """检查数据质量"""
    print("\n" + "=" * 60)
    print("8. 数据质量检查")
    print("=" * 60)
    
    from app.core.config import settings
    
    # 检查中间文件
    chunks_dir = Path(settings.DATA_CHUNKS_DIR)
    canonical_dir = Path(settings.DATA_CANONICAL_DIR)
    
    print(f"\n📁 数据目录检查:")
    
    if chunks_dir.exists():
        chunk_files = list(chunks_dir.glob("*_chunks.json"))
        print(f"   - Chunks文件: {len(chunk_files)} 个")
        if chunk_files:
            # 检查第一个文件的内容
            with open(chunk_files[0], 'r', encoding='utf-8') as f:
                data = json.load(f)
                print(f"   - 示例文件 '{chunk_files[0].name}':")
                print(f"     * 文档: {data.get('doc_id', 'N/A')}")
                print(f"     * 分片数: {len(data.get('chunks', []))}")
                if data.get('chunks'):
                    first_chunk = data['chunks'][0]
                    content_len = len(first_chunk.get('content', ''))
                    print(f"     * 首个分片长度: {content_len} 字符")
    else:
        print(f"   - Chunks目录不存在: {chunks_dir}")
    
    if canonical_dir.exists():
        md_files = list(canonical_dir.rglob("*.md"))
        print(f"   - Markdown文件: {len(md_files)} 个")
    else:
        print(f"   - Canonical目录不存在: {canonical_dir}")
    
    return True

def main():
    """主验证流程"""
    print("\n" + "🧪 " * 30)
    print("RAG工具全面验证")
    print("🧪 " * 30 + "\n")
    
    results = []
    
    # 1. 环境检查
    env_ok = check_environment()
    results.append(("环境配置", env_ok))
    
    # 2. Qdrant连接
    qdrant_ok, doc_count = check_qdrant_connection()
    results.append(("Qdrant连接", qdrant_ok))
    
    # 3. Embedding
    embedding_ok = check_embedding()
    results.append(("Embedding功能", embedding_ok))
    
    # 4. 查询改写
    rewriter_ok = check_query_rewriter()
    results.append(("查询改写", rewriter_ok))
    
    # 5. Rerank
    rerank_ok = check_reranker()
    results.append(("Rerank功能", rerank_ok))
    
    # 6. RAG引擎（需要Qdrant有数据）
    if doc_count > 0:
        engine_ok = check_rag_engine()
        results.append(("RAG引擎", engine_ok))
        
        # 7. RAG工具
        tool_ok = check_rag_tool()
        results.append(("RAG工具", tool_ok))
    else:
        print("\n⚠️ 跳过RAG引擎和工具测试（无数据）")
        results.append(("RAG引擎", False))
        results.append(("RAG工具", False))
    
    # 8. 数据质量
    data_ok = check_data_quality()
    results.append(("数据质量", data_ok))
    
    # 汇总
    print("\n" + "=" * 60)
    print("验证结果汇总")
    print("=" * 60)
    
    for name, ok in results:
        status = "✅ 通过" if ok else "❌ 失败"
        print(f"   {name}: {status}")
    
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    
    print(f"\n总计: {passed}/{total} 项通过")
    
    if passed == total:
        print("\n🎉 所有检查通过！RAG工具工作正常。")
    elif passed >= total * 0.7:
        print("\n⚠️ 部分检查未通过，但核心功能可能可用。")
    else:
        print("\n❌ 多项检查失败，请根据上述日志修复问题。")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
