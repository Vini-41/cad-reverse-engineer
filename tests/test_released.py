"""Geometry the authors released: a STEP's or STL's bodies and a cut file's regions, each compared
whole with the part built in its frame by a shape check, and the params that cite them."""

import importlib
import math
import re

import pytest
from build123d import (
    Axis,
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
    fillet,
)
from conftest import (
    LINK_AT,
    SHEET,
    add,
    change,
    check,
    link_body,
    meta,
    project,
    register,
    released,
    remodel,
    sheet,
    write,
)

# The released link a quarter turn about Z and off the origin: not where model.py builds it.
ELSEWHERE = Location((100, 50, 20), (0, 0, 1), 90)


@pytest.mark.parametrize("name", ["link.step", "link.stl"])
def test_shape_check_compares_a_part_with_its_released_body_in_place(proj_dir, tmp_path, name):
    # An STL's holes are facets, held only where both shapes are exact, so the same link passes
    # at tolerance.length.
    released(proj_dir, tmp_path, name=name)
    run = check(proj_dir)
    result = run.result("shape")
    # An STL's result also says which of its tests found the largest deviation.
    keys = {"distance", "worst_point"} | ({"found", "facets"} if name.endswith(".stl") else set())
    assert run.status == "VERIFIED" and set(result["shape"]) == keys
    assert result["shape"]["distance"] < 1e-3 and result["rests_on"] == "source"


@pytest.mark.parametrize("name", ["link.step", "link.stl"])
def test_shape_check_fails_where_the_part_is_not_built_in_its_bodys_frame(proj_dir, tmp_path, name):
    released(proj_dir, tmp_path, at=ELSEWHERE, name=name)
    run = check(proj_dir)
    assert run.errors == ["check-failed"] and run.result("shape")["shape"]["distance"] > 10


def test_shape_check_fails_at_the_feature_the_built_part_lacks(proj_dir, tmp_path):
    # The released link has a 2 mm hole at its middle, 2.5 mm from the built link's nearest face.
    released(proj_dir, tmp_path, solid=link_body(extra_hole=True))
    run = check(proj_dir)
    shape = run.result("shape")["shape"]
    assert run.errors == ["check-failed"] and not run.result("shape")["ok"]
    assert shape["distance"] == pytest.approx(2.5, abs=1e-6)
    assert math.hypot(*shape["worst_point"][:2]) == pytest.approx(1, abs=1e-6)
    assert run.result("shape")["measured"].endswith(") on body link_step")


def test_shape_check_names_the_part_where_its_worst_point_lies_on_the_part(proj_dir, tmp_path):
    # The built link with a hole at its middle that the released link lacks.
    remodel(
        proj_dir, "    datums = {", "    link -= Cylinder(p.hole_d / 2, p.link_H)\n    datums = {"
    )
    released(proj_dir, tmp_path)
    measured = check(proj_dir).result("shape")["measured"]
    assert measured.endswith(") on part link")


# The STL tests, each held at points both shapes hold exactly.


def test_stl_corner_off_the_part_fails_its_shape_check(proj_dir, tmp_path):
    # The released holes are 32 mm apart and the built ones 30: their rims' corners lie off the
    # built link.
    released(proj_dir, tmp_path, solid=link_body(pitch=32), name="link.stl")
    run = check(proj_dir)
    result = run.result("shape")
    assert run.errors == ["check-failed"] and result["shape"]["distance"] > 0.5
    assert result["shape"]["found"] == "mesh corner"


def test_part_corner_on_no_stl_corner_fails_its_shape_check(proj_dir, tmp_path):
    # The built link has a 3 mm hole at x 7.5 that the mesh lacks. Every mesh corner lies on the
    # built link, and every facet's corners on one of its faces, but the hole's rims pass through
    # no mesh corner.
    hole = "    link -= Pos(p.pitch / 2 / 2, 0, 0) * Cylinder(p.hole_d / 2, p.link_H)\n"
    remodel(proj_dir, "    datums = {", f"{hole}    datums = {{")
    released(proj_dir, tmp_path, name="link.stl")
    run = check(proj_dir)
    result = run.result("shape")
    assert run.errors == ["check-failed"] and result["shape"]["found"] == "closed edge"
    # On the hole's rim, 1.5 from its axis.
    assert math.dist(result["shape"]["worst_point"][:2], (7.5, 0)) == pytest.approx(1.5, abs=1e-6)


