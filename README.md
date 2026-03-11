# Professional BiboBot 开发与调试手册

本项目是一个工业级的 RAG（检索增强生成）系统框架，核心特点是支持 **多格式文档摄取**、**混合搜索 (Dense + Sparse)**、**两阶段检索 (Recall + Rerank)** 以及 **智能 Agent 知识服务**。

## 🌟 核心功能

- 🔍 **RAG 检索**: 混合向量搜索 + 查询改写 + 结果重排
- 🤖 **AI Agent**: LLM + 工具调用（RAG/Bash/Python/Web Search）
- 📄 **多格式支持**: PDF/Word/Excel/PPT/Markdown 等通过 Docling 转换
- 🛡️ **安全机制**: Bash 命令白名单、Python 沙箱、路径限制
- ⚡ **高性能**: 支持本地模型和 API 部署，灵活配置

---

## 1. 项目目录结构

```text
bibobot/
├── app/
│   ├── api/                # API 层：FastAPI 路由定义
│   │   └── routes.py       # 定义 /api/agent, /api/query 等接口
│   ├── core/               # 核心配置：Pydantic 环境校验
│   │   └── config.py       # 统一管理 .env 和默认值
│   ├── agent/              # Agent 核心模块（新增）
│   │   ├── agent.py        # Agent 核心（LLM + 循环 + 工具调用）
│   │   ├── llm.py          # LLM 客户端封装
│   │   └── tools/          # 工具集合
│   │       ├── base.py     # 工具基类
│   │       ├── rag_tool.py # RAG 检索工具
│   │       ├── bash_tool.py# Bash 命令工具
│   │       ├── python_tool.py  # Python 执行工具
│   │       ├── web_search_tool.py  # 网络搜索工具
│   │       └── calculator_tool.py  # 计算器工具
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
├── docs/                   # 文档（新增）
│   ├── agent_architecture.md  # Agent 架构设计
│   └── agent_examples.md      # Agent 使用示例
├── examples/               # 示例代码（新增）
│   └── custom_tools_example.py  # 自定义工具示例
├── data/                   # 数据存储
│   ├── raw/                # 原始文档存放处
│   └── canonical_md/       # 转换后的规范化 Markdown
├── docker/                 # 基础设施
│   └── docker-compose.yml  # Qdrant 容器配置
├── scripts/                # 运维脚本
│   ├── ingest_folder.py    # 批量导入本地文档工具
│   └── agent_cli.py        # Agent 命令行交互测试
├── .env                    # 环境配置文件（密钥存储）
└── requirements.txt        # Python 依赖
```

---

## 2. 快速开发流程

### A. 环境准备
1. 启动向量数据库：`cd docker && docker-compose up -d`
2. 配置环境变量：修改 `.env` 中的 `LLM_API_KEY`。
3. 安装依赖：`pip install -r requirements.txt`

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

### D. 使用 Agent（新增）

#### 方式 1: 命令行交互
```bash
python scripts/agent_cli.py
```

#### 方式 2: API 调用
```bash
# 非流式
curl -X POST "http://localhost:8000/api/agent" \
  -H "Content-Type: application/json" \
  -d '{"query": "帮我分析一下 data 目录下的销售数据"}'

# 流式（实时输出思考过程）
curl -X POST "http://localhost:8000/api/agent" \
  -H "Content-Type: application/json" \
  -d '{"query": "RAG 技术是什么？", "stream": true}'
```

#### 方式 3: Python 代码
```python
from app.agent import Agent, get_default_tools

agent = Agent(tools=get_default_tools())
answer = agent.run("我们的 RAG 系统使用了哪些技术？")
print(answer)
```

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

### 4. Agent 相关问题？

#### Agent 一直循环调用工具
*   检查 `.env` 中的 `AGENT_MAX_ITERATIONS` 配置
*   查看日志确认工具返回结果是否正确
*   优化系统提示词，让 LLM 更清楚何时停止

#### Bash 命令执行失败
*   确认命令在白名单内：`ls, cat, grep, rg, find, ...`
*   检查是否包含危险字符：`|, >, &&, ;`
*   查看 `BASH_TOOL_TIMEOUT` 是否设置合理

#### Python 代码执行报错
*   检查使用的模块是否在允许列表中
*   确保代码语法正确
*   查看详细错误日志定位问题

#### 网络搜索不可用
*   需要在 `.env` 中配置 `SERPER_API_KEY`
*   或使用其他搜索引擎 API 并修改 `web_search_tool.py`

---

## 4. 可用工具列表

Agent 支持以下工具：

| 工具名称 | 功能描述 | 使用场景 |
|---------|---------|---------|
| `search_knowledge` | RAG 知识库检索 | 查询特定主题的知识、寻找相关文档 |
| `run_bash` | 执行 Bash 命令 | 探索文件结构、查找文件内容 |
| `run_python` | 执行 Python 代码 | 数据分析、格式转换、复杂处理 |
| `web_search` | 互联网搜索 | 查询新闻、时事、最新研究成果 |
| `calculator` | 数学计算器 | 算术运算、表达式求值 |

---

## 5. 学习资源

