"""checks.yaml: what each check compares the geometry with, and its evaluation on the built model.

A check compares with the ledger, never with params: a value its evidence and key name, or one
its expect works out from ledger values. What the check reads besides (a pose, a density, a
joint's range) decides what its result rests on.
"""

from __future__ import annotations

import time
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import NamedTuple

from . import Fault, ledger, released, units
from .build import JOINT_TYPES, Model, unmoving, gear_by, prefix, printed, range_ends
from .ledger import TOL_CAP, TOL_REL_CAP, above_cap
from .motion import Mechanism, pose_text
from .project import AXES, DEFAULT_TOL, POSES, RESTS_ON, Project, compared_refs


class Kind(NamedTuple):
    quantity: str  # what it compares in
    expects: bool = False  # may compare with a value its expect works out from the ledger
    changes: bool = False  # may take a from pose, and then compares the change between two poses


# The kinds that compare with the ledger, or for shape with a released body. An interference
# check compares an overlap with a limit instead.
KINDS = {
    "bbox": Kind("length"),
    "distance": Kind("length", expects=True, changes=True),
    "angle": Kind("angle", expects=True, changes=True),
    "diameter": Kind("length", expects=True),
    "mass": Kind("mass", expects=True),  # within tol_rel, a fraction, which has no default
    "range": Kind("angle"),  # a joint's own value where it names no datums
    "stroke": Kind("length", expects=True, changes=True),
    "shape": Kind("length"),  # compared with its released body within tolerance.length
    "count": Kind("count", expects=True),  # compared exactly
}
# What an STL's shape check found its largest deviation at, as its result says it.
_MESH_FOUND = {
    "mesh corner": "largest distance of a mesh corner from the part",
    "part corner": "largest distance of a corner of the part from the nearest mesh corner",
    "closed edge": "largest distance of a closed edge of the part from its third mesh corner",
    "facet": "largest distance from the part of the centre of such a facet",
}


@dataclass
class Result:
    id: str
    kind: str
    ok: bool
    expected: str
    measured: str
    note: str = ""
    # What the check rests on, and the params it reads that rest on that basis.
    rests_on: str = "source"
    rests_on_params: list[str] = field(default_factory=list)
    # Given only for the checks they apply to:
    pairs: int | None = None  # how many instance pairs an interference check evaluated
    pose: dict | None = None  # joint -> {from, value} it was posed at
    from_pose: dict | None = None  # the pose its change is taken from; {} for as built
    sweep: dict | None = None  # a swept check's joint, range params, their values and pose count
    uncounted: dict | None = None  # a mass check's parts in several instances with no count
    shape: dict | None = None  # a shape check's fit: residual, distance, worst_point
    expect: dict | None = None  # an expect's expression and the value it works out to
    miss: str | None = None  # how far a failed comparison is off, beside its tolerance
    part: str | None = None  # the part it reads alone, in that part's own frame


def quantity(c: dict, model: Model | None = None) -> str:
    """What check c compares in: its kind's, a length for a range check between two datums, or
    for one of its joint's own value, that joint's quantity where model moves it."""
    if c.get("kind") == "range":
        between, joint = c.get("between") or (), c.get("joint")
        if len(between) == 2:
            return "length"
        if not between and model is not None and joint in model.moving:
            return model.quantity(str(joint))
    return KINDS[c["kind"]].quantity


def part_of(c: dict, model: Model) -> str | None:
    """The part check c reads alone, in that part's own frame: the one its drawing is
    dimensioned by. None for a check that reads the assembly, or is posed."""
    if "instances" in c or c.get("pose") or "from" in c:
        return None
    kind = c.get("kind")
    if kind in ("bbox", "shape"):
        named = {c.get("part")}
    elif kind in ("distance", "angle"):
        named = {prefix(str(d), model.parts) for d in c.get("between") or ()}
    elif kind == "diameter":
        named = {prefix(str(c.get("at")), model.parts)}
    else:
        return None
    (part,) = named if len(named) == 1 else (None,)
    return part if part in model.parts else None


def tolerance(p: Project, c: dict, compared: str | None = None) -> tuple[str, float] | None:
    """The tolerance check c compares within, as (key, value): tol, in what it compares in, or a
    mass check's tol_rel; None for a kind with none, or a mass check missing its tol_rel."""
    kind = c.get("kind")
    if kind not in KINDS or kind == "count":
        return None
    if kind == "mass":
        return ("tol_rel", float(c["tol_rel"])) if "tol_rel" in c else None
    return "tol", float(c.get("tol", p.tolerance(compared or quantity(c))))


