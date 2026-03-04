"""
自定义工具示例 - 展示如何创建和注册自己的工具
"""
from typing import Any, Dict
from loguru import logger
from app.agent.tools.base import BaseTool, ToolResult


# ============================================================================
# 示例 1: 简单的计算器工具（已实现）
# ============================================================================

class SimpleCalculatorTool(BaseTool):
    """
    简单计算器工具示例
    
    这个工具展示了如何创建一个安全的数学计算工具
    """
    
    @property
    def name(self) -> str:
        return "simple_calculator"
    
    @property
    def description(self) -> str:
        return """执行简单的数学加法运算。
        
        示例:
        - "5 + 3" -> 8
        - "10 + 20" -> 30
        """
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "a": {
                    "type": "number",
                    "description": "第一个加数"
                },
                "b": {
                    "type": "number",
                    "description": "第二个加数"
                }
            },
            "required": ["a", "b"]
        }
    
    def execute(self, a: float, b: float) -> ToolResult:
        """执行加法计算"""
        try:
            result = a + b
            logger.info(f"计算：{a} + {b} = {result}")
            return ToolResult(
                success=True,
                output=f"{a} + {b} = {result}"
            )
        except Exception as e:
            logger.error(f"计算失败：{e}")
            return ToolResult(
                success=False,
                output="",
                error=str(e)
            )


# ============================================================================
# 示例 2: 文件读取工具
# ============================================================================

class FileReadTool(BaseTool):
    """
    文件读取工具示例
    
    安全地读取文件内容，限制在指定目录内
    """
    
    def __init__(self, base_dir: str = None):
        from app.core.config import settings
        self.base_dir = base_dir or settings.DATA_RAW_DIR
    
    @property
    def name(self) -> str:
        return "read_file"
    
    @property
    def description(self) -> str:
        return f"""读取指定文件的内容。
        
        工作目录：{self.base_dir}
        
        用途:
        - 读取文本文件
        - 查看配置文件
        - 获取数据文件内容
        
        注意：只能读取文件，不能修改或删除。
        """
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "要读取的文件名或相对路径"
                },
                "max_lines": {
                    "type": "integer",
                    "description": "最大读取行数，默认 100",
                    "default": 100
                }
            },
            "required": ["filename"]
        }
    
    def execute(self, filename: str, max_lines: int = 100) -> ToolResult:
        """读取文件内容"""
        try:
            from pathlib import Path
            
            # 安全检查：防止路径遍历攻击
            file_path = Path(self.base_dir) / filename
            if not str(file_path.resolve()).startswith(str(Path(self.base_dir).resolve())):
                return ToolResult(
                    success=False,
                    output="",
                    error="不安全的路径访问"
                )
            
            if not file_path.exists():
                return ToolResult(
                    success=False,
                    output="",
                    error=f"文件不存在：{filename}"
                )
            
            logger.info(f"读取文件：{file_path}")
            
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = []
                for i, line in enumerate(f):
                    if i >= max_lines:
                        lines.append(f"... (已截断，共读取 {max_lines} 行)")
                        break
                    lines.append(line.rstrip())
            
            content = '\n'.join(lines)
            
            return ToolResult(
                success=True,
                output=f"文件内容 ({len(lines)} 行):\n\n{content}"
            )
            
        except Exception as e:
            logger.error(f"读取文件失败：{e}")
            return ToolResult(
                success=False,
                output="",
                error=str(e)
            )


# ============================================================================
# 示例 3: API 调用工具
# ============================================================================

