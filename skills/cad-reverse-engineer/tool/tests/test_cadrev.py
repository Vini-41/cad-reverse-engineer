import json
from pathlib import Path

import pytest
import yaml

from cadrev import cli, sources

PAPER = """\
Table 1. Dimensions of key components
Name L×H×W (mm×mm×mm)
Link 40×8×5
The pivot holes of the link are spaced 30 mm apart.
Tests used branches of 60 mm diameter.
"""

MODEL = '''\
from build123d import *


def build(p):
    link = Box(p.link_L, p.link_W, p.link_H)
    link -= Pos(-p.pitch / 2, 0, 0) * Cylinder(p.hole_d / 2, p.link_H)
    link -= Pos(p.pitch / 2, 0, 0) * Cylinder(p.hole_d / 2, p.link_H)
    return {
        "parts": {"link": link},
        "datums": {"link.a": (-p.pitch / 2, 0, 0), "link.b": (p.pitch / 2, 0, 0)},
        "assembly": {"link_1": ("link", Location())},
    }
'''


def write(root: Path, name: str, data) -> None:
    (root / name).write_text(yaml.safe_dump(data, sort_keys=False) if not isinstance(data, str) else data)


@pytest.fixture
def proj_dir(tmp_path):
    root = tmp_path / "demo"
    assert cli.main(["init", str(root)]) == 0
    meta = root / "project.yaml"
    meta.write_text(meta.read_text().replace("TODO one sentence", "A demo link,"))
    paper = tmp_path / "paper.txt"
    paper.write_text(PAPER)
    assert cli.main(["source", str(root), str(paper), "--id", "paper", "--kind", "paper",
                     "--citation", "Doe 2026"]) == 0
    write(root, "evidence.yaml", {
        "evidence": [
            {"id": "T1-link", "source": "paper", "locator": "Table 1",
             "quote": "Link 40×8×5", "values": {"L": 40, "H": 8, "W": 5}},
            {"id": "pitch", "source": "paper", "locator": "Sec. 2",
             "quote": "spaced 30 mm apart", "values": {"pitch": 30}},
        ],
        "skipped": [{"source": "paper", "quote": "branches of 60 mm diameter",
                     "reason": "test condition"}],
        "conflicts": [],
    })
    write(root, "params.yaml", {"params": {
        "link_L": {"basis": "source", "from": "T1-link.L", "interpretation": "envelope along X"},
        "link_H": {"basis": "source", "from": "T1-link.H"},
        "link_W": {"basis": "source", "from": "T1-link.W"},
        "pitch": {"basis": "source", "from": "pitch.pitch"},
        "hole_d": {"basis": "proposed", "value": 3, "rationale": "M3 pin", "gap": "G1"},
    }})
    write(root, "gaps.yaml", {"gaps": [{"id": "G1", "question": "pin diameter?", "ask": "authors"}]})
    write(root, "checks.yaml", {"checks": [
        {"id": "env", "kind": "bbox", "part": "link", "evidence": "T1-link",
         "axes": {"L": "x", "H": "z", "W": "y"}},
        {"id": "pitch", "kind": "distance", "between": ["link.a", "link.b"],
         "evidence": "pitch", "key": "pitch"},
        {"id": "clear", "kind": "interference"},
    ]})
    write(root, "model.py", MODEL)
    return root


def verify(root: Path, *flags: str) -> tuple[int, dict]:
    """Run a verification run through the CLI; return its exit code and report.json."""
    code = cli.main(["check", str(root), *flags])
    return code, json.loads((root / "build" / "report.json").read_text())


def errors(root: Path) -> list[str]:
    _, report = verify(root)
    return [f["rule"] for f in report["findings"] if f["level"] == "error"]


def test_report_json_carries_status_findings_and_counts(proj_dir):
    code, report = verify(proj_dir)
    assert code == 0
    assert report["status"] == "VERIFIED"
    assert all(set(f) == {"level", "rule", "message"} for f in report["findings"])
    assert report["counts"] == {"errors": 0, "warnings": len(report["findings"]),
                                "checks": 5, "checks_passed": 5,
                                "params": 5, "traced": 4, "proposed": 1}


