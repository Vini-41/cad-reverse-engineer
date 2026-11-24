"""The plan: how the object is made and put together, held to the model it is a plan of."""

import pytest
from conftest import (
    ASSEMBLY,
    M3_SCREW,
    TEN_LONG,
    add,
    change,
    check,
    edit,
    meta,
    place,
    remodel,
    stack,
    threaded,
)
from test_drawing import height, highest, inked, lowest

FLAT = "link: [print it flat in PLA, ream both holes]"
STEPS = "[{place: [link_1]}, {place: [link_2]}]"


def test_plan_lists_what_is_made_and_each_step_counted_from_the_model(proj_dir):
    stack(proj_dir, 2)
    add(proj_dir, make=FLAT, buy="glue: a drop of cyanoacrylate")
    add(proj_dir, steps="[{place: [link_1], note: On the bench.}, {place: [link_2]}]")
    run = check(proj_dir)
    assert run.status == "VERIFIED" and run.rules == []
    assert run.report["plan"] == {
        "make": [{"part": "link", "count": 2, "how": ["print it flat in PLA", "ream both holes"]}],
        # What is neither a part nor a screw is listed as it is written, uncounted.
        "buy": [{"item": "glue", "count": None, "what": "a drop of cyanoacrylate"}],
        "steps": [
            {"place": ["link_1"], "with": {}, "note": "On the bench.", "view": "steps/1.png"},
            {"place": ["link_2"], "with": {}, "view": "steps/2.png"},
        ],
    }
    assert run.report["held"] == {"clearance": None, "floating": []}
    # The plan is a file of its own, for whoever makes the object; the report points to it.
    assert "[plan.md](plan.md)" in run.md and "wrote build/plan.md\n" in run.out
    md = run.plan_md
    made = "- **link** × 2 ([drawing](drawings/link.png))\n  1. print it flat in PLA\n  2. ream"
    order = ["![isometric](isometric.png)", "## Make", made, "## Buy"]
    order += ["| glue |  | a drop of cyanoacrylate |", "## Assemble", "### Step 1"]
    order += ["**Place** link.\n\nOn the bench.\n\n![step 1](steps/1.png)", "### Step 2"]
    order += ["![step 2](steps/2.png)"]
    assert [md.index(mark) for mark in order] == sorted(md.index(mark) for mark in order)


def test_plan_states_one_general_tolerance_and_its_guide_prints_it_once(proj_dir):
    add(proj_dir, make=FLAT)
    edit(proj_dir, "plan.yaml", lambda d: d.update(general_tolerance="±0.2 mm unless noted"))
    run = check(proj_dir)
    assert run.status == "VERIFIED" and run.rules == []
    assert run.report["plan"]["general_tolerance"] == "±0.2 mm unless noted"
    assert run.plan_md.count("±0.2 mm unless noted") == 1
    assert run.plan_md.index("±0.2 mm") < run.plan_md.index("- **link**")


def test_each_step_has_a_view_of_what_it_places_on_what_is_already_there(proj_dir):
    stack(proj_dir, 3)
    add(proj_dir, make=FLAT)
    add(proj_dir, steps="[{place: [link_2, link_3]}, {note: Let the glue set.}, {place: [link_1]}]")
    run = check(proj_dir)
    assert run.rules == [] and "wrote build/steps/: 2 step views\n" in run.out
    # A step that places nothing has nothing to show.
    assert [s.get("view") for s in run.report["plan"]["steps"]] == ["steps/1.png", None] + [
        "steps/3.png"
    ]
    assert "steps/1.png" not in run.report["drawings"] and "**Place** link × 2." in run.plan_md
    # Placed first, the two links stand alone; placed last, they are drawn over the first, in grey.
    alone = inked(proj_dir / "build" / "steps" / "1.png", "placed")
    edit(proj_dir, "plan.yaml", lambda d: d["steps"].reverse())
    check(proj_dir)
    assert inked(proj_dir / "build" / "steps" / "3.png", "placed") > alone + 200


def test_step_names_the_direction_its_instances_come_from(proj_dir):
    stack(proj_dir, 2)
    add(proj_dir, make=FLAT, steps="[{place: [link_1]}, {place: [link_2], from: +z}]")
    run = check(proj_dir)
    assert run.status == "VERIFIED" and run.rules == [], run.out
    first, second = run.report["plan"]["steps"]
    assert "from" not in first and second["from"] == "+z"


