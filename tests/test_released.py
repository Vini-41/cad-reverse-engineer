"""Geometry the authors released: a STEP's or STL's bodies, probes of them and shape checks
against them, and a cut file's regions."""

import math
import re

import pytest
from build123d import Box, Compound, Location, Polygon, Pos, Sphere, export_step, extrude
from conftest import (
    FACE_DATUMS,
    PROBE,
    SHEET,
    add,
    change,
    check,
    link_body,
    meta,
    probed,
    project,
    register,
    released,
    remodel,
    sheet,
    write,
)


@pytest.mark.parametrize(
    "file",
    [{}, {"name": "link.stl", "datums": FACE_DATUMS, "tol": 0.01}],
    ids=["step", "stl"],
)
def test_shape_check_carries_the_built_part_onto_its_released_body(proj_dir, tmp_path, file):
    # The file holds the link a quarter turn about Z and off the origin; an STL's holes are
    # facets, which lie within its tolerance of the built link's cylinders.
    released(proj_dir, tmp_path, **file)
    run = check(proj_dir)
    shape = run.result("shape")["shape"]
    assert run.status == "VERIFIED" and set(shape) == {"residual", "distance", "worst_point"}
    assert shape["residual"] < 1e-9 and shape["distance"] < file.get("tol", 1e-9)
    assert run.result("shape")["rests_on"] == "source"


def test_shape_check_fails_at_the_feature_the_built_part_lacks(proj_dir, tmp_path):
    # The released link has a 2 mm hole at its middle, 2.5 mm from the built link's nearest face.
    released(proj_dir, tmp_path, solid=link_body(extra_hole=True), at=Location())
    run = check(proj_dir)
    shape = run.result("shape")["shape"]
    assert run.errors == ["check-failed"] and not run.result("shape")["ok"]
    assert shape["distance"] == pytest.approx(2.5, abs=1e-6)
    assert math.hypot(*shape["worst_point"][:2]) == pytest.approx(1, abs=1e-6)


def test_shape_check_whose_datum_pairs_do_not_fit_fails_before_comparing_surfaces(
    proj_dir, tmp_path
):
    # The released holes are 32 mm apart and the built ones 30, so a and b cannot both fit.
    wide = {"a": (-16, 0, 0), "b": (16, 0, 0), "top": (-16, 0, 4)}
    released(proj_dir, tmp_path, solid=link_body(pitch=32), datums=wide, tol=0.4)
    run = check(proj_dir)
    result = run.result("shape")
    assert not result["ok"] and set(result["shape"]) == {"residual"}
    assert result["shape"]["residual"] > 0.5 and "datum pairs fit within" in result["expected"]


PROBES = """\
- {id: P-pitch, source: link_step, locator: hole axes, probe: distance, values: {v: 30},
   between: [link_step.a, link_step.b], scope: context, reason: restates pitch}
- {id: P-rise, source: link_step, locator: hole a, probe: distance, values: {v: 4}, along: z,
   between: [link_step.b, link_step.top], scope: context, reason: half of T1-link.H}
- {id: P-square, source: link_step, locator: hole a, probe: angle, values: {v: 90},
   between: [link_step.b, link_step.a, link_step.top], scope: context, reason: a right angle}
- {id: P-bore, source: link_step, locator: hole a, probe: diameter, values: {d: 3},
   at: link_step.wall}
"""


