"""model.py and the checks on what it builds: the lint, each check kind passing and failing,
tolerances, and what a check rests on."""

import re

import pytest
from conftest import (
    ASSEMBLY,
    LINK,
    MODEL,
    PAPER,
    add,
    add_line,
    add_quote,
    change,
    check,
    ledgered,
    meta,
    number,
    place,
    project,
    remodel,
    stack,
    write,
)

# A finger of three links, each lying on the last, as its notes state it.
FINGER = [
    ("The holes are bored 3 mm, square at 90° to the face.", {"d": 3, "sq": 90}),
    (
        "Three links make a finger, each lying 8 mm above the last, the upper two 16 mm high.",
        {"n": "three", "lift": 8, "pair": "two", "h": 16},
    ),
    (
        "The upper two weigh 3.57 g, or 11.07 g with a 7.5 g servo, in resin of 1.2 g/cm3.",
        {"m": 3.57, "total": 11.07, "servo": 7.5, "rho": 1.2},
    ),
]
FINGER_PARAMS = """\
rho: {basis: source, from: N2.rho}
rho_guess: {basis: proposed, value: 0.0012, rationale: a typical resin, gap: G1}
servo_m: {basis: source, from: N2.servo}
n_pair: {basis: source, from: N1.pair}
pair: {basis: derived, expr: n_pair * 1}
"""
UPPER = "instances: [link_2, link_3]"
PAIR = f"kind: mass, {UPPER}, counts: {{link: pair}}"
# Each kind with each of its options, compared with a value the notes state; a check named not-*
# compares the same geometry with a value it does not have, or other geometry with the same value.
FINGER_CHECKS = f"""\
- {{id: bbox, kind: bbox, {UPPER}, evidence: N1, axes: {{h: z}}}}
- {{id: not-bbox, kind: bbox, instances: [link_1, link_2, link_3], evidence: N1, axes: {{h: z}}}}
- {{id: distance, kind: distance, instances: [link_1, link_2], between: [link_1.a, link_2.a],
   evidence: N1, key: lift}}
- {{id: along, kind: distance, instances: [link_1, link_3], between: [link_1.a, link_3.b],
   along: z, evidence: N1, key: h}}
- {{id: not-along, kind: distance, instances: [link_1, link_3], between: [link_1.a, link_3.b],
   evidence: N1, key: h}}
- {{id: angle, kind: angle, between: [link.b, link.a, link.top], evidence: N0, key: sq}}
- {{id: not-angle, kind: angle, between: [link.b, link.a, link.wall], evidence: N0, key: sq}}
- {{id: angle-over, kind: angle, instances: [link_1, link_2], evidence: N0, key: sq,
   between: [link_1.b, link_1.a, link_2.a]}}
- {{id: diameter, kind: diameter, at: link.wall, evidence: N0, key: d}}
- {{id: not-diameter, kind: diameter, at: link.wall, evidence: N1, key: lift}}
- {{id: count, kind: count, part: link, evidence: N1, key: n}}
- {{id: not-count, kind: count, part: link, evidence: N1, key: pair}}
- {{id: mass, {PAIR}, density: rho, evidence: N2, key: m, tol_rel: 0.01}}
- {{id: not-mass, {PAIR}, density: rho, evidence: N2, key: total, tol_rel: 0.01}}
- {{id: mass-add, {PAIR}, parts: [link], density: rho, add: [servo_m], evidence: N2, key: total,
   tol_rel: 0.01}}
- {{id: mass-guessed, {PAIR}, density: rho_guess, evidence: N2, key: m, tol_rel: 0.01}}
- {{id: mass-uncounted, kind: mass, {UPPER}, density: rho, evidence: N2, key: m, tol_rel: 0.01}}
- {{id: listed, kind: interference, pairs: [[link_1, link_2]]}}
- {{id: expect, kind: distance, instances: [link_1, link_3], between: [link_1.a, link_3.a],
   expect: "N1.lift * N1.pair"}}
- {{id: not-expect, kind: distance, instances: [link_1, link_3], between: [link_1.a, link_3.a],
   expect: "N1.lift * N1.n"}}
- {{id: expect-angle, kind: angle, between: [link.b, link.a, link.top],
   expect: "2 * degrees(atan2(N1.lift, N1.lift))"}}
- {{id: expect-diameter, kind: diameter, at: link.wall, expect: "N1.h / N1.lift + 1"}}
- {{id: expect-mass, {PAIR}, density: rho, add: [servo_m], expect: "N2.m + N2.servo",
   tol_rel: 0.01}}
- {{id: expect-count, kind: count, part: link, expect: "N1.pair + 1"}}
- {{id: not-expect-count, kind: count, part: link, expect: "N1.pair * N1.pair"}}
"""


