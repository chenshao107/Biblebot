# Docker 沙箱模式使用指南

本文档介绍如何使用 Docker 沙箱模式来完全释放 Agent 工具的能力，同时保证系统安全。

## 🎯 核心优势

### 相比黑白名单方案

| 特性 | 黑白名单 | Docker 沙箱 |
|------|---------|------------|
| **功能限制** | 受限于白名单 | 完全自由 |
| **安全性** | 依赖规则维护 | 物理隔离 |
| **可维护性** | 需不断更新规则 | 一次配置 |
| **扩展性** | 难扩展 | 随时安装新工具 |
| **宿主机安全** | 有风险 | 完全隔离 |

### 具体优势

1. **完全释放 Bash 能力**
   - 可以使用任何 Linux 命令
   - 支持管道、重定向、脚本
   - 可以安装新工具（apt install）

2. **完全释放 Python 能力**
   - 使用任何 Python 包
   - 可以 pip install 新包
   - 无需受限的全局变量

3. **安全保障**
   - 容器隔离，不影响宿主机
   - 知识库只读映射
   - 资源限制（CPU、内存）
   - 超时控制

## 🏗️ 架构设计

```
┌─────────────────────────────────────────┐
│              Host Machine               │
│  ┌─────────────────────────────────┐   │
│  │      Biblebot Application     │   │
│  │         (Docker Container)      │   │
│  │  ┌─────────────────────────┐   │   │
│  │  │    Agent Core (LLM)     │   │   │
│  │  │  ┌─────────────────┐   │   │   │
│  │  │  │  Tool Decision  │───┼───┼───┼──→ 启动沙箱容器
│  │  │  └─────────────────┘   │   │   │
│  │  └─────────────────────────┘   │   │
│  └─────────────────────────────────┘   │
│                   │                     │
│                   ▼                     │
│  ┌─────────────────────────────────┐   │
│  │      Docker Sandbox Container   │   │
│  │  ┌─────────────────────────┐   │   │
│  │  │  /workspace/data/raw    │◄──┼───┼── 只读映射
│  │  │  (知识库 - 只读)         │   │   │
│  │  └─────────────────────────┘   │   │
│  │  ┌─────────────────────────┐   │   │
│  │  │  /workspace/work        │◄──┼───┼── 可写映射
│  │  │  (工作目录 - 可读写)     │   │   │
│  │  └─────────────────────────┘   │   │
│  │                                 │   │
│  │  • 完整的 Bash 环境             │   │
│  │  • 完整的 Python 环境           │   │
│  │  • 资源受限（512m, 1核）        │   │
│  └─────────────────────────────────┘   │
└─────────────────────────────────────────┘
```

## 🚀 快速开始

### 1. 确保 Docker 已安装

```bash
# 检查 Docker 版本
docker --version

# 检查 Docker Compose 版本
docker-compose --version
```

### 2. 构建沙箱镜像

```bash
# 在项目根目录执行
docker build -f docker/Dockerfile.sandbox -t biblebot-sandbox:latest .

# 验证镜像构建成功
docker images | grep biblebot-sandbox
```

### 3. 配置环境变量

在 `.env` 文件中确保以下配置：

```bash
# 启用 Docker 沙箱
USE_DOCKER_SANDBOX=true
DOCKER_SANDBOX_IMAGE=biblebot-sandbox:latest
DOCKER_MEMORY_LIMIT=512m
DOCKER_CPU_QUOTA=100000
DOCKER_TIMEOUT=60
```

### 4. 启动服务

#### 方式 1: 本地开发模式

```bash
# 1. 启动 Qdrant
cd docker && docker-compose up -d

# 2. 构建沙箱镜像
docker build -f docker/Dockerfile.sandbox -t biblebot-sandbox:latest .

# 3. 启动 Biblebot
python app/main.py
```

#### 方式 2: Docker Compose 完整部署

```bash
# 使用完整编排文件
cd docker
docker-compose -f docker-compose.full.yml up -d

# 查看日志
docker-compose -f docker-compose.full.yml logs -f
```

## 📝 使用示例

### 示例 1: 使用完整的 Bash 能力

