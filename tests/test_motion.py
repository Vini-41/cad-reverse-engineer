"""A model that moves: joints and loops posed through MuJoCo, gears, cables, ranges, sweeps,
physics values, the mass model and the MJCF export."""

import importlib
import math
import xml.etree.ElementTree as ET

import pytest
from conftest import (
    CORD,
    FOLD,
    INPUT_RANGE,
    KNEE,
    LOOP,
    SCREW,
    TURNED,
    WOUND,
    add,
    add_quote,
    change,
    check,
    edit,
    meta,
    number,
    open_chain,
    remodel,
    write,
)

RAIL = "instances: [rail_1, slider_1], between: [rail_1.a, slider_1.a], along: x"
STANDS = "instances: [rail_1, crank_1], between: [rail_1.top, rail_1.up, crank_1.down]"
# With the crank at θ above the rail the slider lies 2 L cos θ from the crank pivot.
REACH = "2 * S1.L * cos(radians(%s))"
BUILT, STOOD = 40 * math.sqrt(3), 40  # at rest, θ = 30°, and turned S2.turn on, θ = 60°


def mjcf(root) -> ET.Element:
    return ET.parse(root / "build" / "model.mjcf").getroot()


def floats(text: str | None) -> list[float]:
    return [float(v) for v in (text or "").split()]


def coupled(root) -> dict:
    """Each joint equality of the MJCF: its name -> (driven, driver, polycoef)."""
    found = [e for e in mjcf(root).iter("joint") if e.get("polycoef")]
    return {
        e.get("name"): (e.get("joint1"), e.get("joint2"), floats(e.get("polycoef"))) for e in found
    }


def test_slider_crank_is_posed_through_its_loop_and_exported_as_the_report_describes(mech_dir):
    mujoco = importlib.import_module("mujoco")

    run = check(mech_dir)
    assert run.status == "VERIFIED" and run.rules == []
    # A posed check is evaluated where the loop puts the links, and says where that is.
    assert run.result("stand")["pose"] == {"input": {"from": "S2.turn", "value": 30}}
    assert "pose" not in run.result("rest") and number(run.result("reach")) == STOOD
    assert "**Kinematic**: 3 joints and 1 loop" in run.md
    assert "| posed: input at 30 (S2.turn) |" in run.md
    motion = run.report["motion"]
    assert motion["joints"]["input"] == {
        "type": "revolute",
        "parent": "rail_1",
        "child": "crank_1",
        "drive": "actuated",
        "range": {"from": ["input_min", "input_max"], "value": [-20, 50]},
    }
    assert motion["loops"] == {"closure": ["coupler_1.down", "slider_1.up"]}
    assert (motion["dropped"], motion["gears"], motion["cables"]) == (False, {}, {})
    # The MJCF is that mechanism in the project's units, each body weighed by the mass model.
    m = mujoco.MjModel.from_xml_path(str(mech_dir / "build" / "model.mjcf"))
    hinge, slide = mujoco.mjtJoint.mjJNT_HINGE, mujoco.mjtJoint.mjJNT_SLIDE
    assert list(m.jnt_type) == [hinge, hinge, slide] and (m.neq, m.nu) == (1, 1)
    assert list(m.jnt_range[0]) == pytest.approx([math.radians(-20), math.radians(50)])
    assert list(m.opt.gravity) == [0, 0, 0]
    masses = run.report["masses"]
    assert {part: mass["from"] for part, mass in masses.items()} == {
        "rail": {"density": "rho"},
        "crank": {"density": "rho"},
        "coupler": {"density": "rho"},
        "slider": {"mass": "slider_m"},
    }
    # A bar is its box less two holes, at 1.2 g/cm3; the slider weighs what its datasheet says.
    bar = (45 * 5 * 4 - 2 * math.pi * 4) * 0.0012
    assert (masses["crank"]["mass"], masses["slider"]["mass"]) == (pytest.approx(bar), 2)
    assert masses["crank"]["center"] == pytest.approx([20, 0, 0], abs=1e-9)
    for body in mjcf(mech_dir).iter("body"):
        part = masses[body.get("name", "").removesuffix("_1")]
        inertial = body.find("inertial")
        assert inertial is not None and floats(inertial.get("mass")) == [part["mass"]]
        assert floats(inertial.get("fullinertia")) == part["inertia"]
    meshes = sorted(f.name for f in (mech_dir / "build" / "meshes").iterdir())
    assert meshes == ["coupler.stl", "crank.stl", "rail.stl", "slider.stl"]


