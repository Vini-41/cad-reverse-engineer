"""model.py and the checks on what it builds: the lint, each check kind passing and failing,
tolerances, what a check rests on, and overlays."""

import pytest
from conftest import (
    ASSEMBLY,
    LINK,
    MODEL,
    PAPER,
    add,
    add_line,
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
    assert len(results) == 28 and finger.errors == ["check-failed"] * 7
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
        },
        abs=5e-4,
    )
    assert results["expect"]["expect"] == {"expr": "N1.lift * N1.pair", "value": 16}
    assert results["not-expect"]["expected"] == "24 (N1.lift * N1.n)"
    assert results["mass"]["expected"] == "3.57 ±1% (N2.m)"
    # An interference check says how many pairs it tried, all of them where it lists none.
    assert (results["clear"]["pairs"], results["listed"]["pairs"]) == (3, 1)
    assert results["clear"]["measured"] == "0 over 3 pairs (all)"


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


def test_widened_model_literals_let_their_numbers_in_and_are_shown(proj_dir):
    add_line(proj_dir, "extra = 7.5 + 90")
    meta(proj_dir, model_literals=[0, 1, 2, 7.5])
    run = check(proj_dir)
    assert flagged(run, "model-literal") == {5}  # 7.5 + 90 folds to 97.5, which is not allowed
    add_line(proj_dir, "allowed = 7.5 * p.pitch / 2")
    remodel(proj_dir, "    extra = 7.5 + 90\n", "")
    run = check(proj_dir)
    assert run.status == "VERIFIED" and run.report["model_literals"] == [0, 1, 2, 7.5]
    assert "`model_literals` allows 0, 1, 2, 7.5 in model.py" in run.md


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
    assert (run.report["tolerances"], run.report["overlap_limits"]) == (tolerances, limits)
    # An interference check's limit is tolerance.length cubed, and shown when that is not 1e-9.
    assert ("| clear | 1e-06 |" in run.md) == bool(limits)


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
    assert "| clear | 750 |" in run.md


def test_part_no_instance_places_is_checked_and_exported_in_its_own_frame(proj_dir):
    remodel(proj_dir, ASSEMBLY, '"assembly": {},')
    run = check(proj_dir)
    assert run.status == "VERIFIED" and all(c["ok"] for c in run.report["checks"])
    assert run.result("clear")["measured"] == "0 over 0 pairs (all)"
    assert (proj_dir / "build" / "parts" / "link.step").is_file()
    assert not (proj_dir / "build" / "assembly.step").exists()


# What an overlay names, and the columns of its figure the link's edges then span.
TARGETS = {
    "part": ({"part": "link"}, (160, 240)),
    "instance": ({"instance": "link"}, (220, 300)),
    "assembly": ({"part": "assembly"}, (220, 300)),
}


@pytest.mark.parametrize("named", TARGETS)
def test_overlay_draws_the_models_edges_over_its_figure_pixel_for_pixel(proj_dir, named):
    target, columns = TARGETS[named]
    import numpy as np
    from PIL import Image

    # An instance named after its part and placed 30 mm along X: `part` draws the part in its
    # own frame, `instance` and `assembly` where the assembly places it. 2 px per mm.
    place(proj_dir, link="Location((p.pitch, 0, 0))")
    (proj_dir / "figures").mkdir()
    figure = Image.new("RGB", (400, 200), "white")
    figure.putpixel((0, 0), (255, 0, 0))
    figure.save(proj_dir / "figures" / "fig.png")
    calibration = {"pixels": [[50, 150], [110, 150]], "evidence": "pitch.pitch"}
    overlay = {"id": "front", "image": "figures/fig.png", "view": "front", "origin": [200, 100]}
    add(proj_dir, overlays=overlay | {"calibration": calibration} | target)
    run = check(proj_dir)
    assert run.status == "VERIFIED" and "![front](overlays/front.png)" in run.md
    png = np.asarray(Image.open(proj_dir / "build" / "overlays" / "front.png").convert("RGB"))
    strip = png.shape[0] - 200  # the title, above the figure
    assert png.shape[1] == 400 and strip > 0 and (png[:strip] < 128).any()
    image = png[strip:].astype(int)
    assert tuple(image[0, 0]) == (255, 0, 0)
    magenta = (image[:, :, 0] > 150) & (image[:, :, 1] < 150) & (image[:, :, 2] > 80)
    drawn = np.nonzero(magenta.any(axis=0))[0]
    assert (drawn.min(), drawn.max()) == pytest.approx(columns, abs=1)
    rows = np.nonzero(magenta[:, columns[0] + 20])[0]  # the link's faces at z = ±4 mm
    assert (rows.min(), rows.max()) == pytest.approx((92, 108), abs=1)
    blue = (image[:, :, 2] > 150) & (image[:, :, 0] < 120)  # the calibration span
    assert np.nonzero(blue.any(axis=0))[0].min() == pytest.approx(50, abs=3)