```python
# 在 Agent CLI 或 API 中

# 使用管道和复杂命令
command = """
find /workspace/data/raw -name "*.md" -type f | \
  xargs grep -l "RK3506" | \
  head -5 | \
  while read f; do
    echo "=== $f ==="
    head -20 "$f"
  done
"""

# 使用 ripgrep 快速搜索
command = """
rg -i "uboot.*编译" /workspace/data/raw/RK3506/ --type md -A 3 -B 3
"""

# 使用 fd 查找文件
command = """
fd ".*\\.pdf$" /workspace/data/raw/ --exec ls -lh {}
"""
```

### 示例 2: 使用完整的 Python 能力

```python
# 数据分析
code = """
import pandas as pd
import numpy as np

# 读取数据
df = pd.read_csv('/workspace/data/raw/sales_data.csv')

# 复杂分析
result = df.groupby('category').agg({
    'amount': ['sum', 'mean', 'count'],
    'quantity': 'sum'
}).round(2)

print(result)
"""

# 安装新包并使用
code = """
# 安装需要的包
import subprocess
subprocess.run(['pip', 'install', '-q', 'matplotlib', 'seaborn'])

import matplotlib.pyplot as plt
import seaborn as sns

# 读取数据并绘图
data = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
plt.figure(figsize=(10, 6))
sns.lineplot(data=data)
plt.title('Sample Plot')
plt.savefig('/workspace/work/plot.png')
print("图表已保存到 /workspace/work/plot.png")
"""
```

### 示例 3: 复杂工作流

```python
# 多步骤数据处理
workflow = """
# 步骤 1: 查找所有相关文件
files = !find /workspace/data/raw/RK3506 -name "*.md" | head -10

# 步骤 2: 读取并分析内容
import json
results = []
for f in files:
    with open(f) as file:
        content = file.read()
        # 提取关键信息
        lines = content.split('\\n')
        title = lines[0] if lines else "Unknown"
        results.append({
            'file': f,
            'title': title,
            'length': len(content)
        })

# 步骤 3: 保存结果
with open('/workspace/work/analysis.json', 'w') as f:
    json.dump(results, f, indent=2)

print(f"分析了 {len(results)} 个文件")
print("结果保存到 /workspace/work/analysis.json")
"""
```

## ⚙️ 配置选项

### 环境变量

```bash
# 启用/禁用 Docker 沙箱
USE_DOCKER_SANDBOX=true          # 启用（推荐）
USE_DOCKER_SANDBOX=false         # 禁用，使用原生实现

# 沙箱镜像配置
DOCKER_SANDBOX_IMAGE=biblebot-sandbox:latest

# 资源限制
DOCKER_MEMORY_LIMIT=512m         # 内存限制（512MB）
DOCKER_CPU_QUOTA=100000          # CPU 限制（100000 = 1核）
DOCKER_TIMEOUT=60                # 命令执行超时（秒）
```

### 运行时配置

```python
from app.agent.tools.docker_bash_tool import DockerBashTool
from app.agent.tools.docker_python_tool import DockerPythonTool

# 自定义资源限制
bash_tool = DockerBashTool(
    session_id="my_session",
    timeout=120,                    # 2分钟超时
    memory_limit="1g",              # 1GB 内存
    cpu_quota=200000                # 2核 CPU
)

python_tool = DockerPythonTool(
    session_id="my_session",
    timeout=120,
    memory_limit="1g",
    cpu_quota=200000
)
```

## 🔧 高级用法

### 自定义沙箱镜像

如果你需要额外的工具或 Python 包，可以修改 `docker/Dockerfile.sandbox`：

```dockerfile
FROM python:3.10-slim-bookworm

# ... 基础配置 ...

# 安装额外的系统工具
RUN apt-get update && apt-get install -y \
    your-tool-1 \
    your-tool-2 \
    && rm -rf /var/lib/apt/lists/*

# 安装额外的 Python 包
RUN pip install --no-cache-dir \
    your-package-1 \
    your-package-2

# ... 其余配置 ...
```

然后重新构建：