def test_check_compares_a_pose_or_the_change_between_two_with_what_the_ledger_works_out(mech_dir):
    add(
        mech_dir,
        params="back: {basis: derived, expr: input_min / 2}",
        checks=f"""\
- {{id: back, kind: distance, {RAIL}, pose: {{input: back}},
   expect: "{REACH % "S1.rest + S3.low / 2"}"}}
- {{id: travel, kind: distance, {RAIL}, from: {{}}, {TURNED},
   expect: "{REACH % "S2.stand"} - {REACH % "S1.rest"}"}}
- {{id: swung, kind: angle, {STANDS}, from: {{input: S2.turn}}, pose: {{input: back}},
   expect: "S1.rest + S3.low / 2 - S2.stand"}}
- {{id: not-swung, kind: angle, {STANDS}, from: {{input: S2.turn}}, pose: {{input: back}},
   expect: "S2.stand - S1.rest - S3.low / 2"}}
""",
    )
    run = check(mech_dir)
    assert run.errors == ["check-failed"] and not run.result("not-swung")["ok"]
    back, travel, swung = (run.result(cid) for cid in ("back", "travel", "swung"))
    assert back["ok"] and number(back) == pytest.approx(80 * math.cos(math.radians(20)), abs=5e-3)
    assert back["pose"] == {"input": {"from": "back", "value": -10}}
    assert (back["rests_on"], back["rests_on_params"]) == ("source", ["back"])
    # With `from`, a check compares how far its value changes between two poses.
    assert travel["ok"] and number(travel) == pytest.approx(STOOD - BUILT, abs=5e-3)
    assert (travel["from_pose"], travel["pose"]["input"]["value"]) == ({}, 30)
    assert travel["expect"]["value"] == pytest.approx(STOOD - BUILT)
    assert swung["ok"] and number(swung) == pytest.approx(-40)  # from 60° above the rail to 20°
    assert swung["from_pose"] == {"input": {"from": "S2.turn", "value": 30}}
    assert "from: input at 30 (S2.turn); posed: input at -10 (back)" in run.md
    assert "from input at 30 (S2.turn) to input at -10 (back)" in run.messages("check-failed")[0]


UNREACHED = [
    ("loop-open", f"kind: distance, {RAIL}, key: reach, pose: {{slide: S1.L}}", "slide at 40"),
    ("joint-range", f"kind: angle, {STANDS}, key: stand, pose: {{input: beyond}}", "input at 55"),
    ("joint-range", f"kind: angle, {STANDS}, key: stand, pose: {{input: 360}}", "input at 360"),
]


@pytest.mark.parametrize("rule, far, named", UNREACHED)
def test_pose_the_mechanism_cannot_reach_names_itself_and_leaves_its_check_unevaluated(
    mech_dir, rule, far, named
):
    add(mech_dir, params="beyond: {basis: derived, expr: input_max + 5}")
    add(mech_dir, checks=f"{{id: far, evidence: S2, {far}}}")
    run = check(mech_dir)
    assert run.errors == [rule] and named in run.messages(rule)[0]
    ids = [c["id"] for c in run.report["checks"]]
    assert "far" not in ids and len(ids) == 7  # every other check is evaluated as before


def test_gear_the_loops_do_not_allow_leaves_its_poses_unreached(mech_dir):
    # A screw from the slide to the knee, which the loop already sets as the crank turns: both
    # cannot hold. The loop's rows outweigh the screw's in the solve, so the loop closes within a
    # loose tolerance.length while the screw slips.
    screw = '"gears": {"slip": {"driver": "slide", "driven": "knee", "lead": "lead"}},'
    remodel(mech_dir, LOOP, f"{LOOP}\n        {screw}")
    add(mech_dir, params="lead: {basis: proposed, value: 3600, rationale: a screw, gap: G1}")
    meta(mech_dir, tolerance={"length": 0.1})
    run = check(mech_dir)
    assert set(run.errors) == {"loop-open"} and "gear slip" in run.messages("loop-open")[0]
    assert [c["id"] for c in run.report["checks"]] == ["length", "rest", "mass"]


