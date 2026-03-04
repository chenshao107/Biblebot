# Agent 使用示例

本文档展示如何使用 Agent 进行各种任务。

## 🚀 快速开始

### 1. 命令行交互模式

```bash
# 运行 CLI 测试工具
python scripts/agent_cli.py
```

示例对话：

```
你：查找关于 RAG 技术的相关文档

🤔 [思考] 我来帮你查找关于 RAG 技术的相关文档...

📞 [调用工具] search_knowledge
  参数：{'query': 'RAG 技术', 'top_k': 5}

✅ [工具结果]
找到 5 条相关结果:
[1] 来源：rag_paper.pdf | Introduction
相关度：0.892
内容：RAG (Retrieval-Augmented Generation) 是一种结合检索和生成的方法...

💡 [最终答案]
根据知识库检索结果，RAG（Retrieval-Augmented Generation）是一种...
```

### 2. API 调用

```bash
# 启动服务器
uvicorn app.main:app --host 0.0.0.0 --port 8000

# 调用 Agent 接口
curl -X POST "http://localhost:8000/api/agent" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "帮我分析一下 data/raw 目录下的销售数据",
    "stream": false
  }'
```

## 📚 使用场景示例

### 场景 1：知识库查询

**问题**: "我们的 RAG 系统使用了哪些重排模型？"

**Agent 执行流程**:
1. 调用 `search_knowledge` 工具查询知识库
2. 分析检索结果
3. 给出完整答案

```python
from app.agent import Agent, get_default_tools

agent = Agent(tools=get_default_tools())
answer = agent.run("我们的 RAG 系统使用了哪些重排模型？")
print(answer)
```

### 场景 2：文件系统探索

**问题**: "data/raw 目录下有哪些 PDF 文件？"

**Agent 执行流程**:
1. 调用 `run_bash` 工具执行 `find . -name "*.pdf"`
2. 分析命令输出
3. 列出所有找到的 PDF 文件

```python
answer = agent.run("data/raw 目录下有哪些 PDF 文件？")
print(answer)
```

### 场景 3：数据分析

**问题**: "帮我统计一下 sales.csv 中的总销售额"

**Agent 执行流程**:
1. 调用 `run_bash` 查看文件结构：`head sales.csv`
2. 调用 `run_python` 读取并分析数据
3. 返回统计结果

```python
answer = agent.run("帮我统计一下 sales.csv 中的总销售额")
print(answer)
```

### 场景 4：复杂任务（多工具协作）

**问题**: "找到关于机器学习的文档，并把相关内容整理成 JSON 格式"

**Agent 执行流程**:
1. 调用 `search_knowledge` 查找机器学习相关文档
2. 调用 `run_python` 将结果整理为 JSON 格式
3. 返回结构化的 JSON 数据

```python
answer = agent.run("找到关于机器学习的文档，并把相关内容整理成 JSON 格式")
print(answer)
```

### 场景 5：网络搜索（需配置 API）

**问题**: "2024 年最新的 RAG 技术研究有哪些？"

**Agent 执行流程**:
1. 调用 `web_search` 搜索最新研究
2. 分析搜索结果
3. 总结主要研究成果

```python
# 需要在 .env 中配置 SERPER_API_KEY
answer = agent.run("2024 年最新的 RAG 技术研究有哪些？")
print(answer)
```

### 场景 6：数学计算

**问题**: "计算 (1234 + 5678) * 90 / 12"

**Agent 执行流程**:
1. 调用 `calculator` 工具进行计算
2. 返回计算结果

```python
answer = agent.run("计算 (1234 + 5678) * 90 / 12")
print(answer)
```

## 🛠️ 自定义工具

你可以添加自己的工具：

