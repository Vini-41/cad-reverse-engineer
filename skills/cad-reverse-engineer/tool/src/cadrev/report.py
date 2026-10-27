"""Write build/report.md and build/report.json."""

from __future__ import annotations

import json
import math
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from .geometry import GEAR_BY, PHYSICS, Built, CheckResult, pose_text, printed, range_ends
from .lint import MODEL_LITERALS
from .project import (
    BASES,
    RESTS_ON,
    Project,
    check_tolerance,
    default_overlap_limit,
    default_tolerance,
    OVERLAP_KINDS,
    overlap_limit,
)


def _cell(value) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _table(header: list[str], rows: list[list]) -> list[str]:
    if not rows:
        return ["_None._", ""]
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(_cell(c) for c in row) + " |" for row in rows]
    return lines + [""]


VERIFIED, PENDING_REVIEW, PARTIAL, NOT_VERIFIED = (
    "VERIFIED",
    "VERIFIED PENDING REVIEW",
    "PARTIAL",
    "NOT VERIFIED",
)
STATUSES = (VERIFIED, PENDING_REVIEW, PARTIAL, NOT_VERIFIED)  # every status `cadrev check` reports
PASSING = (VERIFIED, PENDING_REVIEW)


def awaiting_confirmation(p: Project) -> list[dict]:
    """The figure readings no named human has confirmed yet, each with its crop."""
    return [
        {
            "evidence": e["id"],
            "locator": e.get("locator"),
            "reading": e.get("reading"),
            "image": e["image"],
        }
        for e in p.evidence
        if "image" in e and not e.get("confirmed_by")
    ]


def status(p: Project, partial: bool = False) -> str:
    """The one place a verification run's status is decided; everything else reads it.

    partial: the run skipped the build or the coverage sweep, so it makes no claim.
    """
    if partial:
        return PARTIAL
    if any(f.level == "error" for f in p.findings):
        return NOT_VERIFIED
    return PENDING_REVIEW if awaiting_confirmation(p) else VERIFIED


def exact(p: Project, status: str) -> bool:
    """Exact: VERIFIED with no parameter resting on a proposed value but physics values and a
    sweep's resolution, which exact leaves out (ADR-0008)."""
    return status == VERIFIED and not p.proposed - p.physics - p.resolution


def measured_params(p: Project) -> list[dict]:
    """Each measured parameter with the method and uncertainty of its scaling."""
    return [
        {
            "param": n,
            "value": p.values.get(n),
            "from": s.get("from"),
            "method": s.get("method"),
            "uncertainty": s.get("uncertainty"),
        }
        for n, s in p.params.items()
        if s.get("basis") == "measured"
    ]


def tolerances(p: Project) -> list[dict]:
    """Each check whose tolerance is not cadrev's default, with that tolerance: tol for one
    differing from LENGTH_TOL (ANGLE_TOL for an angle check), and tol_rel for every mass check,
    which has no default."""
    out = []
    for c in p.checks:
        tolerance = check_tolerance(p, c)
        if tolerance is not None and tolerance != default_tolerance(c):
            out.append({"check": c.get("id"), "kind": c.get("kind"), tolerance[0]: tolerance[1]})
    return out


def literal_override(p: Project) -> list | None:
    """The numbers project.yaml allows in model.py in place of the default, or None."""
    literals = p.meta.get("model_literals")
    if literals is None or [float(v) for v in literals] == [float(v) for v in MODEL_LITERALS]:
        return None
    return literals


def overlap_limits(p: Project) -> list[dict]:
    """Each interference check whose overlap limit is not cadrev's default, with that limit. An
    overlap limit is not a tolerance, so it is listed apart from the tolerances."""
    out = []
    for c in p.checks:
        if c.get("kind") in OVERLAP_KINDS:
            limit = overlap_limit(p, c)
            if not math.isclose(limit, default_overlap_limit()):
                out.append({"check": c.get("id"), "max_volume": limit})
    return out


def interpretation(r: CheckResult) -> str:
    """A check's interpretation, with what it rests on when that is less than source: the params,
    then each part a mass check weighs in several uncounted instances."""
    if r.rests_on == "source":
        return r.note
    named = r.rests_on_params + [
        f"{part} ({n} instances uncounted)" for part, n in (r.uncounted or {}).items()
    ]
    return "; ".join(filter(None, [r.note, f"rests on {r.rests_on}: {', '.join(named)}"]))


