"""What each check reads, and what it rests on as a result."""

from __future__ import annotations

from dataclasses import dataclass

from .project import RESTS_ON, Project, params_read_by


@dataclass(frozen=True)
class Reads:
    """What a check's evaluation read, shared by all its results: the params it reads itself
    (own), the params the model gives it (given: a joint's range ends, the wheel's turn and the
    closed values a stroke's pose moves), the parts a mass check weighs (weighs, None for other
    kinds) and the parts it weighs in several instances with no stated count (uncounted)."""

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
