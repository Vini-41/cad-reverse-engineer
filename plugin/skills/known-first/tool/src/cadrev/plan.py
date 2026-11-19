"""plan.yaml: how the object is made and put together, held to the built model.

The plan says how each part is made or what is bought for it, and gives the steps that assemble
the instances in order. cadrev holds its bookkeeping to the model, so it cannot drift from what
is built: every part an instance places is made or bought, every instance is placed by one step,
the instances hold together, each touching another or within the plan's clearance of it, and the
screws the steps drive are counted against the holes threaded for them. Whether a hand or a tool
can do what a step says is its author's to judge.
"""

from __future__ import annotations

from collections import Counter

from . import held
from .build import Model
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
    clearance, floating = _held(p, model, plan.get("clearance"))
    return {
        "make": [
            {"part": part, "count": placed[part], "how": how}
            for part, how in make.items()
            if part in model.parts
        ],
        "buy": _bought(p, model, placed, buy, driven),
        "steps": [
            {"place": step.get("place", []), "with": step.get("with", {})}
            | ({"note": step["note"]} if step.get("note") else {})
            for step in steps
        ],
        "clearance": clearance,
        "floating": floating,
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
        threaded = [t for t in model.threads if t.param == param and t.fit == "threaded"]
        holes = sum(placed[t.part] for t in threaded if t.hole)
        shanks = sum(placed[t.part] for t in threaded if not t.hole)
        if param in p.thread_params and holes - shanks > driven[param]:
            built = f" and {_count(shanks, 'screw')} built as a part" if shanks else ""
            p.warn(
                "plan-screw",
                f"{_count(holes, 'hole')} threaded {p.thread_params[param].thread.name} for "
                f"{param}, against {_count(driven[param], 'screw')} the steps drive{built}",
            )
    return driven


def _held(p: Project, model: Model, fit: str | None) -> tuple[dict | None, list[dict]]:
    """[plan-held] for each instance, or group of instances, that nothing holds to the rest: the
    plan's clearance as the report gives it, the param it names and its value, and what floats."""
    limit, clearance = held.TOUCH, None
    if fit is not None:
        if fit not in p.values:
            p.error("plan-held", f"clearance names {fit}, which is no param with a value")
        elif p.values[fit] < 0:
            p.error(
                "plan-held", f"clearance {fit} is {p.values[fit]:g}; a fit's gap is no less than 0"
            )
        else:
            p.hold_param(fit, ("length",), "as the plan's clearance")
            clearance = {"from": fit, "value": p.values[fit]}
            limit += p.values[fit]
    floating = []
    # A part that is no solid has its own finding, and nothing to hold.
    if len(model.assembly) > 1 and not any(f.rule == "part-invalid" for f in p.findings):
        try:
            floating = held.apart(model, limit)
        except Exception as exc:  # noqa: BLE001 - OCC raises many types on a solid it cannot read
            p.error(
                "plan-held",
                "whether the instances hold together could not be evaluated "
                f"({type(exc).__name__}: {exc})",
            )
    floating.sort(key=lambda group: -group["gap"])
    # One finding for all that floats as far from the rest: a fit left out of the plan shows as
    # one gap, whatever number of instances ride on it.
    by_gap: dict[str, dict[tuple, list[dict]]] = {}
    for group in floating:
        parts = sorted(Counter(model.assembly[inst][0] for inst in group["instances"]).items())
        by_gap.setdefault(f"{group['gap']:.4g}", {}).setdefault(tuple(parts), []).append(group)
    for gap, alike in by_gap.items():
        said = []
        for parts, groups in alike.items():
            first, more = groups[0], ", …" * (len(groups) > 1)
            between = f"{first['from']} from {first['nearest']}"
            if len(first["instances"]) > 1:
                count = f"{len(groups)} groups of " * (len(groups) > 1)
                between = f"touching only each other, {between}"
                said.append(f"{count}{len(first['instances'])} instances ({between}{more})")
            elif len(groups) > 1:
                said.append(f"{parts[0][0]} ×{len(groups)} ({between}{more})")
            else:
                said.append(f"{first['instances'][0]} (from {first['nearest']})")
        more = f"; and {len(said) - 3} more kinds" * (len(said) > 3)
        p.error(
            "plan-held",
            f"{gap} {p.units['length']} from the nearest instance, and held by nothing: "
            f"{'; '.join(said[:3])}{more}. An instance sits on what holds it, or within the "
            "plan's clearance of it",
        )
    return clearance, floating


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