@pytest.fixture(scope="module")
def finger(tmp_path_factory):
    """One run of the finger, every static check kind in it."""
    tmp_path = tmp_path_factory.mktemp("finger")
    root = project(tmp_path, PAPER, LINK, "A demo finger, as")
    stack(root, 3)
    add(root, params=FINGER_PARAMS, checks=FINGER_CHECKS)
    return ledgered(root, tmp_path, [(text, text.rstrip("."), values) for text, values in FINGER])


def test_each_check_kind_passes_on_what_the_ledger_states_and_fails_on_what_it_does_not(finger):
    results = {c["id"]: c for c in finger.report["checks"]}
    assert len(results) == 30 and finger.errors == ["check-failed"] * 8
    assert {cid for cid, c in results.items() if not c["ok"]} == {
        cid for cid in results if cid.startswith("not-")
    }
    assert {cid: number(c) for cid, c in results.items()} == pytest.approx(
        {
            "env.L": 40,
            "env.H": 8,
            "env.W": 5,
            "pitch": 30,
            "clear": 0,
            "bbox.h": 16,
            "not-bbox.h": 24,
            "distance": 8,
            "along": 16,
            "not-along": 34,
            "angle": 90,
            "not-angle": 0,
            "angle-over": 90,
            "diameter": 3,
            "not-diameter": 3,
            "count": 3,
            "not-count": 3,
            "mass": 3.569,
            "not-mass": 3.569,
            "mass-add": 11.07,
            "mass-guessed": 3.569,
            "mass-uncounted": 3.569,
            "listed": 0,
            "expect": 16,
            "not-expect": 16,
            "expect-angle": 90,
            "expect-diameter": 3,
            "expect-mass": 11.07,
            "expect-count": 3,
            "not-expect-count": 3,
        },
        abs=5e-4,
    )
    assert results["expect"]["expect"] == {"expr": "N1.lift * N1.pair", "value": 16}
    assert results["not-expect"]["expected"] == "24 (N1.lift * N1.n)"
    # A count per leg or per joint is a stated count times another.
    assert results["expect-count"]["expect"] == {"expr": "N1.pair + 1", "value": 3}
    assert results["not-expect-count"]["expected"] == "4 (N1.pair * N1.pair)"
    assert results["mass"]["expected"] == "3.57 ±1% (N2.m)"
    # An interference check says how many pairs it tried, all of them where it lists none.
    assert (results["clear"]["pairs"], results["listed"]["pairs"]) == (3, 1)
    assert results["clear"]["measured"] == "0 over 3 pairs (all)"


# A datasheet's table: the link's pitch, built to 30, against ranges around and beside it.
TABLE = "Pitch 29.5 mm MIN, 30.5 mm MAX. Next 30.2 mm MIN, 31 mm MAX. Last 28 mm MIN, 29.8 mm MAX."
TABLE_VALUES = {"low": 29.5, "high": 30.5, "above": 30.2, "far": 31, "under": 28, "below": 29.8}
PITCH = "kind: distance, between: [link.a, link.b]"