BAD_TENDON = LOOP + '\n        "tendons": {"band": {"path": ["rail_1.up", "x.y"]}},'


@pytest.mark.parametrize(
    "rule, old, new",
    [
        ("model-joint", '"crank_1.up"]', '"crank_1.a"]'),
        ("model-loop", "slider_1.up", "slider_1.nope"),
        ("model-return", LOOP, BAD_TENDON),
    ],
)
def test_fault_in_what_moves_keeps_the_build_and_drops_the_motion(mech_dir, rule, old, new):
    remodel(mech_dir, old, new)
    run = check(mech_dir)
    assert run.errors == [rule]  # the posed checks are not evaluated, and say nothing more
    assert [c["id"] for c in run.report["checks"]] == ["length", "rest", "mass"]
    motion = run.report["motion"]
    assert motion["dropped"] and motion["joints"] == {} and "**Motion dropped**" in run.md
    assert not (mech_dir / "build" / "model.mjcf").exists()


def test_gear_moves_one_joint_with_the_other_by_its_ratio_and_a_screw_by_its_lead(
    mech_dir, tmp_path
):
    # The coupler geared to fold back twice as fast as the crank turns keeps its tip on the rail,
    # as the loop did; a screw on the crank's joint carries the slider 12 mm per turn.
    add_quote(mech_dir, tmp_path, "The screw carries the slider 12 mm per turn.", values={"v": 12})
    gears = FOLD.replace("}},", "}, ") + SCREW.removeprefix('"gears": {')
    fold = "{basis: proposed, value: -2, rationale: 'meshed to fold back', gap: G1}"
    open_chain(mech_dir, gears, fold=fold, lead="{basis: source, from: N1.v}")
    add(
        mech_dir,
        params="{at: {basis: source, from: S2.turn}, folded: {basis: derived, expr: fold * at}}",
        checks=f"""\
- {{id: travel, kind: distance, {RAIL}, from: {{}}, {TURNED}, expect: "N1.v * S2.turn / 360"}}
- {{id: driven, kind: angle, {STANDS}, evidence: S2, key: stand, pose: {{knee: folded}}}}
""",
    )
    run = check(mech_dir)
    assert run.status == "VERIFIED" and run.rules == []
    assert number(run.result("travel")) == 1 and number(run.result("reach")) == STOOD
    # Posing the driven joint moves its driver: the knee at -60 puts the crank at 30.
    assert number(run.result("driven")) == 60
    # A check rests on the ratio or lead of each gear its pose moves a joint through.
    reach, travel = run.result("reach"), run.result("travel")
    assert (reach["rests_on"], reach["rests_on_params"]) == ("proposed", ["fold"])
    assert (travel["rests_on"], travel["rests_on_params"]) == ("proposed", ["fold"])
    assert run.report["motion"]["gears"] == {
        "fold": {"driver": "input", "driven": "knee", "ratio": {"from": "fold", "value": -2}},
        "screw": {"driver": "input", "driven": "slide", "lead": {"from": "lead", "value": 12}},
    }
    # A lead is millimetres per turn; the MJCF couples the slide to the hinge per radian.
    assert coupled(mech_dir) == {
        "fold": ("knee", "input", [0, -2, 0, 0, 0]),
        "screw": ("slide", "input", pytest.approx([0, 12 / math.tau, 0, 0, 0])),
    }


