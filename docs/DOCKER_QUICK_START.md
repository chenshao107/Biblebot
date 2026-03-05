# Docker 沙箱快速开始 🚀

## 3 分钟快速启动

### 1. 构建沙箱镜像（1 分钟）

```bash
cd /home/chenshao/my-rag-server
docker build -f docker/Dockerfile.sandbox -t rag-sandbox:latest .
```

### 2. 启用 Docker 模式（30 秒）

编辑 `.env` 文件：

```bash
USE_DOCKER_SANDBOX=true
```

### 3. 启动服务（1 分钟）

```bash
# 启动 Qdrant
cd docker && docker-compose up -d

# 启动 RAG Server
cd .. && python app/main.py
```

## 验证安装

### 测试 Bash 工具

```bash
curl -X POST "http://localhost:8000/api/agent" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "使用 ripgrep 搜索 RK3506 相关的 markdown 文件"
  }'
```

### 测试 Python 工具

```bash
curl -X POST "http://localhost:8000/api/agent" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "用 pandas 分析 data/raw 下的数据文件"
  }'
```

## 完整部署（生产环境）

```bash
cd docker
docker-compose -f docker-compose.full.yml up -d
```

访问：`http://localhost:8000`

## 常用命令

```bash
# 查看运行中的沙箱
docker ps | grep rag-sandbox

# 查看沙箱日志
docker logs <container_id>

# 进入沙箱调试
docker exec -it <container_id> /bin/bash

# 清理所有沙箱
docker ps -a | grep rag-sandbox | awk '{print $1}' | xargs docker rm -f

# 停止服务
docker-compose -f docker-compose.full.yml down
```

## 配置速查

```bash
# .env 文件
USE_DOCKER_SANDBOX=true              # 启用 Docker 沙箱
DOCKER_SANDBOX_IMAGE=rag-sandbox:latest
DOCKER_MEMORY_LIMIT=512m             # 内存限制
DOCKER_CPU_QUOTA=100000              # CPU 限制
DOCKER_TIMEOUT=60                    # 超时时间
```

## 故障排除

| 问题 | 解决方案 |
|------|---------|
| Docker 连接失败 | `sudo usermod -aG docker $USER` 后重新登录 |
| 镜像不存在 | `docker build -f docker/Dockerfile.sandbox -t rag-sandbox:latest .` |
| 命令超时 | 增加 `DOCKER_TIMEOUT=120` |
| 内存不足 | 增加 `DOCKER_MEMORY_LIMIT=1g` |

## 下一步

- 📖 [完整使用指南](DOCKER_SANDBOX_GUIDE.md)
- 🏗️ [实现总结](DOCKER_IMPLEMENTATION_SUMMARY.md)
- 💡 [Agent 使用示例](agent_examples.md)

---

**现在你可以完全释放 AI Agent 的能力了！** 🎉
