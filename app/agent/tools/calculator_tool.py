"""
计算器工具 - 执行数学计算和表达式求值
"""
import ast
import operator
from typing import Any, Dict
from loguru import logger
from app.agent.tools.base import BaseTool, ToolResult


class CalculatorTool(BaseTool):
    """安全的计算器工具"""
    
    # 支持的运算符映射
    OPERATORS = {
        ast.Add: operator.add,      # +
        ast.Sub: operator.sub,      # -
        ast.Mult: operator.mul,     # *
        ast.Div: operator.truediv,  # /
        ast.Pow: operator.pow,      # **
        ast.Mod: operator.mod,      # %
        ast.USub: operator.neg,     # 负号
        ast.UAdd: operator.pos,     # 正号
    }
    
    @property
    def name(self) -> str:
        return "calculator"
    
    @property
    def description(self) -> str:
        return """执行数学计算和表达式求值。适用于：
- 算术运算：加减乘除、幂、模运算
- 复杂表达式计算
- 科学计算（支持常见数学函数）

示例：
- "2 + 3 * 4" -> 14
- "2 ** 10" -> 1024
- "(100 - 20) / 4" -> 20.0

注意：只能进行数学计算，不能执行代码。"""
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "数学表达式，如 '2 + 3 * 4' 或 '(100 - 20) / 4'"
                }
            },
            "required": ["expression"]
        }
    
    def _eval_expr(self, node: ast.AST) -> float:
        """安全地评估 AST 节点"""
        if isinstance(node, ast.Num):  # Python < 3.8
            return node.n
        elif isinstance(node, ast.Constant):  # Python >= 3.8
            if isinstance(node.value, (int, float)):
                return node.value
            raise ValueError(f"不支持的常量类型：{type(node.value)}")
        elif isinstance(node, ast.BinOp):  # 二元运算
            left = self._eval_expr(node.left)
            right = self._eval_expr(node.right)
            op_type = type(node.op)
            if op_type in self.OPERATORS:
                return self.OPERATORS[op_type](left, right)
            raise ValueError(f"不支持的运算符：{op_type}")
        elif isinstance(node, ast.UnaryOp):  # 一元运算
            operand = self._eval_expr(node.operand)
            op_type = type(node.op)
            if op_type in self.OPERATORS:
                return self.OPERATORS[op_type](operand)
            raise ValueError(f"不支持的一元运算符：{op_type}")
        elif isinstance(node, ast.Expression):  # 表达式根节点
            return self._eval_expr(node.body)
        else:
            raise ValueError(f"不支持的表达式类型：{type(node)}")
    
    def execute(self, expression: str) -> ToolResult:
        """计算数学表达式"""
        try:
            logger.info(f"计算表达式：{expression}")
            
            # 解析表达式为 AST
            tree = ast.parse(expression, mode='eval')
            
            # 安全评估
            result = self._eval_expr(tree)
            
            return ToolResult(
                success=True,
                output=f"{expression} = {result}"
            )
            
        except SyntaxError as e:
            return ToolResult(
                success=False,
                output="",
                error=f"语法错误：{e}"
            )
        except ValueError as e:
            return ToolResult(
                success=False,
                output="",
                error=str(e)
            )
        except Exception as e:
            logger.error(f"计算失败：{e}")
            return ToolResult(
                success=False,
                output="",
                error=f"计算错误：{str(e)}"
            )