def test_probe_reads_a_released_body_and_a_param_takes_its_value(proj_dir, tmp_path):
    probed(proj_dir, tmp_path)
    add(proj_dir, datums="link_step.wall: [100, 36.5, 20]", evidence=PROBES)
    # No source states the bore, so its probe is in scope: the hole reads it, and a check compares.
    change(proj_dir, "params", "hole_d", basis="source", value=None, rationale=None, gap=None)
    change(proj_dir, "params", "hole_d", **{"from": "P-bore.d"})
    add(proj_dir, checks="{id: bore, kind: diameter, at: link.wall, evidence: P-bore, key: d}")
    write(proj_dir, "gaps.yaml", "gaps: []\n")
    run = check(proj_dir)
    # A probe needs no confirmation, and a project resting on probes and quotes alone is exact.
    assert run.status == "VERIFIED" and run.rules == [] and run.report["exact"]
    assert run.report["params"]["hole_d"]["value"] == 3
    probes = {f"{q['evidence']}.{q['key']}": q for q in run.report["probes"]}
    assert {name: round(q["value"], 9) for name, q in probes.items()} == {
        "P-link.L": 40,
        "P-link.W": 5,
        "P-link.H": 8,
        "P-pitch.v": 30,
        "P-rise.v": 4,
        "P-square.v": 90,
        "P-bore.d": 3,
    }
    assert probes["P-bore.d"] == {
        "evidence": "P-bore",
        "key": "d",
        "body": "link_step",
        "probe": "diameter",
        "recorded": 3,
        "value": pytest.approx(3),
        "tol": 0.001,
        "ok": True,
    }
    assert "| P-pitch.v | link_step | distance | 30 | 30 | pass |" in run.md


def test_probe_recording_another_value_than_its_body_gives_is_a_mismatch(proj_dir, tmp_path):
    probed(proj_dir, tmp_path, values={"L": 40.2, "W": 5, "H": 8})
    run = check(proj_dir)
    (message,) = run.messages("probe-mismatch")
    assert "P-link.L" in message and "40.2" in message and "evaluates to 40 " in message
    assert [q["ok"] for q in run.report["probes"]] == [False, True, True]
    assert "| P-link.L | link_step | bbox | 40.2 | 40 | **MISMATCH** |" in run.md
    # Within the probe's own tol, which is capped at 5% of each value, it matches.
    change(proj_dir, "evidence", "P-link", tol=0.25)
    assert check(proj_dir).status == "VERIFIED"


@pytest.mark.parametrize("name", ["both.step", "both.stl"])
def test_file_of_several_solids_names_each_body_by_its_place_in_it(proj_dir, tmp_path, name):
    # A 4 mm cube, then the link: link_step#1 and link_step#2.
    both = Compound(children=[Pos(0, 40, 0) * Box(4, 4, 4), link_body()])
    released(proj_dir, tmp_path, solid=both, name=name, datums={}, check=False)
    cube = {"id": "P-cube", "body": "link_step#1", "axes": {"s": "z"}, "values": {"s": 4}}
    add(proj_dir, evidence=[PROBE | cube, PROBE | {"body": "link_step#2"}])
    run = check(proj_dir)
    assert [(q["body"], q["ok"]) for q in run.report["probes"]] == [
        ("link_step#1", True),
        *[("link_step#2", True)] * 3,
    ]
    # Each body is compared by a shape check or set aside by a skip.
    assert [m.split(":")[0] for m in run.messages("coverage")] == [
        "link_step body link_step#1",
        "link_step body link_step#2",
    ]
    skips = [{"source": "link_step", "body": f"link_step#{n}", "reason": "probed"} for n in (1, 2)]
    add(proj_dir, skipped=skips)
    assert check(proj_dir).status == "VERIFIED"


@pytest.mark.parametrize("name", ["link.stl", "link.step"])
def test_released_geometry_is_read_in_millimetres_into_the_projects_length_unit(
    proj_dir, tmp_path, name
):
    meta(proj_dir, units={"length": "cm"})
    released(proj_dir, tmp_path, name=name, datums={}, check=False)
    add(proj_dir, evidence=PROBE | {"values": {"L": 4, "W": 0.5, "H": 0.8}})
    add(proj_dir, datums="link_step.side: [9.75, 5, 2]")  # (97.5, 50, 20) mm, on its side face
    add(proj_dir, skipped="{source: link_step, body: link_step, reason: probed only}")
    run = check(proj_dir)
    assert run.status == "VERIFIED" and [q["ok"] for q in run.report["probes"]] == [True] * 3


