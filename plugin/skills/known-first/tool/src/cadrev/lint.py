"""The model lint: model.py holds no dimension and loads no file, so every number reaches the CAD
through params.yaml and every part is built from them."""

from __future__ import annotations

import ast
import math
import operator
import re

from .project import Project

# The numbers model.py may hold, a sign aside: they keep halving, unit vectors and right-angle
# turns readable. Any other number is a param.
MODEL_LITERALS = (0, 1, 2, 0.5, 90, 180, 270, 360)
MODEL_IMPORTS = ("build123d", "math")
# What reads a file: build123d's importers (import_step, import_stl, ...) and its mesh reader. A
# part loaded from a released file is compared with itself, and its params check nothing.
_LOADS = re.compile(r"import_\w+|open|Mesher")
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


def _fold(node: ast.AST) -> float | None:
    """The number a literal spells (1e1, 3.0, 0x3), or that arithmetic on literals alone works
    out to (180 + 90), nan where it cannot be worked out; None for anything else."""
    if isinstance(node, ast.Constant):
        number = node.value
        if not isinstance(number, (int, float)) or isinstance(number, bool):
            return None
        try:
            return float(number)
        except OverflowError:  # an integer of hundreds of digits
            return math.nan
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


def lint(p: Project) -> bool:
    """Whether model.py is there to build. [model-literal] for each number in it other than
    MODEL_LITERALS, a sign aside; [model-import] for each import but build123d and math, and each
    name that reads a file."""
    path = p.root / "model.py"
    if not path.is_file():
        p.error("model-missing", "model.py not found")
        return False
    try:
        tree = ast.parse(path.read_text(encoding="utf8"))
    except (SyntaxError, ValueError) as exc:  # ValueError: null bytes or undecodable text
        line = getattr(exc, "lineno", None)
        p.error(
            "model-syntax", f"model.py{f' line {line}' if line else ''}: {getattr(exc, 'msg', exc)}"
        )
        return False
    folded: set[ast.AST] = set()  # nodes inside a number already judged
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            modules = [a.name for a in node.names]
            if isinstance(node, ast.ImportFrom):
                modules = ["." * node.level + (node.module or "")]
            for module in modules:
                if module.split(".")[0] not in MODEL_IMPORTS:
                    p.error(
                        "model-import",
                        f"model.py:{node.lineno}: imports {module}; model.py imports only "
                        "build123d and math",
                    )
        if isinstance(node, ast.Call) and isinstance(node.func, (ast.Name, ast.Attribute)):
            name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr
            if _LOADS.fullmatch(name):
                p.error(
                    "model-import",
                    f"model.py:{node.lineno}: {name} reads a file; build every part from params",
                )
        value = None if node in folded else _fold(node)
        if value is not None:
            folded.update(ast.walk(node))
            if not any(
                math.isclose(abs(value), a, rel_tol=1e-9, abs_tol=1e-12) for a in MODEL_LITERALS
            ):
                p.error(
                    "model-literal",
                    f"model.py:{getattr(node, 'lineno', '?')}: {ast.unparse(node)} is a number "
                    "model.py may not hold; give it a param in params.yaml, with its basis",
                )
    return True
