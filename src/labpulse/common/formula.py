"""Validate and compile the small arithmetic language used by custom readings."""

from __future__ import annotations

import ast
from dataclasses import dataclass
import math


_BINARY_OPERATORS: dict[type[ast.operator], str] = {
    ast.Add: "+",
    ast.Sub: "-",
    ast.Mult: "*",
    ast.Div: "/",
}
_UNARY_OPERATORS: dict[type[ast.unaryop], str] = {
    ast.UAdd: "+",
    ast.USub: "-",
}


@dataclass(frozen=True)
class CompiledFormula:
    """One validated expression and every runtime divisor it contains."""

    expression: str
    names: frozenset[str]
    divisors: tuple[str, ...]


def compile_formula(formula: str, allowed_names: set[str]) -> CompiledFormula:
    """Compile a restricted numeric expression into Home Assistant-safe syntax."""

    if not formula.strip():
        raise ValueError("formula must not be blank")
    if len(formula) > 500:
        raise ValueError("formula must be at most 500 characters")
    try:
        tree = ast.parse(formula, mode="eval")
    except SyntaxError as error:
        raise ValueError(f"formula is not valid arithmetic: {error.msg}") from error

    if sum(1 for _ in ast.walk(tree)) > 100:
        raise ValueError("formula is too complex")

    names: set[str] = set()
    divisors: list[str] = []

    def render(node: ast.AST) -> str:
        """Validate and render one node from the restricted expression tree."""

        if isinstance(node, ast.Expression):
            return render(node.body)
        if isinstance(node, ast.Name):
            if node.id not in allowed_names:
                raise ValueError(f"formula uses unknown name: {node.id}")
            names.add(node.id)
            return node.id
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
                raise ValueError("formula constants must be finite numbers")
            value = float(node.value)
            if not math.isfinite(value):
                raise ValueError("formula constants must be finite numbers")
            return repr(node.value)
        if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPERATORS:
            return f"({_UNARY_OPERATORS[type(node.op)]}{render(node.operand)})"
        if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPERATORS:
            left = render(node.left)
            right = render(node.right)
            if isinstance(node.op, ast.Div):
                divisors.append(right)
            return f"({left} {_BINARY_OPERATORS[type(node.op)]} {right})"
        raise ValueError("formula may only use names, numbers, parentheses, +, -, *, and /")

    expression = render(tree)
    return CompiledFormula(expression=expression, names=frozenset(names), divisors=tuple(divisors))