def _valued(p: Project, entry: dict, keys) -> dict:
    """Each of keys entry names a param for, as {from: the param, value: its value}, rounded as
    the MJCF prints it."""
    return {
        k: {"from": entry[k], "value": printed(p.values[entry[k]])[0]} for k in keys if k in entry
    }


def motion(p: Project, built: Built) -> dict:
    """How the model moves, as the MJCF exports it: each joint with its type, what it joins, its
    drive, its range and its physics values, each loop, each gear with its joints and ratio or lead,
    each tendon with its path and physics values, and each cable with its path and, wound on a
    wheel, the closed value of each joint it closes; no joints means the model is static, unless a
    finding dropped them."""
    joints = {}
    for name, j in built.joints.items():
        joints[name] = {k: j[k] for k in ("type", "parent", "child", "drive") if k in j}
        if "range" in j:
            (low, lo), (high, hi) = range_ends(p, j)
            joints[name]["range"] = {"from": [low, high], "value": list(printed(lo, hi))}
        joints[name] |= _valued(p, j, PHYSICS["joint"])
    return {
        "joints": joints,
        "loops": {name: list(pair) for name, pair in built.loops.items()},
        "gears": {
            name: {"driver": g["driver"], "driven": g["driven"]} | _valued(p, g, GEAR_BY)
            for name, g in built.gears.items()
        },
        "tendons": {
            name: {"path": list(t["path"])} | _valued(p, t, PHYSICS["tendon"])
            for name, t in built.tendons.items()
        },
        "cables": {
            name: {"path": list(c["path"])}
            | (
                {"wheel": c["wheel"], "closes": _valued(p, c["closes"], c["closes"])}
                if "wheel" in c
                else {}
            )
            for name, c in built.cables.items()
        },
        "dropped": built.dropped,
    }


def masses(built: Built) -> dict:
    """The mass model as the MJCF exports it: each weighed part's mass, the param it comes from,
    and its centre of mass and inertia (ixx iyy izz ixy ixz iyz) in the part's frame."""
    return {
        name: {
            "mass": m.mass,
            "from": {m.by: m.param},
            "center": list(m.center),
            "inertia": list(m.inertia),
        }
        for name, m in built.masses.items()
    }


def _exact_line(p: Project, physics: int) -> str:
    """The Exact line, naming the proposed values exact leaves out: physics values and sweep
    resolutions."""
    aside = [f"{physics} physics value{'s' * (physics != 1)}"] if physics else []
    resolution = sorted(p.proposed & p.resolution)
    if resolution:
        aside.append(f"the sweep resolution{'s' * (len(resolution) != 1)} {', '.join(resolution)}")
    if not aside:
        return "**Exact**: no parameter rests on a proposed value."
    many = len(aside) > 1 or physics > 1 or len(resolution) > 1
    return (
        "**Exact**: no geometry or kinematic parameter rests on a proposed value; "
        f"{' and '.join(aside)} {'are' if many else 'is'} proposed."
    )


def _motion_line(moves: dict | None) -> list[str]:
    if moves is None:
        return []
    if moves["dropped"]:
        return [
            "**Motion dropped**: model.py returns joints or loops the assembly cannot hold (see "
            "the findings), so nothing is posed or exported as MJCF.",
            "",
        ]
    if not moves["joints"]:
        return [
            "**Static**: model.py returns no joints, so nothing is posed or exported as MJCF.",
            "",
        ]
    joints, loops = len(moves["joints"]), len(moves["loops"])
    cables = []
    for name, c in moves["cables"].items():
        line = f"- Cable `{name}` through {' → '.join(c['path'])}"
        if "wheel" in c:
            closes = ", ".join(
                f"{j} to {v['value']:g} ({v['from']})" for j, v in c["closes"].items()
            )
            line += f", wound on {c['wheel']}; its full turn closes {closes}"
        cables.append(line + ".")
    return [
        f"**Kinematic**: {joints} joint{'s' * (joints != 1)} and {loops} "
        f"loop{'s' * (loops != 1)}, exported as `build/model.mjcf`; "
        "a posed check shows its pose beside its interpretation.",
        "",
        *([*cables, ""] if cables else []),
    ]


