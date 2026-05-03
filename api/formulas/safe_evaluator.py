"""
Safe expression evaluator for formulas.

This module provides a secure alternative to eval() for evaluating
mathematical and logical expressions in formulas.
"""
import ast
import operator
import logging
from typing import Any, Dict, Union

logger = logging.getLogger(__name__)

# Safe operators mapping
SAFE_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
    # Comparison operators
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    # Logical operators
    ast.And: lambda a, b: a and b,
    ast.Or: lambda a, b: a or b,
    ast.Not: operator.not_,
}


class SafeExpressionEvaluator:
    """
    Safely evaluates mathematical and logical expressions without using eval().
    
    This class uses AST (Abstract Syntax Tree) parsing to evaluate expressions
    securely, preventing code injection attacks.
    """
    
    def __init__(self, max_recursion_depth: int = 100):
        """
        Initialize the safe evaluator.
        
        Args:
            max_recursion_depth: Maximum depth for expression evaluation
        """
        self.max_recursion_depth = max_recursion_depth
        self._recursion_depth = 0
    
    def evaluate(self, expression: str, context: Dict[str, Any] = None) -> Any:
        """
        Safely evaluate an expression with given context.
        
        Args:
            expression: The expression string to evaluate
            context: Dictionary of variable names to values
            
        Returns:
            The evaluated result
            
        Raises:
            ValueError: If the expression is invalid or unsafe
            RecursionError: If max recursion depth is exceeded
        """
        if context is None:
            context = {}
        
        try:
            # Parse the expression into an AST
            tree = ast.parse(expression, mode='eval')
            self._recursion_depth = 0
            return self._eval_node(tree.body, context)
        except SyntaxError as e:
            logger.error(f"Syntax error in expression '{expression}': {e}")
            raise ValueError(f"Invalid expression syntax: {e}")
        except Exception as e:
            logger.debug(f"Error evaluating expression '{expression}': {e}")
            raise
    
    def _eval_node(self, node: ast.AST, context: Dict[str, Any]) -> Any:
        """
        Recursively evaluate an AST node.
        
        Args:
            node: The AST node to evaluate
            context: Dictionary of variable names to values
            
        Returns:
            The evaluated result
            
        Raises:
            ValueError: If the node type is not allowed
            RecursionError: If max recursion depth is exceeded
        """
        self._recursion_depth += 1
        if self._recursion_depth > self.max_recursion_depth:
            raise RecursionError("Maximum recursion depth exceeded in expression evaluation")
        
        try:
            if isinstance(node, ast.Constant):  # Python 3.8+
                return node.value
            elif isinstance(node, ast.Num):  # Fallback for older Python versions
                return node.n
            elif isinstance(node, ast.Str):  # Fallback for older Python versions
                return node.s
            elif isinstance(node, ast.Name):
                # Variable reference
                if node.id not in context:
                    raise ValueError(f"Undefined variable: {node.id}")
                return context[node.id]
            elif isinstance(node, ast.BinOp):
                # Binary operation (e.g., a + b)
                left = self._eval_node(node.left, context)
                right = self._eval_node(node.right, context)
                op_type = type(node.op)
                if op_type not in SAFE_OPERATORS:
                    raise ValueError(f"Unsupported operator: {op_type.__name__}")
                return SAFE_OPERATORS[op_type](left, right)
            elif isinstance(node, ast.UnaryOp):
                # Unary operation (e.g., -a)
                operand = self._eval_node(node.operand, context)
                op_type = type(node.op)
                if op_type not in SAFE_OPERATORS:
                    raise ValueError(f"Unsupported operator: {op_type.__name__}")
                return SAFE_OPERATORS[op_type](operand)
            elif isinstance(node, ast.Compare):
                # Comparison operation (e.g., a > b)
                left = self._eval_node(node.left, context)
                result = True
                for op, comparator in zip(node.ops, node.comparators):
                    right = self._eval_node(comparator, context)
                    op_type = type(op)
                    if op_type not in SAFE_OPERATORS:
                        raise ValueError(f"Unsupported operator: {op_type.__name__}")
                    result = result and SAFE_OPERATORS[op_type](left, right)
                    if not result:
                        break
                    left = right
                return result
            elif isinstance(node, ast.BoolOp):
                # Boolean operation (e.g., a and b)
                op_type = type(node.op)
                if op_type not in SAFE_OPERATORS:
                    raise ValueError(f"Unsupported operator: {op_type.__name__}")
                
                values = [self._eval_node(v, context) for v in node.values]
                result = values[0]
                for value in values[1:]:
                    result = SAFE_OPERATORS[op_type](result, value)
                return result
            elif isinstance(node, ast.IfExp):
                # Ternary expression (e.g., a if condition else b)
                test = self._eval_node(node.test, context)
                if test:
                    return self._eval_node(node.body, context)
                else:
                    return self._eval_node(node.orelse, context)
            else:
                raise ValueError(f"Unsupported expression type: {type(node).__name__}")
        finally:
            self._recursion_depth -= 1


def safe_evaluate(expression: str, context: Dict[str, Any] = None) -> Any:
    """
    Convenience function to safely evaluate an expression.
    
    Args:
        expression: The expression string to evaluate
        context: Dictionary of variable names to values
        
    Returns:
        The evaluated result
        
    Raises:
        ValueError: If the expression is invalid or unsafe
    """
    evaluator = SafeExpressionEvaluator()
    return evaluator.evaluate(expression, context)