def test_report_json_lists_each_finding_with_level_rule_and_message(proj_dir):
    write(proj_dir, "gaps.yaml", {"gaps": []})
    code, report = verify(proj_dir)
    assert code == 1
    assert report["status"] == "NOT VERIFIED"
    assert {"level": "error", "rule": "param-gap",
            "message": "param hole_d: unknown gap 'G1'"} in report["findings"]
    assert report["counts"]["errors"] == 1


def test_report_md_renders_the_status_and_findings_of_report_json(proj_dir):
    write(proj_dir, "gaps.yaml", {"gaps": []})
    _, report = verify(proj_dir)
    md = (proj_dir / "build" / "report.md").read_text()
    assert f"**{report['status']}**" in md
    for f in report["findings"]:
        assert f"- **{f['level']}** `{f['rule']}`: {f['message']}" in md


@pytest.mark.parametrize("flag", ["--no-build", "--no-coverage"])
def test_skipping_part_of_the_run_is_partial_and_writes_no_report(proj_dir, capsys, flag):
    report_md, report_json = proj_dir / "build" / "report.md", proj_dir / "build" / "report.json"
    assert cli.main(["check", str(proj_dir), flag]) != 0
    assert "PARTIAL" in capsys.readouterr().out
    assert not report_md.exists() and not report_json.exists()


@pytest.mark.parametrize("flag", ["--no-build", "--no-coverage"])
def test_partial_run_leaves_the_existing_report_untouched(proj_dir, flag):
    def build_dir() -> dict[str, bytes]:
        return {str(f): f.read_bytes() for f in (proj_dir / "build").rglob("*") if f.is_file()}

    verify(proj_dir)
    before = build_dir()
    write(proj_dir, "gaps.yaml", {"gaps": []})
    assert cli.main(["check", str(proj_dir), flag]) != 0
    assert build_dir() == before


def test_normalize_matches_layout_variants():
    assert sources.normalize("Bent Link-\nage 37 × 6.5×5") == "bent linkage 37x6.5x5"
    assert sources.numbers_in("40×8×5 mm") == [40, 8, 5]


def test_complete_project_verifies(proj_dir):
    assert cli.main(["check", str(proj_dir)]) == 0
    assert (proj_dir / "build" / "parts" / "link.step").exists()
    assert (proj_dir / "build" / "assembly.step").exists()
    assert "**VERIFIED**" in (proj_dir / "build" / "report.md").read_text()


def test_misquote_is_caught(proj_dir):
    data = yaml.safe_load((proj_dir / "evidence.yaml").read_text())
    data["evidence"][0]["quote"] = "Link 42×8×5"
    write(proj_dir, "evidence.yaml", data)
    assert "quote-not-found" in errors(proj_dir)


def test_value_must_appear_in_quote(proj_dir):
    data = yaml.safe_load((proj_dir / "evidence.yaml").read_text())
    data["evidence"][0]["values"]["L"] = 41
    write(proj_dir, "evidence.yaml", data)
    assert "value-not-in-quote" in errors(proj_dir)


def test_source_tampering_is_caught(proj_dir):
    (proj_dir / "sources" / "paper.txt").write_text(PAPER.replace("40", "45"))
    sources.pages.cache_clear()
    assert "source-hash" in errors(proj_dir)


def test_model_literal_is_rejected(proj_dir):
    write(proj_dir, "model.py", MODEL.replace("p.link_H)\n    link -=", "7.5)\n    link -=", 1))
    assert "model-literal" in errors(proj_dir)


def test_unledgered_dimension_is_reported(proj_dir):
    data = yaml.safe_load((proj_dir / "evidence.yaml").read_text())
    data["skipped"] = []
    write(proj_dir, "evidence.yaml", data)
    assert "coverage" in errors(proj_dir)


def test_unaccounted_evidence_is_reported(proj_dir):
    data = yaml.safe_load((proj_dir / "evidence.yaml").read_text())
    data["evidence"].append({"id": "extra", "source": "paper", "locator": "Sec. 3",
                             "quote": "branches of 60 mm diameter", "values": {"d": 60}})
    write(proj_dir, "evidence.yaml", data)
    assert "evidence-unused" in errors(proj_dir)


def test_geometry_that_misses_the_paper_fails(proj_dir):
    write(proj_dir, "model.py", MODEL.replace("Box(p.link_L,", "Box(p.link_L + p.hole_d,"))
    assert cli.main(["check", str(proj_dir)]) == 1
    report = (proj_dir / "build" / "report.json").read_text()
    assert "check-failed" in report