def test_part_rim_of_two_arcs_on_no_stl_corner_fails_its_shape_check(proj_dir, tmp_path):
    # As above, but the hole is cut as two half circles, so each rim is two arcs that join
    # tangentially: no corner, and still one closed edge the mesh must hold.
    arcs = "(p.pitch / 2 / 2, 0), p.hole_d / 2"
    rim = f"Wire([CenterArc({arcs}, 0, 180), CenterArc({arcs}, 180, 180)])"
    hole = f"    link -= extrude(make_face({rim}), p.link_H / 2, both=True)\n"
    remodel(proj_dir, "    datums = {", f"{hole}    datums = {{")
    released(proj_dir, tmp_path, name="link.stl")
    run = check(proj_dir)
    assert run.errors == ["check-failed"] and run.result("shape")["shape"]["found"] == "closed edge"


def test_stl_facet_on_no_one_smooth_patch_fails_its_shape_check(proj_dir, tmp_path):
    # A hole the built link leaves out: the mesh's 2 mm hole at its middle has wall facets with
    # corners on its top and bottom faces, each of which the built link holds, but on no one face.
    released(proj_dir, tmp_path, solid=link_body(extra_hole=True), name="link.stl")
    run = check(proj_dir)
    result = run.result("shape")
    assert run.errors == ["check-failed"] and result["shape"]["found"] == "facet"
    assert result["shape"]["facets"] > 0
    assert math.hypot(*result["shape"]["worst_point"][:2]) <= 1


def test_stl_of_seams_smooth_edges_and_tangent_joins_passes_its_shape_check(proj_dir, tmp_path):
    # Rounded ends: each fillet meets the long sides along smooth edges, the top face's straight
    # edges join its arcs tangentially, and each hole closes on a seam. None is a point a mesh
    # must hold, so the same link released as a mesh passes.
    remodel(
        proj_dir,
        "    link = Box(p.link_L, p.link_W, p.link_H)\n",
        "    link = fillet(Box(p.link_L, p.link_W, p.link_H).edges().filter_by(Axis.Z), 2)\n",
    )
    rounded = fillet(Box(40, 5, 8).edges().filter_by(Axis.Z), 2)
    for x in (-15, 15):
        rounded -= Pos(x, 0, 0) * Cylinder(1.5, 8)
    released(proj_dir, tmp_path, solid=rounded, name="link.stl")
    run = check(proj_dir)
    assert run.result("shape")["ok"], run.result("shape")["measured"]


# Several bodies, and the project's units.


@pytest.mark.parametrize("name", ["both.step", "both.stl"])
def test_file_of_several_solids_names_each_body_by_its_place_in_it(proj_dir, tmp_path, name):
    # A 4 mm cube, then the link: link_step#1 and link_step#2.
    both = Compound(children=[Pos(0, 40, 0) * Box(4, 4, 4), link_body()])
    released(proj_dir, tmp_path, solid=both, name=name, body="link_step#2")
    run = check(proj_dir)
    assert run.result("shape")["ok"]
    # Each body is compared by a shape check or set aside by a skip.
    assert [m.split(":")[0] for m in run.messages("coverage")] == ["link_step body link_step#1"]
    add(proj_dir, skipped={"source": "link_step", "body": "link_step#1", "reason": "a spacer"})
    assert check(proj_dir).status == "VERIFIED"


@pytest.mark.parametrize("name", ["link.stl", "link.step"])
def test_released_geometry_is_read_in_millimetres_into_the_projects_length_unit(
    proj_dir, tmp_path, name
):
    # Table 1 prints no unit, so in a project in cm the link is 40×8×5 cm, and its holes, 30 mm
    # apart, are 3 cm apart: as the file's link is, 400 mm long with holes 30 mm apart in it.
    meta(proj_dir, units={"length": "cm"})
    change(proj_dir, "params", "hole_d", value=0.3)
    link = Box(400, 50, 80) - [Pos(x, 0, 0) * Cylinder(1.5, 80) for x in (-15, 15)]
    released(proj_dir, tmp_path, solid=link, name=name)
    run = check(proj_dir)
    assert run.status == "VERIFIED", run.out
    assert run.result("shape")["shape"]["distance"] < 1e-4


