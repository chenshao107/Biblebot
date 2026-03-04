# Agent 快速参考手册 🚀

## 📋 可用工具

| 工具 | 命令 | 用途 |
|------|------|------|
| 🔍 RAG 检索 | `search_knowledge(query, top_k=5)` | 知识库语义搜索 |
| 💻 Bash 命令 | `run_bash(command)` | 执行安全的 shell 命令 |
| 🐍 Python 代码 | `run_python(code)` | 执行 Python 代码 |
| 🌐 网络搜索 | `web_search(query, num_results=5)` | 互联网信息检索 |
| 🧮 计算器 | `calculator(expression)` | 数学表达式求值 |

## ⚡ 快速使用

### 方式 1: CLI 交互
```bash
python scripts/agent_cli.py
```

### 方式 2: API 调用
```bash
curl -X POST "http://localhost:8000/api/agent" \
  -H "Content-Type: application/json" \
  -d '{"query": "你的问题"}'
```

### 方式 3: Python 代码
```python
from app.agent import Agent, get_default_tools

agent = Agent(tools=get_default_tools())
answer = agent.run("帮我查一下 RAG 相关资料")
print(answer)
```

## 🎯 典型场景

### 场景 1: 知识查询
```
问：我们的 RAG 系统使用了哪些重排模型？
→ 自动调用 search_knowledge
```

### 场景 2: 文件探索
```
问：data/raw 目录下有多少个 PDF 文件？
→ 自动调用 run_bash: find . -name "*.pdf"
```

### 场景 3: 数据分析
```
问：统计 sales.csv 的总销售额
→ 先用 bash 查看结构
→ 再用 python 计算
```

### 场景 4: 复杂任务
```
问：找到机器学习相关文档并整理成 JSON
→ search_knowledge → run_python → JSON
```

## ⚙️ 配置项 (.env)

```bash
# Agent 配置
AGENT_MAX_ITERATIONS=10      # 最大迭代次数
BASH_TOOL_TIMEOUT=30         # Bash 超时（秒）
PYTHON_TOOL_TIMEOUT=30       # Python 超时（秒）

# 可选配置
SERPER_API_KEY=xxx           # 网络搜索 API Key
BASH_WORK_DIR=data/raw       # Bash 工作目录
```

## 🛠️ 自定义工具

```python
from app.agent.tools.base import BaseTool, ToolResult

class MyTool(BaseTool):
    @property
    def name(self) -> str: return "my_tool"
    
    @property
    def description(self) -> str: return "我的工具..."
    
    @property
    def parameters(self) -> Dict[str, Any]: return {...}
    
    def execute(self, **kwargs) -> ToolResult:
        # 实现逻辑
        pass

# 注册
from app.agent.tools import register_tool
register_tool("my", MyTool)
```

## 📊 API 响应格式

### 非流式
```json
{
  "answer": "最终答案",
  "steps": [
    {"type": "thinking", "content": "..."},
    {"type": "tool_call", "tool_name": "...", "tool_args": {...}},
    {"type": "tool_result", "content": "..."},
    {"type": "final_answer", "content": "..."}
  ]
}
```

### 流式 (SSE)
```
data: {"type": "thinking", "content": "..."}
data: {"type": "tool_call", "tool_name": "..."}
data: {"type": "tool_result", "content": "..."}
data: {"answer": "...", "steps": [...]}
data: [DONE]
```

## 🔍 调试技巧

### 查看详细日志
```bash
LOG_LEVEL=DEBUG python scripts/agent_cli.py
```

### 限制迭代次数
```python
agent = Agent(tools=get_default_tools(), max_iterations=5)
```

### 选择工具
```python
# 只使用部分工具
from app.agent.tools import RAGTool, BashTool
agent = Agent(tools=[RAGTool(), BashTool()])
```

## ⚠️ 常见问题

**Q: Agent 循环调用工具？**
- 检查 `AGENT_MAX_ITERATIONS`
- 优化工具返回结果质量

**Q: Bash 命令失败？**
- 确认在白名单内：`ls, cat, grep, rg, find...`
- 检查危险字符：`|, >, &&`

**Q: Python 代码报错？**
- 检查模块是否允许：`json, re, math...`
- 查看错误日志定位问题

**Q: 网络搜索不可用？**
- 配置 `SERPER_API_KEY`
- 或修改工具使用其他 API

## 📚 学习资源

- 📖 [架构设计](docs/agent_architecture.md)
- 📝 [使用示例](docs/agent_examples.md)
- 💻 [自定义工具](examples/custom_tools_example.py)

---

**快速开始**: `python scripts/agent_cli.py` 🚀
