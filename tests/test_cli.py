"""The commands as an agent runs them: init, source, text, figures, crop, coverage, and the
statuses and report files `cadrev check` ends on."""

import json
import subprocess

import pytest
import yaml
from conftest import (
    PAPER,
    REFUSED,
    add,
    add_line,
    add_reading,
    add_source,
    cadrev,
    change,
    check,
    docx,
    edit,
    meta,
    pdf,
    png,
    register,
    released,
    sha256,
    write,
)

PAGES = ["Table 1. Dimensions\nLink 40x8x5", "The pivot holes are spaced 30 mm apart."]
# A saved datasheet page: markup, a style, a script, an entity and a table row.
DATASHEET = (
    "<html><head><title>Servo 5 mm</title><style>td{width:32px}</style><script>var w=32;</script>"
    "</head><body><p>Servo &amp; horn</p><table><tr><td>Weight</td><td>20.6 g</td></tr></table>"
    "</body></html>"
)


def test_init_scaffolds_a_project_short_only_of_its_target(tmp_path):
    root = tmp_path / "gripper"
    assert cadrev("init", root, "--name", "claw")[0] == 0
    assert yaml.safe_load((root / "project.yaml").read_text())["name"] == "claw"
    run = check(root)
    assert (run.status, run.rules) == ("NOT VERIFIED", ["target"])
    code, out = cadrev("init", root)
    assert code == 1 and "not empty" in out


def test_source_copies_the_file_pins_its_hash_and_lists_it_last(proj_dir, tmp_path):
    before = (proj_dir / "project.yaml").read_text().split("sources:")[0]
    notes = tmp_path / "notes.md"
    notes.write_text("No dimensions.\n")
    register(proj_dir, notes, "notes", "other", "--url", "https://x.org/n", "--rename", "n.md")
    text = (proj_dir / "project.yaml").read_text()
    # Everything above the sources block stays as written, comments included.
    assert text.startswith(before) and "# Reconstruction project" in before
    assert yaml.safe_load(text)["sources"][-1] == {
        "id": "notes",
        "kind": "other",
        "path": "sources/n.md",
        "sha256": sha256(notes),
        "citation": "Doe 2026, notes",
        "url": "https://x.org/n",
    }
    assert (proj_dir / "sources" / "n.md").read_text() == "No dimensions.\n"
    assert check(proj_dir).status == "VERIFIED"


def test_registering_an_id_again_refreshes_its_entry_and_keeps_its_other_keys(proj_dir, tmp_path):
    change(proj_dir, "sources", "paper", url="https://doi.org/x")
    # A clone lacks any source the user keeps out of git: the finding says where to get it.
    (proj_dir / "sources" / "paper.txt").unlink()
    assert "download from https://doi.org/x" in check(proj_dir).messages("source-missing")[0]
    paper = tmp_path / "paper.txt"
    paper.write_text(PAPER + "Received 1 March.\n")
    register(proj_dir, paper, "paper", "supplement")
    (entry,) = yaml.safe_load((proj_dir / "project.yaml").read_text())["sources"]
    assert entry["sha256"] == sha256(paper) and entry["kind"] == "supplement"
    assert entry["url"] == "https://doi.org/x"
    assert check(proj_dir).status == "VERIFIED"


def test_source_rewrites_a_sources_list_however_it_was_written(proj_dir, tmp_path):
    meta = proj_dir / "project.yaml"
    entries = yaml.safe_load(meta.read_text())["sources"]
    flow = "sources: [\n  " + json.dumps(entries[0]) + "\n]\n# kept\nname: demo\n"
    write(proj_dir, "project.yaml", meta.read_text().split("sources:")[0] + flow)
    notes = tmp_path / "notes.md"
    notes.write_text("No dimensions.\n")
    register(proj_dir, notes, "notes", "other")
    text = meta.read_text()
    assert [s["id"] for s in yaml.safe_load(text)["sources"]] == ["paper", "notes"]
    assert "# kept\nname: demo\n" in text and check(proj_dir).status == "VERIFIED"


