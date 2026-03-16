# Professional Biblebot 开发与调试手册

本项目是一个工业级的 RAG（检索增强生成）系统框架，核心特点是支持 **多格式文档摄取**、**混合搜索 (Dense + Sparse)**、**两阶段检索 (Recall + Rerank)** 以及 **智能 Agent 知识服务**。

## 🌟 核心功能

- 🔍 **RAG 检索**: 混合向量搜索 + 查询改写 + 结果重排
- 🤖 **AI Agent**: LLM + 工具调用（RAG/Bash/Python/Web Search）
- 📄 **多格式支持**: PDF/Word/Excel/PPT/Markdown 等通过 Docling 转换
- 🛡️ **安全机制**: Bash 命令白名单、Python 沙箱、路径限制

---

## 1. 项目目录结构

```text
biblebot/
├── app/
│   ├── api/                # API 层：FastAPI 路由定义
│   ├── core/               # 核心配置：Pydantic 环境校验
│   ├── agent/              # Agent 核心模块
│   ├── services/           # 业务逻辑层
│   └── main.py             # 程序入口
├── docs/                   # 文档（新增）
├── examples/               # 示例代码（新增）
├── data/                   # 数据存储
│   ├── raw/                # 原始文档存放处
│   └── canonical_md/       # 转换后的规范化 Markdown
├── docker/                 # 基础设施
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
  -e OPENAI_API_KEY=sk-biblebot \
  --name open-webui \
  ghcr.io/open-webui/open-webui:main
```

**步骤 3：浏览器访问**
- 打开 http://localhost:3000
- 首次使用需要注册管理员账号
- 进入对话界面，选择模型 `biblebot` 即可开始对话

**配置说明：**
- **API 地址**：`http://localhost:8000/v1`（OpenAI 兼容端点）
- **API Key**：任意填写，如 `sk-biblebot`（当前版本不验证）
- **模型名称**：`biblebot`

### 6.3 Lobe Chat 对接步骤

**步骤 1：启动 Lobe Chat**
```bash
# 使用 Docker 启动
docker run -d -p 3210:3210 \
  -e OPENAI_API_KEY=sk-biblebot \
  -e OPENAI_PROXY_URL=http://host.docker.internal:8000/v1 \
  --name lobe-chat \
  lobehub/lobe-chat
```

**步骤 2：配置语言模型**
- 访问 http://localhost:3210
- 点击左下角「设置」→「语言模型」
- 选择 OpenAI，配置如下：
  - **API Key**：`sk-biblebot`
  - **API 代理地址**：`http://localhost:8000/v1`
  - **模型列表**：选择 `biblebot` 或手动输入

### 6.4 ChatGPT-Next-Web 对接步骤

**步骤 1：启动服务**
```bash
docker run -d -p 3001:3000 \
  -e OPENAI_API_KEY=sk-biblebot \
  -e BASE_URL=http://host.docker.internal:8000 \
  -e CUSTOM_MODELS=-all,+biblebot \
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
  -H "Authorization: Bearer sk-biblebot" \
  -d '{
    "model": "biblebot",
    "messages": [{"role": "user", "content": "介绍一下 RAG 技术"}],
    "stream": false
  }'

# 流式请求
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-biblebot" \
  -d '{
    "model": "biblebot",
    "messages": [{"role": "user", "content": "分析一下本地知识库"}],
    "stream": true
  }'
```

### 6.7 注意事项

1. **网络访问**：如果前端使用 Docker 部署，需要使用 `host.docker.internal` 访问宿主机服务
2. **CORS 支持**：服务已默认开启跨域，前端可直接访问
3. **流式响应**：支持 SSE 流式输出，可实时看到 Agent 思考过程
4. **对话历史**：通过 `messages` 参数传递历史记录，Agent 会自动维护上下文

---

## 7. MCP 服务配置

本项目支持 **MCP (Model Context Protocol)** 协议，可将 Agent 作为 MCP 服务器供其他 AI 客户端调用。

### 7.1 MCP 服务模式

支持两种运行模式：

| 模式 | 适用场景 | 访问方式 |
|-----|---------|---------|
| **stdio** | 本地使用 | Claude Desktop、Cursor 等 |
| **HTTP/SSE** | 内网共享 | 远程 AI 客户端通过 URL 访问 |

### 7.2 stdio 模式（本地使用）

适用于本地 AI 客户端，如 Claude Desktop、Cursor 等。

**启动命令：**
```bash
python scripts/run_agent_mcp_server.py
```

**Claude Desktop 配置** (`claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "biblebot-agent": {
      "command": "python",
      "args": ["/home/chenshao/Bibliobot/scripts/run_agent_mcp_server.py"]
    }
  }
}
```

**Cursor 配置** (`.cursor/mcp.json`):
```json
{
  "mcpServers": {
    "biblebot-agent": {
      "command": "python",
      "args": ["/home/chenshao/Bibliobot/scripts/run_agent_mcp_server.py"]
    }
  }
}
```

### 7.3 HTTP/SSE 模式（内网共享）

适用于内网环境，多台机器共享同一个 Agent 服务。

**启动命令：**
```bash
# 默认绑定 0.0.0.0:8001
python scripts/run_agent_mcp_server.py --http

# 或指定主机和端口
python scripts/run_agent_mcp_server.py --http --host 0.0.0.0 --port 8001
```

**环境变量配置** (`.env`):
```bash
# MCP HTTP 服务器配置
AGENT_MCP_HOST=0.0.0.0
AGENT_MCP_PORT=8001
```

**客户端配置示例**（假设服务器 IP 是 `192.168.1.100`）：

```json
{
  "mcpServers": {
    "biblebot-agent": {
      "url": "http://192.168.1.100:8001/sse"
    }
  }
}
```

### 7.4 MCP 服务端点

HTTP 模式下提供以下端点：

| 端点 | 方法 | 说明 |
|-----|------|------|
| `/` | GET | 服务器信息 |
| `/tools` | GET | 获取可用工具列表 |
| `/sse` | GET | SSE 连接端点（MCP 客户端连接） |
| `/message` | POST | 发送消息端点 |

### 7.5 MCP 可用工具

MCP 服务器只暴露一个工具：

| 工具名 | 描述 | 参数 |
|-------|------|------|
| `ask_agent` | 向知识库 Agent 提问 | `question` (必填): 问题内容<br>`context` (可选): 上下文信息 |

### 7.6 手动测试 MCP 服务

```bash
# 1. 启动 HTTP MCP 服务器
python scripts/run_agent_mcp_server.py --http

# 2. 获取工具列表
curl http://localhost:8001/tools

# 3. 建立 SSE 连接（新开终端）
curl http://localhost:8001/sse

# 4. 发送消息调用工具
curl -X POST http://localhost:8001/message \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "ask_agent",
      "arguments": {
        "question": "什么是 RAG 技术？"
      }
    }
  }'
```

### 7.7 MCP 配置检查清单

- [ ] 安装依赖：`pip install mcp>=1.0.0`
- [ ] 配置 `.env` 文件中的 LLM API Key
- [ ] 选择运行模式：stdio（本地）或 HTTP（内网共享）
- [ ] 在 AI 客户端中配置 MCP 服务器地址
- [ ] 测试工具调用是否正常工作