def test_derived_param_must_match_its_expression(proj_dir):
    data = yaml.safe_load((proj_dir / "params.yaml").read_text())
    data["params"]["half_pitch"] = {"basis": "derived", "expr": "pitch / 2", "value": 14}
    write(proj_dir, "params.yaml", data)
    assert "param-mismatch" in errors(proj_dir)


def test_figure_evidence_needs_pinned_crop(proj_dir):
    crop = proj_dir / "figures" / "crops" / "fig2.png"
    crop.parent.mkdir(parents=True)
    crop.write_bytes(b"not really a png")
    data = yaml.safe_load((proj_dir / "evidence.yaml").read_text())
    data["evidence"].append({"id": "F2", "source": "paper", "locator": "Fig. 2", "scope": "context",
                             "reason": "label", "image": "figures/crops/fig2.png",
                             "image_sha256": "0" * 64, "reading": "70 mm"})
    write(proj_dir, "evidence.yaml", data)
    assert "image-hash" in errors(proj_dir)


def test_overlay_renders_against_a_figure(proj_dir):
    from PIL import Image

    (proj_dir / "figures").mkdir(exist_ok=True)
    Image.new("RGB", (400, 200), "white").save(proj_dir / "figures" / "fig.png")
    write(proj_dir, "overlays.yaml", {"overlays": [{
        "id": "front", "image": "figures/fig.png", "part": "link", "view": "front",
        "origin": [200, 100], "calibration": {"pixels": [[50, 150], [350, 150]], "evidence": "pitch.pitch"},
    }]})
    assert cli.main(["check", str(proj_dir)]) == 0
    assert (proj_dir / "build" / "overlays" / "front.png").exists()
    assert "overlays/front.png" in (proj_dir / "build" / "report.md").read_text()


# Named findings, never tracebacks.

def findings(root: Path, rule: str) -> list[str]:
    """Messages of every report.json finding with this rule, from a fresh verification run."""
    _, report = verify(root)
    return [f["message"] for f in report["findings"] if f["rule"] == rule]


def edit(root: Path, name: str, change) -> None:
    data = yaml.safe_load((root / name).read_text())
    change(data)
    write(root, name, data)


@pytest.mark.parametrize("name", ["project.yaml", "evidence.yaml", "params.yaml", "checks.yaml",
                                  "gaps.yaml", "overlays.yaml"])
def test_malformed_yaml_is_a_finding_naming_the_file_and_line(proj_dir, name):
    write(proj_dir, name, "items:\n  - id: a\n    quote: [unclosed\n")
    code, report = verify(proj_dir)
    assert code == 1 and report["status"] == "NOT VERIFIED"
    messages = [f["message"] for f in report["findings"] if f["rule"] == "yaml-syntax"]
    assert len(messages) == 1
    assert messages[0].startswith(f"{name} line ")


def test_wellformed_yaml_raises_no_syntax_finding(proj_dir):
    assert findings(proj_dir, "yaml-syntax") == []


@pytest.mark.parametrize("missing", ["file", "directory"])
def test_missing_project_file_is_a_finding_and_writes_nothing(tmp_path, capsys, missing):
    root = tmp_path / "empty"
    if missing == "file":
        root.mkdir()
    assert cli.main(["check", str(root)]) == 1
    captured = capsys.readouterr()
    assert "[project-missing]" in captured.out
    assert "Traceback" not in captured.out + captured.err
    assert not (root / "build").exists()


def test_present_project_file_raises_no_missing_finding(proj_dir):
    assert findings(proj_dir, "project-missing") == []


def test_evidence_item_without_id_is_a_finding(proj_dir):
    edit(proj_dir, "evidence.yaml", lambda d: d["evidence"][1].pop("id"))
    assert findings(proj_dir, "schema") == ["evidence.yaml evidence[1]: id is required"]


