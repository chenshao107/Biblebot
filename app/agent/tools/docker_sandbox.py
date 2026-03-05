"""
Docker Sandbox - 安全的执行环境管理
为 Agent 工具提供隔离的 Bash 和 Python 执行环境
"""
import os
import uuid
import shutil
import tempfile
from typing import Optional, Dict, Any
from pathlib import Path
from dataclasses import dataclass
from loguru import logger

# 尝试导入 docker，如果未安装则给出友好提示
try:
    import docker
    from docker.errors import DockerException, ContainerError, ImageNotFound
    DOCKER_AVAILABLE = True
except ImportError:
    DOCKER_AVAILABLE = False
    logger.warning("Docker SDK 未安装，Docker 沙箱功能不可用")
    logger.warning("运行: pip install docker")


@dataclass
class SandboxResult:
    """沙箱执行结果"""
    success: bool
    output: str
    error: str = ""
    exit_code: int = 0
    execution_time: float = 0.0


class DockerSandbox:
    """
    Docker 沙箱管理器
    
    为 Agent 工具提供隔离的执行环境：
    - 只读映射知识库 (data/raw)
    - 可写工作目录 (data/work/<session_id>)
    - 完整的 Bash 和 Python 环境
    - 资源限制（CPU、内存）
    """
    
    # 默认镜像名
    DEFAULT_IMAGE = "rag-sandbox:latest"
    
    # 容器内路径
    CONTAINER_RAW_PATH = "/workspace/data/raw"
    CONTAINER_WORK_PATH = "/workspace/work"
    CONTAINER_TEMP_PATH = "/workspace/temp"
    
    def __init__(
        self,
        session_id: Optional[str] = None,
        image: str = None,
        raw_dir: str = None,
        work_dir: str = None,
        memory_limit: str = "512m",
        cpu_quota: int = 100000,
        timeout: int = 60
    ):
        """
        初始化 Docker 沙箱
        
        Args:
            session_id: 会话 ID，用于隔离不同 Agent 实例
            image: Docker 镜像名，默认 rag-sandbox:latest
            raw_dir: 知识库目录（宿主机路径），默认 data/raw
            work_dir: 工作目录（宿主机路径），默认 data/work/<session_id>
            memory_limit: 内存限制，默认 512m
            cpu_quota: CPU 限制，默认 100000 (1核)
            timeout: 命令执行超时（秒）
        """
        if not DOCKER_AVAILABLE:
            raise RuntimeError(
                "Docker SDK 未安装。请运行: pip install docker"
            )
        
        self.session_id = session_id or str(uuid.uuid4())[:8]
        self.image = image or self.DEFAULT_IMAGE
        self.memory_limit = memory_limit
        self.cpu_quota = cpu_quota
        self.timeout = timeout
        
        # 设置目录路径
        base_dir = Path.cwd()
        self.host_raw_dir = Path(raw_dir) if raw_dir else base_dir / "data" / "raw"
        self.host_work_dir = Path(work_dir) if work_dir else base_dir / "data" / "work" / self.session_id
        
        # 确保目录存在
        self._ensure_directories()
        
        # Docker 客户端
        self.client = None
        self.container = None
        self._initialized = False
        
        logger.info(f"DockerSandbox 初始化: session={self.session_id}")
    
    def _ensure_directories(self):
        """确保必要的目录存在"""
        # 知识库目录必须存在
        if not self.host_raw_dir.exists():
            logger.warning(f"知识库目录不存在: {self.host_raw_dir}")
            self.host_raw_dir.mkdir(parents=True, exist_ok=True)
        
        # 创建工作目录
        self.host_work_dir.mkdir(parents=True, exist_ok=True)
        logger.debug(f"工作目录: {self.host_work_dir}")
    
    def _init_docker(self):
        """初始化 Docker 客户端"""
        if self._initialized:
            return
        
        try:
            self.client = docker.from_env()
            # 测试连接
            self.client.ping()
            logger.info("Docker 连接成功")
            self._initialized = True
        except DockerException as e:
            logger.error(f"Docker 连接失败: {e}")
            raise RuntimeError(
                "无法连接到 Docker。请确保:\n"
                "1. Docker 已安装: https://docs.docker.com/get-docker/\n"
                "2. Docker 服务正在运行\n"
                "3. 当前用户有权限访问 Docker"
            )
    
    def _ensure_image(self):
        """确保镜像存在"""
        try:
            self.client.images.get(self.image)
            logger.debug(f"镜像已存在: {self.image}")
        except ImageNotFound:
            logger.warning(f"镜像不存在: {self.image}")
            logger.info("尝试构建镜像...")
            self._build_image()
    
    def _build_image(self):
        """构建沙箱镜像"""
        dockerfile_path = Path(__file__).parent.parent.parent.parent / "docker" / "Dockerfile.sandbox"
        
        if not dockerfile_path.exists():
            raise RuntimeError(f"Dockerfile 不存在: {dockerfile_path}")
        
        try:
            logger.info(f"正在构建镜像: {self.image}")
            image, logs = self.client.images.build(
                path=str(dockerfile_path.parent),
                dockerfile=dockerfile_path.name,
                tag=self.image,
                rm=True
            )
            logger.info(f"镜像构建成功: {image.id}")
        except Exception as e:
            logger.error(f"镜像构建失败: {e}")
            raise
    
    def start(self) -> "DockerSandbox":
        """
        启动沙箱容器
        
        Returns:
            self，支持链式调用
        """
        self._init_docker()
        
        if self.container:
            logger.debug("容器已存在，无需重新启动")
            return self
        
        self._ensure_image()
        
        try:
            logger.info(f"启动沙箱容器: session={self.session_id}")
            
            # 准备卷映射
            volumes = {
                str(self.host_raw_dir.absolute()): {
                    "bind": self.CONTAINER_RAW_PATH,
                    "mode": "ro"  # 只读
                },
                str(self.host_work_dir.absolute()): {
                    "bind": self.CONTAINER_WORK_PATH,
                    "mode": "rw"  # 可读写
                }
            }
            
            # 创建并启动容器
            self.container = self.client.containers.run(
                self.image,
                detach=True,
                tty=True,
                name=f"rag-sandbox-{self.session_id}",
                volumes=volumes,
                working_dir="/workspace",
                mem_limit=self.memory_limit,
                cpu_quota=self.cpu_quota,
                network_mode="bridge",
                # 安全选项
                security_opt=["no-new-privileges:true"],
                cap_drop=["ALL"],
                cap_add=["CHOWN", "SETGID", "SETUID"],
                # 资源限制
                ulimits=[
                    {"name": "nofile", "soft": 1024, "hard": 2048}
                ]
            )
            
            logger.info(f"容器启动成功: {self.container.id[:12]}")
            
            # 等待容器就绪
            self._wait_for_ready()
            
        except Exception as e:
            logger.error(f"容器启动失败: {e}")
            self.cleanup()
            raise
        
        return self
    
    def _wait_for_ready(self, timeout: int = 10):
        """等待容器就绪"""
        import time
        start = time.time()
        
        while time.time() - start < timeout:
            try:
                self.container.reload()
                if self.container.status == "running":
                    # 测试执行一个简单的命令
                    result = self.container.exec_run("echo ready")
                    if result.exit_code == 0:
                        logger.debug("容器已就绪")
                        return
            except Exception:
                pass
            time.sleep(0.5)
        
        raise TimeoutError("容器启动超时")
    
    def execute(
        self,
        command: str,
        workdir: str = None,
        env: Dict[str, str] = None,
        timeout: int = None
    ) -> SandboxResult:
        """
        在沙箱中执行命令
        
        Args:
            command: 要执行的命令
            workdir: 工作目录（容器内路径）
            env: 环境变量
            timeout: 超时时间（秒），默认使用初始化时的设置
        
        Returns:
            SandboxResult 执行结果
        """
        import time
        
        if not self.container:
            self.start()
        
        timeout = timeout or self.timeout
        workdir = workdir or "/workspace"
        
        try:
            logger.debug(f"执行命令: {command[:100]}...")
            start_time = time.time()
            
            # 执行命令
            result = self.container.exec_run(
                ["bash", "-c", command],
                workdir=workdir,
                environment=env or {},
                timeout=timeout
            )
            
            execution_time = time.time() - start_time
            output = result.output.decode("utf-8", errors="replace")
            
            logger.debug(f"命令执行完成: exit_code={result.exit_code}, time={execution_time:.2f}s")
            
            return SandboxResult(
                success=result.exit_code == 0,
                output=output,
                error="" if result.exit_code == 0 else f"Exit code: {result.exit_code}",
                exit_code=result.exit_code,
                execution_time=execution_time
            )
            
        except ContainerError as e:
            logger.error(f"容器执行错误: {e}")
            return SandboxResult(
                success=False,
                output="",
                error=f"容器错误: {str(e)}",
                exit_code=-1
            )
        except Exception as e:
            logger.error(f"执行失败: {e}")
            return SandboxResult(
                success=False,
                output="",
                error=str(e),
                exit_code=-1
            )
    
    def execute_python(
        self,
        code: str,
        workdir: str = None,
        timeout: int = None
    ) -> SandboxResult:
        """
        在沙箱中执行 Python 代码
        
        Args:
            code: Python 代码
            workdir: 工作目录
            timeout: 超时时间
        
        Returns:
            SandboxResult 执行结果
        """
        # 将代码写入临时文件，然后执行
        # 这样可以避免命令行参数长度限制
        import base64
        
        # Base64 编码代码，避免引号问题
        encoded_code = base64.b64encode(code.encode()).decode()
        
        command = f"""
python3 -c "
import base64
import sys
import io
from contextlib import redirect_stdout, redirect_stderr

code = base64.b64decode('{encoded_code}').decode()

stdout_buffer = io.StringIO()
stderr_buffer = io.StringIO()

try:
    with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
        exec(code)
    output = stdout_buffer.getvalue()
    stderr_output = stderr_buffer.getvalue()
    if stderr_output:
        output += f'\\n[stderr]:\\n{{stderr_output}}'
    print(output)
    sys.exit(0)
except Exception as e:
    print(f'Error: {{e}}', file=sys.stderr)
    sys.exit(1)
"
"""
        
        return self.execute(command, workdir, timeout=timeout)
    
    def read_file(self, path: str) -> str:
        """
        从容器中读取文件
        
        Args:
            path: 容器内文件路径
        
        Returns:
            文件内容
        """
        try:
            # 使用 cat 命令读取文件
            result = self.execute(f"cat '{path}'")
            if result.success:
                return result.output
            else:
                raise FileNotFoundError(f"无法读取文件: {path}")
        except Exception as e:
            logger.error(f"读取文件失败: {e}")
            raise
    
    def write_file(self, path: str, content: str):
        """
        向容器写入文件
        
        Args:
            path: 容器内文件路径
            content: 文件内容
        """
        try:
            # 使用 base64 避免转义问题
            import base64
            encoded = base64.b64encode(content.encode()).decode()
            
            command = f"echo '{encoded}' | base64 -d > '{path}'"
            result = self.execute(command)
            
            if not result.success:
                raise IOError(f"无法写入文件: {path}")
                
        except Exception as e:
            logger.error(f"写入文件失败: {e}")
            raise
    
    def list_work_dir(self) -> str:
        """列出工作目录内容"""
        result = self.execute(f"ls -la {self.CONTAINER_WORK_PATH}")
        return result.output if result.success else ""
    
    def cleanup(self):
        """清理沙箱资源"""
        logger.info(f"清理沙箱: session={self.session_id}")
        
        # 停止并删除容器
        if self.container:
            try:
                logger.debug(f"停止容器: {self.container.id[:12]}")
                self.container.stop(timeout=5)
                self.container.remove(force=True)
                logger.debug("容器已删除")
            except Exception as e:
                logger.warning(f"容器清理时出错: {e}")
            finally:
                self.container = None
        
        # 可选：清理工作目录
        # 保留用于调试，可以手动删除
        
        logger.info("沙箱清理完成")
    
    def __enter__(self):
        """上下文管理器入口"""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.cleanup()
        return False
    
    def __del__(self):
        """析构时清理"""
        if self.container:
            self.cleanup()


# 全局沙箱实例管理（用于复用）
_sandboxes: Dict[str, DockerSandbox] = {}


def get_sandbox(session_id: str = None, **kwargs) -> DockerSandbox:
    """
    获取或创建沙箱实例
    
    Args:
        session_id: 会话 ID
        **kwargs: 传递给 DockerSandbox 的参数
    
    Returns:
        DockerSandbox 实例
    """
    session_id = session_id or "default"
    
    if session_id not in _sandboxes:
        _sandboxes[session_id] = DockerSandbox(session_id=session_id, **kwargs)
    
    return _sandboxes[session_id]


def cleanup_all_sandboxes():
    """清理所有沙箱实例"""
    global _sandboxes
    for session_id, sandbox in list(_sandboxes.items()):
        try:
            sandbox.cleanup()
        except Exception as e:
            logger.error(f"清理沙箱 {session_id} 失败: {e}")
    
    _sandboxes.clear()
