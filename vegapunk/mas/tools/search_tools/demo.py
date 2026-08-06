"""
Weather Tool - 天气查询工具函数
"""

import asyncio
import ast
import math
import logging
import molbloom
from typing import Any, Callable, Dict, List
from vegapunk.mas.models.runtime import FunctionTool

logger = logging.getLogger(__name__)


_MAX_EXPRESSION_LENGTH = 1_000
_MAX_AST_NODES = 100
_MAX_POWER_EXPONENT = 1_000

_MATH_FUNCTIONS: Dict[str, Callable[..., float]] = {
    "sqrt": math.sqrt,
    "pow": math.pow,
    "abs": abs,
    "round": round,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "log": math.log,
    "exp": math.exp,
}
_MATH_CONSTANTS = {"pi": math.pi, "e": math.e}


def _safe_math_expression(expression: str) -> float:
    """Evaluate the small arithmetic language exposed by ``calculate``.

    ``eval`` is deliberately avoided here. Even with an empty ``__builtins__``
    mapping, Python objects expose introspection attributes that can be chained
    into arbitrary code execution. An AST whitelist gives the tool an explicit
    language boundary instead of trying to make Python itself safe.
    """

    if not isinstance(expression, str):
        raise TypeError("expression must be a string")
    if len(expression) > _MAX_EXPRESSION_LENGTH:
        raise ValueError("expression is too long")

    tree = ast.parse(expression, mode="eval")
    if sum(1 for _ in ast.walk(tree)) > _MAX_AST_NODES:
        raise ValueError("expression is too complex")

    def evaluate(node: ast.AST) -> float:
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool) or not isinstance(
                node.value, (int, float)
            ):
                raise ValueError("only finite numeric constants are allowed")
            value = float(node.value)
            if not math.isfinite(value):
                raise ValueError("numeric constants must be finite")
            return value

        if isinstance(node, ast.Name):
            if node.id in _MATH_CONSTANTS:
                return _MATH_CONSTANTS[node.id]
            raise ValueError(f"unknown name: {node.id}")

        if isinstance(node, ast.UnaryOp) and isinstance(
            node.op, (ast.UAdd, ast.USub)
        ):
            value = evaluate(node.operand)
            return value if isinstance(node.op, ast.UAdd) else -value

        if isinstance(node, ast.BinOp) and isinstance(
            node.op,
            (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod, ast.Pow),
        ):
            left = evaluate(node.left)
            right = evaluate(node.right)
            if isinstance(node.op, ast.Add):
                value = left + right
            elif isinstance(node.op, ast.Sub):
                value = left - right
            elif isinstance(node.op, ast.Mult):
                value = left * right
            elif isinstance(node.op, ast.Div):
                value = left / right
            elif isinstance(node.op, ast.Mod):
                value = left % right
            else:
                if abs(right) > _MAX_POWER_EXPONENT:
                    raise ValueError("power exponent is too large")
                value = left**right
            if not math.isfinite(value):
                raise ValueError("result is not finite")
            return value

        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in _MATH_FUNCTIONS:
                raise ValueError("only approved math functions may be called")
            if node.keywords:
                raise ValueError("keyword arguments are not supported")
            if len(node.args) > 2:
                raise ValueError("too many function arguments")
            value = _MATH_FUNCTIONS[node.func.id](
                *(evaluate(argument) for argument in node.args)
            )
            if not math.isfinite(value):
                raise ValueError("result is not finite")
            return float(value)

        raise ValueError(
            f"unsupported expression element: {type(node).__name__}"
        )

    return evaluate(tree.body)

# 工具的元数据定义
CALCULATOR_TOOL_DEFINITION = FunctionTool(
        name="calculate",
        description="Perform mathematical calculations. Supports +, -, *, /, **, sqrt, sin, cos, etc.",
        parameters={
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "Mathematical expression to calculate, e.g., '2 + 3 * 4' or 'sqrt(16)'"
                }
            },
            "required": ["expression"]
        },
)