def test_every_registered_source_is_committed(proj_dir, tmp_path):
    notes = tmp_path / "field notes.md"
    notes.write_text("No dimensions.\n")
    register(proj_dir, notes, "notes", "other")
    subprocess.run(["git", "init", "-q", str(proj_dir)], check=True)
    for path in ("sources/field notes.md", "sources/paper.txt"):
        assert subprocess.run(["git", "-C", str(proj_dir), "check-ignore", "-q", path]).returncode
    with pytest.raises(SystemExit):  # nor does cadrev source take a licence
        register(proj_dir, notes, "notes", "other", "--license", "MIT")


@pytest.mark.parametrize("what", ["no file", "no project", "a project.yaml that does not parse"])
def test_source_refuses_what_it_cannot_register(proj_dir, tmp_path, what):
    before = (proj_dir / "project.yaml").read_text()
    file = tmp_path / ("paper.txt" if what != "no file" else "gone.txt")
    if what == "a project.yaml that does not parse":
        before += "  - [unclosed\n"
        write(proj_dir, "project.yaml", before)
    root = tmp_path / "elsewhere" if what == "no project" else proj_dir
    code, _ = cadrev("source", root, file, "--id", "x", "--kind", "paper", "--citation", "c")
    assert code == 1 and (proj_dir / "project.yaml").read_text() == before


def test_text_prints_each_page_as_the_quote_matcher_reads_it(proj_dir, tmp_path):
    assert cadrev("text", proj_dir, "paper") == (0, f"===== paper page 1/1 =====\n{PAPER}\n")
    add_source(proj_dir, tmp_path, "paper.pdf", pdf(PAGES))
    code, out = cadrev("text", proj_dir, "doc")
    assert code == 0 and f"===== doc page 1/2 =====\n{PAGES[0]}" in out
    assert "===== doc page 2/2 =====" in out and "spaced 30 mm apart" in out
    assert cadrev("text", proj_dir, "doc", "--page", 1)[1].count("=====") == 2
    assert cadrev("text", proj_dir, "doc", "--grep", "MM APART")[1] == f"p2: {PAGES[1]}\n"


# A source file's name, its content, and the text cadrev reads from it.
FORMATS = {
    "paper.docx": (docx(PAPER), PAPER),
    "ds.html": (DATASHEET, "Servo & horn\nWeight\n20.6 g\n"),
    "ds.md": (DATASHEET, DATASHEET + "\n"),
}


@pytest.mark.parametrize("name", FORMATS)
def test_text_reads_each_text_format(proj_dir, tmp_path, name):
    content, text = FORMATS[name]
    add_source(proj_dir, tmp_path, name, content)
    assert cadrev("text", proj_dir, "doc") == (0, f"===== doc page 1/1 =====\n{text}")


def test_text_refuses_a_source_that_is_none_or_holds_no_text(proj_dir, tmp_path):
    released(proj_dir, tmp_path)
    code, out = cadrev("text", proj_dir, "nowhere")
    assert code == 1 and "paper" in out and "link_step" in out  # the sources it could read
    code, out = cadrev("text", proj_dir, "link_step")
    assert code == 1 and "not a text source" in out


FIGURES = {
    "paper.pdf": (pdf(PAGES, image=True), "figures/doc/p001_01.png  2 x 2 px"),
    "paper.docx": (docx(PAPER, png((4, 2))), "figures/doc/image1.png  4 x 2 px"),
}


@pytest.mark.parametrize("name", FIGURES)
def test_figures_extracts_a_sources_images_and_prints_each_ones_pixel_size(
    proj_dir, tmp_path, name
):
    content, written = FIGURES[name]
    add_source(proj_dir, tmp_path, name, content)
    assert cadrev("figures", proj_dir, "doc") == (0, written + "\n")
    assert (proj_dir / written.split()[0]).is_file()


def test_crop_writes_the_region_and_prints_the_hash_evidence_pins(proj_dir):
    from PIL import Image

    (proj_dir / "figures").mkdir()
    (proj_dir / "figures" / "page.png").write_bytes(png((40, 20)))
    crop = ("crop", proj_dir, "figures/page.png", 4, 2, 24, 12)
    code, out = cadrev(*crop, "--name", "label", "--zoom", 3)
    target = proj_dir / "figures" / "crops" / "label.png"
    assert code == 0 and Image.open(target).size == (60, 30)
    assert "40 x 20 px" in out and "image: figures/crops/label.png" in out
    assert f"image_sha256: {sha256(target)}" in out


