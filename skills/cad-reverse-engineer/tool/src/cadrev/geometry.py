"""Run model.py, export it, and compare the geometry with the evidence."""

from __future__ import annotations

import importlib.util
import math
import re
from dataclasses import dataclass
from pathlib import Path

from .project import Project, expect_param_quantity, expr_names

AXES = {"x": 0, "y": 1, "z": 2}


class Params:
    """Read-only parameter access that records which parameters the model used."""

    def __init__(self, values: dict[str, float]):
        self._values = values
        self.used: set[str] = set()

    def __getattr__(self, name: str) -> float:
        if name.startswith("_"):
            raise AttributeError(name)
        try:
            value = self._values[name]
        except KeyError:
            raise AttributeError(f"no parameter {name!r} in params.yaml") from None
        self.used.add(name)
        return value


@dataclass
class CheckResult:
    id: str
    kind: str
    ok: bool
    expected: str
    measured: str
    note: str = ""


@dataclass
class Built:
    parts: dict
    datums: dict[str, tuple[float, float, float]]
    assembly: dict
    used: set[str]


def _contract_breach(result) -> str | None:
    """Why build()'s return breaks the model contract, or None if it keeps it."""
    from build123d import Location
    from build123d.topology import Shape

    if not isinstance(result, dict):
        return f"must return a mapping of parts, datums and assembly, not {type(result).__name__}"
    for key in ("parts", "datums", "assembly"):
        if not isinstance(result.get(key, {}), dict):
            return f"{key} must be a mapping of names, not {type(result[key]).__name__}"
    for name, part in result.get("parts", {}).items():
        if not isinstance(part, Shape):
            return f"part {name} must be a build123d shape, not {type(part).__name__}"
        if not re.fullmatch(r"[\w.-]+", str(name)):
            return f"part name {name!r} must be letters, digits, '_', '.' or '-': it names build/parts/<name>.step"
    for name, point in result.get("datums", {}).items():
        if not (
            isinstance(point, (tuple, list))
            and len(point) == 3
            and all(isinstance(c, (int, float)) for c in point)
        ):
            return f"datum {name} must be an (x, y, z) tuple of numbers, not {point!r}"
    for inst, entry in result.get("assembly", {}).items():
        if not (
            isinstance(entry, (tuple, list))
            and len(entry) == 2
            and isinstance(entry[0], str)
            and isinstance(entry[1], Location)
        ):
            return f"assembly instance {inst} must be a (part name, Location) pair, not {entry!r}"
    return None


def build(p: Project) -> Built | None:
    spec = importlib.util.spec_from_file_location("cadrev_model", p.root / "model.py")
    assert spec is not None and spec.loader is not None  # a .py path always gets a source loader
    module = importlib.util.module_from_spec(spec)
    params = Params(p.values)
    try:
        spec.loader.exec_module(module)
        result = module.build(params)
    except (Exception, SystemExit) as exc:  # noqa: BLE001 - a broken model is a finding, not a crash
        p.error("model-build", f"model.build failed: {type(exc).__name__}: {exc}")
        return None
    problem = _contract_breach(result)
    if problem:
        p.error("model-return", f"model.build {problem}")
        return None
    built = Built(
        parts=result.get("parts", {}),
        datums={
            k: (float(x), float(y), float(z)) for k, (x, y, z) in result.get("datums", {}).items()
        },
        assembly=result.get("assembly", {}),
        used=params.used,
    )
    for name in sorted(built.used):
        expect_param_quantity(p, name, ("length", "angle"), "in model.py")
    for name in sorted(p.values.keys() - built.used - _used_by_derived(p)):
        p.warn("param-unused", f"param {name} is defined but the model never reads it")
    for name, part in built.parts.items():
        if not part.is_valid:
            p.error("part-invalid", f"part {name}: solid is not valid")
    for inst, (part, _) in list(built.assembly.items()):
        if part not in built.parts:
            p.error("assembly-part", f"assembly instance {inst}: unknown part {part!r}")
            del built.assembly[inst]
    return built


def _used_by_derived(p: Project) -> set[str]:
    names = set()
    for spec in p.params.values():
        if spec.get("expr"):
            try:
                names |= expr_names(spec["expr"])
            except (SyntaxError, ValueError):
                pass  # already a param-derived finding
    return names


