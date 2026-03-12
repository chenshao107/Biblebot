"""
Bash 命令工具 - 执行安全的 bash 命令探索文件系统
"""
import subprocess
import shlex
from typing import Any, Dict
from loguru import logger
from app.agent.tools.base import BaseTool, ToolResult
from app.core.config import settings


class BashTool(BaseTool):
    """Bash 命令执行工具"""
    
    # 允许的安全命令白名单
    ALLOWED_COMMANDS = {
        "ls", "cat", "head", "tail", "grep", "rg", "find", "wc",
        "file", "stat", "du", "tree", "less", "more",
        "awk", "sed", "sort", "uniq", "cut", "tr",
        # 注意：PDF 相关命令已移除，AI 应使用 Docling 转换后的 Markdown 文件
        "echo", "pwd", "basename", "dirname", "realpath",
    }
    
    # 危险模式黑名单
    DANGEROUS_PATTERNS = [
        "rm ", "rm\t", "rmdir", "mv ", "cp ",
        "chmod", "chown", "sudo", "su ",
        ">", ">>", "|", "&&", "||", ";", "`", "$(",
        "wget", "curl", "nc ", "ssh", "scp",
        "kill", "pkill", "shutdown", "reboot",
        "mkfs", "fdisk", "dd ",
    ]
    
    def __init__(self, data_dir: str = None, timeout: int = None):
        """
        初始化 Bash 工具
        
        Args:
            data_dir: 限制命令只能在此目录下执行，默认为配置的 DATA_CANONICAL_DIR（Docling 转换后的 Markdown 目录）
            timeout: 命令超时时间（秒），默认使用配置值
        """
        from app.core.config import settings
        # 默认使用 canonical_md 目录（Docling 转换后的 Markdown 文件）
        self.data_dir = data_dir or settings.BASH_WORK_DIR or settings.DATA_CANONICAL_DIR
        self.timeout = timeout or settings.BASH_TOOL_TIMEOUT
    
    @property
    def name(self) -> str:
        return "run_bash"
    
    @property
    def description(self) -> str:
        return f"""执行 bash 命令来探索和读取文件。
        
工作目录: {self.data_dir}

可用命令: ls, cat, head, tail, grep, rg, find, wc, file, stat, tree, awk, sed, sort, uniq 等

注意：PDF 文件已通过 Docling 转换为 Markdown，请直接阅读 .md 文件

用途：
- 列出目录内容: ls -la
- 查看文件: cat filename.txt
- 搜索内容: grep -r "关键词" .
- 使用 ripgrep: rg "pattern" --type md
- 查找文件: find . -name "*.pdf"
- Markdown 文本搜索: rg "关键词" --type md

注意：只能执行只读命令，不支持修改、删除。"""
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "要执行的 bash 命令，如 'ls -la' 或 'grep -r keyword .'"
                }
            },
            "required": ["command"]
        }
    
    def _is_safe_command(self, command: str) -> tuple[bool, str]:
        """
        检查命令是否安全
        
        Returns:
            (is_safe, reason)
        """
        from app.core.config import settings
        
        # 如果禁用了白名单检查，直接放行
        if not settings.ENABLE_BASH_WHITELIST:
            return True, ""
        
        # 检查危险模式
        command_lower = command.lower()
        for pattern in self.DANGEROUS_PATTERNS:
            if pattern in command_lower:
                return False, f"命令包含不允许的操作: {pattern.strip()}"
        
        # 提取主命令
        parts = shlex.split(command)
        if not parts:
            return False, "空命令"
        
        main_cmd = parts[0]
        
        # 检查是否在白名单中
        if main_cmd not in self.ALLOWED_COMMANDS:
            return False, f"命令 '{main_cmd}' 不在允许列表中。允许的命令: {', '.join(sorted(self.ALLOWED_COMMANDS))}"
        
        return True, ""
    
    def execute(self, command: str) -> ToolResult:
        """执行 bash 命令"""
        # 安全检查
        is_safe, reason = self._is_safe_command(command)
        if not is_safe:
            return ToolResult(
                success=False,
                output="",
                error=f"安全检查失败: {reason}"
            )
        
        try:
            logger.info(f"执行 bash 命令: {command}")
            
            # 执行命令
            result = subprocess.run(
                command,
                shell=True,
                cwd=self.data_dir,
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            
            # 组合输出
            output = result.stdout
            if result.stderr:
                output += f"\n[stderr]: {result.stderr}"
            
            # 限制输出长度
            max_output_len = 10000
            if len(output) > max_output_len:
                output = output[:max_output_len] + f"\n... (输出被截断，共 {len(output)} 字符)"
            
            if result.returncode != 0:
                return ToolResult(
                    success=False,
                    output=output,
                    error=f"命令退出码: {result.returncode}"
                )
            
            return ToolResult(
                success=True,
                output=output if output else "(无输出)"
            )
            
        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                output="",
                error=f"命令执行超时 ({self.timeout}秒)"
            )
        except Exception as e:
            logger.error(f"Bash 命令执行失败: {e}")
            return ToolResult(
                success=False,
                output="",
                error=str(e)
            )