def test_coverage_lists_each_unledgered_quantity_and_exits_by_whether_there_is_one(proj_dir):
    assert cadrev("coverage", proj_dir) == (0, "0 unledgered stated quantities\n")
    edit(proj_dir, "evidence.yaml", lambda d: d.pop("skipped"))
    code, out = cadrev("coverage", proj_dir)
    lines = out.splitlines()
    assert code == 1 and lines[-1] == "1 unledgered stated quantities"
    assert lines[0].startswith("paper p1: 60 mm") and "branches of 60 mm diameter" in lines[0]


def _confirmed(root):
    add_reading(root, confirmed_by="A. Reviewer")


def _broken(root):
    add_line(root, "extra = 7.5")


EARNED = {
    "as built": ("VERIFIED", lambda r: None, ()),
    "with a proposed param and a warning": ("VERIFIED", lambda r: add(r, gaps="{id: G2}"), ()),
    "a reading a named human confirmed": ("VERIFIED", _confirmed, ()),
    "a reading awaiting confirmation": ("VERIFIED PENDING REVIEW", add_reading, ()),
    "an error": ("NOT VERIFIED", _broken, ()),
    "an error beside an unconfirmed reading": (
        "NOT VERIFIED",
        lambda r: (add_reading(r), _broken(r)),
        (),
    ),
    "without the build": ("PARTIAL", lambda r: None, ("--no-build",)),
    "without the coverage sweep": ("PARTIAL", lambda r: None, ("--no-coverage",)),
    "without the build, whatever is wrong": ("PARTIAL", _broken, ("--no-build",)),
}


@pytest.mark.parametrize("case", EARNED)
def test_check_ends_on_the_status_the_project_has_earned(proj_dir, case):
    # check() holds the exit code to the status: 0 for the two VERIFIED ones, else 1.
    status, arrange, flags = EARNED[case]
    arrange(proj_dir)
    run = check(proj_dir, *flags)
    assert run.status == status
    # A partial run makes no claim, so it writes nothing.
    assert (proj_dir / "build").exists() == (run.status != "PARTIAL")


def test_partial_run_leaves_an_earlier_report_as_it_was(proj_dir):
    check(proj_dir)
    before = {f: f.read_bytes() for f in (proj_dir / "build").rglob("*") if f.is_file()}
    add_line(proj_dir, "extra = 7.5")
    run = check(proj_dir, "--no-build")
    assert "model-literal" in run.errors and "no report was written" in run.out
    assert {f: f.read_bytes() for f in (proj_dir / "build").rglob("*") if f.is_file()} == before


@pytest.mark.parametrize("command", ["check", "coverage", "text", "figures", "source"])
@pytest.mark.parametrize("refusal", ["project-missing", "format-missing", "format-unknown"])
def test_every_command_refuses_a_project_it_cannot_read_and_writes_nothing(
    proj_dir, tmp_path, command, refusal
):
    if refusal == "project-missing":
        (proj_dir / "project.yaml").unlink()
    else:
        meta(proj_dir, format=None if refusal == "format-missing" else 7)
    before = {f: f.read_bytes() for f in proj_dir.rglob("*") if f.is_file()}
    args = {"text": ["paper"], "figures": ["paper"]}.get(command, [])
    if command == "source":
        args = [tmp_path / "paper.txt", "--id", "new", "--kind", "paper", "--citation", "c"]
    code, out = cadrev(command, proj_dir, *args)
    assert code == 1 and (refusal in out or command == "source" and "not found" in out)
    assert (REFUSED in out) == (command == "check")
    assert {f: f.read_bytes() for f in proj_dir.rglob("*") if f.is_file()} == before


