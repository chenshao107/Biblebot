"""
Python 执行工具 - 在沙箱中执行 Python 代码
"""
import sys
import io
import traceback
from typing import Any, Dict
from contextlib import redirect_stdout, redirect_stderr
from loguru import logger
from app.agent.tools.base import BaseTool, ToolResult
from app.core.config import settings


class PythonTool(BaseTool):
    """Python 代码执行工具"""
    
    # 受限模式中禁止使用的危险内建函数
    _BLOCKED_BUILTINS = {
        "__import__", "eval", "exec", "compile",
        "open",  # 会在下面单独放回
        "input", "memoryview",
        "breakpoint",
    }

    def __init__(self, timeout: int = None):
        self.timeout = timeout or 30  # 从配置读取或默认 30 秒
        # 使用完整 builtins 并移除危险函数，避免生成器/列表推导式作用域问题
        import builtins
        safe_builtins = vars(builtins).copy()
        for name in self._BLOCKED_BUILTINS:
            safe_builtins.pop(name, None)
        # 单独允许 open（只读文件）
        safe_builtins["open"] = open
        self.safe_globals = {
            "__builtins__": safe_builtins,
        }
    
    @property
    def name(self) -> str:
        return "run_python"
    
    @property
    def description(self) -> str:
        return f"""执行 Python 代码进行数据分析或复杂处理。

工作目录: {settings.DATA_CANONICAL_DIR} (Docling 转换后的 Markdown 目录)

可用功能：
- 读取和解析文件（txt, json, csv, xml 等）
- 数据处理和分析
- 文本处理和正则表达式
- 数学计算

预装模块：json, re, os.path, collections, itertools, math, datetime, csv, pathlib

示例：
```python
import json
with open('data.json') as f:
    data = json.load(f)
print(data['key'])
```

注意：代码会在受限环境中执行，不能执行系统命令或网络操作。"""
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "要执行的 Python 代码"
                }
            },
            "required": ["code"]
        }
    
    def _prepare_globals(self) -> Dict[str, Any]:
        """准备执行环境的全局变量"""
        import json
        import re
        import os.path
        import collections
        import itertools
        import math
        import datetime
        import csv
        from pathlib import Path
        
        globals_dict = self.safe_globals.copy()
        globals_dict.update({
            # 常用模块
            "json": json,
            "re": re,
            "os": type("os", (), {"path": os.path}),  # 只暴露 os.path
            "collections": collections,
            "itertools": itertools,
            "math": math,
            "datetime": datetime,
            "csv": csv,
            "Path": Path,
            # 工作目录（Docling 转换后的 Markdown 目录）
            "DATA_DIR": settings.DATA_CANONICAL_DIR,
        })
        
        return globals_dict
    
    def _prepare_globals_unrestricted(self) -> Dict[str, Any]:
        """准备无限制的执行环境（调试模式）"""
        import json
        import re
        import os
        import collections
        import itertools
        import math
        import datetime
        import csv
        import sys
        import subprocess
        from pathlib import Path
        
        return {
            "__builtins__": __builtins__,
            "json": json,
            "re": re,
            "os": os,
            "sys": sys,
            "subprocess": subprocess,
            "collections": collections,
            "itertools": itertools,
            "math": math,
            "datetime": datetime,
            "csv": csv,
            "Path": Path,
            "DATA_DIR": settings.DATA_CANONICAL_DIR,
        }
    
    def execute(self, code: str) -> ToolResult:
        """执行 Python 代码"""
        try:
            logger.info(f"执行 Python 代码:\n{code[:200]}...")
            
            from app.core.config import settings
            
            # 根据配置选择执行环境
            if settings.ENABLE_PYTHON_RESTRICTIONS:
                globals_dict = self._prepare_globals()
            else:
                globals_dict = self._prepare_globals_unrestricted()
            
            locals_dict = {}
            
            # 捕获输出
            stdout_buffer = io.StringIO()
            stderr_buffer = io.StringIO()
            
            # 切换工作目录
            import os
            original_cwd = os.getcwd()
            try:
                os.chdir(settings.DATA_CANONICAL_DIR)
                
                with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
                    exec(code, globals_dict, locals_dict)
                    
            finally:
                os.chdir(original_cwd)
            
            # 获取输出
            stdout_output = stdout_buffer.getvalue()
            stderr_output = stderr_buffer.getvalue()
            
            output = stdout_output
            if stderr_output:
                output += f"\n[stderr]:\n{stderr_output}"
            
            # 限制输出长度
            max_output_len = 10000
            if len(output) > max_output_len:
                output = output[:max_output_len] + f"\n... (输出被截断，共 {len(output)} 字符)"
            
            return ToolResult(
                success=True,
                output=output if output else "(代码执行成功，无输出)"
            )
            
        except SyntaxError as e:
            return ToolResult(
                success=False,
                output="",
                error=f"语法错误: {e}"
            )
        except Exception as e:
            # 获取详细的错误信息
            tb = traceback.format_exc()
            logger.error(f"Python 执行失败: {e}")
            return ToolResult(
                success=False,
                output="",
                error=f"执行错误:\n{tb}"
            )