def test_step_with_a_direction_is_drawn_apart_with_a_guideline_to_its_place(proj_dir):
    stack(proj_dir, 2)
    add(proj_dir, make=FLAT, steps=STEPS)
    check(proj_dir)
    view = proj_dir / "build" / "steps" / "2.png"
    in_place = height(view, "black") - height(view, "placed")
    assert inked(view, "guide") == 0
    # From above, the second link hangs clear over the first, a line running down to its place.
    edit(proj_dir, "plan.yaml", lambda d: d["steps"][1].update({"from": "+z"}))
    run = check(proj_dir)
    assert run.rules == [], run.out
    assert height(view, "black") - height(view, "placed") > in_place + 0.1
    assert inked(view, "guide") > 50
    # From below, it is drawn under the first.
    edit(proj_dir, "plan.yaml", lambda d: d["steps"][1].update({"from": "-z"}))
    check(proj_dir)
    assert height(view, "black") < height(view, "placed")
    assert inked(view, "guide") > 50


def _pins(proj_dir, tall: str, *xs: str) -> None:
    """A link with a pin `tall` high, as model.py source, standing on it at each x."""
    remodel(proj_dir, '{"link": link}', f'{{"link": link, "pin": Cylinder(p.hole_d / 2, {tall})}}')
    pins = "".join(
        f', "pin_{i}": ("pin", Location(({x}, 0, (p.link_H + {tall}) / 2)))'
        for i, x in enumerate(xs, 1)
    )
    remodel(proj_dir, ASSEMBLY, ASSEMBLY.replace("},", pins + "},"))
    add(proj_dir, make=FLAT, buy="pin: a dowel pin")


def test_guideline_runs_down_to_what_the_part_lands_on(proj_dir):
    _pins(proj_dir, "p.pitch", "0")
    add(proj_dir, steps="[{place: [link_1]}, {place: [pin_1], from: +z}]")
    run = check(proj_dir)
    assert run.rules == [], run.out
    view = proj_dir / "build" / "steps" / "2.png"
    # From the pin's foot to the link it stands on: further than the pin is tall.
    guideline = highest(view, "guide") - lowest(view, "guide")
    assert guideline > highest(view, "black") - lowest(view, "black")


def test_instances_far_apart_are_each_drawn_as_near_as_one_alone(proj_dir):
    _pins(proj_dir, "p.hole_d", "-p.pitch / 2", "p.pitch / 2")
    add(proj_dir, steps="[{place: [link_1, pin_2]}, {place: [pin_1], from: +z}]")
    check(proj_dir)
    view = proj_dir / "build" / "steps" / "2.png"
    one = inked(view, "guide")
    steps = [{"place": ["link_1"]}, {"place": ["pin_1", "pin_2"], "from": "+z"}]
    edit(proj_dir, "plan.yaml", lambda d: d.update(steps=steps))
    check(proj_dir)
    assert inked(view, "guide") < 2.6 * one


def test_view_shows_the_most_of_the_part_not_the_least_hidden_share(proj_dir):
    # A plate whose top is drilled with blind holes, sitting in an open frame that stands proud
    # of it: from above the frame hides a larger share, but of far more that is there to see.
    board = (
        "Box(p.pitch, p.pitch, p.link_H) - "
        "Pos(0, 0, p.link_H / 2 / 2) * (GridLocations(p.pitch / 2, p.pitch / 2, 2, 2) "
        "* Cylinder(p.hole_d, p.link_H / 2))"
    )
    frame = (
        "Pos(0, 0, p.hole_d / 2) * (Box(p.pitch + p.link_W, p.pitch + p.link_W, p.link_H) "
        "- Box(p.pitch, p.pitch, p.link_H + p.link_W))"
    )
    remodel(proj_dir, '{"link": link}', f'{{"link": {board}, "frame": {frame}}}')
    remodel(proj_dir, ASSEMBLY, ASSEMBLY.replace("},", ', "frame_1": ("frame", Location())},'))
    edit(
        proj_dir,
        "checks.yaml",
        lambda d: d.update(checks=[c for c in d["checks"] if c["id"] == "clear"]),
    )
    add(proj_dir, make=FLAT, buy="frame: a frame")
    add(proj_dir, steps="[{place: [frame_1]}, {place: [link_1]}]")
    run = check(proj_dir)
    assert "corner" not in run.report["plan"]["steps"][1], run.out