def default_tolerance(c: dict, compared: str | None = None) -> tuple[str, float] | None:
    """cadrev's own tolerance for check c, where neither project.yaml nor the check sets one."""
    return (
        ("tol", DEFAULT_TOL[compared or quantity(c)])
        if c.get("kind") in KINDS.keys() - {"mass", "count"}
        else None
    )


def overlap_limit(p: Project, c: dict) -> float:
    """The most overlap an interference check allows: max_volume, else tolerance.length cubed."""
    return float(c.get("max_volume", p.length_tol**3))


def compared_with(c: dict) -> str:
    """What check c compares with, as its result names it: its expect, else its ledger value."""
    return str(c["expect"]) if "expect" in c else f"{c['evidence']}.{c['key']}"


def comparable(p: Project) -> set[int]:
    """Hold each check to what the ledger alone can tell: that it has something to compare with,
    of the quantity it compares, within a tolerance under the cap. The checks, by index, left with
    nothing to compare with are not evaluated."""
    incomparable = set()
    for i, c in enumerate(p.checks):
        cid, before = c["id"], len(p.findings)
        with p.filing("check-config", f"check {cid}: "):
            _comparable(p, c)
        if len(p.findings) > before:
            incomparable.add(i)
        if c.get("kind") in KINDS:
            _quantities(p, c)
        for key in POSES:
            for ref in (c.get(key) or {}).values():
                if isinstance(ref, str):  # a number is a pose fixed by definition
                    p.hold(ref, ("angle", "length"), f"in check {cid}'s {key}")
    return incomparable


def _comparable(p: Project, c: dict) -> None:
    """A Fault where check c names nothing it could be compared with."""
    name = c.get("kind")
    kind = KINDS.get(str(name))
    if kind is None:  # an interference check; an unknown kind is [check-kind]'s to say
        if "expect" in c:
            raise Fault(f"expect is for a check that compares one value; kind {name} takes none")
        return
    if "from" in c and not kind.changes:
        raise Fault(f"from is for a distance, angle or stroke check; kind {name} takes none")
    if "expect" in c:
        if not kind.expects:
            raise Fault(f"expect is for a check that compares one value; kind {name} takes none")
        if "evidence" in c:
            raise Fault("give expect or evidence, not both")
        worked = p.expect(str(c["expect"]))
        if name == "count" and abs(worked - round(worked)) > 1e-9:
            raise Fault(f"expect {c['expect']!r} works out to {worked:g}, which is no count")
    elif kind.expects and "evidence" not in c:
        raise Fault("give evidence and key, or expect, the value it is compared with")
    elif name == "stroke" and "key" not in c:
        raise Fault("give key, the ledger value its stroke is compared with")
    elif name == "bbox" and not c.get("axes"):
        raise Fault("give axes, each value of its evidence item and the axis it runs along")


def _quantities(p: Project, c: dict) -> None:
    """The values check c compares are printed in the quantity it compares, and its tolerance is
    under the cap: tol to TOL_CAP of each value, tol_rel to TOL_REL_CAP."""
    cid, name = c["id"], c["kind"]
    compared = quantity(c)
    joint_valued = name == "range" and "between" not in c  # its joint's quantity, known once built
    for ref in [] if "expect" in c else compared_refs(c):
        p.hold(ref, ("angle", "length") if joint_valued else (compared,), f"check {cid}")
    if name == "mass":
        for param, expected in [
            (c.get("density"), "density"),
            *((n, "mass") for n in c.get("add", [])),
        ]:
            p.hold_param(str(param), (expected,), f"in check {cid}")
        for param in (c.get("counts") or {}).values():
            p.hold_param(str(param), ("count",), f"in check {cid}")
    if name == "count" and c.keys() & {"tol", "tol_rel"}:
        p.error("check-config", f"check {cid}: a count check compares exactly, so it takes no tol")
    if not joint_valued:  # capped once built, in its joint's quantity
        capped(p, c, compared)


