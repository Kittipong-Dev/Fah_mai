# -*- coding: utf-8 -*-
"""Deterministic arithmetic evaluator for the compute node (PAL pattern).

safe_eval("5 * rate", {"rate": 8384324}) -> 41921620.0

Only whitelisted AST nodes are allowed: numbers, named operands, +-*/%**, unary minus,
parentheses, and a small set of functions (round, abs, min, max, sum, len). Anything else
(attribute access, calls to other names, comprehensions, imports) raises ValueError. This
means an LLM-emitted expression can never execute arbitrary code.
"""
from __future__ import annotations

import ast
import operator

_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARYOPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_FUNCS = {"round": round, "abs": abs, "min": min, "max": max, "sum": sum, "len": len}


def safe_eval(expression: str, operands: dict | None = None) -> float:
    """Evaluate an arithmetic expression with named operands. Raises ValueError on anything unsafe."""
    operands = operands or {}
    tree = ast.parse(expression, mode="eval")

    def _ev(node):
        if isinstance(node, ast.Expression):
            return _ev(node.body)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return node.value
            raise ValueError(f"non-numeric constant: {node.value!r}")
        if isinstance(node, ast.Name):
            if node.id in operands:
                return operands[node.id]
            raise ValueError(f"unknown operand: {node.id}")
        if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
            return _BINOPS[type(node.op)](_ev(node.left), _ev(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARYOPS:
            return _UNARYOPS[type(node.op)](_ev(node.operand))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS:
            args = [_ev(a) for a in node.args]
            # min/max/sum may receive a single list arg
            if len(args) == 1 and isinstance(args[0], (list, tuple)):
                return _FUNCS[node.func.id](args[0])
            return _FUNCS[node.func.id](*args)
        if isinstance(node, (ast.List, ast.Tuple)):
            return [_ev(e) for e in node.elts]
        raise ValueError(f"disallowed expression node: {type(node).__name__}")

    result = _ev(tree)
    if isinstance(result, bool) or not isinstance(result, (int, float)):
        raise ValueError(f"expression did not evaluate to a number: {result!r}")
    return float(result)
