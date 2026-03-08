#!/bin/bash
# RAG 数据清理脚本
# 用于清理中间文件和向量数据库，重新初始化环境

set -e

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DATA_DIR="$PROJECT_DIR/data"
QDRANT_HOST="localhost:6333"
COLLECTION_NAME="kb_hybrid"

echo "=========================================="
echo "RAG 数据清理工具"
echo "=========================================="
echo ""

# 1. 清理中间文件
echo "[1/4] 清理中间文件..."
rm -rf "$DATA_DIR"/chunks/*
rm -rf "$DATA_DIR"/embeddings/*
rm -rf "$DATA_DIR"/canonical_md/*/*
rm -rf "$DATA_DIR"/canonical_md/*
echo "  ✓ chunks/ 已清空"
echo "  ✓ embeddings/ 已清空"
echo "  ✓ canonical_md/ 已清空"
echo ""

# 2. 检查并清理 Qdrant 集合
echo "[2/4] 清理向量数据库..."
if curl -s "$QDRANT_HOST"/collections | grep -q "$COLLECTION_NAME"; then
    curl -s -X DELETE "$QDRANT_HOST"/collections/"$COLLECTION_NAME" > /dev/null
    echo "  ✓ Qdrant 集合 '$COLLECTION_NAME' 已删除"
else
    echo "  - Qdrant 集合 '$COLLECTION_NAME' 不存在，跳过"
fi
echo ""

# 3. 检查 Qdrant 容器状态
echo "[3/4] 检查 Qdrant 服务..."
if docker ps | grep -q qdrant; then
    echo "  ✓ Qdrant 容器运行正常"
else
    echo "  ⚠ Qdrant 容器未运行，尝试启动..."
    cd "$PROJECT_DIR/docker" && docker compose up -d qdrant 2>/dev/null || docker-compose up -d qdrant 2>/dev/null
    sleep 2
    if docker ps | grep -q qdrant; then
        echo "  ✓ Qdrant 容器已启动"
    else
        echo "  ✗ Qdrant 启动失败，请手动检查"
        exit 1
    fi
fi
echo ""

# 4. 显示清理结果
echo "[4/4] 清理完成"
echo ""
echo "------------------------------------------"
echo "当前状态:"
echo "  chunks 文件数: $(ls -1 "$DATA_DIR"/chunks/ 2>/dev/null | wc -l)"
echo "  embeddings 文件数: $(ls -1 "$DATA_DIR"/embeddings/ 2>/dev/null | wc -l)"
echo "  canonical_md 文件数: $(find "$DATA_DIR"/canonical_md/ -type f 2>/dev/null | wc -l)"
echo ""
echo "可以运行以下命令重新摄取数据:"
echo "  python scripts/ingest_folder.py"
echo "=========================================="