def test_pose_at_a_number_is_a_test_condition_that_adds_no_basis_to_its_check(mech_dir, tmp_path):
    # "Per turn" fixes the turn by definition: the screw's travel posed at 360°, one full turn of
    # the crank, rests on the lead and the fold it moves through, both stated. With the crank's
    # range left out and the bars worked out from L, nothing is proposed and the project is exact.
    quote = "The screw carries the slider 12 mm per turn, and the coupler folds back at -2 times."
    add_quote(mech_dir, tmp_path, quote, values={"v": 12, "fold": -2})
    gears = FOLD.replace("}},", "}, ") + SCREW.removeprefix('"gears": {')
    stated = {
        name: f"{{basis: source, from: N1.{key}}}"
        for name, key in [("fold", "fold"), ("lead", "v")]
    }
    open_chain(mech_dir, gears, **stated)
    remodel(mech_dir, INPUT_RANGE + ",", "")
    edit(
        mech_dir, "params.yaml", lambda d: [d["params"].pop(n) for n in ("input_min", "input_max")]
    )
    edit(mech_dir, "checks.yaml", lambda d: d["checks"].pop(4))  # swing, the range's check
    change(mech_dir, "evidence", "S3", scope="not-modeled", reason="this test turns the crank on")
    for name, expr in {"W": "L / 8", "H": "L / 10", "hole": "L / 20"}.items():
        change(mech_dir, "params", name, basis="derived", expr=expr, value=None, rationale=None)
        change(mech_dir, "params", name, gap=None)
    write(mech_dir, "gaps.yaml", "gaps: []\n")
    travel = f"kind: distance, {RAIL}, from: {{}}, pose: {{input: 360}}, evidence: N1, key: v"
    add(mech_dir, checks=f"{{id: travel, {travel}}}")
    run = check(mech_dir)
    assert run.status == "VERIFIED" and run.report["exact"] is True
    travel = run.result("travel")
    assert number(travel) == 12 and travel["pose"] == {"input": {"from": None, "value": 360}}
    assert (travel["rests_on"], travel["rests_on_params"]) == ("source", ["fold", "lead"])


def test_cable_wound_on_a_wheel_closes_its_joints_in_proportion_and_a_stroke_reads_it(
    mech_dir, tmp_path
):
    # The crank's joint is the wheel, its one-ended range the full turn: over it the cable draws
    # the slider 20 mm in and folds the coupler back 60°, which keeps its tip on the rail.
    add_quote(mech_dir, tmp_path, "The cord draws the slider 20 mm in.", values={"draw": 20})
    remodel(mech_dir, INPUT_RANGE, '"range": ["turn"]')
    open_chain(
        mech_dir,
        WOUND.replace('"pull"}', '"pull", "knee": "fold"}'),
        turn="{basis: source, from: S2.turn}",
        draw="{basis: source, from: N1.draw}",
        pull="{basis: derived, expr: -draw}",
        fold="{basis: derived, expr: -2 * turn}",
        half="{basis: derived, expr: pull / 2}",
    )
    change(mech_dir, "checks", "swing", ends=["S2.turn"])
    add(
        mech_dir,
        checks=f"""\
- {{id: draw, kind: stroke, cable: cord, evidence: N1, key: draw}}
- {{id: half, kind: angle, {STANDS}, pose: {{slide: half}}, expect: "S1.rest + S2.turn / 2"}}
""",
    )
    run = check(mech_dir)
    assert run.errors == [] and all(c["ok"] for c in run.report["checks"])
    draw = run.result("draw")
    # With no pose of its own a stroke is taken at the wheel's full turn.
    assert number(draw) == 20 and draw["pose"] == {"input": {"from": "turn", "value": 30}}
    assert (draw["rests_on"], draw["rests_on_params"]) == ("source", ["turn", "pull", "fold"])
    # The joint's range is one-ended, so its range check compares the one end.
    assert number(run.result("reach")) == STOOD and run.result("swing.turn")["ok"]
    # Posing a joint the cable closes sets the wheel: the slider half in is the crank half turned.
    assert number(run.result("half")) == 45
    closes = {"slide": {"from": "pull", "value": -20}, "knee": {"from": "fold", "value": -60}}
    path = ["rail_1.up", "slider_1.down"]
    cables = run.report["motion"]["cables"]
    assert cables == {"cord": {"path": path, "wheel": "input", "closes": closes}}
    assert "Cable `cord` through rail_1.up → slider_1.down, wound on input" in run.md
    assert [s.get("site") for s in mjcf(mech_dir).iter("site") if s.get("site")] == path
    assert coupled(mech_dir) == {
        "cord_slide": ("slide", "input", pytest.approx([0, -20 / math.radians(30), 0, 0, 0])),
        "cord_knee": ("knee", "input", pytest.approx([0, -2, 0, 0, 0])),
    }


