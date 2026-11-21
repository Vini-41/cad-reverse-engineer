"""What a reviewer looks at first: the isometric view of the assembly, a drawing of each part
dimensioned by its checks, and the report that shows each part's checks under its drawing."""

import numpy as np
import pytest
from build123d import import_step
from conftest import ASSEMBLY, add_quote, change, check, meta, remodel
from PIL import Image


def inked(path, colour: str) -> int:
    """How many pixels of a drawing are drawn in a colour: blue, red, grey, or the grey of what
    a step's view shows as already placed."""
    r, g, b = (np.asarray(Image.open(path).convert("RGB")).astype(int)[:, :, i] for i in range(3))
    spread = np.maximum(np.maximum(r, g), b) - np.minimum(np.minimum(r, g), b)
    drawn = {
        "blue": (b > 140) & (r < 90),
        "red": (r > 170) & (g < 90) & (b < 90),
        "grey": (spread < 12) & (r > 90) & (r < 135),
        # What a step's view shows as already there: lighter than a reference dimension.
        "placed": (spread < 12) & (r >= 135) & (r < 150),
    }
    return int(drawn[colour].sum())


def test_check_writes_the_isometric_view_and_a_drawing_of_each_part(proj_dir):
    run = check(proj_dir)
    build = proj_dir / "build"
    assert run.report["drawings"] == ["isometric.png", "drawings/link.png"]
    assert all((build / name).stat().st_size > 5000 for name in run.report["drawings"])
    assert "wrote build/drawings/: 1 part drawing\nwrote build/isometric.png\n" in run.out
    # The report opens on the object, and shows each part's drawing over its own checks.
    md = run.md
    assert md.index("![isometric](isometric.png)") < md.index("**VERIFIED**")
    order = ["## Parts", "### link", "![link](drawings/link.png)", "| env.L |", "| pitch |"]
    order += ["## Assembly", "| clear |"]
    assert [md.index(mark) for mark in order] == sorted(md.index(mark) for mark in order)
    parts = {c["id"]: c.get("part") for c in run.report["checks"]}
    assert parts == {"env.L": "link", "env.H": "link", "env.W": "link", "pitch": "link"} | {
        "clear": None
    }


def test_drawing_dimensions_a_part_by_its_checks_as_built(proj_dir):
    sheet = proj_dir / "build" / "drawings" / "link.png"
    # Every envelope and the pitch are checked: blue, the only grey its title and labels.
    check(proj_dir)
    blue, grey = inked(sheet, "blue"), inked(sheet, "grey")
    assert blue > 500 and inked(sheet, "red") == 0
    # An envelope no check compares is a reference dimension, in grey.
    change(proj_dir, "checks", "env", axes={"L": "x"})
    check(proj_dir)
    assert inked(sheet, "grey") > grey + 100 and inked(sheet, "blue") < blue
    # A check that fails is drawn red, at the value the part was built to.
    change(proj_dir, "params", "pitch", basis="proposed", value=28, rationale="r", gap="G1")
    assert "check-failed" in check(proj_dir).errors
    assert inked(sheet, "red") > 100


def test_drawing_prints_a_range_check_at_the_value_as_built(proj_dir, tmp_path):
    sheet = proj_dir / "build" / "drawings" / "link.png"
    check(proj_dir)
    against_one_value = np.asarray(Image.open(sheet).convert("RGB"))
    text = "Pitch 29.5 mm MIN, 30.5 mm MAX, or 29.8 mm MAX."
    add_quote(proj_dir, tmp_path, text, values={"low": 29.5, "high": 30.5, "under": 29.8})
    change(proj_dir, "checks", "pitch", evidence=None, key=None, min="N1.low", max="N1.high")
    check(proj_dir)
    assert np.array_equal(np.asarray(Image.open(sheet).convert("RGB")), against_one_value)
    # Outside its range it is drawn red, still at the value the part was built to.
    change(proj_dir, "checks", "pitch", min=None, max="N1.under")
    assert "check-failed" in check(proj_dir).errors
    assert inked(sheet, "red") > 100


def test_part_that_is_no_solid_gets_its_finding_and_no_drawing(proj_dir):
    remodel(proj_dir, '{"link": link}', '{"link": link - link}')
    run = check(proj_dir)
    assert "part-invalid" in run.errors and run.report["drawings"] == []
    assert "![" not in run.md


def test_part_no_instance_places_is_drawn_without_an_isometric_view(proj_dir):
    remodel(proj_dir, ASSEMBLY, '"assembly": {},')
    assert check(proj_dir).report["drawings"] == ["drawings/link.png"]


@pytest.mark.parametrize("unit, mm", [("mm", 1), ("in", 25.4), ("cm", 10), ("thou", 0.0254)])
def test_step_files_hold_the_object_at_its_true_size_whatever_the_length_unit(proj_dir, unit, mm):
    # Table 1 prints no unit, so its 40 is 40 in in a project in inches: 1016 mm to a CAD program.
    meta(proj_dir, units={"length": unit})
    check(proj_dir)
    for name in ("parts/link.step", "assembly.step"):
        size = import_step(proj_dir / "build" / name).bounding_box().size
        assert tuple(size) == pytest.approx((40 * mm, 5 * mm, 8 * mm), rel=1e-4), name