@pytest.mark.parametrize("name, change, where", [
    ("params.yaml", lambda d: d.update(params=[{"link_L": 40}]), "params.yaml params:"),
    ("params.yaml", lambda d: d["params"].update(link_L=40), "params.yaml params.link_L:"),
    ("evidence.yaml", lambda d: d["evidence"][0]["values"].update(L="forty"),
     "evidence.yaml evidence[0].values.L:"),
    ("project.yaml", lambda d: d.update(sources=3), "project.yaml sources:"),
])
def test_wrongly_typed_entry_is_a_finding_naming_where(proj_dir, name, change, where):
    edit(proj_dir, name, change)
    messages = findings(proj_dir, "schema")
    assert len(messages) == 1 and messages[0].startswith(where)


def test_well_shaped_project_raises_no_schema_finding(proj_dir):
    assert findings(proj_dir, "schema") == []


def test_model_syntax_error_is_a_finding(proj_dir):
    write(proj_dir, "model.py", MODEL.replace("def build(p):", "def build(p)"))
    messages = findings(proj_dir, "model-syntax")
    assert len(messages) == 1 and messages[0].startswith("model.py line 4:")


def test_valid_model_raises_no_syntax_finding(proj_dir):
    assert findings(proj_dir, "model-syntax") == []


def test_derived_expr_syntax_error_is_a_finding_and_other_params_still_evaluate(proj_dir):
    def change(d):
        d["params"]["broken"] = {"basis": "derived", "expr": "pitch /"}
        d["params"]["half_pitch"] = {"basis": "derived", "expr": "pitch / 2"}
    edit(proj_dir, "params.yaml", change)
    _, report = verify(proj_dir)
    messages = [f["message"] for f in report["findings"] if f["rule"] == "param-derived"]
    assert len(messages) == 1 and messages[0].startswith("param broken: expr is not valid")
    assert report["params"]["half_pitch"]["value"] == 15


@pytest.mark.parametrize("returned", ["[]", "None", '{"parts": []}', '{"parts": {}, "datums": {"a": 1}}',
                                      '{"parts": {"link": 3}}'])
def test_build_returning_the_wrong_shape_is_a_finding(proj_dir, returned):
    write(proj_dir, "model.py", MODEL.replace("    return {", f"    return {returned}\n    _ = {{", 1))
    code, report = verify(proj_dir)
    assert code == 1
    assert [f["rule"] for f in report["findings"] if f["rule"] == "model-return"] == ["model-return"]


def test_build_returning_the_expected_mapping_raises_no_return_finding(proj_dir):
    assert findings(proj_dir, "model-return") == []


def test_reregistering_a_source_refreshes_its_path_and_hash(proj_dir, tmp_path, capsys):
    paper = tmp_path / "paper-v2.txt"
    paper.write_text(PAPER + "Received 1 March.\n")
    assert cli.main(["source", str(proj_dir), str(paper), "--id", "paper", "--kind", "paper",
                     "--citation", "Doe 2026", "--rename", "paper-v2.txt"]) == 0
    entries = yaml.safe_load((proj_dir / "project.yaml").read_text())["sources"]
    assert [(s["id"], s["path"], s["sha256"]) for s in entries] == [
        ("paper", "sources/paper-v2.txt", sources.sha256(paper))]
    assert "Traceback" not in capsys.readouterr().err
    assert verify(proj_dir)[0] == 0


def test_source_into_a_missing_project_is_an_error_not_a_traceback(tmp_path, capsys):
    paper = tmp_path / "paper.txt"
    paper.write_text(PAPER)
    assert cli.main(["source", str(tmp_path / "nowhere"), str(paper), "--id", "paper",
                     "--kind", "paper", "--citation", "Doe 2026"]) == 1
    err = capsys.readouterr().err
    assert "project.yaml" in err and "Traceback" not in err


def test_param_without_basis_is_a_finding_in_the_report(proj_dir):
    edit(proj_dir, "params.yaml", lambda d: d["params"]["link_L"].pop("basis"))
    assert "param-basis" in errors(proj_dir)


def test_quote_from_a_non_text_source_is_a_finding(proj_dir, tmp_path):
    frame = tmp_path / "frame.png"
    frame.write_bytes(b"png")
    assert cli.main(["source", str(proj_dir), str(frame), "--id", "video", "--kind", "video",
                     "--citation", "Doe 2026 Movie S1"]) == 0
    edit(proj_dir, "evidence.yaml", lambda d: d["evidence"][1].update(source="video"))
    assert "evidence-anchor" in errors(proj_dir)