### 📚 文档
- [Agent 架构设计](docs/agent_architecture.md) - 详细的架构说明
- [Agent 使用示例](docs/agent_examples.md) - 丰富的使用案例
- [自定义工具示例](examples/custom_tools_example.py) - 如何创建自己的工具

### 🔧 脚本工具
- `scripts/agent_cli.py` - 命令行交互式测试 Agent
- `scripts/ingest_folder.py` - 批量导入文档到知识库

### ⚙️ 配置说明
在 `.env` 文件中配置：
```bash
# Agent 配置
AGENT_MAX_ITERATIONS=10      # 最大迭代次数
BASH_TOOL_TIMEOUT=30         # Bash 超时（秒）
PYTHON_TOOL_TIMEOUT=30       # Python 超时（秒）

# 可选配置
SERPER_API_KEY=xxx           # 网络搜索 API Key
```

---

## 6. 对接 AI 前端界面

本项目提供 **OpenAI 兼容 API**，可无缝对接主流 AI 对话前端：

### 6.1 支持的 AI 前端

| 前端工具 | 特点 | 对接难度 |
|---------|------|---------|
| [Open WebUI](https://github.com/open-webui/open-webui) | 功能丰富、支持多用户、界面美观 | ⭐ 简单 |
| [Lobe Chat](https://github.com/lobehub/lobe-chat) | 现代化 UI、插件生态丰富 | ⭐ 简单 |
| [ChatGPT-Next-Web](https://github.com/ChatGPTNextWeb/ChatGPT-Next-Web) | 轻量快速、跨平台支持 | ⭐ 简单 |
| [Chatbox](https://github.com/Bin-Huang/chatbox) | 桌面客户端、开箱即用 | ⭐ 简单 |

### 6.2 Open WebUI 对接步骤

**步骤 1：启动本服务**
```bash
python app/main.py
# 服务将运行在 http://localhost:8000
```

**步骤 2：启动 Open WebUI**
```bash
# 使用 Docker 快速启动
docker run -d -p 3000:8080 \
  -e OPENAI_API_BASE_URL=http://host.docker.internal:8000/v1 \
  -e OPENAI_API_KEY=sk-bibobot \
  --name open-webui \
  ghcr.io/open-webui/open-webui:main
```

**步骤 3：浏览器访问**
- 打开 http://localhost:3000
- 首次使用需要注册管理员账号
- 进入对话界面，选择模型 `bibobot` 即可开始对话

**配置说明：**
- **API 地址**：`http://localhost:8000/v1`（OpenAI 兼容端点）
- **API Key**：任意填写，如 `sk-bibobot`（当前版本不验证）
- **模型名称**：`bibobot`

### 6.3 Lobe Chat 对接步骤

**步骤 1：启动 Lobe Chat**
```bash
# 使用 Docker 启动
docker run -d -p 3210:3210 \
  -e OPENAI_API_KEY=sk-bibobot \
  -e OPENAI_PROXY_URL=http://host.docker.internal:8000/v1 \
  --name lobe-chat \
  lobehub/lobe-chat
```

**步骤 2：配置语言模型**
- 访问 http://localhost:3210
- 点击左下角「设置」→「语言模型」
- 选择 OpenAI，配置如下：
  - **API Key**：`sk-bibobot`
  - **API 代理地址**：`http://localhost:8000/v1`
  - **模型列表**：选择 `bibobot` 或手动输入

### 6.4 ChatGPT-Next-Web 对接步骤

**步骤 1：启动服务**
```bash
docker run -d -p 3001:3000 \
  -e OPENAI_API_KEY=sk-bibobot \
  -e BASE_URL=http://host.docker.internal:8000 \
  -e CUSTOM_MODELS=-all,+bibobot \
  --name chatgpt-next-web \
  yidadaa/chatgpt-next-web
```

**步骤 2：访问使用**
- 打开 http://localhost:3001
- 在设置中确认 API 地址和模型配置
- 开始对话

### 6.5 API 端点说明

本项目提供以下 OpenAI 兼容端点：

| 端点 | 路径 | 说明 |
|-----|------|------|
| 对话完成 | `POST /v1/chat/completions` | 标准 OpenAI 格式，支持流式 |
| 模型列表 | `GET /v1/models` | 返回可用模型列表 |
| Agent 接口 | `POST /api/agent` | 原生接口，功能更丰富 |
| RAG 检索 | `POST /api/query` | 纯检索接口 |

### 6.6 手动测试 OpenAI 兼容接口

```bash
# 非流式请求
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-bibobot" \
  -d '{
    "model": "bibobot",
    "messages": [{"role": "user", "content": "介绍一下 RAG 技术"}],
    "stream": false
  }'

# 流式请求
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-bibobot" \
  -d '{
    "model": "bibobot",
    "messages": [{"role": "user", "content": "分析一下本地知识库"}],
    "stream": true
  }'
```

### 6.7 注意事项

1. **网络访问**：如果前端使用 Docker 部署，需要使用 `host.docker.internal` 访问宿主机服务
2. **CORS 支持**：服务已默认开启跨域，前端可直接访问
3. **流式响应**：支持 SSE 流式输出，可实时看到 Agent 思考过程
4. **对话历史**：通过 `messages` 参数传递历史记录，Agent 会自动维护上下文


