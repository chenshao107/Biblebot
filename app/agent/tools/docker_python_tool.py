"""
Docker Python Tool - 基于 Docker 沙箱的 Python 代码执行工具
完全释放 Python 能力，无需受限的全局变量
"""
from typing import Any, Dict
from loguru import logger
from app.agent.tools.base import BaseTool, ToolResult
from app.agent.tools.docker_sandbox import DockerSandbox, get_sandbox
from app.core.config import settings


class DockerPythonTool(BaseTool):
    """
    基于 Docker 沙箱的 Python 代码执行工具
    
    优势：
    - 完全隔离，不影响宿主机
    - 可以使用任何 Python 包（通过 pip 安装）
    - 资源受限（CPU、内存限制）
    - 知识库只读，工作目录可写
    - 无需受限的全局变量
    """
    
    def __init__(
        self,
        session_id: str = None,
        timeout: int = None,
        memory_limit: str = None,
        cpu_quota: int = None
    ):
        """
        初始化 Docker Python 工具
        
        Args:
            session_id: 会话 ID，用于隔离不同 Agent 实例
            timeout: 代码执行超时（秒）
            memory_limit: Docker 内存限制
            cpu_quota: Docker CPU 限制
        """
        self.timeout = timeout or getattr(settings, 'PYTHON_TOOL_TIMEOUT', 30)
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
        
        logger.info(f"DockerPythonTool 初始化: session={session_id or 'default'}")
    
    @property
    def name(self) -> str:
        return "run_python"
    
    @property
    def description(self) -> str:
        return """在隔离的 Docker 环境中执行 Python 代码。

工作目录结构:
- /workspace/data/raw - 知识库（只读）
- /workspace/work - 工作目录（可读写）
- /workspace/temp - 临时目录（可读写）

预装 Python 包:
- numpy - 数值计算
- pandas - 数据处理
- matplotlib - 数据可视化
- requests - HTTP 请求
- beautifulsoup4 - HTML 解析
- lxml - XML 处理
- pyyaml - YAML 处理
- python-dateutil - 日期处理

可以安装其他包:
代码中可以运行: !pip install package_name

示例:
- 读取文件:
  with open('/workspace/data/raw/RK3506/README.md') as f:
      content = f.read()
  print(content)

- 数据分析:
  import pandas as pd
  df = pd.read_csv('/workspace/data/raw/data.csv')
  print(df.describe())

- 文件处理:
  import json
  with open('/workspace/data/raw/config.json') as f:
      config = json.load(f)
  print(config['version'])

- 复杂计算:
  import numpy as np
  result = np.random.randn(100).mean()
  print(f"平均值: {result}")

注意: 代码在隔离的 Docker 容器中执行，不会影响宿主机。"""
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "要执行的 Python 代码，可以使用标准库和预装的第三方库"
                },
                "workdir": {
                    "type": "string",
                    "description": "工作目录，默认为 /workspace/work",
                    "default": "/workspace/work"
                },
                "timeout": {
                    "type": "integer",
                    "description": f"代码执行超时时间（秒），默认 {self.timeout}",
                    "default": self.timeout
                }
            },
            "required": ["code"]
        }
    
    def execute(self, code: str, workdir: str = "/workspace/work", timeout: int = None) -> ToolResult:
        """
        在 Docker 沙箱中执行 Python 代码
        
        Args:
            code: Python 代码
            workdir: 工作目录
            timeout: 超时时间（秒）
        
        Returns:
            ToolResult 执行结果
        """
        try:
            logger.info(f"🐳 Docker Python 执行:\n{code[:200]}...")
            
            # 确保沙箱已启动
            if not self.sandbox.container:
                logger.info("启动 Docker 沙箱...")
                self.sandbox.start()
            
            # 执行代码
            timeout = timeout or self.timeout
            result = self.sandbox.execute_python(
                code=code,
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
            
            logger.info(f"✅ 代码执行完成: success={result.success}, time={result.execution_time:.2f}s")
            
            return ToolResult(
                success=result.success,
                output=output if output else "(代码执行成功，无输出)",
                error=result.error if not result.success else ""
            )
            
        except Exception as e:
            logger.error(f"❌ Docker Python 执行失败: {e}")
            return ToolResult(
                success=False,
                output="",
                error=f"执行失败: {str(e)}\n\n请确保:\n1. Docker 已安装并运行\n2. 当前用户有 Docker 权限\n3. 已构建沙箱镜像: docker build -f docker/Dockerfile.sandbox -t biblebot-sandbox:latest ."
            )
    
    def cleanup(self):
        """清理资源"""
        if self.sandbox:
            self.sandbox.cleanup()


# 保持向后兼容的别名
PythonTool = DockerPythonTool