def test_check_against_a_stated_range_passes_inside_and_fails_outside(proj_dir, tmp_path):
    add_quote(proj_dir, tmp_path, TABLE, values=TABLE_VALUES)
    add(
        proj_dir,
        checks=f"""\
- {{id: inside, {PITCH}, min: N1.low, max: N1.high}}
- {{id: not-under-min, {PITCH}, min: N1.above, max: N1.far}}
- {{id: not-over-max, {PITCH}, min: N1.under, max: N1.below}}
- {{id: at-most, {PITCH}, max: N1.high}}
- {{id: not-at-most, {PITCH}, max: N1.below}}
- {{id: at-least, {PITCH}, min: N1.low}}
- {{id: not-at-least, {PITCH}, min: N1.above}}
""",
    )
    run = check(proj_dir)
    ranged = [c for c in run.report["checks"] if c["id"] not in ("env.L", "env.H", "env.W")]
    ranged = {c["id"]: c for c in ranged if c["id"] not in ("pitch", "clear")}
    assert {cid for cid, c in ranged.items() if not c["ok"]} == {
        cid for cid in ranged if cid.startswith("not-")
    }
    assert len(ranged) == 7 and run.errors == ["check-failed"] * 4
    assert ranged["inside"]["expected"] == "29.5 to 30.5 (N1.low to N1.high)"
    assert ranged["at-most"]["expected"] == "≤ 30.5 (N1.high)"
    assert ranged["at-least"]["expected"] == "≥ 29.5 (N1.low)"


def test_each_kind_that_compares_one_value_takes_a_stated_range(proj_dir, tmp_path):
    text = "Holes of 2.9 mm to 3.1 mm, square at 89° to 91°, 1 to 2 links, of 1.7 g to 1.9 g in "
    values = {"d_lo": 2.9, "d_hi": 3.1, "sq_lo": 89, "sq_hi": 91, "n_lo": 1, "n_hi": 2}
    values |= {"m_lo": 1.7, "m_hi": 1.9, "rho": 1.2}
    add_quote(proj_dir, tmp_path, text + "resin of 1.2 g/cm3.", values=values)
    add(
        proj_dir,
        params="rho: {basis: source, from: N1.rho}",
        checks="""\
- {id: bore, kind: diameter, at: link.wall, min: N1.d_lo, max: N1.d_hi}
- {id: square, kind: angle, between: [link.b, link.a, link.top], min: N1.sq_lo, max: N1.sq_hi}
- {id: links, kind: count, part: link, min: N1.n_lo, max: N1.n_hi}
- {id: not-links, kind: count, part: link, min: N1.n_hi}
- {id: weight, kind: mass, parts: [link], density: rho, min: N1.m_lo, max: N1.m_hi}
- {id: not-weight, kind: mass, parts: [link], density: rho, min: N1.m_hi}
""",
    )
    run = check(proj_dir)
    assert run.errors == ["check-failed"] * 2
    assert [run.result(c)["ok"] for c in ("bore", "square", "links", "weight")] == [True] * 4
    assert not run.result("not-links")["ok"] and not run.result("not-weight")["ok"]
    assert run.result("not-links")["expected"] == "≥ 2 (N1.n_hi)"
    assert run.result("weight")["expected"] == "1.7 to 1.9 (N1.m_lo to N1.m_hi)"


def test_a_stated_range_holds_its_ends_to_how_closely_the_model_realises_a_value(
    proj_dir, tmp_path
):
    text = "Pitch 0 mm MIN, 30 mm, 29.995 mm MIN, 30.005 mm MAX, 29.9995 mm MAX, or 29.99 mm MAX."
    values = {"zero": 0, "same": 30, "low": 29.995, "high": 30.005, "near": 29.9995, "past": 29.99}
    add_quote(proj_dir, tmp_path, text, values=values)
    add(
        proj_dir,
        checks=f"""\
- {{id: from-zero, {PITCH}, min: N1.zero}}
- {{id: one-value, {PITCH}, min: N1.same, max: N1.same}}
- {{id: narrow, {PITCH}, min: N1.low, max: N1.high}}
- {{id: within-tolerance, {PITCH}, max: N1.near}}
- {{id: not-past, {PITCH}, max: N1.past}}
""",
    )
    run = check(proj_dir)
    assert run.errors == ["check-failed"] and not run.result("not-past")["ok"]
    held = ("from-zero", "one-value", "narrow", "within-tolerance")
    assert all(run.result(cid)["ok"] for cid in held)


