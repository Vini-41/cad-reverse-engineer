"""plan.yaml: how the object is made and put together, held to the built model.

The plan says how each part is made or what is bought for it, and gives the steps that assemble
the instances in order. cadrev holds its bookkeeping to the model, so it cannot drift from what
is built: every part an instance places is made or bought, every instance is placed by one step,
and the screws the steps drive are counted against the holes threaded for them. That the instances
hold together is held.py's to say. Whether a hand or a tool can do what a step says is its
author's to judge.
"""

from __future__ import annotations

from collections import Counter

from .build import Model, screws
from .project import Project


def check(p: Project, model: Model) -> dict | None:
    """File the plan's findings against the built model, and return the plan as the report lists
    it: what is made, what is bought and the steps, each with its count; None for a project
    with no plan."""
    plan = p.plan
    if plan is None:
        return None
    placed = Counter(part for part, _ in model.assembly.values())
    make = {
        part: [how] if isinstance(how, str) else list(how)
        for part, how in plan.get("make", {}).items()
    }
    buy, steps = plan.get("buy", {}), plan.get("steps", [])
    for part, how in make.items():
        if part not in model.parts:
            p.error("plan-part", f"make {part}: model.build returns no part {part}")
        if not how or not all(op.strip() for op in how):
            p.error("plan-part", f"make {part}: say how it is made")
    for name, what in buy.items():
        if name in make:
            p.error("plan-part", f"{name} is both made and bought; the plan gives it one")
        if not what.strip():
            p.error("plan-part", f"buy {name}: say what is bought")
    for part in model.parts:
        if placed[part] and part not in make and part not in buy:
            p.error("plan-part", f"part {part}: the plan neither makes it nor buys it")
    driven = _steps(p, model, placed, steps)
    general = " ".join((plan.get("general_tolerance") or "").split())  # printed as one line
    return ({"general_tolerance": general} if general else {}) | {
        "make": [
            {"part": part, "count": placed[part], "how": how}
            for part, how in make.items()
            if part in model.parts
        ],
        "buy": _bought(p, model, placed, buy, driven),
        "steps": [
            {"place": step.get("place", []), "with": step.get("with", {})}
            | ({"from": step["from"]} if "from" in step else {})
            | ({"note": step["note"]} if step.get("note") else {})
            for step in steps
        ],
    }


def _steps(p: Project, model: Model, placed: Counter, steps: list[dict]) -> Counter:
    """[plan-step] unless each instance is placed by one step, and [plan-screw] unless each
    screw a step drives is a thread param's, with a warning where holes threaded for a screw
    are left without one; the screws driven, by thread param."""
    placed_by: dict[str, int] = {}
    driven: Counter = Counter()
    for i, step in enumerate(steps, 1):
        if not (step.get("place") or step.get("with") or step.get("note")):
            p.error("plan-step", f"step {i}: places nothing, drives nothing and says nothing")
        for inst in step.get("place", []):
            if inst not in model.assembly:
                p.error("plan-step", f"step {i}: {inst} is not an instance of the assembly")
            elif inst in placed_by:
                earlier = placed_by[inst]
                p.error("plan-step", f"step {i}: {inst} is already placed by step {earlier}")
            else:
                placed_by[inst] = i
        for param, count in step.get("with", {}).items():
            if param not in p.thread_params:
                p.error(
                    "plan-screw",
                    f"step {i}: with names {param}, which is no thread param; a step drives the "
                    "screws, nuts and inserts of a thread param, and says anything else in its "
                    "note",
                )
            elif count < 1:
                p.error("plan-screw", f"step {i}: drives {count} of {param}")
            else:
                driven[param] += count
    unplaced = [inst for inst in model.assembly if inst not in placed_by]
    if unplaced and (steps or len(model.assembly) > 1):
        p.error(
            "plan-step",
            f"no step places {', '.join(unplaced)}: the steps place every instance of the "
            "assembly, each once",
        )
    for param in p.screws:
        threaded = [
            t for t in model.threads if t.param == param and t.fit == "threaded" and placed[t.part]
        ]
        shanks, unfilled = screws(threaded, model.assembly, p.length_tol)
        holes = sum(placed[t.part] for t in threaded if t.hole)
        if param in p.thread_params and unfilled > driven[param]:
            built = f" and {_count(shanks, 'screw')} built as a part" if shanks else ""
            p.warn(
                "plan-screw",
                f"{_count(holes, 'hole')} threaded {p.thread_params[param].thread.name} for "
                f"{param}, against {_count(driven[param], 'screw')} the steps drive{built}",
            )
    return driven


def _count(count: int, noun: str) -> str:
    return f"{count} {noun}{'s' * (count != 1)}"


def _bought(p: Project, model: Model, placed: Counter, buy: dict, driven: Counter) -> list[dict]:
    """What is bought, as the report lists it: each bought part with its instances, each thread
    param the plan names or the steps drive with how many are driven, and anything else the plan
    lists, uncounted."""
    listed: list[dict] = [
        {"item": part, "count": placed[part], "what": buy[part]}
        for part in model.parts
        if part in buy
    ]
    for param, size in p.thread_params.items():
        if param not in model.parts and (param in buy or driven[param]):
            listed.append(
                {
                    "item": param,
                    "count": driven[param],
                    "what": buy.get(param, ""),
                    "thread": p.screw(param) or size.thread.name,
                }
            )
    listed += [
        {"item": name, "count": None, "what": what}
        for name, what in buy.items()
        if name not in model.parts and name not in p.thread_params
    ]
    return listed
