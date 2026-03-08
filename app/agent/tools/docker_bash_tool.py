"""
Docker Bash Tool - 基于 Docker 沙箱的 Bash 命令执行工具
完全释放 Bash 能力，无需黑白名单限制
"""
from typing import Any, Dict
from loguru import logger
from app.agent.tools.base import BaseTool, ToolResult
from app.agent.tools.docker_sandbox import DockerSandbox, get_sandbox
from app.core.config import settings


class DockerBashTool(BaseTool):
    """
    基于 Docker 沙箱的 Bash 命令执行工具
    
    优势：
    - 完全隔离，不影响宿主机
    - 无需黑白名单，可以使用任何命令
    - 资源受限（CPU、内存限制）
    - 知识库只读，工作目录可写
    """
    
    def __init__(
        self,
        session_id: str = None,
        timeout: int = None,
        memory_limit: str = None,
        cpu_quota: int = None
    ):
        """
        初始化 Docker Bash 工具
        
        Args:
            session_id: 会话 ID，用于隔离不同 Agent 实例
            timeout: 命令执行超时（秒）
            memory_limit: Docker 内存限制
            cpu_quota: Docker CPU 限制
        """
        self.timeout = timeout or getattr(settings, 'BASH_TOOL_TIMEOUT', 30)
        self.memory_limit = memory_limit or getattr(settings, 'DOCKER_MEMORY_LIMIT', '512m')
        self.cpu_quota = cpu_quota or getattr(settings, 'DOCKER_CPU_QUOTA', 100000)
        
        # 获取或创建沙箱实例
        self.sandbox = get_sandbox(
            session_id=session_id,
            raw_dir=settings.DATA_RAW_DIR,
            memory_limit=self.memory_limit,
            cpu_quota=self.cpu_quota,
            timeout=self.timeout
        )
        
        logger.info(f"DockerBashTool 初始化: session={session_id or 'default'}")
    
    @property
    def name(self) -> str:
        return "run_bash"
    
    @property
    def description(self) -> str:
        return """在隔离的 Docker 环境中执行 Bash 命令。

工作目录结构:
- /workspace/data/raw - 知识库（只读）
- /workspace/work - 工作目录（可读写）
- /workspace/temp - 临时目录（可读写）

可用工具:
- 所有标准 Linux 命令 (ls, cat, grep, find, etc.)
- ripgrep (rg) - 快速文本搜索
- fd (fd-find) - 快速文件查找
- jq - JSON 处理
- git - 版本控制
- curl/wget - 网络下载
- 以及任何可以通过 apt 安装的工具

示例:
- 列出知识库: ls -la /workspace/data/raw/
- 搜索文件: find /workspace/data/raw -name "*.pdf"
- 文本搜索: rg "关键词" /workspace/data/raw/
- 统计分析: cat file.txt | wc -l
- 复杂处理: ls -la | grep ".md" | sort

注意: 命令在隔离的 Docker 容器中执行，不会影响宿主机。"""
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "要执行的 bash 命令，可以使用任何标准 Linux 命令和工具"
                },
                "workdir": {
                    "type": "string",
                    "description": "工作目录，默认为 /workspace",
                    "default": "/workspace"
                },
                "timeout": {
                    "type": "integer",
                    "description": f"命令执行超时时间（秒），默认 {self.timeout}",
                    "default": self.timeout
                }
            },
            "required": ["command"]
        }
    
    def execute(self, command: str, workdir: str = "/workspace", timeout: int = None) -> ToolResult:
        """
        在 Docker 沙箱中执行 Bash 命令
        
        Args:
            command: Bash 命令
            workdir: 工作目录
            timeout: 超时时间（秒）
        
        Returns:
            ToolResult 执行结果
        """
        try:
            logger.info(f"🐳 Docker Bash 执行: {command[:100]}...")
            
            # 确保沙箱已启动
            if not self.sandbox.container:
                logger.info("启动 Docker 沙箱...")
                self.sandbox.start()
            
            # 执行命令
            timeout = timeout or self.timeout
            result = self.sandbox.execute(
                command=command,
                workdir=workdir,
                timeout=timeout
            )
            
            # 构建输出
            output = result.output
            if result.error:
                output += f"\n[Error]: {result.error}"
            
            # 限制输出长度
            max_output_len = 10000
            if len(output) > max_output_len:
                output = output[:max_output_len] + f"\n... (输出被截断，共 {len(output)} 字符)"
            
            logger.info(f"✅ 命令执行完成: success={result.success}, time={result.execution_time:.2f}s")
            
            return ToolResult(
                success=result.success,
                output=output if output else "(命令执行成功，无输出)",
                error=result.error if not result.success else ""
            )
            
        except Exception as e:
            logger.error(f"❌ Docker Bash 执行失败: {e}")
            return ToolResult(
                success=False,
                output="",
                error=f"执行失败: {str(e)}\n\n请确保:\n1. Docker 已安装并运行\n2. 当前用户有 Docker 权限\n3. 已构建沙箱镜像: docker build -f docker/Dockerfile.sandbox -t bibobot-sandbox:latest ."
            )
    
    def cleanup(self):
        """清理资源"""
        if self.sandbox:
            self.sandbox.cleanup()


# 保持向后兼容的别名
BashTool = DockerBashTool