def test_each_end_of_a_stated_range_counts_as_compared(proj_dir, tmp_path):
    add_quote(proj_dir, tmp_path, TABLE, values={"low": 29.5, "high": 30.5})
    assert check(proj_dir).rules.count("evidence-unused") == 2
    # The pitch param's own value is then compared only through the range's end that names it.
    change(proj_dir, "checks", "pitch", evidence=None, key=None, max="pitch.pitch")
    add(proj_dir, checks=f"{{id: table, {PITCH}, min: N1.low, max: N1.high}}")
    run = check(proj_dir)
    assert "evidence-unused" not in run.rules and "unchecked-source" not in run.rules


@pytest.mark.parametrize("chosen", ["(pitch_min + pitch_max) / 2", "pitch_max - 0.5"])
def test_value_chosen_inside_a_range_is_a_derived_choice_resting_on_proposed(
    proj_dir, tmp_path, chosen
):
    # The source states the pitch only as a range, so the 30 it is built to is the model's choice.
    add_quote(proj_dir, tmp_path, TABLE, values={"low": 29.5, "high": 30.5})
    change(proj_dir, "evidence", "pitch", scope="not-modeled", reason="another variant")
    change(proj_dir, "checks", "pitch", evidence=None, key=None, min="N1.low", max="N1.high")
    add(
        proj_dir,
        gaps="{id: G2, question: 'what is the nominal pitch?', ask: the maker}",
        params="""\
pitch_min: {basis: source, from: N1.low}
pitch_max: {basis: source, from: N1.high}
""",
    )
    choice = {"expr": chosen, "gap": "G2", "from": None}
    change(proj_dir, "params", "pitch", basis="derived", interpretation="mid-range", **choice)
    run = check(proj_dir)
    assert run.status == "VERIFIED" and run.result("pitch")["ok"]
    assert run.report["params"]["pitch"]["rests_on"] == "proposed"
    assert run.report["params"]["pitch_max"]["rests_on"] == "source"
    assert "| pitch | 30 | derived (rests on proposed) |" in run.md
    assert "| G2 | what is the nominal pitch? | the maker | pitch |" in run.md


def test_check_rests_on_the_weakest_param_it_reads_and_checks_the_source_ones(finger):
    results = {c["id"]: c for c in finger.report["checks"]}
    rests = {cid: (c["rests_on"], c["rests_on_params"]) for cid, c in results.items()}
    assert rests["diameter"] == ("source", []) and rests["mass"] == ("source", ["rho", "pair"])
    assert rests["mass-add"] == ("source", ["rho", "servo_m", "pair"])
    assert rests["mass-guessed"] == ("proposed", ["rho_guess"])
    # How many links there are is the model's choice where no stated count is given.
    assert rests["mass-uncounted"] == ("proposed", [])
    assert results["mass-uncounted"]["uncounted"] == {"link": 2}
    assert "uncounted" not in results["diameter"] and results["mass"]["uncounted"] == {}
    assert "rests on proposed: rho_guess |" in finger.md
    assert "rests on proposed: link (2 instances uncounted) |" in finger.md
    # A density, an add and a count read through a derived param are checked by the check that
    # reads them, and need no read in model.py.
    assert set(finger.rules) == {"check-failed"}


