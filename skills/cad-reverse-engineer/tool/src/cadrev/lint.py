"""The model lint: model.py holds no dimension, so every number reaches the CAD through params.yaml."""

from __future__ import annotations

import ast
import math
import operator
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .project import Project

MODEL_LITERALS = (0, 1, 2, -1, 0.5, 90, 180, 270, 360)  # model_literals when project.yaml sets none
MODEL_IMPORTS = ("build123d", "math")
_FOLDS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}
_TEXT_TO_NUMBER = ("float", "int", "complex", "eval")
_SUM = (ast.Add, ast.Sub)


def _literal(node: ast.AST) -> float | None:
    """The value of a number literal, in any spelling (1e1, 3.0, 0x3, 3_0), or None."""
    if (
        isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float))
        and not isinstance(node.value, bool)
    ):
        return float(node.value)
    return None


def _fold(node: ast.AST) -> float | None:
    """The value of a constant expression built from number literals by arithmetic, nan where it
    cannot be computed, or None when node is not one."""
    if isinstance(node, ast.Constant):
        return _literal(node)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _FOLDS:
        operands = [_fold(node.operand)]
    elif isinstance(node, ast.BinOp) and type(node.op) in _FOLDS:
        operands = [_fold(node.left), _fold(node.right)]
    else:
        return None
    if None in operands:
        return None
    try:
        return float(_FOLDS[type(node.op)](*operands))
    except (ArithmeticError, ValueError, TypeError):  # 1/0, 2.0**1e9, a complex root
        return math.nan


def _chain(node: ast.BinOp, sign: float = 1.0) -> tuple[list[tuple[float, ast.AST]], list[ast.AST]]:
    """The operands of the chain of one commutative operator that node heads, and the BinOps
    inside it: a product's factors, or a sum's terms each with the sign it is added with, since
    a - b adds -b. Each operand is (sign, node); a product's signs are all 1."""
    product = isinstance(node.op, ast.Mult)
    operands: list[tuple[float, ast.AST]] = []
    inner: list[ast.AST] = []
    for child, child_sign in (
        (node.left, sign),
        (node.right, -sign if isinstance(node.op, ast.Sub) else sign),
    ):
        if isinstance(child, ast.BinOp) and isinstance(child.op, ast.Mult if product else _SUM):
            more, nested = _chain(child, child_sign)
            operands += more
            inner += [child, *nested]
        else:
            operands.append((child_sign, child))
    return operands, inner


def _fold_chain(node: ast.BinOp, folded: set[ast.AST]) -> float | None:
    """What the literals of the chain node heads fold to, in any order (p.x * 2 * 2 and
    2 * 2 * p.x both fold 2 * 2), or None when fewer than two of its operands are constant.
    Marks the chain's inner BinOps folded, and its constant operands when they fold."""
    if not isinstance(node.op, (ast.Mult, *_SUM)):
        return None
    operands, inner = _chain(node)
    folded.update(inner)  # a shorter chain inside this one folds a subset of its literals
    constants = [(sign, op, value) for sign, op in operands if (value := _fold(op)) is not None]
    if len(constants) < 2:
        return None
    for _, op, _ in constants:
        folded.update(ast.walk(op))
    try:
        if isinstance(node.op, ast.Mult):
            return math.prod(value for _, _, value in constants)
        return math.fsum(sign * value for sign, _, value in constants)
    except (ArithmeticError, ValueError):  # inf - inf
        return math.nan


def lint_model(p: Project) -> None:
    """model.py may hold no dimension literals; every number comes through params: it imports
    only build123d and math, converts no text to a number, and its constant arithmetic, and the
    literals of each chain of one commutative operator, fold to an allowed literal."""
    path = p.root / "model.py"
    if not path.is_file():
        p.error("model-missing", "model.py not found")
        return
    allowed = [float(v) for v in p.meta.get("model_literals", MODEL_LITERALS)]
    try:
        tree = ast.parse(path.read_text(encoding="utf8"))
    except (SyntaxError, ValueError) as exc:  # ValueError: null bytes or undecodable text
        line = getattr(exc, "lineno", None)
        where = f"model.py line {line}" if line else "model.py"
        p.error("model-syntax", f"{where}: {getattr(exc, 'msg', exc)}")
        return

    def is_allowed(value: float) -> bool:  # a sign is free: -90 rotates as readably as 90
        return any(math.isclose(abs(value), abs(a), rel_tol=1e-9, abs_tol=1e-12) for a in allowed)

    folded: set[ast.AST] = set()  # nodes inside a constant expression or chain already folded
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            modules = (
                [a.name for a in node.names]
                if isinstance(node, ast.Import)
                else ["." * node.level + (node.module or "")]
            )
            for module in modules:
                if module.split(".")[0] not in MODEL_IMPORTS:
                    p.error(
                        "model-import",
                        f"model.py:{node.lineno}: imports {module}; model.py may "
                        "import only build123d and math, so every number comes through params",
                    )
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in _TEXT_TO_NUMBER
            and any(
                isinstance(n, ast.JoinedStr)
                or (isinstance(n, ast.Constant) and isinstance(n.value, str))
                for arg in node.args
                for n in ast.walk(arg)
            )
        ):
            p.error(
                "model-text-number",
                f"model.py:{node.lineno}: {node.func.id}() of text; "
                "move the number to params.yaml with a basis",
            )
        if isinstance(node, ast.Constant):
            literal = _literal(node)
            if literal is not None and not is_allowed(literal):
                p.error(
                    "model-literal",
                    f"model.py:{node.lineno}: literal {ast.unparse(node)}; "
                    "move it to params.yaml with a basis",
                )
        elif isinstance(node, ast.BinOp) and node not in folded:
            value = _fold(node)
            if value is not None:
                folded.update(ast.walk(node))
                what = "folds to"
            else:
                value = _fold_chain(node, folded)
                what = "folds its literals to"
            if value is not None and not is_allowed(value):
                p.error(
                    "model-arithmetic",
                    f"model.py:{node.lineno}: {ast.unparse(node)} {what} "
                    f"{value:g}, not an allowed literal; move it to params.yaml with a basis",
                )