def test_shape_check_reports_its_distance_where_no_point_needs_a_faces_bound(tmp_path):
    # A flat-faced gusset against the same gusset with a 0.2 mm pocket: every point of the flat
    # side is settled by the sample bound, and the pocket's depth is still the distance found.
    paper = "The gusset is a right triangle with legs of 30 mm and 20 mm, 6 mm thick.\n"
    quote = "legs of 30 mm and 20 mm, 6 mm thick"
    files = {
        "evidence.yaml": f"evidence:\n  - {{id: S1, source: paper, locator: Sec. 1, "
        f'quote: "{quote}", values: {{a: 30, b: 20, t: 6}}}}\n'
        "datums: {body.o: [0, 0, 0], body.x: [30, 0, 0], body.y: [0, 20, 0]}\n",
        "params.yaml": "params:\n"
        + "".join(f"  {k}: {{basis: source, from: S1.{k}}}\n" for k in "abt"),
        "checks.yaml": "checks:\n"
        "  - {id: env, kind: bbox, part: plate, evidence: S1, axes: {a: x, b: y, t: z}}\n"
        "  - {id: shape, kind: shape, part: plate, body: body, tol: 0.25,\n"
        "     pairs: [[plate.o, body.o], [plate.x, body.x], [plate.y, body.y]]}\n",
        "model.py": "from build123d import *\n\n\ndef build(p):\n"
        "    plate = extrude(Polygon((0, 0), (p.a, 0), (0, p.b), align=None), p.t)\n"
        '    datums = {"plate.o": (0, 0, 0), "plate.x": (p.a, 0, 0), "plate.y": (0, p.b, 0)}\n'
        '    return {"parts": {"plate": plate}, "datums": datums,\n'
        '            "assembly": {"plate_1": ("plate", Location())}}\n',
    }
    root = project(tmp_path, paper, files, "A demo gusset, as")
    plate = extrude(Polygon((0, 0), (30, 0), (0, 20), align=None), 6)
    export_step(plate - Pos(8, 6, 6) * Sphere(0.2), str(tmp_path / "body.step"))
    register(root, tmp_path / "body.step", "body", "geometry")
    run = check(root)
    assert run.status == "VERIFIED"
    assert run.result("shape")["shape"]["distance"] == pytest.approx(0.2, abs=1e-6)


STROKED = SHEET.replace('fill="black"', 'fill="none" stroke="black"')


@pytest.mark.parametrize("svg", [SHEET, STROKED], ids=["filled", "stroked"])
def test_shape_check_compares_a_built_plate_with_its_region_of_a_cut_file(proj_dir, tmp_path, svg):
    # The sheet is drawn at half size inside a moved group; its link lies at x 20..60, y 40..45.
    sheet(proj_dir, tmp_path, svg=svg)
    run = check(proj_dir)
    shape = run.result("shape")["shape"]
    assert run.status == "VERIFIED" and shape["distance"] < 1e-4 and shape["residual"] < 1e-9
    assert len(shape["worst_point"]) == 2  # [x, y] on the sheet


def test_shape_check_against_a_region_fails_at_the_hole_the_part_lacks(proj_dir, tmp_path):
    sheet(proj_dir, tmp_path)
    remodel(proj_dir, "    link -= Pos(p.pitch / 2, 0, 0) * Cylinder(p.hole_d / 2, p.link_H)\n", "")
    run = check(proj_dir)
    shape = run.result("shape")["shape"]
    assert not run.result("shape")["ok"] and 1 <= shape["distance"] <= 2.5
    # The sheet's hole at (55, 42.5), 1.5 mm in radius, has no edge of the part near it.
    assert math.dist(shape["worst_point"], (55, 42.5)) == pytest.approx(1.5, abs=1e-3)


def test_coverage_names_each_region_by_a_point_a_skip_can_copy(proj_dir, tmp_path):
    sheet(proj_dir, tmp_path, check=False)
    messages = check(proj_dir).messages("coverage")
    named = re.findall(r"^sheet body (sheet@[\d.]+,[\d.]+): ", "\n".join(messages), re.M)
    (x, y), plate = (tuple(map(float, n.split("@")[1].split(","))) for n in named)
    assert 20 < x < 60 and 40 < y < 45 and 120 < plate[0] < 140 and 40 < plate[1] < 60
    skips = [{"source": "sheet", "body": n, "reason": "another device"} for n in named]
    add(proj_dir, skipped=skips)
    assert check(proj_dir).status == "VERIFIED"