def test_angle_check_along_an_axis_reads_it_in_the_parts_or_the_assemblys_frame(proj_dir):
    # The angle at the link's top datum between its side datum, 2.5 mm across the link, and hole
    # b: 11.71° in 3-D, 9.462° about the part's Z and 7.337° about its Y. link_1 is turned a
    # quarter about X, which carries the part's Y onto the assembly's Z.
    place(proj_dir, link_1="Location((0, 0, 0), (1, 0, 0), 90)")
    about_z, about_y = "degrees(atan2(2.5, 15))", "degrees(atan2(4, 15) - atan2(4, 30))"
    solid = "degrees(acos(466 / sqrt(247.25 * 916)))"
    part = {"kind": "angle", "between": ["link.side", "link.top", "link.b"]}
    turned = {"kind": "angle", "instances": ["link_1"]}
    turned |= {"between": ["link_1.side", "link_1.top", "link_1.b"]}
    add(
        proj_dir,
        checks=[
            part | {"id": "part-z", "along": "z", "expect": about_z},
            part | {"id": "part-y", "along": "y", "expect": about_y},
            part | {"id": "part", "expect": solid},
            turned | {"id": "turned-z", "along": "z", "expect": about_y},
            turned | {"id": "turned-y", "along": "y", "expect": about_z},
            turned | {"id": "turned", "expect": solid},
        ],
    )
    run = check(proj_dir)
    assert run.status == "VERIFIED", run.out
    measured = {c["id"]: number(c) for c in run.report["checks"] if c["kind"] == "angle"}
    assert measured == pytest.approx(
        {"part-z": 9.462, "part-y": 7.337, "part": 11.71}
        | {"turned-z": 7.337, "turned-y": 9.462, "turned": 11.71},
        abs=5e-4,
    )


def flagged(run, rule: str) -> set[int]:
    """The model.py lines a rule's findings name."""
    return {int(message.split(":")[1]) for message in run.messages(rule)}


# A statement of model.py, and whether the lint finds a number in it that params.yaml must hold.
LITERALS = {
    "7.5": True,
    "1e1": True,
    "3.0": True,
    "0x3": True,
    "3_0": True,
    "p.link_L / 3": True,
    "p.pitch ** 3": True,
    "2 * 2 - 0.5": True,
    "p.pitch * (180 + 91)": True,
    "-90": False,
    "2.0": False,
    "1 / 2": False,
    "180 + 90": False,
    "p.pitch * 2 * 0.5": False,
    "-p.pitch / 2": False,
    "int(p.pitch) + True": False,
    '"7.5 mm"': False,
}
IMPORTS = {
    "from __future__ import annotations": True,
    "import os": True,
    "from json import loads": True,
    "import fractions as f": True,
    "import math": False,
    "from math import pi": False,
    "import build123d.topology as topo": False,
    "from build123d import Box": False,
}
LOADS = {
    'import_stl("link.stl")': True,
    'open("link.txt")': True,
    "Mesher()": True,
    "topo.Mesher().read(p.pitch)": True,
    "math.floor(p.pitch)": False,
}


def test_lint_finds_every_number_import_and_file_read_and_nothing_else(proj_dir):
    # Each literal is a statement of build(), each call one of a function nothing calls.
    literals = {f"    x = {literal}": found for literal, found in LITERALS.items()}
    loads = {f"    y = {call}": found for call, found in LOADS.items()}
    first = "def build(p):\n"
    body = MODEL.replace(first, first + "".join(f"{line}\n" for line in literals))
    lines = [*IMPORTS, *body.splitlines(), "", "", "def unused(p):", *loads]
    write(proj_dir, "model.py", "\n".join(lines) + "\n")
    run = check(proj_dir)

    def found(*tables: dict) -> set[int]:
        return {lines.index(row) + 1 for table in tables for row in table if table[row]}

    assert flagged(run, "model-literal") == found(literals)
    assert flagged(run, "model-import") == found(IMPORTS, loads)
    assert set(run.errors) == {"model-literal", "model-import"}  # and it still builds


def test_model_that_fails_to_build_still_reports_the_ledger(proj_dir):
    add_line(proj_dir, "raise ValueError(p.pitch)")
    run = check(proj_dir)
    assert run.errors == ["model-build"] and "model.py line 5" in run.messages("model-build")[0]
    assert (run.report["checks"], run.report["motion"], run.report["masses"]) == ([], None, None)
    assert run.report["params"]["pitch"]["value"] == 30 and "| pitch | paper |" in run.md