def test_stroke_of_a_cable_is_compared_with_a_stated_direction_or_a_worked_length(mech_dir):
    # A cord from the crank pivot to the slider is as long as the slider is far.
    remodel(mech_dir, LOOP, LOOP + "\n        " + CORD)
    cord = "kind: stroke, cable: cord"
    add(
        mech_dir,
        checks=f"""\
- {{id: shortens, {cord}, evidence: S2, claim: shortens, {TURNED}}}
- {{id: not-lengthens, {cord}, evidence: S2, claim: lengthens, {TURNED}}}
- {{id: not-moved, {cord}, evidence: S2, claim: shortens, {TURNED}, from: {{input: S2.turn}}}}
- {{id: lengthens, {cord}, evidence: S2, claim: lengthens, from: {{input: S2.turn}},
   pose: {{input: S3.low}}}}
- {{id: worked, {cord}, {TURNED}, expect: "{REACH % "S1.rest"} - S2.reach"}}
- {{id: paid-out, {cord}, from: {{input: S2.turn}}, pose: {{input: S3.low}},
   expect: "S2.reach - {REACH % "S1.rest + S3.low"}"}}
""",
    )
    run = check(mech_dir)
    failed = [c["id"] for c in run.report["checks"] if not c["ok"]]
    assert failed == ["not-lengthens", "not-moved"] and run.rules == ["check-failed"] * 2
    assert run.result("shortens")["expected"] == "shortens by more than 0.001 (S2)"
    assert number(run.result("shortens")) == pytest.approx(BUILT - STOOD, abs=5e-3)
    assert run.result("worked")["expect"]["value"] == pytest.approx(BUILT - STOOD)
    # A stroke with `from` is taken between two poses: here the cord pays out, a negative stroke.
    paid = run.result("paid-out")
    assert number(paid) == pytest.approx(STOOD - 80 * math.cos(math.radians(10)), abs=5e-3)
    assert paid["from_pose"] == {"input": {"from": "S2.turn", "value": 30}}
    assert paid["pose"] == {"input": {"from": "S3.low", "value": -20}}
    assert run.report["motion"]["cables"] == {"cord": {"path": ["rail_1.up", "slider_1.down"]}}


SPRUNG = (
    "The knee spring is 0.25 N·m/rad, preset at 45°, its damper 0.002 N·m·s/rad; a 300 N/m band."
)
PHYSICS = """\
knee_k: {basis: source, from: N1.k, physics: true}
knee_rest: {basis: source, from: N1.rest, physics: true}
knee_c: {basis: source, from: N1.c, physics: true}
knee_f: {basis: proposed, value: 2, rationale: light friction, gap: G1, physics: true}
band_k: {basis: source, from: N1.band, physics: true}
band_c: {basis: proposed, value: 0.001, rationale: light damping, gap: G1, physics: true}
"""
SPRING = '"stiffness": "knee_k", "spring_rest": "knee_rest", "damping": "knee_c", '
BAND = '"tendons": {"band": {"path": ["rail_1.up", "slider_1.down"], "stiffness": "band_k",'


def test_physics_values_reach_the_mjcf_in_its_units_and_shape_no_geometry(mech_dir, tmp_path):
    add_quote(mech_dir, tmp_path, SPRUNG, values={"k": 0.25, "rest": 45, "c": 0.002, "band": 300})
    remodel(mech_dir, KNEE, SPRING + '"friction": "knee_f", ' + KNEE)
    remodel(mech_dir, LOOP, LOOP + "\n        " + BAND + ' "damping": "band_c"}},')
    add(mech_dir, params=PHYSICS)
    run = check(mech_dir)
    # No check sees a physics value, so a source one needs none; a proposed one is counted apart.
    assert run.status == "VERIFIED" and run.rules == []
    counts = run.report["counts"]
    assert (counts["proposed"], counts["physics_proposed"]) == (3, 2)
    assert "3 on proposed values; 2 more are proposed physics values." in run.md
    # The report gives each in the project's units: N·mm per radian, degrees, N/mm.
    knee, band = run.report["motion"]["joints"]["knee"], run.report["motion"]["tendons"]["band"]
    assert {k: v["value"] for k, v in knee.items() if isinstance(v, dict)} == {
        "stiffness": 250,
        "spring_rest": 45,
        "damping": 2,
        "friction": 2,
    }
    assert band == {
        "path": ["rail_1.up", "slider_1.down"],
        "stiffness": {"from": "band_k", "value": 0.3},
        "damping": {"from": "band_c", "value": 0.001},
    }
    # The MJCF is in mm, g and s, so a newton is 1e6 g·mm/s², and angles are radians.
    (joint,) = [j for j in mjcf(mech_dir).iter("joint") if j.get("name") == "knee"]
    written = ("stiffness", "springref", "damping", "frictionloss")
    assert [float(joint.get(k, 0)) for k in written] == pytest.approx(
        [2.5e8, math.radians(45), 2e6, 2e6]
    )
    (spatial,) = mjcf(mech_dir).iter("spatial")
    assert (float(spatial.get("stiffness", 0)), float(spatial.get("damping", 0))) == (3e5, 1e3)