def export(p: Project, built: Built) -> list[Path]:
    from build123d import Compound, export_step

    out = p.root / "build"
    (out / "parts").mkdir(parents=True, exist_ok=True)
    written = []
    for name, part in built.parts.items():
        part.label = name
        target = out / "parts" / f"{name}.step"
        export_step(part, str(target))
        written.append(target)
    if built.assembly:
        children = []
        for inst, (part, location) in built.assembly.items():
            child = built.parts[part].moved(location)
            child.label = inst
            children.append(child)
        target = out / "assembly.step"
        export_step(Compound(children=children, label=p.meta.get("name", "assembly")), str(target))
        written.append(target)
    return written


def _expect(p: Project, ref: str) -> float:
    value = p.evidence_value(ref)
    if value is None:
        raise KeyError(f"evidence value {ref}")
    return value


def _instances(built: Built):
    for inst, (part, location) in built.assembly.items():
        yield inst, built.parts[part].moved(location)


def run_checks(p: Project, built: Built) -> list[CheckResult]:
    results = []
    for c in p.checks:
        cid, kind = c.get("id", "?"), c.get("kind")
        tol = float(c.get("tol", p.length_tol))
        try:
            if kind == "bbox":
                part = built.parts[c["part"]]
                s = part.bounding_box().size
                size = (s.X, s.Y, s.Z)
                for key, axis in c["axes"].items():
                    expected = _expect(p, f"{c['evidence']}.{key}")
                    measured = size[AXES[axis]]
                    results.append(
                        CheckResult(
                            f"{cid}.{key}",
                            kind,
                            abs(measured - expected) <= tol,
                            f"{expected:g} ({c['evidence']}.{key})",
                            f"{measured:.4g} along {axis}",
                            c.get("interpretation", ""),
                        )
                    )
            elif kind == "distance":
                a, b = (built.datums[d] for d in c["between"])
                if c.get("along"):
                    i = AXES[c["along"]]
                    measured = abs(a[i] - b[i])
                else:
                    measured = math.dist(a, b)
                expected = _expect(p, f"{c['evidence']}.{c['key']}")
                results.append(
                    CheckResult(
                        cid,
                        kind,
                        abs(measured - expected) <= tol,
                        f"{expected:g} ({c['evidence']}.{c['key']})",
                        f"{measured:.4g} {' - '.join(c['between'])}",
                        c.get("interpretation", ""),
                    )
                )
            elif kind == "mass":
                names = c.get("parts") or list(built.parts)
                counts = c.get("counts", {})
                density = p.values[c["density"]]
                measured = sum(built.parts[n].volume * counts.get(n, 1) for n in names) * density
                measured += sum(p.values[n] for n in c.get("add", []))
                expected = _expect(p, f"{c['evidence']}.{c['key']}")
                tol_rel = float(c["tol_rel"])
                results.append(
                    CheckResult(
                        cid,
                        kind,
                        abs(measured - expected) <= tol_rel * expected,
                        f"{expected:g} ±{tol_rel:.0%} ({c['evidence']}.{c['key']})",
                        f"{measured:.4g}",
                        c.get("interpretation", ""),
                    )
                )
            elif kind == "interference":
                limit = float(c.get("max_volume", p.length_tol**3))
                pairs = [tuple(pair) for pair in c.get("pairs", [])]
                shapes = dict(_instances(built))
                if not pairs:
                    names = sorted(shapes)
                    pairs = [(a, b) for i, a in enumerate(names) for b in names[i + 1 :]]
                worst = (0.0, "")
                for a, b in pairs:
                    overlap = shapes[a].intersect(shapes[b])
                    volume = overlap.volume if overlap is not None else 0.0
                    worst = max(worst, (volume, f"{a} ∩ {b}"))
                results.append(
                    CheckResult(
                        cid,
                        kind,
                        worst[0] <= limit,
                        f"overlap ≤ {limit:g}",
                        f"{worst[0]:.4g} {worst[1]}".strip(),
                        c.get("interpretation", ""),
                    )
                )
            else:
                p.error("check-kind", f"check {cid}: unknown kind {kind!r}")
                continue
        except (KeyError, TypeError, ValueError) as exc:
            p.error("check-config", f"check {cid}: missing or unknown {exc}")
            continue
    for r in results:
        if not r.ok:
            p.error("check-failed", f"{r.id}: expected {r.expected}, measured {r.measured}")
    return results