SLACK = "slack: {basis: proposed, value: 0.004, rationale: print slack, gap: G1}"
ENV_TOL = {"check": "env", "kind": "bbox", "tol": 0.01}
PITCH_TOL = {"check": "pitch", "kind": "distance", "tol": 0.01}
# Where the tolerance is loosened: the tolerances and the overlap limits the report then lists.
LOOSENED = {
    "nowhere": ([], []),
    "check": ([ENV_TOL], []),
    "project": ([ENV_TOL, PITCH_TOL], [{"check": "clear", "max_volume": pytest.approx(1e-6)}]),
}


@pytest.mark.parametrize("where", LOOSENED)
def test_check_passes_within_its_tolerance_and_the_report_lists_each_one_loosened(proj_dir, where):
    tolerances, limits = LOOSENED[where]
    # The link is built 0.004 mm too long, four times the default tolerance.
    add(proj_dir, params=SLACK)
    remodel(proj_dir, "Box(p.link_L,", "Box(p.link_L + p.slack,")
    if where == "check":
        change(proj_dir, "checks", "env", tol=0.01)
    elif where == "project":
        meta(proj_dir, tolerance={"length": 0.01})
    run = check(proj_dir)
    assert run.result("env.L")["ok"] == (where != "nowhere")
    assert run.errors == (["check-failed"] if where == "nowhere" else [])
    # An interference check's limit is tolerance.length cubed, and listed when that is not 1e-9.
    assert (run.report["tolerances"], run.report["overlap_limits"]) == (tolerances, limits)


def test_interference_names_the_worst_overlap_and_passes_under_a_stated_limit(proj_dir):
    place(proj_dir, link_1="Location()", link_2="Location((0, 0, p.link_H / 2))")
    run = check(proj_dir)
    clear = run.result("clear")
    assert not clear["ok"] and clear["measured"] == "743.5 link_1 ∩ link_2 over 1 pair (all)"
    assert clear["expected"] == "overlap ≤ 1e-09"
    change(proj_dir, "checks", "clear", max_volume=750)
    run = check(proj_dir)
    assert run.result("clear")["ok"] and run.status == "VERIFIED"
    assert run.report["overlap_limits"] == [{"check": "clear", "max_volume": 750}]


def test_interference_between_instances_of_a_part_of_no_solid_is_its_finding(proj_dir):
    stack(proj_dir, 2)
    remodel(proj_dir, '"parts": {"link": link}', '"parts": {"link": Compound([])}')
    run = check(proj_dir)
    assert "part-invalid" in run.errors and run.status == "NOT VERIFIED"
    assert run.result("clear")["measured"] == "0 over 1 pair (all)"


@pytest.mark.parametrize("link", ["link", "Rot(0, 0, 180) * link"])  # as built, and located
def test_assembly_step_names_each_part_once_and_each_instance_as_placed(proj_dir, link):
    remodel(proj_dir, '"parts": {"link": link}', f'"parts": {{"link": {link}}}')
    stack(proj_dir, 3)
    check(proj_dir)
    step = (proj_dir / "build" / "assembly.step").read_text()
    products = re.findall(r"= PRODUCT\('([^']+)'", step)
    placed = re.findall(r"NEXT_ASSEMBLY_USAGE_OCCURRENCE\('\d+','([^']+)'", step)
    assert products[1:] == ["link"] and placed == ["link_1", "link_2", "link_3"]


def test_part_no_instance_places_is_checked_and_exported_in_its_own_frame(proj_dir):
    remodel(proj_dir, ASSEMBLY, '"assembly": {},')
    run = check(proj_dir)
    assert run.status == "VERIFIED" and all(c["ok"] for c in run.report["checks"])
    assert run.result("clear")["measured"] == "0 over 0 pairs (all)"
    assert (proj_dir / "build" / "parts" / "link.step").is_file()
    assert not (proj_dir / "build" / "assembly.step").exists()
