"""Threads: a thread param named from the ISO metric or the Unified table, the plain holes and
shanks model.py declares for it, the screw it is bought as, and what the report says of them."""

import pytest
from conftest import (
    M3_SCREW,
    TEN_LONG,
    add,
    add_quote,
    change,
    check,
    edit,
    meta,
    remodel,
    stack,
    threaded,
)


@pytest.mark.parametrize(
    "size, fit, diameter", [("tap", "threaded", 2.5), ("clearance", "clearance", 3.4)]
)
def test_thread_param_sizes_its_holes_from_the_table_and_the_report_lists_them(
    proj_dir, tmp_path, size, fit, diameter
):
    threaded(proj_dir, size)
    add_quote(proj_dir, tmp_path, f"The holes are drilled {diameter} mm.", values={"d": diameter})
    add(proj_dir, checks="{id: bore, kind: diameter, at: link.wall, evidence: N1, key: d}")
    run = check(proj_dir)
    assert run.status == "VERIFIED" and run.result("bore")["ok"]
    assert run.report["params"]["screw"]["value"] == 3  # its major diameter
    other = "clearance" if fit == "threaded" else "threaded"
    assert run.report["threads"] == [
        {"param": "screw", "thread": "M3×0.5", "table": "metric", "basis": "proposed"}
        | {fit: ["link.a", "link.b"], other: []}
    ]
    assert "## Threads" in run.md and "| screw | M3×0.5 | proposed |" in run.md
    assert "| screw | 3 (M3×0.5) | proposed |" in run.md


# A statement of a thread, the designation a param reads from it, and its tap drill in mm.
STATED = {
    "a size before a length": ("an M3x10 screw", "M3", 2.5),
    "a fine pitch": ("an M3 × 0.35 screw", "M3x0.35", 2.65),
    "a Unified size": ("a 4-40 UNC screw", "4-40", 2.2098),
    "a Unified size by its number sign": ("a #10-32 screw", "10-32", 4.03225),
    "a second-choice metric size": ("an M4.5 screw", "M4.5", 3.75),
    "a Unified size with no clearance hole in its table": ("a No. 12-24 screw", "12-24", 4.428067),
}


@pytest.mark.parametrize("case", STATED)
def test_source_thread_is_the_designation_its_statement_prints(proj_dir, tmp_path, case):
    stated, designation, tap = STATED[case]
    text = f"Each pin is {stated}, in a hole drilled {tap} mm."
    add_quote(proj_dir, tmp_path, text, values={"d": tap})
    threaded(proj_dir, spec=f"screw: {{basis: source, thread: {designation}, from: N1}}")
    edit(proj_dir, "gaps.yaml", lambda d: d.update(gaps=[]))  # the gap hole_d named
    add(proj_dir, checks="{id: bore, kind: diameter, at: link.wall, evidence: N1, key: d}")
    run = check(proj_dir)
    # Declared on its holes, a source thread is checked: they are held to its sizes.
    assert run.status == "VERIFIED" and run.rules == [] and run.result("bore")["ok"]
    assert run.report["rests_on_proposed"] == []


def test_proposed_thread_comes_from_the_projects_table_and_a_stated_one_from_either(
    proj_dir, tmp_path
):
    threaded(proj_dir)
    meta(proj_dir, threads="unified")
    run = check(proj_dir)
    assert run.errors == ["thread-standard"] and "ISO metric table" in run.out
    add_quote(proj_dir, tmp_path, "Each pin is an M3 screw.")
    add(proj_dir, params="screw: {basis: source, thread: M3, from: N1}")
    assert check(proj_dir).status == "VERIFIED"


def test_thread_reads_in_the_projects_length_unit(proj_dir):
    threaded(proj_dir)
    meta(proj_dir, units={"length": "in"}, threads="metric", tolerance={"length": 1e-5})
    run = check(proj_dir)
    assert run.status == "VERIFIED"
    assert run.report["params"]["screw"]["value"] == pytest.approx(3 / 25.4)


def test_proposed_thread_is_unified_in_a_project_in_inches_unless_it_says_metric(proj_dir):
    # US is one answer: the length unit alone gives the thread table.
    threaded(proj_dir)
    meta(proj_dir, units={"length": "in"}, tolerance={"length": 1e-5})
    run = check(proj_dir)
    assert run.errors == ["thread-standard"] and "threads is unified" in run.out
    change(proj_dir, "params", "screw", thread="4-40")
    assert check(proj_dir).status == "VERIFIED"


def test_screw_is_its_thread_and_a_standard_length_as_it_is_ordered(proj_dir):
    threaded(proj_dir, spec=M3_SCREW)
    add(proj_dir, params=TEN_LONG)
    run = check(proj_dir)
    # Its length shapes no geometry here: it says what is bought, and needs no check.
    assert run.status == "VERIFIED" and run.rules == []
    (listed,) = run.report["threads"]
    assert (listed["length"], listed["screw"]) == ("screw_len", "M3×10")
    assert "| screw | M3×0.5 | M3×10 (screw_len) | proposed |" in run.md
    # A length that is not on the chart is one nobody sells.
    change(proj_dir, "params", "screw_len", value=11.27)
    run = check(proj_dir)
    assert run.errors == ["screw-length"]
    assert "the nearest are 10 mm and 12 mm" in run.messages("screw-length")[0]
    change(proj_dir, "params", "screw_len", value=1)
    assert "the nearest is 2 mm" in check(proj_dir).messages("screw-length")[0]


