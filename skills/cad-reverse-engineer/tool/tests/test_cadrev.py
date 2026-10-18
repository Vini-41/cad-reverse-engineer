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