def _posed(r: CheckResult) -> str:
    """A check's interpretation, after the pose it was evaluated at, if any."""
    posed = swept = ""
    if r.pose is not None:
        posed = f"posed: {pose_text(r.pose)}"
    if r.from_pose is not None:
        posed = f"from: {pose_text(r.from_pose)}; {posed}"
    if r.sweep is not None:
        (low, high), (low_from, high_from) = r.sweep["range"], r.sweep["from"]
        swept = (
            f"swept: {r.sweep['joint']} {low:g} to {high:g} ({low_from} to {high_from}), "
            f"{r.sweep['poses']} poses"
        )
    return "; ".join(filter(None, [swept, posed, interpretation(r)]))


def counts(p: Project, results: list[CheckResult]) -> dict[str, int]:
    """The headline numbers shown beside the status: the params by what they rest on, proposed
    physics values counted apart from the proposed ones."""
    errors = sum(f.level == "error" for f in p.findings)
    apart = p.proposed & p.physics
    return (
        {
            "errors": errors,
            "warnings": len(p.findings) - errors,
            "checks": len(results),
            "checks_passed": sum(r.ok for r in results),
            "params": len(p.params),
        }
        | {
            basis: sum(b == basis and n not in apart for n, b in p.rests_on.items())
            for basis in RESTS_ON
        }
        | {"physics_proposed": len(apart)}
    )