def test_reregistering_one_source_leaves_the_others_untouched(proj_dir, tmp_path):
    notes = tmp_path / "notes.txt"
    notes.write_text("No dimensions here.\n")
    assert cli.main(["source", str(proj_dir), str(notes), "--id", "notes", "--kind", "other",
                     "--citation", "Doe notes"]) == 0
    before = yaml.safe_load((proj_dir / "project.yaml").read_text())["sources"]
    (proj_dir / "sources" / "paper.txt").write_text(PAPER + "Received 1 March.\n")
    assert cli.main(["source", str(proj_dir), str(proj_dir / "sources" / "paper.txt"), "--id", "paper",
                     "--kind", "paper", "--citation", "Doe 2026"]) == 0
    after = yaml.safe_load((proj_dir / "project.yaml").read_text())["sources"]
    assert after[1] == before[1]
    assert after[0] == {**before[0], "sha256": sources.sha256(proj_dir / "sources" / "paper.txt")}


def _overlay(root: Path, **changes) -> None:
    from PIL import Image

    (root / "figures").mkdir(exist_ok=True)
    Image.new("RGB", (40, 20), "white").save(root / "figures" / "fig.png")
    overlay = {"id": "front", "image": "figures/fig.png", "part": "link", "view": "front",
               "origin": [20, 10], "calibration": {"pixels": [[5, 15], [35, 15]], "evidence": "pitch.pitch"}}
    write(root, "overlays.yaml", {"overlays": [{**overlay, **changes}]})


def _zero_pitch(root: Path) -> None:
    edit(root, "evidence.yaml", lambda d: d["evidence"].append(
        {"id": "zero", "source": "paper", "locator": "Table 1", "quote": "Link 40×8×5",
         "scope": "context", "reason": "test", "values": {"z": 0}}))
    _overlay(root, calibration={"pixels": [[5, 15], [35, 15]], "evidence": "zero.z"})


@pytest.mark.parametrize("damage, rule", [
    (lambda r: edit(r, "params.yaml", lambda d: d["params"].update({1: {"basis": "proposed", "value": 1,
                                                                       "rationale": "x"}})), "schema"),
    (lambda r: _overlay(r, id="a/b"), "overlay-config"),
    (_zero_pitch, "overlay-config"),
    (lambda r: ((r / "model.py").unlink(), (r / "model.py").mkdir()), "model-missing"),
    (lambda r: write(r, "model.py", MODEL.replace("def build(p):", "raise SystemExit(3)\n\ndef build(p):")),
     "model-build"),
    (lambda r: write(r, "model.py", MODEL.replace('{"link": link}', '{"a/b": link}')), "model-return"),
    (lambda r: (r / "sources" / "paper.txt").write_bytes(b"\xff\xfe\x00broken"), "source-hash"),
])
def test_damaged_input_is_a_finding_not_a_crash(proj_dir, damage, rule):
    damage(proj_dir)
    sources.pages.cache_clear()
    code, report = verify(proj_dir)
    assert code == 1 and rule in [f["rule"] for f in report["findings"]]


@pytest.mark.parametrize("name, content", [("paper.pdf", b"%PDF-1.4 not really"),
                                           ("paper.docx", b"PK not a zip")])
def test_unreadable_source_is_a_finding(proj_dir, tmp_path, name, content):
    broken = tmp_path / name
    broken.write_bytes(content)
    assert cli.main(["source", str(proj_dir), str(broken), "--id", "broken", "--kind", "other",
                     "--citation", "Doe"]) == 0
    assert "source-unreadable" in errors(proj_dir)


def test_readable_sources_raise_no_unreadable_finding(proj_dir):
    assert findings(proj_dir, "source-unreadable") == []


def _add_source(root: Path, sid: str, path: str) -> None:
    meta = root / "project.yaml"
    meta.write_text(meta.read_text() + f"  - id: {sid}\n    kind: paper\n    path: {path}\n"
                    "    sha256: x\n    citation: c\n")


def _replace(root: Path, name: str, old: str, new: str) -> None:
    (root / name).write_text((root / name).read_text().replace(old, new))


