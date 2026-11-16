"""Threads: a thread param named from the ISO metric or the Unified table, the plain holes and
shanks model.py declares for it, and what the report says of them."""

import pytest
from conftest import ASSEMBLY, add, add_quote, change, check, edit, meta, remodel

M3 = "screw: {basis: proposed, thread: M3, rationale: the pins are M3 screws, gap: G1}"


def threaded(root, size: str = "tap", spec: str = M3) -> None:
    """The link with both holes sized by a thread param, in place of hole_d, and declared for
    it: at its tap drill, or at its clearance hole."""
    edit(root, "params.yaml", lambda d: d["params"].pop("hole_d"))
    add(root, params=spec)
    remodel(root, "p.hole_d", f"p.screw.{size}")
    remodel(
        root, ASSEMBLY, ASSEMBLY + '\n        "threads": {"link.a": "screw", "link.b": "screw"},'
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
    meta(proj_dir, units={"length": "in"}, tolerance={"length": 1e-5})
    run = check(proj_dir)
    assert run.status == "VERIFIED"
    assert run.report["params"]["screw"]["value"] == pytest.approx(3 / 25.4)


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