def capped(p: Project, c: dict, compared: str) -> None:
    """[tolerance-cap] where check c's tolerance, in the quantity it compares, is above the cap."""
    cid, name = c["id"], c["kind"]
    found = tolerance(p, c, compared)
    if found is None:
        return
    key, tol = found
    if key == "tol_rel":
        if tol > TOL_REL_CAP:
            p.error(
                "tolerance-cap", f"check {cid}: tol_rel {tol:g} is above the cap of {TOL_REL_CAP:g}"
            )
        return
    where = "" if "tol" in c else f" (tolerance.{compared})"
    refs = compared_refs(c)
    # What the tolerance is capped against, each as (its name, its value, the fraction of it). A
    # shape check compares with no ledger value, so nothing caps it.
    if "expect" in c:
        caps = [(f"expect {c['expect']}", lambda: p.expect(str(c["expect"])), TOL_CAP)]
    elif name == "range" and len(refs) == 2:  # the span between its ends: one is often 0
        span = lambda: p.stated(refs[1], compared) - p.stated(refs[0], compared)  # noqa: E731
        caps = [(f"the range {refs[0]} to {refs[1]}", span, TOL_CAP)]
    else:
        caps = [(ref, lambda ref=ref: p.stated(ref, compared), TOL_CAP) for ref in refs]
    for what, value, fraction in caps:
        try:
            against = value()
        except Fault:
            continue  # what it cannot be compared with is another finding's to say
        if above_cap(tol, against, fraction):
            p.error(
                "tolerance-cap",
                f"check {cid}: tol {tol:g}{where} is above {fraction:.0%} of {what}, {against:.4g}",
            )
            break


def rests_on(p: Project, reads: list[str], uncounted=()) -> tuple[str, list[str]]:
    """What a check that read these params rests on: the weakest basis among them, or source when
    it reads none, with the params resting on that basis; proposed, naming none, where a mass check
    weighs a part in several instances with no stated count, since how many there are is then the
    model's choice. A sweep's resolution states nothing about the object, so no check rests on
    it."""
    bases = {
        n: p.rests_on.get(n, "proposed") for n in dict.fromkeys(reads) if n not in p.resolution
    }
    weakest = max(bases.values(), key=RESTS_ON.index, default="source")
    if uncounted and weakest != "proposed":
        return "proposed", []
    return weakest, [name for name, basis in bases.items() if basis == weakest]