def test_every_instance_a_step_places_is_drawn_in_black(proj_dir):
    # A link either side of the first, so neither of the two hides the other.
    sides = {"link_2": "Location((0, p.link_W, 0))", "link_3": "Location((0, -p.link_W, 0))"}
    place(proj_dir, link_1="Location()", **sides)
    add(proj_dir, make=FLAT, steps="[{place: [link_1, link_3]}, {place: [link_2], from: +z}]")
    check(proj_dir)
    view = proj_dir / "build" / "steps" / "2.png"
    one = inked(view, "black")
    steps = [{"place": ["link_1"]}, {"place": ["link_2", "link_3"], "from": "+z"}]
    edit(proj_dir, "plan.yaml", lambda d: d.update(steps=steps))
    check(proj_dir)
    assert inked(view, "black") > 1.5 * one


def test_view_of_a_part_that_goes_in_from_below_looks_at_where_it_lands(proj_dir):
    # The second link under the first, coming up from below: drawn clear of the first, it would
    # show from any corner, but its place shows only from beneath.
    place(proj_dir, link_1="Location()", link_2="Location((0, 0, -p.link_H))")
    add(proj_dir, make=FLAT, steps="[{place: [link_1]}, {place: [link_2], from: -z}]")
    run = check(proj_dir)
    assert run.rules == [], run.out
    assert run.report["plan"]["steps"][1]["corner"].endswith("-z")


def test_step_is_viewed_from_the_corner_that_shows_what_it_places(proj_dir):
    # A wall against the link's -y face, between it and the corner a view takes by default.
    wall = "Box(2 * p.pitch, p.hole_d, 2 * p.pitch)"
    remodel(proj_dir, '{"link": link}', f'{{"link": link, "wall": {wall}}}')
    at = "Location((0, -(p.link_W + p.hole_d) / 2, 0))"
    remodel(proj_dir, ASSEMBLY, ASSEMBLY.replace("},", f', "wall_1": ("wall", {at})}},'))
    add(proj_dir, make=FLAT, buy="wall: a plate", steps="[{place: [wall_1]}, {place: [link_1]}]")
    run = check(proj_dir)
    assert run.rules == [], run.out
    first, behind = run.report["plan"]["steps"]
    # Nothing stands before the wall, so it keeps the default; the link is seen from behind it.
    assert "corner" not in first
    assert "+y" in behind["corner"] and behind["corner"].endswith("+z")
    # Placed in the other order, nothing hides either from the default corner.
    edit(proj_dir, "plan.yaml", lambda d: d["steps"].reverse())
    run = check(proj_dir)
    assert not any("corner" in step for step in run.report["plan"]["steps"])


def test_project_with_no_plan_reports_none(proj_dir):
    run = check(proj_dir)
    assert run.report["plan"] is None and "## Plan" not in run.md
    assert not (proj_dir / "build" / "plan.md").exists()


def test_plan_of_one_instance_needs_no_steps(proj_dir):
    add(proj_dir, make="link: mill it from 5 mm plate")
    run = check(proj_dir)
    assert run.status == "VERIFIED" and run.rules == []
    assert "- **link** × 1 ([drawing](drawings/link.png)): mill it from 5 mm plate\n" in run.plan_md
    assert "_No steps: the assembly places one instance._" in run.plan_md
    # Its screws still need a step to drive them, or the plan buys none.
    threaded(proj_dir, spec=M3_SCREW)
    add(proj_dir, params=TEN_LONG)
    run = check(proj_dir)
    assert run.findings == [("warning", "plan-screw")]
    add(proj_dir, steps="{place: [link_1], with: {screw: 2}}")
    run = check(proj_dir)
    assert run.rules == [] and run.report["plan"]["buy"][0]["count"] == 2


