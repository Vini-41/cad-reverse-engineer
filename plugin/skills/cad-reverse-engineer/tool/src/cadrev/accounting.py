"""What each check reads, and what follows from it: what the check rests on, and which source
params no check checks ([unchecked-source])."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .project import RESTS_ON, Project, check_refs, expr_names, params_read_by


@dataclass(frozen=True)
class Reads:
    """What a check's evaluation read, shared by all its results: the params it reads itself
    (own), the params the model gives it (given: a joint's range ends, the wheel's turn and the
    closed values a pose moves through a cable), the parts a mass check weighs (weighs, None for
    other kinds) and the parts it weighs in several instances with no stated count (uncounted). The
    check reads both own and given params: each is checked, and its rests on is judged from both."""

    own: tuple[str, ...] = ()
    given: tuple[str, ...] = ()
    weighs: tuple[str, ...] | None = None
    uncounted: tuple[str, ...] = ()


def reads(
    p: Project,
    c: dict,
    given: tuple[str, ...] = (),
    weighs: tuple[str, ...] | None = None,
    uncounted: tuple[str, ...] = (),
) -> Reads:
    """The Reads of check c: the params it reads itself, a mass check's narrowed to the parts it
    weighs, with what the model gives it."""
    return Reads(tuple(params_read_by(p, c, weighs=weighs)), given, weighs, uncounted)


def estimated(p: Project) -> list[Reads]:
    """Each check's Reads from the check alone, where nothing was built to evaluate it on: a mass
    check naming no parts then reads every part's mass model params."""
    return [reads(p, c) for c in p.checks]


def rests_on(p: Project, r: Reads) -> tuple[str, list[str]]:
    """What a check that read r rests on: the weakest basis among the params it reads, or source
    when it reads none, with the params that rest on that basis; proposed, naming none, when it
    weighs a part in several instances with no stated count, since how many there are is then the
    model's choice. A sweep's resolution (Project.resolution) states nothing about the object, so
    no check rests on it."""
    names = dict.fromkeys(n for n in [*r.own, *r.given] if n not in p.resolution)
    bases = {name: p.rests_on.get(name, "proposed") for name in names}
    weakest = max(bases.values(), key=RESTS_ON.index, default="source")
    if r.uncounted and weakest != "proposed":
        return "proposed", []
    return weakest, [name for name, basis in bases.items() if basis == weakest]


def check_source_params(
    p: Project, evaluated: Iterable[Reads] | None, model_reads: set[str]
) -> None:
    """[unchecked-source] for each source param no check checks, once per verification run, where
    evaluated is the Reads the checks' evaluations returned and model_reads what model.py reads;
    when nothing was built, each check's Reads is estimated from the check alone, which names no
    params the model gives it. A check checks what the params it reads feed, its own and those the
    model gives it, and the params whose ledger value it compares."""
    read = {
        n for r in (estimated(p) if evaluated is None else evaluated) for n in [*r.own, *r.given]
    }
    unchecked = _unchecked_geometry(p, read) | _unchecked_physics(p, read, model_reads)
    compared = {ref for c in p.checks for ref in check_refs(c)}
    for name in [n for n in p.params if n in unchecked]:
        spec = p.params[name]
        if spec.get("basis") == "source" and spec.get("from") not in compared:
            p.warn(
                "unchecked-source",
                f"param {name}: {spec.get('from')} feeds the model but no "
                "check confirms the geometry realises it",
            )


def _unchecked_geometry(p: Project, read: set[str]) -> set[str]:
    """The params that no check feeds, where read is the params the checks read. A check compares
    what its params feed with the ledger; no check sees a physics value, nor the params that feed
    only physics values, unless model.py reads them (_unchecked_physics)."""
    return p.params.keys() - _feeding(p, read) - p.physics - _physics_only(p)


def _unchecked_physics(p: Project, read: set[str], model_reads: set[str]) -> set[str]:
    """The params read only on the way to a physics value that model.py reads too, directly or
    through a param, and that no check feeds, where read is the params the checks read."""
    return _physics_only(p) & _feeding(p, model_reads) - _feeding(p, read)


def _physics_only(p: Project) -> set[str]:
    """The params read only on the way to a physics value: every param whose expr reads one is a
    physics value or read only on the way to one."""
    feeding = _feeding(p, p.physics) - p.physics
    return feeding - _feeding(p, p.params.keys() - p.physics - feeding)


def _feeding(p: Project, names: set[str]) -> set[str]:
    """names, and every param their derived exprs read, however deep: a check reading a derived
    count reads the stated counts it multiplies."""
    found, pending = set(), list(names)
    while pending:
        name = pending.pop()
        if name in found:
            continue
        found.add(name)
        spec = p.params.get(name) or {}
        if spec.get("basis") == "derived":
            try:
                pending += expr_names(str(spec.get("expr", ""))) & p.params.keys()
            except (SyntaxError, ValueError):
                pass  # [param-derived] says why
    return found