class Checks:
    """One verification run's checks, evaluated on a built model: on the assembly as built, or
    for a check that names a pose, where its mechanism places it."""

    def __init__(self, p: Project, model: Model, mechanism: Mechanism | None, skipped: set[int]):
        self.p, self.model, self.mechanism, self.skipped = p, model, mechanism, skipped
        # What the check being evaluated has read: the assemblies it was evaluated at, and for a
        # mass check the parts it weighs and those it weighs uncounted.
        self.read_at: list[Model] = []
        self.weighs: tuple[str, ...] | None = None
        self.uncounted: tuple[str, ...] = ()
        # For interference, each assembly's instances numbered by part and placement, and the
        # overlap volume of two parts by their two numbers (_overlap_at) and by where one lies
        # from the other (_overlap_of).
        self._numbered: dict[int, dict[str, int]] = {}
        self._numbers: dict[tuple, int] = {}
        self._solids: dict[int, tuple] = {}
        self._overlap_at: dict[tuple[int, int], float] = {}
        self._overlap_of: dict[tuple, float] = {}
        self._kinds = {kind: getattr(self, f"_{kind}") for kind in (*KINDS, "interference")}

    def run(self) -> tuple[list[Result], set[str], tuple[str, float] | None]:
        """Every check's results, the params the checks read, and the check that took longest,
        with its seconds at every pose it was evaluated at."""
        p, results, read, slowest = self.p, [], set(), None
        self._hold_joint_values()
        for i, c in enumerate(p.checks):
            cid, found, start = c["id"], [], time.perf_counter()
            self.read_at, self.weighs, self.uncounted = [], None, ()
            evaluate = self._kinds.get(str(c.get("kind")))
            if evaluate is None:
                p.error("check-kind", f"check {cid}: unknown kind {c.get('kind')!r}")
            elif i not in self.skipped:
                try:
                    placed, pose = self._posed(c)
                    for result in evaluate(c, placed):
                        result.pose = result.pose or pose
                        found.append(result)
                except Fault as fault:
                    if fault.message:
                        p.error(fault.rule or "check-config", f"check {cid}: {fault.message}")
                except (KeyError, TypeError, ValueError) as exc:
                    p.error("check-config", f"check {cid}: missing or unknown {exc}")
            seconds = time.perf_counter() - start
            if found and (slowest is None or seconds > slowest[1]):
                slowest = (str(cid), seconds)
            reads = ledger.named_by_checks(p, c, weighs=self.weighs) + self._given(c)
            read |= set(reads)
            basis, params = rests_on(p, reads, self.uncounted)
            for r in found:
                r.rests_on, r.rests_on_params, r.note = basis, params, c.get("interpretation", "")
                r.part = part_of(c, self.model)
                if not r.ok:
                    moved = "" if r.from_pose is None else f" from {pose_text(r.from_pose)}"
                    moved += f" to {pose_text(r.pose)}" if moved and r.pose else ""
                    miss = f" ({r.miss})" if r.miss else ""
                    p.error(
                        "check-failed",
                        f"{r.id}: expected {r.expected}, measured {r.measured}{miss}{moved}",
                    )
            results += found
        return results, read, slowest

    def _hold_joint_values(self) -> None:
        """[unit-quantity] for each pose value, and each end of a range check of a joint's own
        value, printed as the other quantity than its joint's: a length for a revolute joint.
        Printed as any other quantity, it is comparable's finding already. And such a range check's
        tolerance, in its joint's quantity, held to its cap."""
        for c in self.p.checks:
            named = [
                (j, ref, f"in check {c['id']}'s {key}")
                for key in POSES
                for j, ref in (c.get(key) or {}).items()
                if isinstance(ref, str)
            ]
            if c.get("kind") == "range" and "between" not in c:
                named += [(c.get("joint"), ref, f"check {c['id']}") for ref in c.get("ends") or []]
                if c.get("joint") in self.model.moving:
                    capped(self.p, c, quantity(c, self.model))
            for joint, ref, use in named:
                unit, _ = self.p.printed_as(str(ref))
                if joint in self.model.moving and unit:
                    if units.quantity(unit) in ("angle", "length"):
                        self.p.hold(str(ref), (self.model.quantity(joint),), use)

    def _given(self, c: dict) -> list[str]:
        """The params the model gives the check just evaluated: the range ends of a joint it names,
        the ratio or lead of each gear its poses move a joint through, and for each cable whose
        wheel they move, the wheel's turn and closed values."""
        model = self.model
        joint = c.get("joint") or (c.get("sweep") or {}).get("joint") or ""
        given = list(model.joints.get(joint, {}).get("range", ()))
        moved = set().union(*(placed.moved for placed in self.read_at))
        given += (gear_by(g)[1] for g in model.gears.values() if g["driver"] in moved)
        for cable in model.cables.values():
            if cable.get("wheel") in moved:
                given += (model.joints[cable["wheel"]]["range"][0], *cable["closes"].values())
        return list(dict.fromkeys(given))

    # Where a check is evaluated.

    def _posed(
        self, c: dict, key: str = "pose", set_to: dict | None = None
    ) -> tuple[Model, dict | None]:
        """The assembly check c is evaluated on, with its pose as the report shows it: as built,
        or placed at the joint values its `key` names and those set_to gives, each joint as (its
        value, what that is from). A number `key` gives is the joint's value in the project's
        units, from nothing. A joint set_to names is where its check puts it."""
        p, model, named = self.p, self.model, c.get(key) or {}
        if not named and not set_to:
            self.read_at.append(model)
            return model, None
        if self.mechanism is None:
            # Where a finding dropped the joints, it says so.
            why = f"its {key} names a joint, but model.build returns no joints"
            raise Fault("" if model.dropped else why)
        values, pose = {}, {}
        for joint, ref in named.items():
            if joint not in model.moving:
                raise Fault(f"{key} names {joint}, which is {unmoving(model, joint)}")
            source = ref if isinstance(ref, str) else None
            if source is None:
                value = float(ref)
            else:
                value = p.values[source] if source in p.params else p.value(source)
                if value is None:
                    raise Fault(f"{key} {joint}: {ref} names neither a param nor a ledger value")
            values[joint], pose[joint] = value, {"from": source, "value": printed(value)[0]}
        for joint, (value, label) in (set_to or {}).items():
            values[joint], pose[joint] = value, {"from": label, "value": printed(value)[0]}
        try:
            placed = self.mechanism.at(values, pose, frozenset(set_to or ()))
        except Fault as fault:
            raise Fault(f"{key} {fault.message}" if fault.message else "") from None
        self.read_at.append(placed)
        return placed, pose

    def _instances(self, c: dict, placed: Model) -> dict:
        """The instances a check names, each as its (part, Location) where placed has it."""
        if not c["instances"]:
            raise Fault("instances is empty; name the instances it reads")
        unknown = [n for n in c["instances"] if n not in placed.assembly]
        if unknown:
            raise Fault(f"{', '.join(unknown)} is not an instance of the assembly")
        return {n: placed.assembly[n] for n in c["instances"]}

    def _datums(self, c: dict, placed: Model) -> list[tuple[float, float, float]]:
        """The points of the datums a check names in between: in one part's frame, or under
        instances each <instance>.<feature> where placed has its instance."""
        from build123d import Location

        if "instances" not in c:
            if len({prefix(d, placed.parts) for d in c["between"]} - {None}) > 1:
                raise Fault(
                    f"{' and '.join(c['between'])} are datums of different parts, each in its own "
                    "frame; name them <instance>.<feature> under instances"
                )
            return [placed.datums[d] for d in c["between"]]
        instances, points = self._instances(c, placed), []
        for name in c["between"]:
            inst = prefix(name, instances)
            if inst is None:
                raise Fault(f"{name} names none of its instances {', '.join(instances)}")
            part, location = instances[inst]
            datum = f"{part}.{str(name)[len(inst) + 1 :]}"
            if datum not in placed.datums:
                raise Fault(f"{name}: instance {inst}'s part {part} has no datum {datum}")
            points.append(tuple((location * Location(placed.datums[datum])).position))
        return points

    def _joint(self, c: dict) -> tuple[str, dict]:
        """The ranged joint a range check names or an interference check is swept over."""
        name = c.get("joint") or (c.get("sweep") or {})["joint"]
        if self.mechanism is None:
            why = f"names joint {name}, but model.build returns no joints"
            raise Fault("" if self.model.dropped else why)
        if "range" not in self.model.joints.get(name, {}):
            raise Fault(f"{name} is not a joint with a range")
        return name, self.model.joints[name]

    # What a check compares. Each kind takes the check and the assembly it is posed at, and
    # yields its results; one that poses the model itself sets its results' pose.

    def _compare(
        self,
        c: dict,
        rid: str,
        ref: str,
        measured: float,
        shown: str = "",
        compared: str | None = None,
    ) -> Result:
        """The value a check evaluates against the ledger value at ref, or the value its expect
        works out: it passes within the check's tolerance."""
        p = self.p
        expected = p.expect(ref) if "expect" in c else p.stated(ref, compared or quantity(c))
        found = tolerance(p, c, compared)
        if found is None:
            raise KeyError("tol_rel")  # the only tolerance a comparing check can lack
        key, tol = found
        band = ""
        if key == "tol_rel":
            tol, band = tol * expected, f" ±{tol:.0%}"
        off = abs(measured - expected)
        return Result(
            rid,
            c["kind"],
            off <= tol,
            f"{expected:g}{band} ({ref})",
            f"{measured:.4g}{shown}",
            expect={"expr": ref, "value": printed(expected)[0]} if "expect" in c else None,
            miss=None if off <= tol else f"off by {off:.3g}, tolerance {tol:.3g}",
        )

    def _measured(self, c: dict, placed: Model, evaluate, shown: tuple[str, str]) -> Result:
        """Check c's result: the value evaluate returns where it is posed, or with from its change
        between the two poses, shown after it as the first of shown, or the second for a change."""
        value, start_pose = evaluate(placed), None
        if "from" in c:
            start, start_pose = self._posed(c, "from")
            value, start_pose = value - evaluate(start), start_pose or {}
        result = self._compare(c, c["id"], compared_with(c), value, shown["from" in c])
        result.from_pose = start_pose
        return result

    def _bbox(self, c: dict, placed: Model) -> Iterator[Result]:
        from build123d import Compound

        shape = placed.parts[c["part"]] if "instances" not in c else None
        if shape is None:
            instances = self._instances(c, placed).values()
            shape = Compound(children=[placed.parts[part].moved(at) for part, at in instances])
        size = tuple(shape.bounding_box().size)
        for key, axis in c["axes"].items():
            ref = f"{c['evidence']}.{key}"
            yield self._compare(c, f"{c['id']}.{key}", ref, size[AXES[axis]], f" along {axis}")

    def _distance(self, c: dict, placed: Model) -> Iterator[Result]:
        def evaluate(at: Model) -> float:
            return released.datum_distance(self._datums(c, at), c.get("along"))

        between = " - ".join(c["between"])
        yield self._measured(c, placed, evaluate, (f" {between}", f" change in {between}"))

    def _angle(self, c: dict, placed: Model) -> Iterator[Result]:
        def evaluate(at: Model) -> float:
            points = self._datums(c, at)
            return released.angle_at(points, self.p.length_tol, c["between"], c.get("along"))

        yield self._measured(c, placed, evaluate, (f"° {_at(c)}", f"° change {_at(c)}"))

    def _diameter(self, c: dict, placed: Model) -> Iterator[Result]:
        at = str(c["at"])
        part = prefix(at, placed.parts)
        if part is None or at not in placed.datums:
            raise Fault(f"{at} is not a datum of a part")
        found = released.diameter_at(placed.parts[part], placed.datums[at], self.p.length_tol, at)
        yield self._compare(c, c["id"], compared_with(c), found, f" at {at}")

    def _count(self, c: dict, placed: Model) -> Iterator[Result]:
        """How many instances of its part the assembly places; or, of its thread, how many holes
        and shanks carry it, each once per instance of its part, or once where none places it."""
        ref = compared_with(c)
        stated = round(self.p.expect(ref)) if "expect" in c else self.p.stated(ref, "count")
        worked = {"expr": ref, "value": printed(stated)[0]} if "expect" in c else None
        placed_parts = Counter(name for name, _ in placed.assembly.values())
        if "thread" in c:
            thread = str(c["thread"])
            if thread not in self.p.thread_params:
                raise Fault(f"{thread} is not a thread param")
            found = sum(
                placed_parts[t.part] or 1
                for t in self.model.threads
                if t.param == thread and t.fit == "threaded"
            )
            measured = f"{found} hole{'s' * (found != 1)} or shank{'s' * (found != 1)} threaded "
            measured += f"{self.p.thread_params[thread].thread.name} ({thread})"
        else:
            part = str(c["part"])
            if part not in placed.parts:
                raise Fault(f"{part} is not a part model.build returns")
            found = placed_parts[part]
            measured = f"{found} instance{'s' * (found != 1)} of {part}"
        expected = f"{stated:g} ({ref})"
        yield Result(c["id"], "count", stated == found, expected, measured, expect=worked)

    def _mass(self, c: dict, placed: Model) -> Iterator[Result]:
        """Each instance it weighs, by its part's volume times the check's density, or without one
        by the mass model as the MJCF export weighs it, plus its add params."""
        p = self.p
        instances = self._instances(c, placed) if "instances" in c else placed.assembly
        named = c.get("parts") or None
        tally = Counter(part for part, _ in instances.values() if named is None or part in named)
        if missing := [name for name in named or [] if name not in tally]:
            raise Fault(f"parts names {', '.join(missing)}, but it weighs no instance of it")
        self.weighs = tuple(tally)
        counts = c.get("counts", {})
        miscounted = [
            f"counts {part} as {param} ({p.values[param]:g}), but it weighs {tally[part]} instances"
            for part, param in counts.items()
            if p.values[param] != tally[part]
        ]
        if miscounted:
            raise Fault("; ".join(miscounted))
        if "density" in c:
            each = {n: placed.parts[n].volume * p.values[c["density"]] for n in tally}
        elif unweighed := [n for n in tally if n not in placed.masses]:
            raise Fault(
                "names no density, and the mass model in params.yaml parts weighs no "
                + ", ".join(unweighed)
            )
        else:
            each = {n: placed.masses[n].mass for n in tally}
        added = sum(p.values[n] for n in c.get("add", []))
        measured = sum(each[n] * tally[n] for n in tally) + added
        result = self._compare(c, c["id"], compared_with(c), measured)
        result.uncounted = {n: k for n, k in tally.items() if k > 1 and n not in counts}
        self.uncounted = tuple(result.uncounted)
        yield result

    def _range(self, c: dict, placed: Model) -> Iterator[Result]:
        """One result per end of its joint's range. With between, the model posed at that end, and
        the angle there, or between two datums the distance, against the end's ledger value.
        Without, the model posed at the ledger value itself, which shows the mechanism reaches
        it, and the range param for that end against it."""
        p = self.p
        name, joint = self._joint(c)
        if len(c["ends"]) != len(joint["range"]):
            raise Fault(
                f"ends names {len(c['ends'])} values, and joint {name}'s range has "
                f"{len(joint['range'])}"
            )
        own = self.model.quantity(name)
        for param, ref in zip(joint["range"], c["ends"]):
            try:
                if "between" in c:
                    at, pose = self._posed({**c, "pose": {**(c.get("pose") or {}), name: param}})
                    points = self._datums(c, at)
                    if len(points) == 2:
                        measured = released.datum_distance(points, c.get("along"))
                        shown = f" {' - '.join(c['between'])}"
                    else:
                        measured = released.angle_at(
                            points, p.length_tol, c["between"], c.get("along")
                        )
                        shown = f"° {_at(c)}"
                    result = self._compare(c, f"{c['id']}.{param}", ref, measured, shown)
                else:
                    _, pose = self._posed(c, set_to={name: (p.stated(ref), ref)})
                    measured = p.values[param] * p.degrees(own)
                    shown = f"{JOINT_TYPES[joint['type']].symbol} {name}'s range end ({param})"
                    result = self._compare(c, f"{c['id']}.{param}", ref, measured, shown, own)
            except Fault as fault:
                if fault.message:
                    raise
                continue  # this end is not reached, as a finding already says
            result.pose = pose
            yield result

    def _stroke(self, c: dict, placed: Model) -> Iterator[Result]:
        """How much its cable shortens from as built, or from its from pose, to the pose it
        names, or without one to its wheel's full turn."""
        p, cid, name = self.p, c["id"], c["cable"]
        cable, pose = self.model.cables.get(name), None
        if cable is None:
            raise Fault("" if self.model.dropped else f"{name} is not a cable")
        if not c.get("pose"):
            if "wheel" not in cable:
                raise Fault(f"cable {name} has no wheel, so name the pose its stroke is taken at")
            turn = self.model.joints[cable["wheel"]]["range"][0]
            placed, pose = self._posed(c, set_to={cable["wheel"]: (p.values[turn], turn)})
        start, start_pose = self._posed(c, "from")
        if start_pose is None and "from" in c:
            start_pose = {}
        shortening = start.path_length(cable["path"]) - placed.path_length(cable["path"])
        shown = f" shortening of {name}"
        result = self._compare(c, cid, compared_with(c), shortening, shown)
        result.pose, result.from_pose = pose, start_pose
        yield result

    def _interference(self, c: dict, placed: Model) -> Iterator[Result]:
        """The worst overlap among its pairs: on the assembly where it is posed, or with sweep
        across evenly spaced poses of its joint's range, ends included."""
        p = self.p
        sweep, poses = None, [(placed, None)]
        if "sweep" in c:
            name, joint = self._joint(c)
            steps = p.values[c["sweep"]["steps"]]
            if steps < 2 or steps != int(steps):
                raise Fault(
                    f"sweep steps {c['sweep']['steps']} is {steps:g}; sweep a whole number of "
                    "poses, at least 2"
                )
            (low_name, low), (high_name, high) = range_ends(p, joint)
            count, label = int(steps), f"{low_name}..{high_name}"
            poses = [
                self._posed(c, set_to={name: (low + (high - low) * i / (count - 1), label)})
                for i in range(count)
            ]
            ends = {"from": [low_name, high_name], "range": [low, high]}
            sweep = {"joint": name, **ends, "poses": count}
        pairs = [tuple(pair) for pair in c.get("pairs", [])]
        listed = "listed" if pairs else "all"
        if not pairs:
            names = sorted(placed.assembly)
            pairs = [(a, b) for i, a in enumerate(names) for b in names[i + 1 :]]
        worst, worst_pair, worst_pose = 0.0, "", None
        for at, pose in poses:
            numbers = self._numbering(at)
            for a, b in pairs:
                volume = self._overlap_at.get((numbers[a], numbers[b]))
                if volume is None:
                    volume = self._overlap(at, a, b, numbers)
                if volume > worst:  # name a pair only where instances overlap
                    worst, worst_pair, worst_pose = volume, f"{a} ∩ {b}", pose
        measured = f"{worst:.4g} {worst_pair}".strip()
        if sweep is not None and worst_pose is not None:
            measured += f" at {sweep['joint']} {worst_pose[sweep['joint']]['value']:g}"
        measured += f" over {len(pairs)} pair{'s' * (len(pairs) != 1)} ({listed})"
        if sweep is not None:
            measured += f" across {sweep['poses']} poses of {sweep['joint']}"
        limit = overlap_limit(p, c)
        result = Result(c["id"], "interference", worst <= limit, f"overlap ≤ {limit:g}", measured)
        result.pairs, result.sweep, result.pose = len(pairs), sweep, worst_pose
        yield result

    def _numbering(self, placed: Model) -> dict[str, int]:
        """Each instance of an assembly as a number naming its part and where it is, the same
        number wherever an instance of that part lies there. Every posed assembly is kept for the
        run by the mechanism that placed it, so its id stays its own."""
        if id(placed) not in self._numbered:
            self._numbered[id(placed)] = {
                inst: self._numbers.setdefault((part, _placement(at)), len(self._numbers))
                for inst, (part, at) in placed.assembly.items()
            }
        return self._numbered[id(placed)]

    def _overlap(self, placed: Model, a: str, b: str, numbers: dict[str, int]) -> float:
        """The volume two instances share where placed has them. It depends only on the two parts
        and where one lies from the other, so each such pair is intersected once a run: the
        instances a pose leaves in step, and those other checks already tried, are not again."""
        from build123d import Compound

        for inst in (a, b):
            if numbers[inst] not in self._solids:
                part, at = placed.assembly[inst]
                # Its solids alone: build123d's intersect places a Compound's children by the
                # wrong transform.
                solids = Compound(placed.parts[part].moved(at).solids())
                self._solids[numbers[inst]] = (solids, solids.bounding_box().wrapped)
        (solid_a, box_a), (solid_b, box_b) = self._solids[numbers[a]], self._solids[numbers[b]]
        volume = 0.0
        # A part of no solid is [part-invalid] and has no box: it shares no volume. Boxes apart
        # share none either, and the boolean is the slow part.
        if box_a is not None and box_b is not None and not box_a.IsOut(box_b):
            (part_a, at_a), (part_b, at_b) = placed.assembly[a], placed.assembly[b]
            relative = (part_a, part_b, _placement(at_a.inverse() * at_b))
            if relative not in self._overlap_of:
                overlap = solid_a.intersect(solid_b)
                if isinstance(overlap, list):  # nothing, one shape, or a list of shapes
                    self._overlap_of[relative] = sum(shape.volume for shape in overlap)
                else:
                    self._overlap_of[relative] = 0.0 if overlap is None else overlap.volume
            volume = self._overlap_of[relative]
        self._overlap_at[numbers[a], numbers[b]] = volume
        return volume

    def _shape(self, c: dict, placed: Model) -> Iterator[Result]:
        """Its part, built in its released body's frame, compared whole with the body in place
        within tolerance.length: a STEP's surfaces both ways, an STL at the points both hold
        exactly (distance.mesh_fit), and a cut file's region with the part's outline projected
        along an axis, where model.py's sheets places it."""
        p, cid, name, tol = self.p, c["id"], str(c["body"]), self.p.length_tol
        if c["part"] not in placed.parts:
            raise Fault(f"{c['part']} is not a part model.build returns")
        part, body = placed.parts[c["part"]], p.body(name)
        sheet, along = released.at_point(name), c.get("along")
        if sheet is None and along is not None:
            raise Fault(f"along projects a part onto a region of a cut file, and {name} is a solid")
        if sheet is not None and along not in AXES:
            raise Fault(
                f"along names the axis x, y or z along which part {c['part']} is projected onto "
                f"{name}"
            )
        expected, mesh = f"within {tol:g} of body {name} (tolerance.length)", {}
        if sheet is not None:
            where = self._on_sheet(c, name)
            outline = released.outline(part, str(along)).moved(where)
            distance, at, on_body = released.outline_distance(outline, body)
            ok, measured = distance <= tol, f"{distance:.4g} largest outline distance"
        elif released.is_mesh(p.source_path(released.source_of(name))):
            fit = released.mesh_fit(part, body, tol)
            ok, distance, at = fit.ok, fit.distance, fit.at
            on_body, mesh = (
                fit.found in ("mesh corner", "facet"),
                {"found": fit.found, "facets": fit.facets},
            )
            measured = f"{distance:.4g} " + _MESH_FOUND[fit.found]
            if fit.facets:
                facets = f"{fit.facets} facet{'s' * (fit.facets != 1)}"
                measured = f"{facets} on no one smooth patch; {measured}"
        else:
            distance, at, on_body = released.surface_distance(part, body)
            ok, measured = distance <= tol, f"{distance:.4g} largest surface distance"
        shown, on = ", ".join(f"{v:.4g}" for v in at), f"body {name}" if on_body else ""
        measured += f", at ({shown}) on {on or 'part ' + str(c['part'])}"
        fitted = {"distance": printed(distance)[0], "worst_point": list(printed(*at))}
        fitted |= mesh  # an STL's: what found its largest deviation, and the facets on no one patch
        yield Result(cid, "shape", ok, expected, measured, shape=fitted)

    def _on_sheet(self, c: dict, name: str):
        """Where model.py's sheets places check c's part on the region its body names."""
        p, model = self.p, self.model
        region = p.region(name)
        placing = []
        for named, (part, where) in model.sheets.items():
            try:
                if p.region(named) == region:
                    placing.append((named, part, where))
            except Fault:
                continue  # a name that is no region places nothing
        if not placing:
            raise Fault(
                f"model.build's sheets places no part on region {name}; place part {c['part']} "
                "there, as the cut file draws it"
            )
        if len(placing) > 1:
            raise Fault(f"model.build's sheets places {len(placing)} parts on region {name}")
        ((named, part, where),) = placing
        if part != c["part"]:
            raise Fault(f"model.build's sheets places part {part} on {named}, not {c['part']}")
        return where


def _at(c: dict) -> str:
    """Where an angle is taken, as a result shows it."""
    a, vertex, b = c["between"]
    return f"at {vertex} between {a} and {b}" + (f" along {c['along']}" if c.get("along") else "")


def _placement(location) -> tuple[float, ...]:
    """A Location as the twelve numbers of its transform, rounded past rounding's noise."""
    trsf = location.wrapped.Transformation()
    return tuple(round(trsf.Value(i, j), 9) for i in (1, 2, 3) for j in (1, 2, 3, 4))