def test_steps_drive_the_screws_the_model_has_holes_threaded_for(proj_dir):
    threaded(proj_dir, spec=M3_SCREW)
    add(proj_dir, params=TEN_LONG, make=FLAT, buy="screw: socket head cap screw, ISO 4762")
    add(proj_dir, steps="{place: [link_1], with: {screw: 2}, note: Snug.}")
    run = check(proj_dir)
    assert run.status == "VERIFIED" and run.rules == []
    assert run.report["plan"]["buy"] == [
        {
            "item": "screw",
            "count": 2,
            "what": "socket head cap screw, ISO 4762",
            "thread": "M3×10",
        }
    ]
    assert "| screw | 2 | M3×10: socket head cap screw, ISO 4762 |" in run.plan_md
    assert "**Place** link. **Drive** 2 × screw (M3×10).\n\nSnug.\n" in run.plan_md
    # A hole threaded for a screw and left without one is said, and may be meant.
    change(proj_dir, "steps", None, **{"with": {"screw": 1}})
    run = check(proj_dir)
    assert run.status == "VERIFIED" and run.findings == [("warning", "plan-screw")]
    assert "2 holes threaded M3×0.5 for screw, against 1 screw the steps drive" in run.out
    # A thread with no length names no screw: a hole left open for the user's own.
    edit(proj_dir, "params.yaml", lambda d: d["params"]["screw"].pop("length"))
    edit(proj_dir, "params.yaml", lambda d: d["params"].pop("screw_len"))
    run = check(proj_dir)
    assert run.rules == [] and run.report["plan"]["buy"][0]["thread"] == "M3×0.5"


PINNED = '"link_1": ("link", Location()), "pin_1": ("pin", Location((-p.pitch / 2, 0, p.link_H)))'


def test_screw_built_as_a_part_fills_its_hole_without_a_step_driving_it(proj_dir):
    # The screw as a part, its shank declared for the thread its holes carry, standing on the link
    # over the hole it fills.
    threaded(proj_dir, spec=M3_SCREW)
    add(proj_dir, params=TEN_LONG)
    remodel(proj_dir, '{"link": link}', '{"link": link, "pin": Cylinder(p.screw / 2, p.link_H)}')
    remodel(proj_dir, '"link.b": "screw"', '"link.b": "screw", "pin.axis": "screw"')
    remodel(proj_dir, '"link.top":', '"pin.axis": (0, 0, 0),\n        "link.top":')
    two = PINNED + ', "pin_2": ("pin", Location((p.pitch / 2, 0, p.link_H)))'
    remodel(proj_dir, '"link_1": ("link", Location())', two)
    add(proj_dir, make=FLAT, buy="pin: M3×10 socket head cap screw, ISO 4762")
    add(proj_dir, steps="[{place: [link_1]}, {place: [pin_1, pin_2], note: Snug.}]")
    run = check(proj_dir)
    assert run.status == "VERIFIED" and run.rules == [], run.out
    assert run.report["threads"][0]["threaded"] == ["link.a", "link.b", "pin.axis"]
    assert run.report["plan"]["buy"] == [
        {"item": "pin", "count": 2, "what": "M3×10 socket head cap screw, ISO 4762"}
    ]
    # One screw fewer leaves a threaded hole open.
    remodel(proj_dir, two, PINNED)
    edit(proj_dir, "plan.yaml", lambda d: d["steps"][1].update(place=["pin_1"]))
    run = check(proj_dir)
    assert run.findings == [("warning", "plan-screw")]
    assert "against 0 screws the steps drive and 1 screw built as a part" in run.out


def test_screw_built_as_a_part_fills_every_threaded_hole_on_its_axis(proj_dir):
    # A screw through a tapped link into a second one, as a screw into a bracket and a locknut.
    threaded(proj_dir, spec=M3_SCREW)
    add(proj_dir, params=TEN_LONG)
    remodel(proj_dir, '{"link": link}', '{"link": link, "pin": Cylinder(p.screw / 2, p.link_H)}')
    remodel(proj_dir, '"link.b": "screw"', '"pin.axis": "screw"')
    remodel(proj_dir, '"link.top":', '"pin.axis": (0, 0, 0),\n        "link.top":')
    stacked = (
        '"link_1": ("link", Location()), "link_2": ("link", Location((0, 0, p.link_H))), '
        '"pin_1": ("pin", Location((-p.pitch / 2, 0, 2 * p.link_H)))'
    )
    remodel(proj_dir, '"link_1": ("link", Location())', stacked)
    add(proj_dir, make=FLAT, buy="pin: M3×10 socket head cap screw, ISO 4762")
    add(proj_dir, steps="{place: [link_1, link_2, pin_1]}")
    assert ("warning", "plan-screw") not in check(proj_dir).findings