# A param a released body settles.


def cite(root, body: str = "link_step") -> None:
    """Take the link's hole diameter from the released body, which leaves its gap unasked."""
    bore = {"basis": "source", "from": body, "value": 3, "rationale": None, "gap": None}
    change(root, "params", "hole_d", **bore)
    write(root, "gaps.yaml", "gaps: []\n")


def test_param_citing_a_body_rests_on_source_and_is_checked_by_its_shape_check(proj_dir, tmp_path):
    released(proj_dir, tmp_path)
    cite(proj_dir)
    run = check(proj_dir)
    assert run.status == "VERIFIED" and run.rules == [], run.out
    assert run.report["params"]["hole_d"]["rests_on"] == "source" and run.report["exact"]


def test_param_citing_a_body_whose_shape_check_fails_is_unchecked(proj_dir, tmp_path):
    released(proj_dir, tmp_path, solid=link_body(extra_hole=True))
    cite(proj_dir)
    assert check(proj_dir).rules == ["check-failed", "unchecked-source"]


# Surfaces as sampled.


def test_shape_check_reports_its_distance_where_no_point_needs_a_faces_bound(tmp_path):
    # A flat-faced gusset against the same gusset with a 0.2 mm pocket: every point of the flat
    # side is settled by the sample bound, and the pocket's depth is still the distance found.
    paper = "The gusset is a right triangle with legs of 30 mm and 20 mm, 6 mm thick.\n"
    quote = "legs of 30 mm and 20 mm, 6 mm thick"
    files = {
        "evidence.yaml": f"evidence:\n  - {{id: S1, source: paper, locator: Sec. 1, "
        f'quote: "{quote}", values: {{a: 30, b: 20, t: 6}}}}\n',
        "params.yaml": "params:\n"
        + "".join(f"  {k}: {{basis: source, from: S1.{k}}}\n" for k in "abt"),
        "checks.yaml": "checks:\n"
        "  - {id: env, kind: bbox, part: plate, evidence: S1, axes: {a: x, b: y, t: z}}\n"
        "  - {id: shape, kind: shape, part: plate, body: body}\n",
        "model.py": "from build123d import *\n\n\ndef build(p):\n"
        "    plate = extrude(Polygon((0, 0), (p.a, 0), (0, p.b), align=None), p.t)\n"
        '    return {"parts": {"plate": plate},\n'
        '            "assembly": {"plate_1": ("plate", Location())}}\n',
    }
    root = project(tmp_path, paper, files, "A demo gusset, as")
    plate = extrude(Polygon((0, 0), (30, 0), (0, 20), align=None), 6)
    export_step(plate - Pos(8, 6, 6) * Sphere(0.2), str(tmp_path / "body.step"))
    register(root, tmp_path / "body.step", "body", "geometry")
    run = check(root)
    assert run.errors == ["check-failed"]
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
        f'quote: "{quote}", values: {{d: 20, h: 8, hole: 3}}}}\n',
        "params.yaml": "params:\n"
        + "".join(f"  {k}: {{basis: source, from: S1.{k}}}\n" for k in ("d", "h", "hole")),
        "checks.yaml": "checks:\n"
        "  - {id: env, kind: bbox, part: drum, evidence: S1, axes: {d: x, h: z}}\n"
        "  - {id: hole, kind: diameter, at: drum.wall, evidence: S1, key: hole}\n"
        "  - {id: shape, kind: shape, part: drum, body: body}\n",
        "model.py": "from build123d import *\n\n\ndef build(p):\n"
        "    drum = Cylinder(p.d / 2, p.h) - Rot(0, 90, 0) * Cylinder(p.hole / 2, 2 * p.d)\n"
        '    datums = {"drum.wall": (0, 0, -p.hole / 2)}\n'
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


# Cut files.