def test_check_prints_each_finding_then_the_status_line_with_its_counts(proj_dir):
    add(proj_dir, gaps="{id: G2}")
    change(proj_dir, "checks", "pitch", tol=1.51)
    lines = check(proj_dir).out.splitlines()
    assert sorted(line.split("]")[0] for line in lines[2:4]) == [
        "error: [tolerance-cap",
        "warning: [gap-unused",
    ]
    assert lines[-1] == (
        "NOT VERIFIED: 1 errors, 1 warnings, 5/5 checks pass. Report: build/report.md"
    )
    for written in ("parts/link.step", "assembly.step", "report.md", "report.json"):
        assert (proj_dir / "build" / written).is_file()


REPORT_KEYS = {
    "status", "exact", "known_first", "waiting", "counts", "findings", "checks", "tolerances",
    "overlap_limits", "motion", "masses", "model_literals", "params", "bases",
    "rests_on_proposed", "measured", "awaiting_confirmation", "probes",
}  # fmt: skip


def test_report_json_holds_the_run_as_data(proj_dir):
    add(proj_dir, gaps="{id: G2}")
    change(proj_dir, "checks", "pitch", tol=1.51)
    report = check(proj_dir).report
    assert set(report) == REPORT_KEYS
    assert report["counts"] == {
        "errors": 1,
        "warnings": 1,
        "checks": 5,
        "checks_passed": 5,
        "params": 5,
        "source": 4,
        "measured": 0,
        "proposed": 1,
        "physics_proposed": 0,
    }
    assert [(f["level"], f["rule"]) for f in report["findings"]] == [
        ("error", "tolerance-cap"),
        ("warning", "gap-unused"),
    ]
    assert all(set(f) == {"level", "rule", "message"} for f in report["findings"])
    assert [(c["id"], c["kind"], c["ok"]) for c in report["checks"]] == [
        ("env.L", "bbox", True),
        ("env.H", "bbox", True),
        ("env.W", "bbox", True),
        ("pitch", "distance", True),
        ("clear", "interference", True),
    ]
    assert report["checks"][3] | {"measured": "", "expected": ""} == {
        "id": "pitch",
        "kind": "distance",
        "ok": True,
        "expected": "",
        "measured": "",
        "note": "",
        "rests_on": "source",
        "rests_on_params": [],
    }
    assert report["tolerances"] == [{"check": "pitch", "kind": "distance", "tol": 1.51}]
    assert report["params"]["pitch"] == {
        "value": 30.0,
        "rests_on": "source",
        "basis": "source",
        "from": "pitch.pitch",
    }
    assert report["bases"] == {"source": 4, "proposed": 1}
    assert report["rests_on_proposed"] == ["hole_d"]
    assert (report["exact"], report["known_first"], report["waiting"]) == (False, False, None)
    assert report["motion"] == {
        "joints": {},
        "loops": {},
        "gears": {},
        "tendons": {},
        "cables": {},
        "coarsened": {},
        "dropped": False,
    }
    assert (report["masses"], report["model_literals"], report["probes"]) == ({}, None, [])


def test_report_md_renders_what_report_json_holds(proj_dir):
    add(proj_dir, gaps="{id: G2}", conflicts="{id: K1, evidence: [pitch], summary: two pitches}")
    change(proj_dir, "checks", "pitch", tol=1.51, interpretation="hole axis to hole axis")
    add_reading(proj_dir)
    run = check(proj_dir)
    report, md = run.report, run.md
    counts = report["counts"]
    assert f"**{report['status']}**: {counts['errors']} errors, {counts['warnings']} warnings" in md
    for f in report["findings"]:
        assert f"- **{f['level']}** `{f['rule']}`: {f['message']}" in md
    for c in report["checks"]:
        assert f"| {c['id']} | pass | {c['expected']} | {c['measured']} |" in md
    assert "hole axis to hole axis" in md and "| pitch | distance | tol 1.51 |" in md
    for name, spec in report["params"].items():
        assert f"| {name} | {spec['value']:g} | {spec['basis']} |" in md
    assert "| G1 | pin diameter? | authors | hole_d |" in md
    assert "| K1 | pitch | two pitches | **open** |" in md
    assert "**Static**" in md and "## Figure readings awaiting human confirmation" in md
    assert "![F2](../figures/crops/fig2.png)" in md