def test_report_says_what_the_object_is_made_of_and_what_it_follows(proj_dir):
    meta(proj_dir, material="PLA, FDM printed", follows="function")
    run = check(proj_dir)
    assert (run.report["material"], run.report["follows"]) == ("PLA, FDM printed", "function")
    assert "**Material**: PLA, FDM printed. **Follows** the function:" in run.md
    meta(proj_dir, material=None, follows="design")
    assert "\n**Follows** the design:" in check(proj_dir).md


# The second link a hole's width above the first: 3 mm of air between them.
LIFTED = {"link_1": "Location()", "link_2": "Location((0, 0, p.link_H + p.hole_d))"}


def test_each_instance_is_held_by_another(proj_dir):
    place(proj_dir, **LIFTED)
    # A complete model with no plan is told what floats, and stands: what holds a part may be
    # left out of its target.
    run = check(proj_dir)
    assert run.status == "VERIFIED" and run.findings == [("warning", "held")]
    (floating,) = run.report["held"]["floating"]
    assert floating["instances"] == ["link_2"] and floating["nearest"] == "link_1"
    assert floating["gap"] == pytest.approx(3)
    # A known-first project's parts may wait on what holds them.
    meta(proj_dir, known_first=True)
    run = check(proj_dir)
    assert "held" not in run.rules and run.report["held"] is None
    meta(proj_dir, known_first=None)
    # A plan claims the object is put together, so there what floats is an error.
    add(proj_dir, make=FLAT, steps=STEPS)
    run = check(proj_dir)
    assert run.status == "NOT VERIFIED" and run.errors == ["held"]
    assert run.report["held"]["floating"] == [floating]
    # A fit leaves a gap: project.yaml names the param that states it, and the two hold again.
    # A param only the clearance reads is read.
    add(proj_dir, params="fit: {basis: derived, expr: hole_d}")
    meta(proj_dir, clearance="fit")
    run = check(proj_dir)
    assert run.rules == [] and run.report["held"]["floating"] == []
    assert run.report["held"]["clearance"] == {"from": "fit", "value": 3}
    assert "within 3 mm of each other, the loosest fit (`fit`)" in run.plan_md
    # Set down on the first link, the second needs no clearance to be held.
    meta(proj_dir, clearance=None)
    remodel(proj_dir, "p.link_H + p.hole_d", "p.link_H")
    run = check(proj_dir)
    assert run.status == "VERIFIED" and run.report["held"]["floating"] == []


def test_parts_built_to_touch_touch_within_the_length_tolerance(proj_dir):
    # Two gears in mesh, or two faces a kernel builds to meet, lie a hair apart: as far as the
    # model realises any length.
    add(proj_dir, params="hair: {basis: derived, expr: hole_d / 6000}")
    place(proj_dir, link_1="Location()", link_2="Location((0, 0, p.link_H + p.hair))")
    add(proj_dir, make=FLAT, steps=STEPS)
    run = check(proj_dir)
    assert run.rules == [] and run.report["held"]["floating"] == []
    meta(proj_dir, tolerance={"length": 0.0001, "angle": 0.01})
    run = check(proj_dir)
    assert run.errors == ["held"]
    assert run.report["held"]["floating"][0]["gap"] == pytest.approx(0.0005)


def test_instances_that_hold_only_each_other_float_as_one_group(proj_dir):
    lifts = ["0", "p.link_H", "2 * p.link_H", "p.pitch", "p.pitch + p.link_H"]
    names = [f"link_{i + 1}" for i in range(5)]
    place(proj_dir, **{name: f"Location((0, 0, {lift}))" for name, lift in zip(names, lifts)})
    add(proj_dir, make=FLAT, steps=[{"place": [name]} for name in names])
    run = check(proj_dir)
    assert run.errors == ["held"]
    (floating,) = run.report["held"]["floating"]
    assert floating["instances"] == ["link_4", "link_5"]
    assert (floating["from"], floating["nearest"]) == ("link_4", "link_3")
    assert floating["gap"] == pytest.approx(30 - 3 * 8)