# Damage that once crashed, or plausibly could crash, a verification run. Add a case for every
# new way project input or user code enters the run.
DAMAGE = {
    "param named by a number": lambda r: edit(r, "params.yaml", lambda d: d["params"].update(
        {7: {"basis": "proposed", "value": 3, "rationale": "x", "gap": "G1"}})),
    "overlay pixels in 3D": lambda r: _overlay(r, calibration={"pixels": [[0, 0, 0], [1, 1, 1]],
                                                               "evidence": "pitch.pitch"}),
    "source path is a directory": lambda r: _add_source(r, "d", "sources"),
    "source path outside the project": lambda r: _add_source(r, "e", "/etc/hosts"),
    "text source not UTF-8": lambda r: ((r / "sources" / "b.txt").write_bytes(b"\xff\xfe 30 mm"),
                                        _add_source(r, "b", "sources/b.txt")),
    "name is a number": lambda r: _replace(r, "project.yaml", "name:", "name: 5\noldname:"),
    "units is a number": lambda r: _replace(r, "project.yaml", "units:", "units: 5\nxunits:"),
    "tolerance of zero": lambda r: _replace(r, "project.yaml", "tolerance:", "tolerance: {length: 0}\nxtolerance:"),
    "model_literals is a number": lambda r: _replace(r, "project.yaml", "name:", "model_literals: 5\nname:"),
    "deeply nested expr": lambda r: edit(r, "params.yaml", lambda d: d["params"].update(
        {"deep": {"basis": "derived", "expr": "(" * 300 + "pitch" + ")" * 300}})),
    "expr overflows": lambda r: edit(r, "params.yaml", lambda d: d["params"].update(
        {"big": {"basis": "derived", "expr": "pitch ** 1000"}})),
    "derived without inputs": lambda r: edit(r, "params.yaml", lambda d: d["params"].update(
        {"q": {"basis": "derived", "expr": "pitch", "value": 30}})),
    "mass check counts not numbers": lambda r: edit(r, "checks.yaml", lambda d: d["checks"].append(
        {"id": "m", "kind": "mass", "density": "pitch", "evidence": "pitch", "key": "pitch",
         "tol_rel": 0.1, "counts": {"link": "x"}})),
    "bbox along an unknown axis": lambda r: edit(r, "checks.yaml", lambda d: d["checks"].append(
        {"id": "q", "kind": "bbox", "part": "link", "evidence": "pitch", "axes": {"pitch": "w"}})),
    "datum of booleans": lambda r: write(r, "model.py", MODEL.replace("(-p.pitch / 2, 0, 0)", "(True, 0, 0)")),
    "part name is a number": lambda r: write(r, "model.py", MODEL.replace('{"link": link}', '{"link": link, 3: link}')),
    "unhashable YAML key": lambda r: write(r, "params.yaml", "params:\n  ? [a, b]\n  : {basis: proposed}\n"),
    "undefined YAML alias": lambda r: write(r, "gaps.yaml", "gaps: *nope\n"),
    "NUL byte in YAML": lambda r: (r / "gaps.yaml").write_bytes(b"gaps: []\x00\n"),
    "file is a top-level list": lambda r: write(r, "params.yaml", "- a\n- b\n"),
    "project file is a directory": lambda r: ((r / "evidence.yaml").unlink(), (r / "evidence.yaml").mkdir()),
    "evidence value keyed by a number": lambda r: edit(r, "evidence.yaml",
                                                       lambda d: d["evidence"][1]["values"].update({3: 30})),
    "skip by from without to": lambda r: edit(r, "evidence.yaml", lambda d: d["skipped"].append(
        {"source": "paper", "from": "Tests", "reason": "r"})),
    "image evidence is a directory": lambda r: edit(r, "evidence.yaml", lambda d: d["evidence"].append(
        {"id": "im", "source": "paper", "locator": "F", "image": "sources", "reading": "3"})),
    "duplicate gap ids": lambda r: write(r, "gaps.yaml", {"gaps": [{"id": "G1"}, {"id": "G1"}]}),
}


@pytest.mark.parametrize("damage", sorted(DAMAGE))
def test_no_damage_escapes_a_verification_run(proj_dir, capsys, damage):
    DAMAGE[damage](proj_dir)
    sources.pages.cache_clear()
    code = cli.main(["check", str(proj_dir)])
    out = capsys.readouterr()
    assert code in (0, 1) and "Traceback" not in out.out + out.err
    assert json.loads((proj_dir / "build" / "report.json").read_text())["status"]
