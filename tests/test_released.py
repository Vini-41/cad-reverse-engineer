"""Geometry the authors released: a STEP's or STL's bodies, probes of them and shape checks
against them, and a cut file's regions."""

import importlib
import math
import re

import pytest
from build123d import (
    Box,
    Compound,
    Cylinder,
    GeomType,
    Location,
    Polygon,
    Pos,
    Rot,
    Sphere,
    export_step,
    extrude,
)
from conftest import (
    FACE_DATUMS,
    PROBE,
    REPO,
    SHEET,
    SHEET_PROBE,
    add,
    add_quote,
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
    # A probe of a length is compared as one, as a quote printed in mm is.
    span = "kind: distance, between: [link.a, link.b], evidence: P-pitch, key: v"
    add(proj_dir, checks=f"{{id: span, {span}}}")
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


@pytest.mark.parametrize(
    ("ref", "quantity"),
    [("P-pitch.v", "length"), ("P-square.v", "angle")],
    ids=["distance", "angle"],
)
def test_count_citing_a_probe_of_a_length_or_an_angle_is_a_unit_quantity(
    proj_dir, tmp_path, ref, quantity
):
    probed(proj_dir, tmp_path)
    add(proj_dir, datums="link_step.wall: [100, 36.5, 20]", evidence=PROBES)
    entry, key = ref.split(".")
    add(proj_dir, checks=f"{{id: n, kind: count, part: link, evidence: {entry}, key: {key}}}")
    (message,) = check(proj_dir).messages("unit-quantity")
    assert ref in message and quantity in message


def test_mass_check_counting_by_a_param_from_a_distance_probe_is_a_unit_quantity(
    proj_dir, tmp_path
):
    probed(proj_dir, tmp_path)
    add(proj_dir, evidence=PROBES.split("- {id: P-rise")[0])
    resin = "The link weighs 1.8 g in resin of 1.2 g/cm3."
    add_quote(proj_dir, tmp_path, resin, values={"m": 1.8, "rho": 1.2})
    add(proj_dir, params={"rho": {"basis": "source", "from": "N1.rho"}})
    add(proj_dir, params={"n": {"basis": "source", "from": "P-pitch.v"}})
    weighed = "kind: mass, evidence: N1, key: m, density: rho, tol_rel: 0.1, counts: {link: n}"
    add(proj_dir, checks=f"{{id: m, {weighed}}}")
    (message,) = check(proj_dir).messages("unit-quantity")
    assert "P-pitch.v" in message and "length" in message


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


# Three corners of the 5 mm bore of COMPAct's sun at z 0, as its STL stores them: the bore has 13
# sides, so no two corners lie opposite each other and the longest chord is 4.9635 (#136).
SUN_RIM = {
    "sun.r1": [14.07264518737793, 15.901710510253906, 0],
    "sun.r2": [15.613487243652344, 14.162459373474121, 0],
    "sun.r3": [17.920162200927734, 14.442540168762207, 0],
}


def test_diameter_probe_at_a_circle_datum_reads_an_odd_sided_bore_on_an_stl(proj_dir):
    register(proj_dir, REPO / "examples/compact-sspg/sources/sspg_sun.STL", "sun", "geometry")
    add(proj_dir, datums=SUN_RIM | {"sun.bore": {"circle": list(SUN_RIM)}})
    bore = {"id": "P-sun", "source": "sun", "locator": "sun bore", "probe": "diameter"}
    add(proj_dir, evidence=bore | {"at": "sun.bore", "values": {"d": 5}, "scope": "context"})
    change(proj_dir, "evidence", "P-sun", reason="the sun is another part")
    add(proj_dir, skipped={"source": "sun", "body": "sun", "reason": "another part"})
    run = check(proj_dir)
    assert run.status == "VERIFIED", run.out
    (probe,) = run.report["probes"]
    assert probe["value"] == pytest.approx(5, abs=1e-5) and probe["probe"] == "diameter"


def _corners(x: float, y: float, r: float, sides: int, turn: float = 360) -> list:
    """sides + 1 corners on the arc of radius r about (x, y) from 0 to turn degrees; all sides
    of them for a whole turn."""
    steps = [math.radians(turn * k / sides) for k in range(sides + (turn < 360))]
    return [(x + r * math.cos(t), y + r * math.sin(t)) for t in steps]


# A 40×10×4 plate with two 3 mm holes 30 apart, each of 9 facets, which no axis passes through.
PLATE = Box(40, 10, 4) - [
    Pos(0, 0, -2) * extrude(Polygon(*_corners(x, 0, 1.5, 9), align=None), 4) for x in (-15, 15)
]
# Three corners of each hole on the plate's top face, and the circles through them.
HOLES = {
    f"{hole}{i}": (*_corners(x, 0, 1.5, 9)[k], 2)
    for hole, x in (("a", -15), ("b", 15))
    for i, k in enumerate((0, 3, 6), 1)
}
CIRCLES = {f"link_step.{h}": {"circle": [f"link_step.{h}{i}" for i in (1, 2, 3)]} for h in "ab"}


def _faceted(root, tmp_path, solid=PLATE, datums=HOLES, derived=CIRCLES, name="plate.stl"):
    """Register solid as geometry source link_step where it lies, declare datums and derived on
    it, and skip its body."""
    released(root, tmp_path, solid=solid, at=Location(), name=name, datums=datums, check=False)
    add(root, datums=derived, skipped="{source: link_step, body: link_step, reason: probed}")


def _probe(kind: str, value: float, **fields) -> dict:
    entry = {"id": "P-c", "source": "link_step", "locator": "holes", "probe": kind}
    return entry | fields | {"values": {"v": value}, "scope": "context", "reason": "probed"}


def test_diameter_probe_at_a_circle_datum_reads_a_faceted_fillets_radius(proj_dir, tmp_path):
    # A 10 mm square plate whose corner is rounded to radius 3 in six facets.
    arc = _corners(7, 7, 3, 6, turn=90)
    rounded = extrude(Polygon((0, 0), (10, 0), *arc, (0, 10), align=None), 2)
    corners = {f"f{i}": (*arc[k], 2) for i, k in enumerate((0, 3, 6), 1)}
    fillet = {"link_step.fillet": {"circle": [f"link_step.f{i}" for i in (1, 2, 3)]}}
    _faceted(proj_dir, tmp_path, solid=rounded, datums=corners, derived=fillet)
    add(proj_dir, evidence=_probe("diameter", 6, at="link_step.fillet"))
    run = check(proj_dir)
    assert run.status == "VERIFIED" and run.report["probes"][0]["value"] == pytest.approx(6)


def test_distance_between_circle_datums_reads_the_spacing_of_faceted_holes(proj_dir, tmp_path):
    _faceted(proj_dir, tmp_path)
    add(proj_dir, evidence=_probe("distance", 30, between=["link_step.a", "link_step.b"]))
    run = check(proj_dir)
    assert run.status == "VERIFIED" and "datum-off-solid" not in run.rules
    assert run.report["probes"][0]["value"] == pytest.approx(30, abs=1e-6)


def test_distance_from_a_mid_datum_reads_from_the_midpoint_of_its_two(proj_dir, tmp_path):
    # The midpoint of the plate's two top corners at x -20 is 5 from hole a's centre.
    ends = {"e1": (-20, -5, 2), "e2": (-20, 5, 2)}
    end = {"link_step.end": {"mid": ["link_step.e1", "link_step.e2"]}}
    _faceted(proj_dir, tmp_path, datums=HOLES | ends, derived=CIRCLES | end)
    add(proj_dir, evidence=_probe("distance", 5, between=["link_step.end", "link_step.a"]))
    run = check(proj_dir)
    assert run.status == "VERIFIED" and run.report["probes"][0]["value"] == pytest.approx(5)



def test_angle_along_an_axis_reads_at_a_circle_datums_centre(proj_dir, tmp_path):
    # At hole a's centre, hole b's centre lies on +x and a bottom corner of the plate's end 4 below
    # the top: 135° about z, 128.0° in 3-D.
    _faceted(proj_dir, tmp_path, datums=HOLES | {"e": (-20, 5, -2)})
    at = {"between": ["link_step.b", "link_step.a", "link_step.e"]}
    add(proj_dir, evidence=_probe("angle", 135, along="z", **at))
    run = check(proj_dir)
    assert run.status == "VERIFIED", run.out
    assert run.report["probes"][0]["value"] == pytest.approx(135, abs=1e-6)

@pytest.mark.parametrize(
    ("length_tol", "off", "found"),
    [(0.001, 0.4, True), (0.01, 0.005, False), (0.01, 0.02, True)],
)
def test_datum_a_derived_one_names_on_an_stl_lies_on_a_triangle_corner(
    proj_dir, tmp_path, length_tol, off, found
):
    # Moved off its corner radially, a1 lies on the plate's top face.
    meta(proj_dir, tolerance={"length": length_tol, "angle": 0.01})
    _faceted(proj_dir, tmp_path, datums=HOLES | {"a1": (-13.5 + off, 0, 2)})
    messages = check(proj_dir).messages("datum-off-solid")
    assert [m.split(":")[0] for m in messages] == (["datum link_step.a1 of body link_step"] * found)


def test_datum_a_derived_one_names_on_a_step_needs_no_corner(proj_dir, tmp_path):
    # Three points on hole a's wall, half way up it, far from any vertex of the solid.
    wall = {f"w{i}": (*_corners(-15, 0, 1.5, 3)[i - 1], 0) for i in (1, 2, 3)}
    hole = {"link_step.hole": {"circle": ["link_step.w1", "link_step.w2", "link_step.w3"]}}
    _faceted(proj_dir, tmp_path, solid=link_body(), datums=wall, derived=hole, name="link.step")
    add(proj_dir, evidence=_probe("diameter", 3, at="link_step.hole"))
    run = check(proj_dir)
    assert run.status == "VERIFIED" and run.report["probes"][0]["value"] == pytest.approx(3)


@pytest.mark.parametrize(
    "through",
    [["p1", "p1b", "q"], ["p1", "p2", "p3"], ["p1", "q", "z"], ["p1", "q", "c"]],
    ids=["coincident", "collinear", "unknown", "derived"],
)
def test_derived_datum_whose_datums_give_no_circle_is_a_finding_naming_it(
    proj_dir, tmp_path, through
):
    # p1, p2 and p3 lie along the released link's top face, p1b within tolerance of p1, q on its
    # side; c is a circle.
    faces = {"p1": (-10, 0, 4), "p1b": (-10, 0.0005, 4), "p2": (0, 0, 4), "p3": (10, 0, 4)}
    faces |= {"q": (0, 2.5, 0)}
    derived = {
        f"link_step.{name}": {"circle": [f"link_step.{i}" for i in names]}
        for name, names in (("c", ["p1", "p2", "q"]), ("bad", through))
    }
    _faceted(proj_dir, tmp_path, link_body(), faces, derived, name="link.step")
    (message,) = check(proj_dir).messages("datum-off-solid")
    assert message.startswith("datum link_step.bad: ")


def test_angle_probe_along_an_axis_reads_the_angle_about_it(proj_dir, tmp_path):
    # #143's disc: a Ø28 flange with a Ø5 bore, a Ø4 hole on +x and a lug turned 4.454° about
    # the axis. The hole's datum lies on its axis 3 mm above the bore's, so the 3-D angle is not
    # the lug's phase about the axis.
    disc = Cylinder(14, 4) - Cylinder(2.5, 4) - Pos(11.5, 0, 0) * Cylinder(2, 4)
    disc += Rot(0, 0, 4.454) * Pos(14.5, 0, 0) * Box(1.5, 2, 4)
    export_step(disc, str(tmp_path / "disc.step"))
    register(proj_dir, tmp_path / "disc.step", "disc", "geometry")
    datums = {
        "disc.hole": [11.5, 0, 1.5],
        "disc.axis": [0, 0, -1.5],
        "disc.lug": [15.20395, 1.1843, 0],
    }
    add(proj_dir, datums=datums, skipped="{source: disc, body: disc, reason: probed only}")
    phase = {"source": "disc", "locator": "lug", "probe": "angle", "scope": "context"}
    phase |= {"between": ["disc.hole", "disc.axis", "disc.lug"], "reason": "the lug's phase"}
    add(
        proj_dir,
        evidence=[
            phase | {"id": "P-about", "values": {"v": 4.454}, "along": "z"},
            phase | {"id": "P-3d", "values": {"v": 10.012}},
        ],
    )
    run = check(proj_dir)
    assert run.status == "VERIFIED", run.out
    assert [q["value"] for q in run.report["probes"]] == pytest.approx([4.45402, 10.01207])


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


def test_shape_check_reads_a_released_edge_on_its_faces_not_its_curve(tmp_path):
    # A drum with a hole drilled across it, as built and as released. The file gives one rim's
    # curve, where the hole meets the drum's wall, only 0.003 mm off the hole's wall, within the
    # tolerance it sets for that edge, as another CAD's intersection curve can be. The rim is
    # where the two faces meet, so the same drum reads within tolerance.length.
    paper = "The drum is 20 mm across and 8 mm tall, with a 3 mm hole drilled across it.\n"
    quote = "20 mm across and 8 mm tall, with a 3 mm hole"
    files = {
        "evidence.yaml": f"evidence:\n  - {{id: S1, source: paper, locator: Sec. 1, "
        f'quote: "{quote}", values: {{d: 20, h: 8, hole: 3}}}}\n'
        "datums: {body.top: [0, 0, 4], body.x: [10, 0, 4], body.y: [0, 10, 4]}\n",
        "params.yaml": "params:\n"
        + "".join(f"  {k}: {{basis: source, from: S1.{k}}}\n" for k in ("d", "h", "hole")),
        "checks.yaml": "checks:\n"
        "  - {id: env, kind: bbox, part: drum, evidence: S1, axes: {d: x, h: z}}\n"
        "  - {id: hole, kind: diameter, at: drum.wall, evidence: S1, key: hole}\n"
        "  - {id: shape, kind: shape, part: drum, body: body,\n"
        "     pairs: [[drum.top, body.top], [drum.x, body.x], [drum.y, body.y]]}\n",
        "model.py": "from build123d import *\n\n\ndef build(p):\n"
        "    drum = Cylinder(p.d / 2, p.h) - Rot(0, 90, 0) * Cylinder(p.hole / 2, 2 * p.d)\n"
        '    datums = {"drum.top": (0, 0, p.h / 2), "drum.x": (p.d / 2, 0, p.h / 2),\n'
        '              "drum.y": (0, p.d / 2, p.h / 2), "drum.wall": (0, 0, -p.hole / 2)}\n'
        '    return {"parts": {"drum": drum}, "datums": datums,\n'
        '            "assembly": {"drum_1": ("drum", Location())}}\n',
    }
    root = project(tmp_path, paper, files, "A demo drum, as")
    drum = Cylinder(10, 8) - Rot(0, 90, 0) * Cylinder(1.5, 40)
    rim = next(e for e in drum.edges() if e.geom_type == GeomType.BSPLINE)
    brep, gp = (importlib.import_module(f"OCP.{name}") for name in ("BRep", "gp"))
    curve = brep.BRep_Tool.Curve_s(rim.wrapped, 0.0, 0.0)
    brep.BRep_Builder().UpdateEdge(rim.wrapped, curve.Translated(gp.gp_Vec(0, 0, 0.003)), 0.003)
    export_step(drum, str(tmp_path / "body.step"))
    register(root, tmp_path / "body.step", "body", "geometry")
    run = check(root)
    assert run.status == "VERIFIED", run.out
    assert run.result("shape")["shape"]["distance"] < 1e-6


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


def _sheet_probe(eid: str, kind: str, values: dict, **fields) -> dict:
    """SHEET_PROBE as probe kind of values, with fields in place of its datums."""
    entry = {k: v for k, v in SHEET_PROBE.items() if k != "between"}
    return entry | {"id": eid, "probe": kind, "values": values} | fields


def test_probe_reads_a_region_of_a_cut_file_in_the_sheets_plane(proj_dir, tmp_path):
    # The sheet's link lies at x 20..60, y 40..45, its holes centred 30 apart along x at y 42.5,
    # and its side datum on its lower edge at (40, 45).
    sheet(proj_dir, tmp_path)
    between = {"between": ["sheet.bore_a", "sheet.side"]}
    probes = [
        _sheet_probe("P-env", "bbox", {"L": 40, "W": 5}, axes={"L": "x", "W": "y"}),
        _sheet_probe("P-pitch", "distance", {"v": 30}, between=["sheet.bore_a", "sheet.bore_b"]),
        _sheet_probe("P-side", "distance", {"v": 15.2069}, **between, tol=1e-4),
        _sheet_probe("P-drop", "distance", {"v": 2.5}, **between, along="y"),
        _sheet_probe("P-bore", "diameter", {"d": 3}, at="sheet.bore_a"),
    ]
    add(proj_dir, evidence=probes)
    run = check(proj_dir)
    assert run.status == "VERIFIED", run.out
    values = {f"{q['evidence']}.{q['key']}": q["value"] for q in run.report["probes"]}
    expected = {"P-env.L": 40, "P-env.W": 5, "P-side.v": 15.2069, "P-drop.v": 2.5}
    assert values == pytest.approx(expected | {"P-pitch.v": 30, "P-bore.d": 3}, abs=1e-4)
    # A circle datum on an arc of the file gives its centre and diameter to float precision.
    assert values["P-pitch.v"] == pytest.approx(30, abs=1e-6)
    assert values["P-bore.d"] == pytest.approx(3, abs=1e-6)


def test_angle_probe_reads_the_angle_at_the_middle_of_three_sheet_datums(proj_dir, tmp_path):
    # From hole b's centre at (55, 42.5), hole a's lies along -x and the link's lower edge at
    # (55, 45) along +y on the sheet.
    sheet(proj_dir, tmp_path)
    add(proj_dir, datums={"sheet.under": [55, 45]})
    corner = ["sheet.bore_a", "sheet.bore_b", "sheet.under"]
    add(proj_dir, evidence=_sheet_probe("P-square", "angle", {"v": 90}, between=corner))
    run = check(proj_dir)
    assert run.status == "VERIFIED", run.out
    assert run.report["probes"][0]["value"] == pytest.approx(90)


def test_distance_from_a_mid_datum_on_a_sheet_reads_from_the_midpoint_of_its_two(
    proj_dir, tmp_path
):
    # The middle of the link's edges at x 40 is (40, 42.5), 15 from hole a's centre.
    sheet(proj_dir, tmp_path)
    add(proj_dir, datums={"sheet.top": [40, 40], "sheet.mid": {"mid": ["sheet.top", "sheet.side"]}})
    between = ["sheet.bore_a", "sheet.mid"]
    add(proj_dir, evidence=_sheet_probe("P-mid", "distance", {"v": 15}, between=between))
    run = check(proj_dir)
    assert run.status == "VERIFIED", run.out
    assert run.report["probes"][0]["value"] == pytest.approx(15, abs=1e-6)


def test_probe_at_a_sheet_datum_off_its_regions_edge_is_a_datum_off_solid(proj_dir, tmp_path):
    # Hole a's centre lies inside the link's outer contour, 1.5 from the hole's edge; a shape
    # check's pair may still name it.
    sheet(proj_dir, tmp_path)
    add(proj_dir, evidence=SHEET_PROBE | {"between": ["sheet.a", "sheet.bore_b"]})
    run = check(proj_dir)
    (message,) = run.messages("datum-off-solid")
    assert "sheet.a " in message and "1.5" in message
    assert run.result("shape")["ok"]


def test_shape_check_pairs_a_built_part_with_circle_datums_at_a_sheets_holes(proj_dir, tmp_path):
    pairs = [["link.a", "sheet.bore_a"], ["link.b", "sheet.bore_b"], ["link.side", "sheet.side"]]
    sheet(proj_dir, tmp_path, pairs=pairs)
    run = check(proj_dir)
    assert run.status == "VERIFIED", run.out
    assert run.result("shape")["shape"]["residual"] < 1e-6


def test_param_taken_from_a_probe_of_a_cut_file_rests_on_source(proj_dir, tmp_path):
    sheet(proj_dir, tmp_path)
    probe = {k: v for k, v in SHEET_PROBE.items() if k not in ("scope", "reason")}
    add(proj_dir, evidence=probe)
    change(proj_dir, "params", "pitch", **{"from": "P-s.v"})
    run = check(proj_dir)
    assert run.status == "VERIFIED", run.out
    assert run.report["params"]["pitch"]["rests_on"] == "source"
    assert run.report["probes"][0]["value"] == pytest.approx(30)