def test_a_slides_physics_values_are_a_force_per_length_and_a_force(mech_dir, tmp_path):
    quote = "The slider's spring is 0.5 N/mm, its damper 0.01 N·s/mm, its friction 2 N."
    add_quote(mech_dir, tmp_path, quote, values={"k": 0.5, "c": 0.01, "f": 2})
    sprung = '"stiffness": "slide_k", "damping": "slide_c", "friction": "slide_f", "drive"'
    remodel(mech_dir, '"slider_1.x"], "drive"', '"slider_1.x"], ' + sprung)
    add(
        mech_dir,
        params={
            f"slide_{key}": {"basis": "source", "from": f"N1.{key}", "physics": True}
            for key in "kcf"
        },
    )
    run = check(mech_dir)
    assert run.status == "VERIFIED" and run.rules == []
    (joint,) = [j for j in mjcf(mech_dir).iter("joint") if j.get("name") == "slide"]
    written = ("stiffness", "damping", "frictionloss")
    assert [float(joint.get(k, 0)) for k in written] == pytest.approx([5e5, 1e4, 2e6])


RANGED = "The crank stands from 10° to 80° above the rail, the slider 78.7846 mm to 13.8919 mm out."


def test_range_check_holds_each_end_of_a_joints_range_to_what_the_source_states(mech_dir, tmp_path):
    values = {"lo": 10, "hi": 80, "far": 78.7846, "near": 13.8919}
    add_quote(mech_dir, tmp_path, RANGED, values=values)
    add(
        mech_dir,
        checks=f"""\
- {{id: stands, kind: range, joint: input, ends: [N1.lo, N1.hi], {STANDS}}}
- {{id: slides, kind: range, joint: input, ends: [N1.far, N1.near], {RAIL}}}
- {{id: not-slides, kind: range, joint: input, ends: [N1.near, N1.far], {RAIL}}}
""",
    )
    run = check(mech_dir)
    measured = {c["id"]: (c["ok"], number(c)) for c in run.report["checks"] if c["kind"] == "range"}
    far, near = (pytest.approx(v, abs=5e-3) for v in (78.7846, 13.8919))
    # The joint's own ends, then at each end an angle between three datums and a distance of two.
    assert measured == {
        "swing.input_min": (True, -20),
        "swing.input_max": (True, 50),
        "stands.input_min": (True, 10),
        "stands.input_max": (True, 80),
        "slides.input_min": (True, far),
        "slides.input_max": (True, near),
        "not-slides.input_min": (False, far),
        "not-slides.input_max": (False, near),
    }
    stands = run.result("stands.input_max")
    assert stands["pose"] == {"input": {"from": "input_max", "value": 50}}
    assert stands["rests_on_params"] == ["input_min", "input_max"]
    # A range param that stops short of its stated end fails that end.
    change(mech_dir, "params", "input_max", basis="proposed", value=45, rationale="a guess")
    change(mech_dir, "params", "input_max", gap="G1", **{"from": None})
    run = check(mech_dir)
    short = run.result("swing.input_max")
    assert not short["ok"] and (short["expected"], number(short)) == ("50 (S3.high)", 45)
    assert (short["rests_on"], short["rests_on_params"]) == ("proposed", ["input_max"])
    assert run.result("swing.input_min")["ok"]


SWEEP = "kind: interference, sweep: {joint: input, steps: steps}"


