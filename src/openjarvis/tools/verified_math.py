"""Exact rational arithmetic and checked linear/quadratic equations.

No eval, symbolic parser, model or network. The grammar and numerical work
are bounded before arithmetic, including exponentiation and integer sizes.
"""

from __future__ import annotations

import ast
import json
import math
import re
from fractions import Fraction
from typing import Any

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools._stubs import BaseTool, ToolSpec

Poly = list[Fraction]


def bounded(values: Poly) -> Poly:
    if any(
        max(v.numerator.bit_length(), v.denominator.bit_length()) > 4096 for v in values
    ):
        raise ValueError("El cálculo excede el límite de tamaño.")
    while len(values) > 1 and values[-1] == 0:
        values.pop()
    if len(values) > 3:
        raise ValueError("Solo ecuaciones de grado 1 o 2.")
    return values


def combine(a: Poly, b: Poly, multiply: bool = False) -> Poly:
    out = [Fraction(0)] * (len(a) + len(b) - 1 if multiply else max(len(a), len(b)))
    if multiply:
        for i, left in enumerate(a):
            for j, right in enumerate(b):
                out[i + j] += left * right
    else:
        for items in (a, b):
            for i, value in enumerate(items):
                out[i] += value
    return bounded(out)


def polynomial(expression: str, variable: str = "x") -> Poly:
    if not isinstance(expression, str) or not expression or len(expression) > 1000:
        raise ValueError("Expresión vacía o demasiado larga.")
    source = expression.replace("^", "**")
    tree = ast.parse(source, mode="eval")
    if sum(1 for _ in ast.walk(tree)) > 200:
        raise ValueError("Expresión demasiado compleja.")

    def visit(node: ast.AST) -> Poly:
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            literal = ast.get_source_segment(source, node) or str(node.value)
            exponent = re.search(r"[eE]([+-]?\d+)$", literal.replace("_", ""))
            if exponent and abs(int(exponent[1])) > 500:
                raise ValueError("Exponente decimal fuera del límite.")
            # Keep the typed decimal, even when Python's float rounds it.
            value = (
                Fraction(node.value) if type(node.value) is int else Fraction(literal)
            )
            return bounded([value])
        if isinstance(node, ast.Name) and node.id == variable:
            return [Fraction(0), Fraction(1)]
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            return [
                v * (-1 if isinstance(node.op, ast.USub) else 1)
                for v in visit(node.operand)
            ]
        if isinstance(node, ast.BinOp):
            a, b = visit(node.left), visit(node.right)
            if isinstance(node.op, (ast.Add, ast.Sub)):
                return combine(
                    a, [v * (-1 if isinstance(node.op, ast.Sub) else 1) for v in b]
                )
            if isinstance(node.op, ast.Mult):
                return combine(a, b, True)
            if isinstance(node.op, ast.Div) and len(b) == 1:
                return bounded([v / b[0] for v in a])
            if isinstance(node.op, ast.Pow) and len(b) == 1 and b[0].denominator == 1:
                power = int(b[0])
                if not 0 <= power <= 8:
                    raise ValueError("Exponente permitido: entero entre 0 y 8.")
                result = [Fraction(1)]
                for _ in range(power):
                    result = combine(result, a, True)
                return result
        raise ValueError(
            "Use números, x, paréntesis y + - * / **; sin funciones ni código."
        )

    return visit(tree.body)


def verified(expression: str, variable: str = "x") -> dict[str, Any]:
    if not variable.isidentifier() or len(variable) > 16:
        raise ValueError("Variable no válida.")
    if "=" not in expression:
        values = polynomial(expression, variable)
        if len(values) != 1:
            raise ValueError("Falta una ecuación para resolver la variable.")
        return {
            "exact": str(values[0]),
            "decimal": float(values[0]),
            "verified": True,
            "method": "aritmética racional exacta",
        }
    if expression.count("=") != 1:
        raise ValueError("Use una sola igualdad.")
    left, right = expression.split("=")
    a, b = polynomial(left.strip(), variable), polynomial(right.strip(), variable)
    coefficients = combine(a, [-v for v in b])
    if len(coefficients) == 1:
        return {
            "solutions": [],
            "kind": "identity" if coefficients[0] == 0 else "inconsistent",
            "verified": True,
        }
    if len(coefficients) == 2:
        roots = [-coefficients[0] / coefficients[1]]
    else:
        c, b1, a2 = coefficients
        discriminant = b1 * b1 - 4 * a2 * c
        if discriminant < 0:
            return {"solutions": [], "kind": "no_real_roots", "verified": True}
        n, d = math.isqrt(discriminant.numerator), math.isqrt(discriminant.denominator)
        if n * n != discriminant.numerator or d * d != discriminant.denominator:
            return {
                "kind": "irrational",
                "coefficients": [str(v) for v in coefficients],
                "discriminant": str(discriminant),
                "verified": False,
                "note": "Raíces irracionales: no se afirma una verificación racional exacta.",
            }
        root = Fraction(n, d)
        roots = list(dict.fromkeys([(-b1 + root) / (2 * a2), (-b1 - root) / (2 * a2)]))
    checks = [sum(v * r**i for i, v in enumerate(coefficients)) for r in roots]
    return {
        "solutions": [str(r) for r in roots],
        "variable": variable,
        "residuals": [str(c) for c in checks],
        "verified": all(c == 0 for c in checks),
        "method": "raíces sustituidas en la ecuación original",
    }


@ToolRegistry.register("verified_math")
class VerifiedMathTool(BaseTool):
    tool_id = "verified_math"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.tool_id,
            category="math",
            description=(
                "Exact rational arithmetic and linear/quadratic equations. Returns checked roots "
                "and residuals, not a model's guess. Example: 0.1+0.2 or 2*x+3=11. "
                "Explicit multiplication is required. Unsupported problems are reported honestly."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "expression": {"type": "string"},
                    "variable": {"type": "string", "default": "x"},
                },
                "required": ["expression"],
            },
        )

    def execute(self, **params: Any) -> ToolResult:
        try:
            result = verified(
                str(params.get("expression") or ""), str(params.get("variable") or "x")
            )
            return ToolResult(
                tool_name=self.tool_id,
                content=json.dumps(result, ensure_ascii=False),
                success=True,
            )
        except (
            ValueError,
            SyntaxError,
            ZeroDivisionError,
            OverflowError,
            RecursionError,
        ) as exc:
            return ToolResult(
                tool_name=self.tool_id, content=f"No verificado: {exc}", success=False
            )


__all__ = ["VerifiedMathTool", "verified"]