def write(
    p: Project,
    status: str,
    results: list[CheckResult],
    images: list[Path],
    moves: dict | None = None,
    weighed: dict | None = None,
) -> Path:
    """Write build/report.md and build/report.json. moves: how the model moves, and weighed: its
    masses; each None when no model was built."""
    out = p.root / "build"
    out.mkdir(exist_ok=True)
    errors = [f for f in p.findings if f.level == "error"]
    warnings = [f for f in p.findings if f.level == "warning"]
    bases = Counter(spec.get("basis") for spec in p.params.values())
    headline = counts(p, results)
    loosened = tolerances(p)
    limits = overlap_limits(p)
    override = literal_override(p)

    md = [f"# {p.meta.get('name', 'Reconstruction')}: verification report", ""]
    md += [
        f"**{status}**: {headline['errors']} errors, {headline['warnings']} warnings. "
        f"{headline['checks_passed']}/{headline['checks']} geometry checks pass.",
        f"Of {headline['params']} parameters, {headline['source']} rest on sources, "
        f"{headline['measured']} on measured values and {headline['proposed']} on proposed values"
        + (
            f"; {headline['physics_proposed']} more are proposed physics values."
            if headline["physics_proposed"]
            else "."
        ),
        "",
    ]
    if exact(p, status):
        md += [_exact_line(p, headline["physics_proposed"]), ""]
    md += _motion_line(moves)
    md += [
        "VERIFIED means every number in the model is accounted for and the geometry matches "
        "every checked source value. It does not mean the sources fully define the part: "
        "proposed parameters are reconstruction choices, listed below.",
        "",
    ]
    awaiting = awaiting_confirmation(p)
    if status == PENDING_REVIEW:
        md += [
            f"PENDING REVIEW: {len(awaiting)} figure readings await human confirmation, "
            "listed below. "
            "Once a named reviewer has checked each against its crop and written `confirmed_by`, "
            "the project is VERIFIED.",
            "",
        ]

    md += ["## Sources", ""]
    md += _table(
        ["id", "kind", "citation", "sha256"],
        [
            [s["id"], s.get("kind"), s.get("citation"), str(s.get("sha256", ""))[:12]]
            for s in p.meta.get("sources", [])
        ],
    )

    md += ["## Geometry checks against the sources", ""]
    md += _table(
        ["check", "result", "expected (evidence)", "measured", "interpretation"],
        [
            [r.id, "pass" if r.ok else "**FAIL**", r.expected, r.measured, _posed(r)]
            for r in results
        ],
    )

    md += ["## Non-default tolerances", ""]
    md += _table(
        ["check", "kind", "tolerance"],
        [
            [t["check"], t["kind"], next(f"{k} {t[k]:g}" for k in ("tol", "tol_rel") if k in t)]
            for t in loosened
        ],
    )

    md += ["## Non-default overlap limits", ""]
    md += _table(["check", "max_volume"], [[o["check"], f"{o['max_volume']:g}"] for o in limits])

    md += ["## Model literal override", ""]
    md += (
        [
            "project.yaml `model_literals` allows "
            f"{', '.join(f'{v:g}' for v in override)} in model.py, "
            f"in place of the default {', '.join(f'{v:g}' for v in MODEL_LITERALS)}.",
            "",
        ]
        if override is not None
        else ["_None._", ""]
    )

    md += ["## Parameters", ""]
    md += ["Declared basis: " + " · ".join(f"{b}: {bases[b]}" for b in BASES), ""]
    md += _table(
        ["param", "value", "basis", "from / expr", "note"],
        [
            [
                n,
                f"{p.values.get(n, float('nan')):g}",
                str(s.get("basis"))
                + (
                    f" (rests on {p.rests_on[n]})"
                    if s.get("basis") == "derived" and n in p.rests_on
                    else ""
                ),
                s.get("from") or s.get("expr") or "",
                s.get("interpretation") or s.get("rationale") or s.get("method") or "",
            ]
            for n, s in p.params.items()
        ],
    )

    md += ["## Measured parameters", ""]
    md += _table(
        ["param", "value", "from", "method", "uncertainty"],
        [
            [m["param"], f"{m['value']:g}", m["from"], m["method"], m["uncertainty"]]
            for m in measured_params(p)
        ],
    )

    md += ["## Evidence", ""]
    md += _table(
        ["id", "source", "locator", "values", "anchor"],
        [
            [
                e["id"],
                e.get("source"),
                f"{e.get('locator', '')}" + (f", p{e['page']}" if e.get("page") else ""),
                ", ".join(f"{k}={v}" for k, v in (e.get("values") or {}).items()),
                f"“{e['quote']}”"
                if "quote" in e
                else f"figure {e.get('image')}: “{e.get('reading')}”"
                + ("" if e.get("confirmed_by") else " (unconfirmed)"),
            ]
            for e in p.evidence
        ],
    )

    md += ["## Probes of released geometry", ""]
    md += _table(
        ["probe", "body", "kind", "records", "evaluates to", "result"],
        [
            [
                f"{q['evidence']}.{q['key']}",
                q["body"],
                q["probe"],
                f"{q['recorded']:g}",
                f"{q['value']:.6g}",
                "pass" if q["ok"] else "**MISMATCH**",
            ]
            for q in p.probes
        ],
    )

    if awaiting:
        md += ["## Figure readings awaiting human confirmation", ""]
        for a in awaiting:
            md += [
                f"- **{a['evidence']}** ({a['locator']}): reads “{a['reading']}” in `{a['image']}`",
                "",
                f"  ![{a['evidence']}](../{a['image']})",
                "",
            ]

    md += ["## Conflicts between sources", ""]
    md += _table(
        ["id", "evidence", "summary", "resolution"],
        [
            [
                c.get("id"),
                ", ".join(c.get("evidence", [])),
                c.get("summary", ""),
                c.get("resolution") or "**open**",
            ]
            for c in p.conflicts
        ],
    )

    md += ["## Open gaps", ""]
    affected = {gid: [n for n, s in p.params.items() if s.get("gap") == gid] for gid in p.gaps}
    md += _table(
        ["gap", "question", "close by", "params"],
        [
            [gid, g.get("question", ""), g.get("ask", ""), ", ".join(affected[gid])]
            for gid, g in p.gaps.items()
        ],
    )

    if images:
        md += [
            "## Figure overlays",
            "",
            "Model edges (magenta) over the figure, scaled by the cited dimension "
            "(blue). Visual comparison only.",
            "",
        ]
        md += [f"![{i.stem}](overlays/{i.name})" for i in images] + [""]

    md += ["## Findings", ""]
    md += [f"- **{f.level}** `{f.rule}`: {f.message}" for f in errors + warnings] or ["_None._"]

    path = out / "report.md"
    path.write_text("\n".join(md) + "\n", encoding="utf8")
    (out / "report.json").write_text(
        json.dumps(
            {
                "status": status,
                "counts": headline,
                "findings": [asdict(f) for f in errors + warnings],
                "checks": [
                    {
                        k: v
                        for k, v in asdict(r).items()
                        if k not in ("pairs", "pose", "from_pose", "sweep", "uncounted", "shape")
                        or v is not None
                    }
                    for r in results
                ],
                "tolerances": loosened,
                "overlap_limits": limits,
                "model_literals": override,
                "exact": exact(p, status),
                "motion": moves,
                "masses": weighed,
                "params": {
                    n: {"value": p.values.get(n), "rests_on": p.rests_on.get(n), **s}
                    for n, s in p.params.items()
                },
                "bases": dict(bases),
                "rests_on_proposed": sorted(p.proposed),
                "measured": measured_params(p),
                "awaiting_confirmation": awaiting,
                "probes": p.probes,
            },
            indent=2,
            default=str,
        ),
        encoding="utf8",
    )
    return path
