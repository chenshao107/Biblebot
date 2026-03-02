# Professional RAG Server 开发与调试手册

本项目是一个工业级的 RAG（检索增强生成）系统框架，核心特点是支持 **多格式文档摄取**、**混合搜索 (Dense + Sparse)** 以及 **两阶段检索 (Recall + Rerank)**。

---

## 1. 项目目录结构

```text
my-rag-server/
├── app/
│   ├── api/                # API 层：FastAPI 路由定义
│   │   └── routes.py       # 定义 /rag/query 等接口
│   ├── core/               # 核心配置：Pydantic 环境校验
│   │   └── config.py       # 统一管理 .env 和默认值
│   ├── services/           # 业务逻辑层
│   │   ├── ingestion/      # 文档摄取管道
│   │   │   ├── converter.py# Docling 多格式转换逻辑
│   │   │   └── chunker.py  # Markdown 语义切片
│   │   ├── storage/        # 存储层
│   │   │   └── qdrant_client.py # Qdrant 混合索引与检索
│   │   └── rag/            # RAG 核心算法
│   │       ├── embedder.py # 稠密/稀疏向量生成 (支持 API/本地)
│   │       ├── query_rewriter.py # LLM 查询改写逻辑
│   │       ├── retriever.py# 检索编排（核心入口）
│   │       └── reranker.py # 结果精排 (支持 API/本地)
│   └── main.py             # 程序入口
├── data/                   # 数据存储
│   ├── raw/                # 原始文档存放处
│   └── canonical_md/       # 转换后的规范化 Markdown
├── docker/                 # 基础设施
│   └── docker-compose.yml  # Qdrant 容器配置
├── scripts/                # 运维脚本
│   └── ingest_folder.py    # 批量导入本地文档工具
└── .env                    # 环境配置文件（密钥存储）
```

---

## 2. 快速开发流程

### A. 环境准备
1. 启动向量数据库：`cd docker && docker-compose up -d`
2. 配置环境变量：修改 `.env` 中的 `LLM_API_KEY`。

### B. 导入数据 (Ingestion Phase)
将文件放入 `data/raw`，运行：
```bash
python scripts/ingest_folder.py
```
**调试技巧**：如果转换失败，查看 `data/canonical_md` 是否生成了中间文件，以判断是 Docling 转换问题还是切片逻辑问题。

### C. 启动服务 (Serving Phase)
```bash
python app/main.py
```
访问 `http://localhost:8000/docs` 即可通过交互式文档测试检索效果。

---

## 3. 核心调试建议

### 1. 检索效果不佳？
*   **查看改写结果**：在 `app/services/rag/query_rewriter.py` 中观察 LLM 是否正确理解了意图并生成了有效的扩展词。
*   **调节混合比例**：在 `app/services/storage/qdrant_client.py` 的 `search_hybrid` 方法中，我们使用了 RRF (Reciprocal Rank Fusion)。
*   **观察精排分数**：在 `app/services/rag/reranker.py` 中打印 `score`，看看模型是否把真正相关的片段排到了前面。

### 2. 性能瓶颈？
*   **本地 VS API**：如果你觉得启动慢或推理慢，请在 `.env` 中开启 `USE_EMBEDDING_API=True`，使用硅基流动等高性能 API 代替本地加载模型。

### 3. 增加新文档格式？
*   项目默认使用 Docling。如果需要处理特殊格式（如扫描件 OCR），只需在 `app/services/ingestion/converter.py` 中调整 `DocumentConverter` 的参数即可。

---