def test_stated_screw_length_is_taken_as_stated_and_none_is_fitted_to_the_model(proj_dir, tmp_path):
    add_quote(proj_dir, tmp_path, "Each pin is an M3 screw 11 mm long.", values={"len": 11})
    threaded(proj_dir, spec=M3_SCREW)
    add(proj_dir, params="screw_len: {basis: source, from: N1.len}")
    run = check(proj_dir)
    assert run.status == "VERIFIED" and run.rules == []
    assert run.report["threads"][0]["screw"] == "M3×11"
    # The model is fitted to the screw that is bought, never the screw to the model.
    change(proj_dir, "params", "screw_len", basis="derived", expr="link_H + 3", **{"from": None})
    run = check(proj_dir)
    assert "screw-length" in run.errors and "is derived" in run.messages("screw-length")[0]


def test_unified_screw_is_ordered_in_fractions_of_an_inch(proj_dir):
    threaded(proj_dir, spec=M3_SCREW.replace("M3,", "4-40,"))
    add(proj_dir, params=TEN_LONG.replace("10", "0.375"))
    meta(proj_dir, units={"length": "in"}, tolerance={"length": 1e-5})
    run = check(proj_dir)
    assert run.status == "VERIFIED", run.out
    assert run.report["threads"][0]["screw"] == "#4-40 UNC × 3/8 in"
    change(proj_dir, "params", "screw_len", value=0.3)
    message = check(proj_dir).messages("screw-length")[0]
    assert "(0.3 in)" in message and "the nearest are 1/4 in and 3/8 in" in message
    # A metric screw in a project in inches is still bought in millimetres.
    meta(proj_dir, threads="metric")
    change(proj_dir, "params", "screw", thread="M3")
    change(proj_dir, "params", "screw_len", value=0.3937)
    run = check(proj_dir)
    assert run.status == "VERIFIED" and run.report["threads"][0]["screw"] == "M3×10"


def test_count_check_counts_the_holes_a_thread_is_cut_in(proj_dir, tmp_path):
    threaded(proj_dir)
    add_quote(proj_dir, tmp_path, "Two M3 screws hold each link.", values={"n": "two"})
    add(proj_dir, checks="{id: screws, kind: count, thread: screw, evidence: N1, key: n}")
    run = check(proj_dir)
    screws = run.result("screws")
    assert run.status == "VERIFIED" and screws["ok"], run.out
    assert screws["measured"] == "2 holes or shanks threaded M3×0.5 (screw)"
    assert (screws["rests_on"], screws["rests_on_params"]) == ("proposed", ["screw"])
    # A clearance hole carries no thread, so it is not one of them.
    remodel(proj_dir, '"link.b": "screw"', '"link.side": "screw"')
    assert "model-thread" in check(proj_dir).errors
    remodel(proj_dir, ', "link.side": "screw"', "")
    run = check(proj_dir)
    assert run.errors == ["check-failed"] and run.result("screws")["measured"].startswith("1 hole ")


def test_thread_declared_on_the_axis_of_a_hole_in_a_boss_is_the_holes(proj_dir):
    # A screw boss: the hole and the boss around it share one axis, and the thread fits one.
    threaded(proj_dir)
    boss = "Cylinder(p.screw, p.link_H) - Cylinder(p.screw.tap / 2, p.link_H)"
    remodel(proj_dir, '{"link": link}', f'{{"link": link, "post": {boss}}}')
    remodel(proj_dir, '"link.b": "screw"', '"link.b": "screw", "post.axis": "screw"')
    remodel(proj_dir, '"link.top":', '"post.axis": (0, 0, 0),\n        "link.top":')
    run = check(proj_dir)
    assert run.status == "VERIFIED" and run.rules == [], run.out
    assert run.report["threads"][0]["threaded"] == ["link.a", "link.b", "post.axis"]


def test_report_counts_a_threads_holes_across_the_assembly(proj_dir):
    threaded(proj_dir)
    stack(proj_dir, 2)
    assert "| screw | M3×0.5 | proposed | link ×4 |  |" in check(proj_dir).md


def test_two_parts_built_as_one_shape_each_declare_their_own_holes(proj_dir):
    threaded(proj_dir)
    remodel(proj_dir, '"parts": {"link": link}', '"parts": {"link": link, "twin": link}')
    remodel(proj_dir, '"link.b": "screw"', '"link.b": "screw", "twin.a": "screw"')
    remodel(
        proj_dir,
        '"link.a": (-p.pitch / 2, 0, 0),',
        '"link.a": (-p.pitch / 2, 0, 0),\n        "twin.a": (-p.pitch / 2, 0, 0),',
    )
    run = check(proj_dir)
    assert run.status == "VERIFIED", run.out
    assert run.report["threads"][0]["threaded"] == ["link.a", "link.b", "twin.a"]


def test_declared_clearance_hole_may_be_any_its_table_gives_as_a_released_bodys_is(proj_dir):
    # The authors drew their M3 holes Ø3.5: between the normal 3.4 and the loosest, 3.6.
    threaded(proj_dir, "clearance")
    add(proj_dir, params="wide: {basis: proposed, value: 3.5, rationale: as released, gap: G1}")
    remodel(proj_dir, "p.screw.clearance", "p.wide")
    run = check(proj_dir)
    assert run.status == "VERIFIED" and run.report["threads"][0]["clearance"] == [
        "link.a",
        "link.b",
    ]
    change(proj_dir, "params", "wide", value=3.7)
    assert check(proj_dir).errors == ["model-thread", "model-thread"]
