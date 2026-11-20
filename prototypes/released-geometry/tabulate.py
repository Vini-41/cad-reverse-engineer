"""PROTOTYPE for #246, throwaway: the seeded errors' table, today's checks against the one
comparison.

    python tabulate.py <base dir> <seeds dir> <frames/baselines dir>

Today catches a seed when its run files an error the unseeded example does not: a failed check
(split into those comparing with a probe, the shape check, and the rest) or any other error rule.
The comparison catches it when a part it compares fails where the unseeded part passes, or, on a
part that already fails unseeded (compact-sspg's gears, carriers and casing), when more points
lie past tolerance.length than unseeded or the largest deviation grows by more than it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))
from seeds import SEEDS  # noqa: E402

TOL = 0.001


def errors(project: Path) -> set[tuple[str, str]]:
    report = json.loads((project / "build" / "report.json").read_text())
    return {(f["rule"], f["message"]) for f in report["findings"] if f["level"] == "error"}


def check_kinds(project: Path) -> dict[str, str]:
    """Each check id: 'probe' where it compares with a probe, 'shape', or 'other'."""
    evidence = yaml.safe_load((project / "evidence.yaml").read_text()) or {}
    probes = {e["id"] for e in evidence.get("evidence", []) if "probe" in e}
    checks = yaml.safe_load((project / "checks.yaml").read_text()) or {}
    out = {}
    for c in checks.get("checks", []):
        kind = c.get("kind")
        if kind == "shape":
            out[c["id"]] = "shape"
        elif str(c.get("evidence", "")) in probes:
            out[c["id"]] = "probe"
        else:
            out[c["id"]] = "other"
    return out


def today(base: Path, seed: Path) -> dict:
    new = errors(seed) - errors(base)
    kinds = check_kinds(base)
    by = {"probe": [], "shape": [], "other": [], "rules": []}
    for rule, message in sorted(new):
        if rule == "check-failed":
            cid = message.split(":")[0]
            # a shape check of a cut file expands to one id per region
            by[kinds.get(cid, "shape" if cid.startswith("shape-") else "other")].append(cid)
        else:
            by["rules"].append(rule)
    by["rules"] = sorted(set(by["rules"]))
    return by


def comparison(baseline: dict, seeded: dict) -> dict:
    base = {r["check"]: r for r in baseline["rows"]}
    out = {"caught": False, "parts": []}
    for r in seeded["rows"]:
        b = base[r["check"]]
        if "error" in r:
            out["parts"].append(f"{r['check']}: error {r['error']}")
            continue
        if r["kind"] == "stl":
            more = (r["corners_over"] or 0) > (b["corners_over"] or 0) or r["part_points_over"] > b[
                "part_points_over"
            ] or r["facets_over"] > b["facets_over"]
            grew = r["deviation"] > b["deviation"] + TOL
            caught = (not r["ok"] and b["ok"]) or more or grew
            note = (
                f"{r['check']}: corners {b['corner_dev']:.3g}->{r['corner_dev']:.3g} "
                f"({b['corners_over']}->{r['corners_over']} past tol), part points "
                f"{b['part_dev']:.3g}->{r['part_dev']:.3g} "
                f"({b['part_points_over']}->{r['part_points_over']}), facets off a patch "
                f"{b['facets_over']}->{r['facets_over']}"
            )
        else:
            caught = (not r["ok"] and b["ok"]) or r["deviation"] > b["deviation"] + TOL
            note = f"{r['check']}: {b['deviation']:.3g}->{r['deviation']:.3g}"
        out["caught"] |= caught
        if caught or r["check"] == seeded["rows"][0]["check"]:
            out["parts"].append(note)
    return out


def main() -> None:
    base_dir, seeds_dir, frames_dir = (Path(a) for a in sys.argv[1:4])
    rows = []
    for sid, (example, kind, what, _, _, _) in SEEDS.items():
        seed = seeds_dir / sid
        t = today(base_dir / example, seed)
        baseline = json.loads((frames_dir / f"{example}.base.json").read_text())
        dev = json.loads((seeds_dir / f"{sid}.dev.json").read_text())
        c = comparison(baseline, dev)
        caught_today = bool(t["probe"] or t["shape"] or t["other"] or t["rules"])
        rows.append(
            {
                "seed": sid,
                "example": example,
                "kind": kind,
                "what": what,
                "today": caught_today,
                "today_probe_checks": t["probe"],
                "today_shape_checks": t["shape"],
                "today_other_checks": t["other"],
                "today_rules": t["rules"],
                "comparison": c["caught"],
                "comparison_detail": c["parts"],
            }
        )
    print(json.dumps(rows, indent=1))


if __name__ == "__main__":
    main()