```python
from app.agent.tools.base import BaseTool, ToolResult
from typing import Any, Dict

class MyCustomTool(BaseTool):
    @property
    def name(self) -> str:
        return "my_custom_tool"
    
    @property
    def description(self) -> str:
        return "我的自定义工具，用于..."
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "param1": {
                    "type": "string",
                    "description": "参数 1 的描述"
                }
            },
            "required": ["param1"]
        }
    
    def execute(self, param1: str) -> ToolResult:
        # 实现你的逻辑
        result = f"处理结果：{param1}"
        return ToolResult(success=True, output=result)

# 注册工具
from app.agent.tools import register_tool
register_tool("my_custom", MyCustomTool)

# 使用自定义工具
from app.agent import Agent
from app.agent.tools import get_default_tools

tools = get_default_tools() + [MyCustomTool()]
agent = Agent(tools=tools)
```

## 🎯 流式输出

使用流式模式可以实时看到 Agent 的思考过程：

```python
for step in agent.run_stream("你的问题"):
    if step["type"] == "thinking":
        print(f"思考：{step['content']}")
    elif step["type"] == "tool_call":
        print(f"调用工具：{step['tool_name']}")
    elif step["type"] == "tool_result":
        print(f"工具结果：{step['content'][:100]}...")
    elif step["type"] == "final_answer":
        print(f"最终答案：{step['content']}")
```

## 📊 API 响应格式

### 非流式响应

```json
{
  "answer": "最终答案",
  "steps": [
    {
      "type": "thinking",
      "content": "让我来帮你查询..."
    },
    {
      "type": "tool_call",
      "tool_name": "search_knowledge",
      "tool_args": {"query": "...", "top_k": 5}
    },
    {
      "type": "tool_result",
      "tool_name": "search_knowledge",
      "content": "找到 5 条结果..."
    },
    {
      "type": "final_answer",
      "content": "根据检索结果..."
    }
  ]
}
```

### 流式响应 (SSE)

```
data: {"type": "thinking", "content": "..."}

data: {"type": "tool_call", "tool_name": "search_knowledge", ...}

data: {"type": "tool_result", "content": "..."}

data: {"answer": "...", "steps": [...]}

data: [DONE]
```

## ⚙️ 配置选项

在 `.env` 文件中配置：

```bash
# Agent 最大迭代次数
AGENT_MAX_ITERATIONS=10

# Bash 命令超时时间（秒）
BASH_TOOL_TIMEOUT=30

# Python 执行超时时间（秒）
PYTHON_TOOL_TIMEOUT=30

# Bash 工作目录
BASH_WORK_DIR=data/raw

# 网络搜索 API Key（可选）
SERPER_API_KEY=your_api_key_here
```

## 🔍 调试技巧

1. **查看详细日志**:
   ```bash
   LOG_LEVEL=DEBUG python scripts/agent_cli.py
   ```

2. **限制迭代次数**:
   ```python
   agent = Agent(tools=get_default_tools(), max_iterations=5)
   ```

3. **禁用特定工具**:
   ```python
   from app.agent.tools import RAGTool, BashTool, PythonTool
   
   # 只使用部分工具
   tools = [RAGTool(), BashTool()]
   agent = Agent(tools=tools)
   ```

## 📝 最佳实践

1. **明确的问题描述**: 问题越具体，Agent 越能准确执行
2. **分步任务**: 复杂任务可以分解为多个小问题
3. **利用上下文**: 可以在对话中提供背景信息
4. **监控工具调用**: 注意 Agent 的工具选择是否合理
5. **设置合理超时**: 根据任务复杂度调整超时时间

## 🚨 常见问题

**Q: Agent 一直循环调用工具怎么办？**
A: 检查 `AGENT_MAX_ITERATIONS` 配置，确保设置了合理的上限

**Q: Bash 命令执行失败？**
A: 确认命令在安全白名单内，且不包含危险操作

**Q: Python 代码执行报错？**
A: 检查代码语法，确保只使用了允许的模块和函数

**Q: 网络搜索不可用？**
A: 需要在 `.env` 中配置有效的 `SERPER_API_KEY`