def test_sweep_finds_the_pose_where_two_instances_collide_across_a_joints_range(mech_dir):
    # Eight poses from -20° to 50°: at the last the crank's hub runs into the slider's shoe.
    add(
        mech_dir,
        params="steps: {basis: proposed, value: 8, rationale: every 10°}",
        checks=f"""\
- {{id: clear, {SWEEP}, pairs: [[rail_1, coupler_1]]}}
- {{id: not-clear, {SWEEP}, pairs: [[crank_1, slider_1]]}}
- {{id: built, kind: interference}}
""",
    )
    run = check(mech_dir)
    clear, hit = run.result("clear"), run.result("not-clear")
    assert run.rules == ["check-failed"] and run.result("built")["pairs"] == 6
    assert clear["ok"] and clear["measured"] == "0 over 1 pair (listed) across 8 poses of input"
    swept = {"joint": "input", "from": ["input_min", "input_max"], "range": [-20, 50], "poses": 8}
    assert clear["sweep"] == swept and hit["sweep"] == swept
    assert not hit["ok"] and "crank_1 ∩ slider_1 at input 50 over 1 pair" in hit["measured"]
    assert hit["pose"] == {"input": {"from": "input_min..input_max", "value": 50}}
    assert "swept: input -20 to 50 (input_min to input_max), 8 poses" in run.md
    # A sweep's steps is its resolution: proposed, it asks no gap and no check rests on it.
    assert (clear["rests_on"], clear["rests_on_params"]) == ("source", ["input_min", "input_max"])
    assert "steps" in run.report["rests_on_proposed"]


def test_proposed_sweep_steps_and_physics_values_leave_a_project_exact(mech_dir):
    for name, expr in {"W": "L / 8", "H": "L / 10", "hole": "L / 20"}.items():
        change(mech_dir, "params", name, basis="derived", expr=expr, value=None, rationale=None)
        change(mech_dir, "params", name, gap=None)
    write(mech_dir, "gaps.yaml", "gaps: []\n")
    remodel(mech_dir, KNEE, '"damping": "knee_c", ' + KNEE)
    add(
        mech_dir,
        params="""\
steps: {basis: proposed, value: 3, rationale: coarse}
knee_c: {basis: proposed, value: 2, rationale: light damping, physics: true}
""",
        checks=f"{{id: clear, {SWEEP}, pairs: [[rail_1, coupler_1]]}}",
    )
    run = check(mech_dir)
    assert run.status == "VERIFIED" and run.report["exact"] is True
    assert run.report["rests_on_proposed"] == ["knee_c", "steps"]
    assert "1 physics value and the sweep resolution steps are proposed" in run.md
    assert run.messages("param-gap") == ["param knee_c: proposed value names no gap to close it"]


def test_mass_check_without_a_density_weighs_each_instance_by_the_mass_model(mech_dir):
    run = check(mech_dir)
    mass = run.result("mass")
    assert mass["ok"] and number(mass) == pytest.approx(6.11) and mass["uncounted"] == {}
    assert (mass["rests_on"], mass["rests_on_params"]) == ("source", ["rho", "slider_m"])
    # A slider a gram heavier than its datasheet takes the total past the stated 6.1 g ± 5%.
    change(mech_dir, "params", "slider_m", basis="proposed", value=3, rationale="a guess")
    change(mech_dir, "params", "slider_m", gap="G1", **{"from": None})
    run = check(mech_dir)
    mass = run.result("mass")
    assert not mass["ok"] and number(mass) == pytest.approx(7.11)
    assert (mass["rests_on"], mass["rests_on_params"]) == ("proposed", ["slider_m"])
    assert run.report["masses"]["slider"]["mass"] == 3


def test_part_no_instance_places_is_exported_in_its_own_frame_and_neither_weighed_nor_posed(
    mech_dir,
):
    # A settled part whose place the sources leave open needs no mass-model entry.
    pin = '    parts["pin"] = Cylinder(p.hole / 2, p.L)\n'
    remodel(mech_dir, "    datums = {", f"{pin}    datums = {{")
    run = check(mech_dir)
    assert run.status == "VERIFIED" and run.rules == []
    assert (mech_dir / "build" / "parts" / "pin.step").exists()
    assert number(run.result("mass")) == pytest.approx(6.11) and "pin" not in run.report["masses"]
    meshes = {g.get("mesh") for g in mjcf(mech_dir).iter("geom")}
    assert "crank" in meshes and "pin" not in meshes