def test_part_made_beside_the_object_is_placed_by_no_instance(proj_dir):
    coupon = '{"link": link, "coupon": Box(p.link_W, p.link_W, p.link_H)}'
    remodel(proj_dir, '{"link": link}', coupon)
    steps = "[{note: Print the coupon and try a pin in it.}, {place: [link_1]}]"
    add(proj_dir, make=FLAT, steps=steps)
    add(proj_dir, make="coupon: print it first")
    run = check(proj_dir)
    assert run.status == "VERIFIED" and run.rules == [], run.out
    assert run.report["plan"]["make"][1] == {"part": "coupon", "count": 0} | {
        "how": ["print it first"]
    }
    assert "- **coupon** ([drawing](drawings/coupon.png)): print it first\n" in run.plan_md


def test_small_part_is_shown_on_the_whole_of_what_it_goes_onto(proj_dir):
    # A pin a thirteenth of the link's length, standing on the link's middle: every edge of the
    # link lies further from the pin than the pin is large.
    pin = "Cylinder(p.hole_d / 2, p.hole_d)"
    remodel(proj_dir, '{"link": link}', f'{{"link": link, "pin": {pin}}}')
    on = "Location((0, 0, p.link_H / 2 + p.hole_d / 2))"
    remodel(proj_dir, ASSEMBLY, ASSEMBLY.replace("},", f', "pin_1": ("pin", {on})}},'))
    add(proj_dir, make=FLAT, buy="pin: a dowel pin", steps="[{place: [link_1]}, {place: [pin_1]}]")
    run = check(proj_dir)
    assert run.rules == [], run.out
    # The pin's view draws the link whole, in grey.
    view = proj_dir / "build" / "steps" / "2.png"
    assert inked(view, "placed") > 3000
    # And so it does where the pin stands a fit's gap above the link, held across it.
    remodel(proj_dir, "p.link_H / 2 + p.hole_d / 2", "p.link_H / 2 + p.hole_d / 2 + p.hole_d")
    meta(proj_dir, clearance="hole_d")
    run = check(proj_dir)
    assert run.rules == [] and inked(view, "placed") > 3000
    # Or a hair above it, touching it as far as the model realises any length.
    meta(proj_dir, clearance=None)
    add(proj_dir, params="hair: {basis: derived, expr: hole_d / 6000}")
    remodel(
        proj_dir, "p.link_H / 2 + p.hole_d / 2 + p.hole_d", "p.link_H / 2 + p.hole_d / 2 + p.hair"
    )
    view.unlink()
    run = check(proj_dir)
    assert run.rules == [] and inked(view, "placed") > 3000


def test_instance_inside_another_and_clear_of_its_walls_floats(proj_dir):
    # A pin half the size of the link's hole, standing in it and touching nothing.
    pin = "Cylinder(p.hole_d / 2 / 2, p.link_H / 2)"
    remodel(proj_dir, '{"link": link}', f'{{"link": link, "pin": {pin}}}')
    one = ASSEMBLY.replace("},", ', "pin_1": ("pin", Location((p.pitch / 2, 0, 0)))},')
    remodel(proj_dir, ASSEMBLY, one)
    add(proj_dir, make=FLAT, buy="pin: a dowel pin", steps="[{place: [link_1, pin_1]}]")
    run = check(proj_dir)
    assert run.errors == ["held"]
    (floating,) = run.report["held"]["floating"]
    assert floating["instances"] == ["pin_1"] and floating["gap"] == pytest.approx(0.75)
    # Sunk whole into the link's material, clear of every face, it overlaps the link, which
    # so holds it.
    remodel(proj_dir, "Location((p.pitch / 2, 0, 0))", "Location((0, 0, 0))")
    change(proj_dir, "checks", "clear", max_volume=100)
    run = check(proj_dir)
    assert run.rules == [] and run.report["held"]["floating"] == []
