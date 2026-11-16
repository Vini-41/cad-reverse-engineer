"""The plan: how the object is made and put together, held to the model it is a plan of."""

from conftest import (
    M3_SCREW,
    TEN_LONG,
    add,
    change,
    check,
    edit,
    meta,
    remodel,
    stack,
    threaded,
)

FLAT = "link: [print it flat in PLA, ream both holes]"


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
            {"place": ["link_1"], "with": {}, "note": "On the bench."},
            {"place": ["link_2"], "with": {}},
        ],
    }
    md = run.md
    order = ["## Plan", "### Make", "- **link** × 2\n  1. print it flat in PLA\n  2. ream both"]
    order += ["### Buy", "| glue |  | a drop of cyanoacrylate |", "### Assemble"]
    order += ["1. **link_1**. On the bench.", "2. **link_2**", "## Parts"]
    assert [md.index(mark) for mark in order] == sorted(md.index(mark) for mark in order)


def test_project_with_no_plan_reports_none(proj_dir):
    run = check(proj_dir)
    assert run.report["plan"] is None and "## Plan" not in run.md


def test_plan_of_one_instance_needs_no_steps(proj_dir):
    add(proj_dir, make="link: mill it from 5 mm plate")
    run = check(proj_dir)
    assert run.status == "VERIFIED" and run.rules == []
    assert "- **link** × 1: mill it from 5 mm plate\n" in run.md
    assert "_No steps: the assembly places one instance._" in run.md
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
    assert "| screw | 2 | M3×10: socket head cap screw, ISO 4762 |" in run.md
    assert "1. **link_1** with 2 × screw (M3×10). Snug." in run.md
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


PINNED = '"link_1": ("link", Location()), "pin_1": ("pin", Location((0, p.pitch, 0)))'


def test_screw_built_as_a_part_fills_its_hole_without_a_step_driving_it(proj_dir):
    # The screw as a part, its shank declared for the thread its holes carry, placed off the link.
    threaded(proj_dir, spec=M3_SCREW)
    add(proj_dir, params=TEN_LONG)
    remodel(proj_dir, '{"link": link}', '{"link": link, "pin": Cylinder(p.screw / 2, p.link_H)}')
    remodel(proj_dir, '"link.b": "screw"', '"link.b": "screw", "pin.axis": "screw"')
    remodel(proj_dir, '"link.top":', '"pin.axis": (0, 0, 0),\n        "link.top":')
    two = PINNED + ', "pin_2": ("pin", Location((0, 2 * p.pitch, 0)))'
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


def test_report_says_what_the_object_is_made_of_and_what_it_follows(proj_dir):
    meta(proj_dir, material="PLA, FDM printed", follows="function")
    run = check(proj_dir)
    assert (run.report["material"], run.report["follows"]) == ("PLA, FDM printed", "function")
    assert "**Material**: PLA, FDM printed. **Follows** the function:" in run.md
    meta(proj_dir, material=None, follows="design")
    assert "\n**Follows** the design:" in check(proj_dir).md
