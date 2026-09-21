"""Räknade kolumner i mängdtabellen, utan att någonsin köra användarens kod.

En mängdare vill skriva `Yta * Spill` eller `Mangd * Apris` och få en kolumn. Det är en formel, inte ett
program: den läses till ett uttrycksträd av tal, namn, fyra räknesätt och en handfull funktioner, och trädet
räknas ut. Ingenting annat går att uttrycka, så ingenting annat kan hända - ingen import, ingen attributåtkomst,
ingen loop som aldrig tar slut, inget anrop till något som inte står i listan nedan.

Formler får referera andra formler. Ordningen räknas ut ur beroendena, och en cirkel avvisas med namnen i
felet i stället för att köra tills stacken tar slut.
"""
from __future__ import annotations

import ast
import math
from typing import Any, Iterable

MAX_LENGTH = 500

FUNCTIONS: dict[str, Any] = {
    "abs": abs, "min": min, "max": max, "round": round,
    "sqrt": math.sqrt, "floor": math.floor, "ceil": math.ceil,
    "sum": lambda *xs: float(sum(xs)),
    "om": lambda villkor, ja, nej: ja if villkor else nej,      # om(A > B; A; B)
}

_ALLOWED_NODES = (
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant, ast.Name, ast.Load, ast.Call,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow, ast.USub, ast.UAdd,
    ast.Compare, ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.IfExp, ast.BoolOp, ast.And, ast.Or,
)


class FormulaError(ValueError):
    """Formeln går inte att läsa eller räkna, och kolumnen ska säga det i klartext."""


def _parse(expr: str) -> ast.Expression:
    if not isinstance(expr, str) or not expr.strip():
        raise FormulaError("formeln är tom")
    if len(expr) > MAX_LENGTH:
        raise FormulaError(f"formeln är längre än {MAX_LENGTH} tecken")
    try:
        tree = ast.parse(expr.replace(";", ","), mode="eval")
    except SyntaxError as e:
        raise FormulaError(f"formeln går inte att läsa: {e.msg}") from None
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise FormulaError(f"{type(node).__name__.lower()} hör inte hemma i en formel")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in FUNCTIONS:
                raise FormulaError("bara formelfunktionerna går att anropa: " + ", ".join(sorted(FUNCTIONS)))
            if node.keywords:
                raise FormulaError("en formelfunktion tar bara vanliga argument")
        if isinstance(node, ast.Constant) and not isinstance(node.value, (int, float, bool)):
            raise FormulaError("en formel räknar med tal")
    return tree


def referenced_names(expr: str) -> set[str]:
    """Vilka kolumner formeln läser."""
    tree = _parse(expr)
    return {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and n.id not in FUNCTIONS}


def _eval(node: ast.AST, values: dict[str, Any]) -> Any:
    if isinstance(node, ast.Expression):
        return _eval(node.body, values)
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id not in values:
            raise FormulaError(f"okänd kolumn: {node.id}")
        v = values[node.id]
        if v is None:
            return 0.0
        if isinstance(v, bool):
            return v
        try:
            return float(v)
        except (TypeError, ValueError):
            raise FormulaError(f"kolumnen {node.id} är inget tal") from None
    if isinstance(node, ast.UnaryOp):
        v = _eval(node.operand, values)
        return -v if isinstance(node.op, ast.USub) else +v
    if isinstance(node, ast.BinOp):
        a, b = _eval(node.left, values), _eval(node.right, values)
        op = node.op
        if isinstance(op, ast.Add):
            return a + b
        if isinstance(op, ast.Sub):
            return a - b
        if isinstance(op, ast.Mult):
            return a * b
        if isinstance(op, (ast.Div, ast.FloorDiv)):
            if b == 0:
                raise FormulaError("division med noll")
            return a / b if isinstance(op, ast.Div) else a // b
        if isinstance(op, ast.Mod):
            if b == 0:
                raise FormulaError("rest vid division med noll")
            return a % b
        if isinstance(op, ast.Pow):
            if abs(b) > 8:
                raise FormulaError("för hög exponent i en formel")
            return a ** b
    if isinstance(node, ast.Compare):
        left = _eval(node.left, values)
        for op, comp in zip(node.ops, node.comparators):
            right = _eval(comp, values)
            ok = {ast.Eq: left == right, ast.NotEq: left != right, ast.Lt: left < right,
                  ast.LtE: left <= right, ast.Gt: left > right, ast.GtE: left >= right}[type(op)]
            if not ok:
                return False
            left = right
        return True
    if isinstance(node, ast.BoolOp):
        vals = [_eval(v, values) for v in node.values]
        return all(vals) if isinstance(node.op, ast.And) else any(vals)
    if isinstance(node, ast.IfExp):
        return _eval(node.body, values) if _eval(node.test, values) else _eval(node.orelse, values)
    if isinstance(node, ast.Call):
        args = [_eval(a, values) for a in node.args]
        try:
            return FUNCTIONS[node.func.id](*args)
        except FormulaError:
            raise
        except Exception as e:
            raise FormulaError(f"{node.func.id}: {e}") from None
    raise FormulaError("formeln innehåller något den inte får innehålla")


def evaluate(expr: str, values: dict[str, Any]) -> float:
    """Räkna en formel mot en rads värden."""
    v = _eval(_parse(expr), values)
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    try:
        f = float(v)
    except (TypeError, ValueError):
        raise FormulaError("formeln gav inget tal") from None
    if math.isnan(f) or math.isinf(f):
        raise FormulaError("formeln gav inget ändligt tal")
    return f


def order_of_evaluation(formulas: dict[str, str], known: Iterable[str] = ()) -> list[str]:
    """I vilken ordning formlerna kan räknas, så att den som läser en annan räknas efter den.

    En cirkel är ett fel med namn: `Total` som läser `Netto` som läser `Total` går inte att räkna, och det ska
    stå vilka två det gäller i stället för att kolumnen tyst blir tom.
    """
    known = set(known)
    deps = {name: (referenced_names(expr) & set(formulas)) - {name} for name, expr in formulas.items()}
    order: list[str] = []
    done: set[str] = set()
    while len(order) < len(formulas):
        ready = sorted(n for n in formulas if n not in done and deps[n] <= done)
        if not ready:
            left = sorted(n for n in formulas if n not in done)
            raise FormulaError("formlerna hänvisar till varandra i en cirkel: " + ", ".join(left))
        order.extend(ready)
        done.update(ready)
    return order


def evaluate_all(formulas: dict[str, str], values: dict[str, Any]) -> dict[str, Any]:
    """Räkna alla formler i beroendeordning. En formel som inte går att räkna får sitt fel som text."""
    out = dict(values)
    errors: dict[str, str] = {}
    for name in order_of_evaluation(formulas, values):
        try:
            out[name] = evaluate(formulas[name], out)
        except FormulaError as e:
            out[name] = None
            errors[name] = str(e)
    if errors:
        out["_fel"] = errors
    return out