class APICallTool(BaseTool):
    """
    HTTP API 调用工具示例
    
    用于发送 HTTP 请求并获取响应
    """
    
    def __init__(self, allowed_domains: list = None):
        self.allowed_domains = allowed_domains or [
            "api.example.com",
            "jsonplaceholder.typicode.com"
        ]
    
    @property
    def name(self) -> str:
        return "http_request"
    
    @property
    def description(self) -> str:
        return f"""发送 HTTP GET 请求。
        
        允许的域名：{', '.join(self.allowed_domains)}
        
        用途:
        - 获取 API 数据
        - 查询网络资源
        - 获取实时信息
        """
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "endpoint": {
                    "type": "string",
                    "description": "API 端点路径，如 '/users/1'"
                },
                "domain": {
                    "type": "string",
                    "description": f"目标域名，必须是：{', '.join(self.allowed_domains)}"
                }
            },
            "required": ["endpoint", "domain"]
        }
    
    def execute(self, endpoint: str, domain: str) -> ToolResult:
        """发送 HTTP 请求"""
        # 安全检查：验证域名
        if domain not in self.allowed_domains:
            return ToolResult(
                success=False,
                output="",
                error=f"不允许的域名：{domain}"
            )
        
        try:
            import requests
            
            url = f"https://{domain}{endpoint}"
            logger.info(f"发送请求：GET {url}")
            
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            
            # 尝试解析 JSON
            try:
                data = response.json()
                content = f"JSON 响应:\n{data}"
            except:
                content = f"文本响应:\n{response.text[:500]}"
            
            return ToolResult(
                success=True,
                output=f"状态码：{response.status_code}\n\n{content}"
            )
            
        except requests.exceptions.RequestException as e:
            logger.error(f"HTTP 请求失败：{e}")
            return ToolResult(
                success=False,
                output="",
                error=f"请求失败：{str(e)}"
            )


# ============================================================================
# 示例 4: 数据库查询工具
# ============================================================================

class DatabaseQueryTool(BaseTool):
    """
    数据库查询工具示例
    
    执行只读的 SQL 查询
    """
    
    def __init__(self, database_url: str = None):
        self.database_url = database_url or "sqlite:///example.db"
    
    @property
    def name(self) -> str:
        return "db_query"
    
    @property
    def description(self) -> str:
        return """执行 SQL SELECT 查询。
        
        用途:
        - 查询数据库记录
        - 统计数据
        - 获取报表信息
        
        注意：只能执行 SELECT 查询，不能修改数据。
        """
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "SQL SELECT 查询语句"
                }
            },
            "required": ["query"]
        }
    
    def execute(self, query: str) -> ToolResult:
        """执行数据库查询"""
        # 安全检查：只允许 SELECT 语句
        query_upper = query.strip().upper()
        if not query_upper.startswith("SELECT"):
            return ToolResult(
                success=False,
                output="",
                error="只允许执行 SELECT 查询语句"
            )
        
        try:
            import sqlite3
            from contextlib import closing
            
            logger.info(f"执行 SQL 查询：{query}")
            
            with closing(sqlite3.connect(self.database_url)) as conn:
                with closing(conn.cursor()) as cursor:
                    cursor.execute(query)
                    rows = cursor.fetchall()
                    
                    if not rows:
                        return ToolResult(
                            success=True,
                            output="查询结果为空"
                        )
                    
                    # 格式化输出
                    columns = [desc[0] for desc in cursor.description]
                    output_lines = [f"列：{', '.join(columns)}"]
                    output_lines.append("-" * 50)
                    
                    for i, row in enumerate(rows[:20], 1):  # 限制显示 20 行
                        row_str = ", ".join(str(val) for val in row)
                        output_lines.append(f"[{i}] {row_str}")
                    
                    if len(rows) > 20:
                        output_lines.append(f"... (还有 {len(rows) - 20} 行)")
                    
                    return ToolResult(
                        success=True,
                        output="\n".join(output_lines)
                    )
        
        except Exception as e:
            logger.error(f"数据库查询失败：{e}")
            return ToolResult(
                success=False,
                output="",
                error=f"查询错误：{str(e)}"
            )


# ============================================================================
# 使用示例
# ============================================================================

def demo_custom_tools():
    """演示如何使用自定义工具"""
    from app.agent import Agent
    from app.agent.tools import get_default_tools
    
    # 创建自定义工具列表
    custom_tools = [
        SimpleCalculatorTool(),
        FileReadTool(),
        # APICallTool(),  # 需要时启用
        # DatabaseQueryTool(),  # 需要时启用
    ]
    
    # 将自定义工具添加到默认工具中
    all_tools = get_default_tools() + custom_tools
    
    # 创建 Agent
    agent = Agent(tools=all_tools)
    
    # 测试自定义工具
    print("\n=== 测试简单计算器 ===")
    answer = agent.run("计算 5 + 3 等于多少？")
    print(answer)
    
    print("\n=== 测试文件读取 ===")
    answer = agent.run("读取 README.md 文件的前 10 行")
    print(answer)


if __name__ == "__main__":
    demo_custom_tools()