# Tool definition for agent
PATENT_CHECK_TOOL = FunctionTool(
        name="patent_check",
        description=(
            "Check if a molecule is patented by querying the SureChEMBL patent database. "
            "This tool determines whether a compound has been patented or is novel. "
            "You can input a single SMILES string or multiple SMILES strings separated by periods. "
            "Returns 'Patented' if the molecule is found in patents, or 'Novel' if not found."
        ),
        parameters={
            "type": "object",
            "properties": {
                "smiles": {
                    "type": "string",
                    "description": (
                        "SMILES string(s) to check for patent status. "
                        "Can be a single SMILES (e.g., 'CC(=O)OC1=CC=CC=C1C(=O)O') "
                        "or multiple SMILES separated by periods (e.g., 'CCO.CC(C)O.c1ccccc1'). "
                        "Each SMILES will be checked independently."
                    )
                }
            },
            "required": ["smiles"]
        },
)

async def calculate(expression: str) -> Dict[str, Any]:
    """
    执行数学计算
    
    Args:
        expression: 数学表达式字符串
    
    Returns:
        包含计算结果的字典
    """
    logger.info(f"Calculating: {expression}")
    
    try:
        result = _safe_math_expression(expression)
        
        output = {
            "expression": expression,
            "result": float(result),
            "success": True
        }
        
        logger.info(f"Result: {expression} = {result}")
        return output
        
    except Exception as e:
        logger.error(f"Calculation error: {e}")
        return {
            "expression": expression,
            "error": str(e),
            "success": False
        }


def is_smiles(text: str) -> bool:
    """Check if text is a valid SMILES string"""
    import re
    smiles_pattern = r'^[A-Za-z0-9@+\-\[\]\(\)=#$:/\\\.%]+$'
    return bool(re.match(smiles_pattern, text))


def is_multiple_smiles(text: str) -> bool:
    """Check if text contains multiple SMILES strings (separated by periods)"""
    # 检查是否有多个分子（通常用.分隔）
    parts = text.split('.')
    # 确保不是分子内部的点（如芳香环）
    return len(parts) > 1 and all(len(p.strip()) > 0 for p in parts)


def split_smiles(text: str) -> List[str]:
    """Split multiple SMILES strings separated by periods"""
    return [s.strip() for s in text.split('.') if s.strip()]


async def patent_check(smiles: str) -> Dict[str, Any]:
    """
    Check if molecule(s) are patented by querying SureChEMBL database.
    
    Args:
        smiles: SMILES string(s). Can be a single SMILES or multiple SMILES separated by periods.
        
    Returns:
        Dictionary containing:
            - success: Boolean indicating if check was successful
            - results: Dictionary mapping SMILES to patent status ("Patented" or "Novel")
            - error: Error message if check failed
            - message: Human-readable summary
    """
    logger.info(f"PatentCheck: Checking patent status for: {smiles}")
    
    # Validate input
    if not smiles or not isinstance(smiles, str):
        return {
            "success": False,
            "error": "Invalid input: SMILES string is required"
        }
    
    # Parse input SMILES
    if is_multiple_smiles(smiles):
        smiles_list = split_smiles(smiles)
        logger.info(f"Detected {len(smiles_list)} SMILES strings")
    else:
        smiles_list = [smiles]
    
    try:
        results = {}
        
        for smi in smiles_list:
            logger.debug(f"Checking patent status for: {smi}")
            
            try:
                # Query SureChEMBL database via molbloom
                is_patented = molbloom.buy(smi, canonicalize=True, catalog="surechembl")
                
                if is_patented:
                    results[smi] = "Patented"
                    logger.info(f"{smi} is patented")
                else:
                    results[smi] = "Novel"
                    logger.info(f"{smi} is novel (not patented)")
                    
            except Exception as e:
                logger.warning(f"Error checking {smi}: {e}")
                results[smi] = f"Error: {str(e)}"
        
        # Create summary message
        patented_count = sum(1 for v in results.values() if v == "Patented")
        novel_count = sum(1 for v in results.values() if v == "Novel")
        error_count = sum(1 for v in results.values() if v.startswith("Error"))
        
        summary_parts = []
        if patented_count > 0:
            summary_parts.append(f"{patented_count} patented")
        if novel_count > 0:
            summary_parts.append(f"{novel_count} novel")
        if error_count > 0:
            summary_parts.append(f"{error_count} errors")
        
        message = f"Patent check completed: {', '.join(summary_parts)}"
        
        return {
            "success": True,
            "results": results,
            "message": message,
            "summary": {
                "total": len(results),
                "patented": patented_count,
                "novel": novel_count,
                "errors": error_count
            }
        }
        
    except Exception as e:
        error_msg = f"Failed to check patent status: {str(e)}"
        logger.error(f"PatentCheck failed: {e}", exc_info=True)
        return {
            "success": False,
            "error": error_msg
        }
