"""
Evaluador aritmético seguro para las fórmulas de las acciones 'calculate' de Matrix.

Solo admite números, variables del contexto, + - * / // % **, paréntesis y min/max/round/abs.
"""

from __future__ import annotations

import ast
import operator
from typing import Any, Callable, Dict, Mapping

MAX_FORMULA_LENGTH = 500
MAX_EXPONENT = 10

_BINARY: Dict[type, Callable[[Any, Any], Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY: Dict[type, Callable[[Any], Any]] = {ast.USub: operator.neg, ast.UAdd: operator.pos}
_FUNCTIONS: Dict[str, Callable[..., Any]] = {"min": min, "max": max, "round": round, "abs": abs}


class FormulaError(ValueError):
    pass


def _number(value: Any, name: str) -> float:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        try:
            return float(value) if any(c in value for c in ".eE") else int(value)
        except ValueError:
            pass
    raise FormulaError(f"La variable '{name}' no es numérica")


def parse(formula: str) -> ast.Expression:
    if not isinstance(formula, str) or not formula.strip():
        raise FormulaError("La fórmula está vacía")
    if len(formula) > MAX_FORMULA_LENGTH:
        raise FormulaError(f"La fórmula supera {MAX_FORMULA_LENGTH} caracteres")
    try:
        tree = ast.parse(formula.strip(), mode="eval")
    except SyntaxError as e:
        raise FormulaError(f"Fórmula inválida: {e.msg}") from None
    for node in ast.walk(tree):
        if isinstance(node, (ast.Expression, ast.Load, ast.Name, ast.BinOp, ast.UnaryOp)):
            continue
        if isinstance(node, tuple(_BINARY) + tuple(_UNARY)):
            continue
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            continue
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCTIONS and not node.keywords:
            continue
        raise FormulaError(f"Elemento no permitido en la fórmula: {type(node).__name__}")
    return tree


def variables(formula: str) -> set:
    tree = parse(formula)
    calls = {id(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}
    return {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and id(n) not in calls}


def evaluate(formula: str, context: Mapping[str, Any]) -> Any:
    tree = parse(formula)

    def visit(node: ast.AST) -> Any:
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            if node.id not in context:
                raise FormulaError(f"Variable desconocida: '{node.id}'")
            return _number(context[node.id], node.id)
        if isinstance(node, ast.UnaryOp):
            return _UNARY[type(node.op)](visit(node.operand))
        if isinstance(node, ast.BinOp):
            left, right = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > MAX_EXPONENT:
                raise FormulaError(f"El exponente no puede superar {MAX_EXPONENT}")
            try:
                return _BINARY[type(node.op)](left, right)
            except ZeroDivisionError:
                raise FormulaError("División por cero") from None
        if isinstance(node, ast.Call):
            return _FUNCTIONS[node.func.id](*(visit(a) for a in node.args))
        raise FormulaError(f"Elemento no permitido en la fórmula: {type(node).__name__}")

    return visit(tree)