STROKED = SHEET.replace('fill="black"', 'fill="none" stroke="black"')


@pytest.mark.parametrize("svg", [SHEET, STROKED], ids=["filled", "stroked"])
def test_shape_check_compares_a_built_plate_with_its_region_where_the_sheet_places_it(
    proj_dir, tmp_path, svg
):
    # The sheet is drawn at half size inside a moved group; its link lies at x 20..60, y 40..45.
    sheet(proj_dir, tmp_path, svg=svg)
    run = check(proj_dir)
    shape = run.result("shape")["shape"]
    assert run.status == "VERIFIED" and shape["distance"] < 1e-4
    assert len(shape["worst_point"]) == 2  # [x, y] on the sheet


def test_shape_check_against_a_region_fails_at_the_hole_the_part_lacks(proj_dir, tmp_path):
    sheet(proj_dir, tmp_path)
    remodel(proj_dir, "    link -= Pos(p.pitch / 2, 0, 0) * Cylinder(p.hole_d / 2, p.link_H)\n", "")
    run = check(proj_dir)
    shape = run.result("shape")["shape"]
    assert not run.result("shape")["ok"] and 1 <= shape["distance"] <= 2.5
    # The sheet's hole at (55, 42.5), 1.5 mm in radius, has no edge of the part near it.
    assert math.dist(shape["worst_point"], (55, 42.5)) == pytest.approx(1.5, abs=1e-3)


def test_shape_check_against_a_region_fails_where_the_sheet_places_the_part_off_it(
    proj_dir, tmp_path
):
    sheet(proj_dir, tmp_path, places={LINK_AT: (41, 42.5, False)})
    run = check(proj_dir)
    assert run.errors == ["check-failed"]
    assert run.result("shape")["shape"]["distance"] == pytest.approx(1, abs=1e-4)


# The link cut twice: the second region 40 mm below the first, where the sheet places the link
# turned over.
TWICE = SHEET.replace(
    '<path fill="black" d="M 50 0',
    '<path fill="black" fill-rule="evenodd" d="M 0 20 H 20 V 22.5 H 0 Z'
    " M 1.75 21.25 a 0.75 0.75 0 1 0 1.5 0 a 0.75 0.75 0 1 0 -1.5 0 Z"
    ' M 16.75 21.25 a 0.75 0.75 0 1 0 1.5 0 a 0.75 0.75 0 1 0 -1.5 0 Z"/>\n'
    '    <path fill="black" d="M 50 0',
)


def test_part_cut_from_two_regions_is_placed_on_the_sheet_once_for_each(proj_dir, tmp_path):
    places = {LINK_AT: (40, 42.5, False), "sheet@30,81": (40, 82.5, True)}
    sheet(proj_dir, tmp_path, svg=TWICE, places=places)
    add(
        proj_dir,
        checks={
            "id": "again",
            "kind": "shape",
            "part": "link",
            "body": "sheet@30,81",
            "along": "z",
        },
    )
    run = check(proj_dir)
    assert run.status == "VERIFIED", run.out
    assert run.result("again")["shape"]["distance"] < 1e-4


def test_coverage_names_each_region_by_a_point_a_skip_can_copy(proj_dir, tmp_path):
    sheet(proj_dir, tmp_path, check=False)
    messages = check(proj_dir).messages("coverage")
    named = re.findall(r"^sheet body (sheet@[\d.]+,[\d.]+): ", "\n".join(messages), re.M)
    (x, y), plate = (tuple(map(float, n.split("@")[1].split(","))) for n in named)
    assert 20 < x < 60 and 40 < y < 45 and 120 < plate[0] < 140 and 40 < plate[1] < 60
    skips = [{"source": "sheet", "body": n, "reason": "another device"} for n in named]
    add(proj_dir, skipped=skips)
    assert check(proj_dir).status == "VERIFIED"


def test_param_citing_a_region_rests_on_source(proj_dir, tmp_path):
    sheet(proj_dir, tmp_path)
    cite(proj_dir, LINK_AT)
    run = check(proj_dir)
    assert run.status == "VERIFIED" and run.rules == [], run.out
    assert run.report["params"]["hole_d"]["rests_on"] == "source"
