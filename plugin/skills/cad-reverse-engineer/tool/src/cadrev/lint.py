"""The model lint: model.py holds no dimension, so every number reaches the CAD through
params.yaml."""

from __future__ import annotations

import ast
import math
import operator
import random
from typing import TYPE_CHECKING
from collections.abc import Callable

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
_ARITHMETIC = (ast.Add, ast.Sub, ast.Mult, ast.Div)


def _same(a: float, b: float) -> bool:
    """Whether two computed values are one number, past rounding."""
    return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-12)


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
    literals of each chain of one commutative operator, fold to an allowed literal, as does the
    factor each arithmetic of params multiplies a param by."""
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
        return any(_same(abs(value), abs(a)) for a in allowed)

    folded: set[ast.AST] = set()  # nodes inside a constant expression or chain already folded
    flagged: set[ast.AST] = set()  # the BinOps raised as model-arithmetic
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
                flagged.add(node)
                p.error(
                    "model-arithmetic",
                    f"model.py:{node.lineno}: {ast.unparse(node)} {what} "
                    f"{value:g}, not an allowed literal; move it to params.yaml with a basis",
                )
    _lint_param_expressions(p, tree, is_allowed, flagged)


_MATH = {name: getattr(math, name) for name in dir(math) if not name.startswith("_")}
_BUILTINS = {"min": min, "max": max, "abs": abs}
# The two evaluations scale each param by factors from ranges this far apart, so a floor, a
# remainder or a clamp of a param still changes between them.
_FACTORS = ((0.3, 0.7), (1.4, 3.0))


class _ParamExpressions:
    """The param expressions of build(p): those built only from p.<name> reads, allowed
    literals, arithmetic, math.* and min/max/abs calls, and local names assigned once straight
    from such an expression. A name assigned more than once is not followed, since which value
    it holds where it is read depends on the control flow."""

    def __init__(self, build: ast.FunctionDef, math_names: set[str], is_allowed) -> None:
        self.param_name = build.args.args[0].arg if build.args.args else None
        self.math_names, self.is_allowed = math_names, is_allowed
        bound: dict[str, list[ast.AST]] = {}
        for node in ast.walk(build):
            if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
                bound.setdefault(node.id, []).append(node)
            elif isinstance(node, ast.arg):
                bound.setdefault(node.arg, []).append(node)
        self.bound = set(bound)
        self.local: dict[str, ast.expr] = {}  # name: the expression it is assigned once from
        for node in ast.walk(build):
            if (
                isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and len(bound[node.targets[0].id]) == 1
            ):
                self.local[node.targets[0].id] = node.value
        self._following: set[str] = set()

    def reads(self, node: ast.AST) -> set[str] | None:
        """The params node reads, through local names too, or None if it is no param expression."""
        if isinstance(node, ast.Constant):
            literal = _literal(node)
            return set() if literal is not None and self.is_allowed(literal) else None
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id == self.param_name:
                return {node.attr}
            if node.value.id in self.math_names and node.value.id not in self.bound:
                return set() if isinstance(_MATH.get(node.attr), float) else None
            return None
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            if node.id in self.local and node.id not in self._following:
                self._following.add(node.id)
                try:
                    return self.reads(self.local[node.id])
                finally:
                    self._following.discard(node.id)
            return None
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            return self.reads(node.operand)
        if isinstance(node, ast.BinOp) and type(node.op) in _FOLDS:
            left, right = self.reads(node.left), self.reads(node.right)
            return None if left is None or right is None else left | right
        if isinstance(node, ast.Call) and not node.keywords and self.function(node.func):
            names: set[str] = set()
            for arg in node.args:
                more = self.reads(arg)
                if more is None:
                    return None
                names |= more
            return names
        return None

    def arithmetic(self, node: ast.AST, skip: set[ast.AST]) -> bool:
        """Whether param expression node, through local names too, is built from p.<name> reads,
        literals, + - * / and signs alone, with no node in skip."""
        if node in skip:
            return False
        if isinstance(node, ast.Constant):
            return True
        if isinstance(node, ast.Attribute):
            return isinstance(node.value, ast.Name) and node.value.id == self.param_name
        if isinstance(node, ast.Name) and node.id in self.local and node.id not in self._following:
            self._following.add(node.id)
            try:
                return self.arithmetic(self.local[node.id], skip)
            finally:
                self._following.discard(node.id)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            return self.arithmetic(node.operand, skip)
        if isinstance(node, ast.BinOp) and isinstance(node.op, _ARITHMETIC):
            return self.arithmetic(node.left, skip) and self.arithmetic(node.right, skip)
        return False

    def function(self, func: ast.AST) -> Callable[..., float] | None:
        """The math function or min/max/abs func names, or None."""
        if isinstance(func, ast.Name) and func.id not in self.bound:
            if func.id in _BUILTINS:
                return _BUILTINS[func.id]
            if func.id in self.math_names and callable(_MATH.get(func.id)):
                return _MATH[func.id]
        if (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id in self.math_names
            and func.value.id not in self.bound
            and callable(_MATH.get(func.attr))
        ):
            return _MATH[func.attr]
        return None

    def evaluate(self, node: ast.AST, params: dict[str, float]) -> float:
        """node's value with p.<name> read from params; raises ValueError where node is no param
        expression, and whatever the arithmetic raises where it cannot be computed."""
        literal = _literal(node)
        if literal is not None:
            return literal
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id == self.param_name and node.attr in params:
                return params[node.attr]
            if node.value.id in self.math_names - self.bound and isinstance(
                _MATH.get(node.attr), float
            ):
                return _MATH[node.attr]
        if isinstance(node, ast.Name) and node.id in self.local:
            return self.evaluate(self.local[node.id], params)
        if isinstance(node, (ast.UnaryOp, ast.BinOp)) and type(node.op) in _FOLDS:
            operands = [node.operand] if isinstance(node, ast.UnaryOp) else [node.left, node.right]
            return _FOLDS[type(node.op)](*(self.evaluate(o, params) for o in operands))
        if isinstance(node, ast.Call) and (function := self.function(node.func)) is not None:
            return function(*(self.evaluate(a, params) for a in node.args))
        raise ValueError(f"{ast.unparse(node)} is no param expression")


def _lint_param_expressions(
    p: Project, tree: ast.Module, is_allowed, flagged: set[ast.AST]
) -> None:
    """A param expression in build(p), or one inside it, whose value stays put when its params
    are scaled is a constant built from params (atan2(p.h, p.h)): its number belongs in
    params.yaml. So does the factor an arithmetic of params multiplies a param by alike at both
    scalings (p.h + p.h / 2 multiplies h by 1.5), unless one allowed literal multiplies or
    divides by it, or the arithmetic holds a number flagged already."""
    build = next(
        (n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "build"), None
    )
    if build is None:
        return
    math_names = set()  # what model.py calls math, and the math names it imports bare
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            math_names |= {a.asname or a.name for a in node.names if a.name == "math"}
        elif isinstance(node, ast.ImportFrom) and node.module == "math" and not node.level:
            math_names |= {a.asname or a.name for a in node.names if a.name != "*"}
            if any(a.name == "*" for a in node.names):
                math_names |= set(_MATH)
    exprs = _ParamExpressions(build, math_names, is_allowed)
    base = {k: v if math.isfinite(v) and v != 0 else 1.0 for k, v in p.values.items()}

    def evaluate(node: ast.AST, params: dict[str, float]) -> float | None:
        """node's finite value with these params, or None where it cannot be computed."""
        try:
            value = exprs.evaluate(node, params)
        except (ArithmeticError, ValueError, TypeError, RecursionError):
            return None
        return float(value) if isinstance(value, (int, float)) and math.isfinite(value) else None

    def lint_factors(
        node: ast.expr, text: str, points: list[dict[str, float]], values: list[float]
    ) -> bool:
        """Raise each param node multiplies by the same factor at both points, the change in its
        value per unit change of the param, unless that factor or its reciprocal is an allowed
        literal; whether any was raised."""
        raised = False
        for name in points[0]:
            factors = factors_of(node, name, points, values)
            if (
                factors is not None
                and _same(factors[0], factors[1])
                and not is_allowed(factors[0])
                and not (factors[0] and is_allowed(1 / factors[0]))  # p.x / 90 divides by 90
            ):
                raised = True
                p.error(
                    "model-arithmetic",
                    f"model.py:{node.lineno}: {text} multiplies {name} by {factors[0]:g}, not "
                    f"an allowed literal{through(node, name, points)}; move the number to "
                    "params.yaml as a derived param with a basis",
                )
        return raised

    def factors_of(
        node: ast.expr, name: str, points: list[dict[str, float]], values: list[float]
    ) -> list[float] | None:
        """The change in node's value per unit change of param name at each point, or None
        where it cannot be computed."""
        factors = []
        for params, value in zip(points, values):
            shifted = evaluate(node, {**params, name: 2 * params[name]})
            if shifted is None:
                return None
            factors.append((shifted - value) / params[name])
        return factors

    def through(node: ast.expr, name: str, points: list[dict[str, float]]) -> str:
        """Where part of node's factor on param name comes from: each local name node reads
        that reads name, with the line it is assigned on and its own factor, so a factor built
        up on another line is traced there."""
        parts, seen = [], set()
        for child in ast.walk(node):
            if (
                not isinstance(child, ast.Name)
                or child.id in seen
                or (assigned := exprs.local.get(child.id)) is None
                or name not in (exprs.reads(assigned) or set())
            ):
                continue
            seen.add(child.id)
            values = [v for params in points if (v := evaluate(assigned, params)) is not None]
            factors = (
                factors_of(assigned, name, points, values) if len(values) == len(points) else None
            )
            own = (
                f", multiplies {name} by {factors[0]:g}"
                if factors is not None and _same(factors[0], factors[1])
                else ""
            )
            parts.append(f"{child.id}, assigned on model.py:{assigned.lineno}{own}")
        return "".join(f" ({part})" for part in parts)

    def visit(node: ast.AST) -> None:
        if not isinstance(node, ast.expr) or (reads := exprs.reads(node)) is None:
            for child in ast.iter_child_nodes(node):
                visit(child)
            return
        if not reads or isinstance(node, ast.Name):  # a bare alias is judged where it is assigned
            return
        text = ast.unparse(node)
        rng = random.Random(f"{node.lineno}:{text}")
        points = [
            {k: base.get(k, 1.0) * rng.uniform(low, high) for k in sorted(reads)}
            for low, high in _FACTORS
        ]
        values = [v for params in points if (v := evaluate(node, params)) is not None]
        if len(values) < len(points):
            return  # a domain error, an overflow or a complex root: skipped, not judged
        if not _same(values[0], values[1]):
            if exprs.arithmetic(node, flagged) and lint_factors(node, text, points, values):
                return
            # p.y * atan2(p.h, p.h) varies, but its atan2 does not: each part of a varying
            # expression is judged too, beyond #31's maximal sub-expressions.
            for child in ast.iter_child_nodes(node):
                visit(child)
        else:
            p.error(
                "model-constant",
                f"model.py:{node.lineno}: {text} is {values[0]:g} whatever its params; "
                "a constant built from params hides its number, so move it to params.yaml "
                "with a basis",
            )

    for statement in build.body:
        visit(statement)