```bash
docker build -f docker/Dockerfile.sandbox -t biblebot-sandbox:latest .
```

### 多会话隔离

```python
from app.agent.tools.docker_sandbox import get_sandbox

# 会话 1 - 用户 A
sandbox_a = get_sandbox(session_id="user_a")
sandbox_a.execute("echo 'User A data' > /workspace/work/data.txt")

# 会话 2 - 用户 B（完全隔离）
sandbox_b = get_sandbox(session_id="user_b")
# sandbox_b 看不到 sandbox_a 的文件
```

### 清理资源

```python
from app.agent.tools.docker_sandbox import cleanup_all_sandboxes

# 清理所有沙箱
cleanup_all_sandboxes()
```

## 🛡️ 安全机制

### 1. 文件系统隔离

- **知识库** (`/workspace/data/raw`): 只读映射
- **工作目录** (`/workspace/work`): 可读写，但只在容器内
- **临时目录** (`/workspace/temp`): 可读写，自动清理

### 2. 资源限制

- **内存**: 默认 512MB（可配置）
- **CPU**: 默认 1核（可配置）
- **超时**: 默认 60秒（可配置）

### 3. 网络隔离

- 默认使用 bridge 网络模式
- 可以限制网络访问（配置 `network_mode`）

### 4. 权限控制

- 容器以非 root 用户运行（可选）
- 丢弃不必要的 capabilities
- 禁止特权提升

## 🐛 故障排除

### 问题 1: Docker 连接失败

```
Error: Docker 连接失败
```

**解决方案:**

```bash
# 1. 检查 Docker 是否运行
sudo systemctl status docker

# 2. 检查用户权限
sudo usermod -aG docker $USER
# 重新登录或执行:
newgrp docker

# 3. 测试 Docker
docker run hello-world
```

### 问题 2: 镜像不存在

```
Error: 镜像不存在: biblebot-sandbox:latest
```

**解决方案:**

```bash
# 构建镜像
docker build -f docker/Dockerfile.sandbox -t biblebot-sandbox:latest .
```

### 问题 3: 命令执行超时

```
Error: 命令执行超时
```

**解决方案:**

```bash
# 增加超时时间
DOCKER_TIMEOUT=120  # .env 文件中
```

### 问题 4: 内存不足

```
Error: 内存不足或 OOM
```

**解决方案:**

```bash
# 增加内存限制
DOCKER_MEMORY_LIMIT=1g  # .env 文件中
```

## 📊 性能对比

### 启动时间

| 场景 | 时间 |
|------|------|
| 首次启动沙箱 | ~3-5 秒 |
| 复用已有沙箱 | ~0.1 秒 |
| 原生执行 | ~0.01 秒 |

### 内存占用

| 场景 | 内存 |
|------|------|
| 沙箱容器 | ~50-100 MB |
| Biblebot | ~500 MB - 2 GB |
| Qdrant | ~200 MB - 1 GB |

## 🎯 最佳实践

### 1. 开发环境

- 使用 `USE_DOCKER_SANDBOX=true` 获得完整功能
- 设置合理的资源限制
- 定期清理未使用的沙箱

### 2. 生产环境

- 使用 Docker Compose 完整部署
- 监控资源使用情况
- 设置适当的超时和限制

### 3. 调试技巧

```bash
# 查看运行中的沙箱容器
docker ps | grep biblebot-sandbox

# 进入沙箱容器调试
docker exec -it <container_id> /bin/bash

# 查看沙箱日志
docker logs <container_id>

# 清理所有沙箱容器
docker ps -a | grep biblebot-sandbox | awk '{print $1}' | xargs docker rm -f
```

## 🚀 部署建议

### 单机部署

```bash
# 使用完整编排
cd docker
docker-compose -f docker-compose.full.yml up -d
```

### 集群部署

- 使用 Kubernetes 编排
- 配置资源配额
- 使用持久化存储

## 📚 相关文档

- [架构设计](agent_architecture.md)
- [使用示例](agent_examples.md)
- [快速参考](QUICK_REFERENCE.md)

---

**现在你可以完全释放 AI Agent 的能力，同时保证系统安全！** 🎉
