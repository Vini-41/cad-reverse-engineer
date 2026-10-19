import contextlib
import hashlib
import io
import json
import re
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest
import yaml

from cadrev import cli

PAPER = """\
Table 1. Dimensions of key components
Name L×H×W (mm×mm×mm)
Link 40×8×5
The pivot holes of the link are spaced 30 mm apart.
Tests used branches of 60 mm diameter.
"""

MODEL = """\
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
"""


def write(root: Path, name: str, data) -> None:
    (root / name).write_text(
        yaml.safe_dump(data, sort_keys=False) if not isinstance(data, str) else data
    )


@pytest.fixture
def proj_dir(tmp_path):
    root = tmp_path / "demo"
    assert cli.main(["init", str(root)]) == 0
    meta = root / "project.yaml"
    meta.write_text(meta.read_text().replace("TODO one sentence", "A demo link,"))
    paper = tmp_path / "paper.txt"
    paper.write_text(PAPER)
    assert (
        cli.main(
            [
                "source",
                str(root),
                str(paper),
                "--id",
                "paper",
                "--kind",
                "paper",
                "--citation",
                "Doe 2026",
            ]
        )
        == 0
    )
    write(
        root,
        "evidence.yaml",
        {
            "evidence": [
                {
                    "id": "T1-link",
                    "source": "paper",
                    "locator": "Table 1",
                    "quote": "Link 40×8×5",
                    "values": {"L": 40, "H": 8, "W": 5},
                },
                {
                    "id": "pitch",
                    "source": "paper",
                    "locator": "Sec. 2",
                    "quote": "spaced 30 mm apart",
                    "values": {"pitch": 30},
                },
            ],
            "skipped": [
                {
                    "source": "paper",
                    "quote": "branches of 60 mm diameter",
                    "reason": "test condition",
                }
            ],
            "conflicts": [],
        },
    )
    write(
        root,
        "params.yaml",
        {
            "params": {
                "link_L": {
                    "basis": "source",
                    "from": "T1-link.L",
                    "interpretation": "envelope along X",
                },
                "link_H": {"basis": "source", "from": "T1-link.H"},
                "link_W": {"basis": "source", "from": "T1-link.W"},
                "pitch": {"basis": "source", "from": "pitch.pitch"},
                "hole_d": {"basis": "proposed", "value": 3, "rationale": "M3 pin", "gap": "G1"},
            }
        },
    )
    write(
        root, "gaps.yaml", {"gaps": [{"id": "G1", "question": "pin diameter?", "ask": "authors"}]}
    )
    write(
        root,
        "checks.yaml",
        {
            "checks": [
                {
                    "id": "env",
                    "kind": "bbox",
                    "part": "link",
                    "evidence": "T1-link",
                    "axes": {"L": "x", "H": "z", "W": "y"},
                },
                {
                    "id": "pitch",
                    "kind": "distance",
                    "between": ["link.a", "link.b"],
                    "evidence": "pitch",
                    "key": "pitch",
                },
                {"id": "clear", "kind": "interference"},
            ]
        },
    )
    write(root, "model.py", MODEL)
    return root


def verify(root: Path, *flags: str) -> tuple[int, dict]:
    """Run a verification run through the CLI; return its exit code and report.json."""
    code = cli.main(["check", str(root), *flags])
    return code, json.loads((root / "build" / "report.json").read_text())


def run(*args: str) -> tuple[int, str]:
    """Run a cadrev command through the CLI; return its exit code and what it prints."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = cli.main(list(args))
    return code, out.getvalue()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def errors(root: Path) -> list[str]:
    _, report = verify(root)
    return [f["rule"] for f in report["findings"] if f["level"] == "error"]


def test_report_json_carries_status_findings_and_counts(proj_dir):
    code, report = verify(proj_dir)
    assert code == 0
    assert report["status"] == "VERIFIED"
    assert all(set(f) == {"level", "rule", "message"} for f in report["findings"])
    assert report["counts"] == {
        "errors": 0,
        "warnings": len(report["findings"]),
        "checks": 5,
        "checks_passed": 5,
        "params": 5,
        "source": 4,
        "measured": 0,
        "proposed": 1,
    }


def test_guard_report_json_has_the_keys_project_format_documents(proj_dir):
    doc = (Path(__file__).parents[2] / "references" / "project-format.md").read_text()
    rows = dict(re.findall(r"^\| `(\w+)` \| (.*) \|$", doc.split("## build/report.json")[1], re.M))
    _, report = verify(proj_dir)
    assert set(report) == set(rows), "report.json and project-format.md list different keys"
    assert set(report["counts"]) == set(re.findall(r"`(\w+)`", rows["counts"]))


def test_every_status_cadrev_check_reports_is_defined_in_project_format(proj_dir):
    def reported(*flags: str) -> str:
        """The status the last line of `cadrev check` prints."""
        return run("check", str(proj_dir), *flags)[1].splitlines()[-1].split(":")[0]

    statuses = {reported(), reported("--no-build")}
    add_reading(proj_dir)
    statuses.add(reported())
    write(proj_dir, "gaps.yaml", {"gaps": []})
    statuses.add(reported())
    doc = (Path(__file__).parents[2] / "references" / "project-format.md").read_text()
    section = doc.split("\n## Statuses\n")[1].split("\n## ")[0]
    defined = re.findall(r"^\| \*\*([A-Z ]+)\*\* \|", section, re.M)
    assert sorted(defined) == sorted(statuses), (
        "cadrev check and project-format.md differ on statuses"
    )


def test_report_json_lists_each_finding_with_level_rule_and_message(proj_dir):
    write(proj_dir, "gaps.yaml", {"gaps": []})
    code, report = verify(proj_dir)
    assert code == 1
    assert report["status"] == "NOT VERIFIED"
    assert {
        "level": "error",
        "rule": "param-gap",
        "message": "param hole_d: unknown gap 'G1'",
    } in report["findings"]
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


def test_guard_quote_matches_across_a_hyphenated_line_break_and_spaced_times(proj_dir, tmp_path):
    text, quote = "Bent Link-\nage 37 × 6.5×5", "Bent Linkage 37×6.5×5"
    add_quote(proj_dir, tmp_path, text, quote, {"L": 37, "H": 6.5, "W": 5})
    rules = errors(proj_dir)
    assert "quote-not-found" not in rules and "value-not-in-quote" not in rules


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


def add_quote(root: Path, tmp_path: Path, text: str, quote: str, values: dict) -> None:
    """Register one more source holding text, and ledger quote from it as evidence N1."""
    notes = tmp_path / "notes.txt"
    notes.write_text(text)
    assert (
        cli.main(
            [
                "source",
                str(root),
                str(notes),
                "--id",
                "notes",
                "--kind",
                "paper",
                "--citation",
                "Doe 2026 notes",
            ]
        )
        == 0
    )
    edit(
        root,
        "evidence.yaml",
        lambda d: d["evidence"].append(
            {"id": "N1", "source": "notes", "locator": "Sec. 1", "quote": quote, "values": values}
        ),
    )


@pytest.mark.parametrize(
    "text, quote", [("The rod is 137 mm long.", "37 mm"), ("The rod is 3.7 mm wide.", "7 mm")]
)
def test_quote_matches_whole_numbers_only(proj_dir, tmp_path, text, quote):
    add_quote(proj_dir, tmp_path, text, quote, {"x": 37})
    assert "quote-not-found" in errors(proj_dir)


def test_quote_of_whole_numbers_is_found(proj_dir, tmp_path):
    add_quote(proj_dir, tmp_path, "The rod is 137 mm long.", "is 137 mm", {"x": 137})
    assert "quote-not-found" not in errors(proj_dir)


# How a quote reads: the values it yields and the near misses it must refuse. Add a row for every
# new quote form the reader handles, with the closest input on the other side of the rule.
QUOTES = {
    "Fig. 2 shows the 4 cm link": ([4], [2]),
    "Figure S3 shows the 4 cm link": ([4], [3]),
    "Fig. 2a, 7 mm": ([7], [2]),
    "Fig. 2 in the text shows the 4 cm link": ([4], [2]),
    "Figs. 2 and 3 show the 4 cm link": ([4], [2, 3]),
    "Table 5 lists the 4 cm link": ([4], [5]),
    "Tables 1-3 list the 4 cm link": ([4], [1, 3]),
    "Eq. (6) gives the 4 cm link": ([4], [6]),
    "Section 4.2 gives the 4 cm link": ([4], [4.2]),
    "Sec. 4.2.1 gives the 4 cm link": ([4], [4.2]),
    "the tab 3 mm wide": ([3], []),
    "2 sec per stride": ([2], []),
    "a section 4 mm thick": ([4], []),
    "a table 30 mm wide": ([30], [3]),
    "Hole spacing 5-10 mm": ([5, 10], [-10]),
    "Hole spacing 5–10 mm": ([5, 10], [-10]),
    "Walls 3–5 mm": ([3, 5], [-5]),
    "Hole spacing 5 mm - 10 mm": ([5, 10], [-10]),
    "tilted from -10 to -5 deg": ([-10, -5], [10, 5]),
    "The pin is 3.7 mm wide and 137 mm long.": ([3.7, 137], [37, 7]),
    "Link 40×8×5": ([40, 8, 5], [408]),
    "Walls 3,5 mm": ([3.5], [5, 3]),
    "a 1/4 inch shaft": ([0.25], [4, 1]),
    "a 1 1/2 inch shaft": ([1.5], [0.5, 2]),
    "gear ratio 1/50": ([1, 50], [0.02]),
    "widths 1,5,10 mm": ([1, 5, 10], [1.5]),
    "a 1,250 mm rail": ([1, 250], [1.25]),
}


@pytest.mark.parametrize("quote", sorted(QUOTES))
def test_quote_yields_its_values_and_refuses_near_misses(proj_dir, tmp_path, quote):
    accepted, refused = QUOTES[quote]
    values = {f"a{i}": v for i, v in enumerate(accepted)} | {
        f"r{i}": v for i, v in enumerate(refused)
    }
    add_quote(proj_dir, tmp_path, quote, quote, values)
    _, report = verify(proj_dir)
    missing = {
        f["message"].split(" ")[0].removeprefix("N1.")
        for f in report["findings"]
        if f["rule"] == "value-not-in-quote"
    }
    assert missing == {f"r{i}" for i in range(len(refused))}


def test_source_tampering_is_caught(proj_dir):
    (proj_dir / "sources" / "paper.txt").write_text(PAPER.replace("40", "45"))
    assert "source-hash" in errors(proj_dir)


def test_source_rewritten_between_runs_is_read_afresh(proj_dir):
    assert verify(proj_dir)[0] == 0
    paper = proj_dir / "sources" / "paper.txt"
    paper.write_text(PAPER.replace("30 mm apart", "32 mm apart"))
    register = ["source", str(proj_dir), str(paper), "--id", "paper", "--kind", "paper"]
    assert cli.main([*register, "--citation", "Doe 2026"]) == 0
    assert "quote-not-found" in errors(proj_dir)


def test_model_literal_is_rejected(proj_dir):
    write(proj_dir, "model.py", MODEL.replace("p.link_H)\n    link -=", "7.5)\n    link -=", 1))
    assert "model-literal" in errors(proj_dir)


# The model lint closes every route a number could take into model.py.


def _model_with(root: Path, header: str = "", line: str = "") -> None:
    """model.py with header above it and line as the first statement of build()."""
    body = MODEL.replace("def build(p):\n", f"def build(p):\n    {line}\n") if line else MODEL
    write(root, "model.py", header + "\n" + body)


@pytest.mark.parametrize(
    "header",
    [
        "import os",
        "from json import loads",
        "import fractions as f",
        "from __future__ import annotations",
    ],
)
def test_model_importing_beyond_build123d_and_math_is_a_finding(proj_dir, header):
    _model_with(proj_dir, header=header)
    assert errors(proj_dir) == ["model-import"]


def test_guard_model_importing_build123d_and_math(proj_dir):
    _model_with(
        proj_dir,
        header="import math\nfrom math import pi\nimport build123d.topology as topo\n"
        "from build123d import Box",
    )
    code, _ = verify(proj_dir)
    assert code == 0 and findings(proj_dir, "model-import") == []


@pytest.mark.parametrize(
    "line",
    ['extra = float("4")', "extra = int('1' + '0')", 'extra = complex("4")', 'extra = eval("4")'],
)
def test_model_converting_text_to_a_number_is_a_finding(proj_dir, line):
    _model_with(proj_dir, line=line)
    assert errors(proj_dir) == ["model-text-number"]


def test_guard_model_converting_a_param_to_a_number_or_text(proj_dir):
    _model_with(proj_dir, line="extra = int(p.link_H), float(p.pitch), str(p.link_L)")
    code, _ = verify(proj_dir)
    assert code == 0 and findings(proj_dir, "model-text-number") == []


@pytest.mark.parametrize(
    "expr",
    [
        "2*2 - 0.5",
        "2 ** 2",
        "-(1 + 2)",
        "90 + 0.5",
        "(0.5 + 0.5) * 90 / 2",
        "2 ** 2 ** 2 ** 2 ** 2",
    ],
)
def test_model_constant_arithmetic_folding_to_a_disallowed_value_is_a_finding(proj_dir, expr):
    _model_with(proj_dir, line=f"extra = {expr}")
    messages = findings(proj_dir, "model-arithmetic")
    assert errors(proj_dir) == ["model-arithmetic"] and len(messages) == 1


@pytest.mark.parametrize(
    "expr",
    [
        "p.pitch * 2 * 2",
        "p.pitch * 2 * 2 - 0.5",
        "2 * p.pitch * 2",
        "p.pitch * 2 * -2",
        "p.pitch + 90 + 0.5",
        "p.pitch - 90 - 0.5",
        "90 - p.pitch + 0.5",
        "p.pitch - (p.link_H - 90 - 0.5)",
    ],
)
def test_model_chain_of_one_operator_folds_its_literals_in_any_order(proj_dir, expr):
    _model_with(proj_dir, line=f"extra = {expr}")
    messages = findings(proj_dir, "model-arithmetic")
    assert errors(proj_dir) == ["model-arithmetic"] and len(messages) == 1


@pytest.mark.parametrize(
    "expr",
    [
        "1 / 2",
        "180 + 90",
        "-90",
        "-0.5",
        "2 * 0.5 - 1",
        "-p.pitch / 2 * 2",
        "p.pitch * 2 * 0.5",
        "2 * p.pitch * 90",
        "p.pitch - 90 + 180",
        "p.pitch * 2 - 0.5",
        "p.pitch / 2 * 2",
        "p.pitch * p.link_H * 2",
    ],
)
def test_guard_model_constant_arithmetic_folding_to_an_allowed_value(proj_dir, expr):
    _model_with(proj_dir, line=f"extra = {expr}")
    code, _ = verify(proj_dir)
    assert code == 0


@pytest.mark.parametrize("literal", ["1e1", "3.0", "10.", "0x3", "3_0", "2.5e0"])
def test_guard_model_literal_in_any_spelling_is_rejected(proj_dir, literal):
    _model_with(proj_dir, line=f"extra = {literal}")
    assert errors(proj_dir) == ["model-literal"]


@pytest.mark.parametrize("literal", ["2.0", "5e-1", "9e1", "0x2", "1_8_0"])
def test_guard_model_allowed_literal_in_any_spelling(proj_dir, literal):
    _model_with(proj_dir, line=f"extra = {literal}")
    code, _ = verify(proj_dir)
    assert code == 0


def test_report_shows_the_project_override_of_the_allowed_literals(proj_dir):
    edit(proj_dir, "project.yaml", lambda d: d.update(model_literals=[0, 1, 2, 7.5]))
    code, report = verify(proj_dir)
    assert code == 0 and report["model_literals"] == [0, 1, 2, 7.5]
    md = (proj_dir / "build" / "report.md").read_text()
    assert "## Model literal override" in md and "0, 1, 2, 7.5" in md


def test_report_shows_no_override_when_the_project_keeps_the_default_literals(proj_dir):
    _, report = verify(proj_dir)
    assert report["model_literals"] is None
    md = (proj_dir / "build" / "report.md").read_text()
    assert md.split("## Model literal override\n\n")[1].startswith("_None._")


def test_guard_unledgered_stated_quantity_is_reported(proj_dir):
    data = yaml.safe_load((proj_dir / "evidence.yaml").read_text())
    data["skipped"] = []
    write(proj_dir, "evidence.yaml", data)
    assert "coverage" in errors(proj_dir)


def test_unaccounted_evidence_is_reported(proj_dir):
    data = yaml.safe_load((proj_dir / "evidence.yaml").read_text())
    data["evidence"].append(
        {
            "id": "extra",
            "source": "paper",
            "locator": "Sec. 3",
            "quote": "branches of 60 mm diameter",
            "values": {"d": 60},
        }
    )
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
    data["evidence"].append(
        {
            "id": "F2",
            "source": "paper",
            "locator": "Fig. 2",
            "scope": "context",
            "reason": "label",
            "image": "figures/crops/fig2.png",
            "image_sha256": "0" * 64,
            "reading": "70 mm",
        }
    )
    write(proj_dir, "evidence.yaml", data)
    assert "image-hash" in errors(proj_dir)


def add_reading(root: Path, **fields) -> dict:
    """Ledger a Fig. 2 crop, pinned by `cadrev crop`, whose reading no human has confirmed;
    return its entry."""
    from PIL import Image

    (root / "figures").mkdir(exist_ok=True)
    Image.new("RGB", (40, 20), "white").save(root / "figures" / "page2.png")
    code, out = run("crop", str(root), "figures/page2.png", "0", "0", "20", "10", "--name", "fig2")
    assert code == 0
    entry = {
        "id": "F2",
        "source": "paper",
        "locator": "Fig. 2",
        "scope": "context",
        "reason": "label",
        "image": "figures/crops/fig2.png",
        "image_sha256": out.split("image_sha256: ")[1].strip(),
        "reading": "70 mm",
        **fields,
    }
    edit(root, "evidence.yaml", lambda d: d["evidence"].append(entry))
    return entry


def test_project_whose_only_shortfall_is_an_unconfirmed_reading_is_pending_review(proj_dir):
    add_reading(proj_dir)
    code, report = verify(proj_dir)
    assert report["counts"]["errors"] == 0
    assert (code, report["status"]) == (0, "VERIFIED PENDING REVIEW")
    assert report["findings"] == []
    assert "**VERIFIED PENDING REVIEW**" in (proj_dir / "build" / "report.md").read_text()


def test_report_lists_each_reading_awaiting_confirmation_with_its_crop(proj_dir):
    add_reading(proj_dir)
    _, report = verify(proj_dir)
    assert report["awaiting_confirmation"] == [
        {
            "evidence": "F2",
            "locator": "Fig. 2",
            "reading": "70 mm",
            "image": "figures/crops/fig2.png",
        }
    ]
    md = (proj_dir / "build" / "report.md").read_text()
    awaiting = md.split("## Figure readings awaiting human confirmation")[1].split("\n## ")[0]
    assert "F2" in awaiting and "70 mm" in awaiting and "figures/crops/fig2.png" in awaiting


def test_confirming_the_reading_makes_the_project_verified(proj_dir):
    add_reading(proj_dir)
    assert verify(proj_dir)[1]["status"] == "VERIFIED PENDING REVIEW"
    edit(proj_dir, "evidence.yaml", lambda d: d["evidence"][-1].update(confirmed_by="A. Reviewer"))
    code, report = verify(proj_dir)
    assert (code, report["status"], report["awaiting_confirmation"]) == (0, "VERIFIED", [])


def test_guard_error_beside_an_unconfirmed_reading_is_not_verified(proj_dir):
    add_reading(proj_dir)
    write(proj_dir, "gaps.yaml", {"gaps": []})
    code, report = verify(proj_dir)
    assert (code, report["status"]) == (1, "NOT VERIFIED")
    assert [f["rule"] for f in report["findings"] if f["level"] == "error"] == ["param-gap"]


def test_overlay_renders_against_a_figure(proj_dir):
    from PIL import Image

    (proj_dir / "figures").mkdir(exist_ok=True)
    Image.new("RGB", (400, 200), "white").save(proj_dir / "figures" / "fig.png")
    write(
        proj_dir,
        "overlays.yaml",
        {
            "overlays": [
                {
                    "id": "front",
                    "image": "figures/fig.png",
                    "part": "link",
                    "view": "front",
                    "origin": [200, 100],
                    "calibration": {"pixels": [[50, 150], [350, 150]], "evidence": "pitch.pitch"},
                }
            ]
        },
    )
    assert cli.main(["check", str(proj_dir)]) == 0
    assert (proj_dir / "build" / "overlays" / "front.png").exists()
    assert "overlays/front.png" in (proj_dir / "build" / "report.md").read_text()


# Basis: what each parameter rests on, and the headline that counts them.


def add_params(root: Path, **params) -> None:
    edit(root, "params.yaml", lambda d: d["params"].update(params))


def add_measured(root: Path) -> None:
    """Ledger the Fig. 2 crop, confirmed, and scale param foot_w off it."""
    add_reading(root, confirmed_by="A. Reviewer")
    add_params(
        root,
        foot_w={
            "basis": "measured",
            "from": "F2",
            "value": 5.5,
            "method": "pitch as scale, 12 px/mm",
            "uncertainty": "±0.3 mm",
        },
    )


@pytest.mark.parametrize("expr", ["2.2", "2 * pi"])
def test_derived_param_whose_expr_references_no_param_is_a_finding(proj_dir, expr):
    add_params(proj_dir, half={"basis": "derived", "expr": expr})
    assert "param-constant" in errors(proj_dir)


def test_guard_derived_param_whose_expr_references_a_param_raises_no_constant_finding(proj_dir):
    add_params(proj_dir, half={"basis": "derived", "expr": "pi * pitch / 2"})
    assert "param-constant" not in errors(proj_dir)


@pytest.mark.parametrize(
    "expr, rests_on",
    [
        ("pitch / 2", "source"),
        ("pitch - foot_w", "measured"),
        ("pitch - hole_d", "proposed"),
        ("pitch - foot_w - hole_d", "proposed"),
        ("twice - pitch", "measured"),
    ],
)
def test_derived_param_rests_on_the_weakest_basis_it_depends_on(proj_dir, expr, rests_on):
    add_measured(proj_dir)
    add_params(
        proj_dir,
        twice={"basis": "derived", "expr": "2 * foot_w"},
        result={"basis": "derived", "expr": expr},
    )
    _, report = verify(proj_dir)
    assert report["params"]["result"]["rests_on"] == rests_on


def test_report_headline_counts_parameters_by_what_they_rest_on(proj_dir):
    add_measured(proj_dir)
    add_params(
        proj_dir,
        slot={"basis": "derived", "expr": "foot_w + hole_d"},
        half={"basis": "derived", "expr": "pitch / 2"},
    )
    code, report = verify(proj_dir)
    assert (code, report["status"]) == (0, "VERIFIED")
    assert {k: report["counts"][k] for k in ("params", "source", "measured", "proposed")} == {
        "params": 8,
        "source": 5,
        "measured": 1,
        "proposed": 2,
    }
    md = (proj_dir / "build" / "report.md").read_text()
    assert (
        "Of 8 parameters, 5 rest on sources, 1 on measured values and 2 on proposed values." in md
    )


def test_report_lists_each_measured_param_with_its_method_and_uncertainty(proj_dir):
    add_measured(proj_dir)
    _, report = verify(proj_dir)
    assert report["measured"] == [
        {
            "param": "foot_w",
            "value": 5.5,
            "from": "F2",
            "method": "pitch as scale, 12 px/mm",
            "uncertainty": "±0.3 mm",
        }
    ]
    md = (proj_dir / "build" / "report.md").read_text()
    measured = md.split("## Measured parameters")[1].split("\n## ")[0]
    assert "| foot_w | 5.5 | F2 | pitch as scale, 12 px/mm | ±0.3 mm |" in measured


def _no_proposed(root: Path) -> None:
    """Derive the fixture's one proposed param, hole_d, from the pitch instead."""
    add_params(root, hole_d={"basis": "derived", "expr": "pitch / 10"})


def test_verified_project_with_no_proposed_param_is_exact(proj_dir):
    _no_proposed(proj_dir)
    code, report = verify(proj_dir)
    assert (code, report["status"], report["counts"]["proposed"], report["exact"]) == (
        0,
        "VERIFIED",
        0,
        True,
    )
    assert (
        "**Exact**: no parameter rests on a proposed value."
        in (proj_dir / "build" / "report.md").read_text()
    )


@pytest.mark.parametrize("change", ["proposed param", "unconfirmed reading", "error"])
def test_project_with_a_proposed_param_or_short_of_verified_is_not_exact(proj_dir, change):
    if change != "proposed param":
        _no_proposed(proj_dir)
    if change == "unconfirmed reading":
        add_reading(proj_dir)
    if change == "error":
        add_params(proj_dir, half={"basis": "derived", "expr": "2.2"})
    _, report = verify(proj_dir)
    assert report["exact"] is False
    assert "**Exact**" not in (proj_dir / "build" / "report.md").read_text()


# Named findings, never tracebacks.


def findings(root: Path, rule: str) -> list[str]:
    """Messages of every report.json finding with this rule, from a fresh verification run."""
    _, report = verify(root)
    return [f["message"] for f in report["findings"] if f["rule"] == rule]


def edit(root: Path, name: str, change) -> None:
    data = yaml.safe_load((root / name).read_text())
    change(data)
    write(root, name, data)


@pytest.mark.parametrize(
    "name",
    ["project.yaml", "evidence.yaml", "params.yaml", "checks.yaml", "gaps.yaml", "overlays.yaml"],
)
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


@pytest.mark.parametrize(
    "name, change, where",
    [
        ("params.yaml", lambda d: d.update(params=[{"link_L": 40}]), "params.yaml params:"),
        ("params.yaml", lambda d: d["params"].update(link_L=40), "params.yaml params.link_L:"),
        (
            "evidence.yaml",
            lambda d: d["evidence"][0]["values"].update(L="forty"),
            "evidence.yaml evidence[0].values.L:",
        ),
        ("project.yaml", lambda d: d.update(sources=3), "project.yaml sources:"),
    ],
)
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


@pytest.mark.parametrize(
    "returned",
    ["[]", "None", '{"parts": []}', '{"parts": {}, "datums": {"a": 1}}', '{"parts": {"link": 3}}'],
)
def test_build_returning_the_wrong_shape_is_a_finding(proj_dir, returned):
    write(
        proj_dir, "model.py", MODEL.replace("    return {", f"    return {returned}\n    _ = {{", 1)
    )
    code, report = verify(proj_dir)
    assert code == 1
    assert [f["rule"] for f in report["findings"] if f["rule"] == "model-return"] == [
        "model-return"
    ]


def test_build_returning_the_expected_mapping_raises_no_return_finding(proj_dir):
    assert findings(proj_dir, "model-return") == []


def test_reregistering_a_source_refreshes_its_path_and_hash(proj_dir, tmp_path, capsys):
    paper = tmp_path / "paper-v2.txt"
    paper.write_text(PAPER + "Received 1 March.\n")
    assert (
        cli.main(
            [
                "source",
                str(proj_dir),
                str(paper),
                "--id",
                "paper",
                "--kind",
                "paper",
                "--citation",
                "Doe 2026",
                "--rename",
                "paper-v2.txt",
            ]
        )
        == 0
    )
    entries = yaml.safe_load((proj_dir / "project.yaml").read_text())["sources"]
    assert [(s["id"], s["path"], s["sha256"]) for s in entries] == [
        ("paper", "sources/paper-v2.txt", sha256(paper))
    ]
    assert "Traceback" not in capsys.readouterr().err
    assert verify(proj_dir)[0] == 0


def test_source_into_a_missing_project_is_an_error_not_a_traceback(tmp_path, capsys):
    paper = tmp_path / "paper.txt"
    paper.write_text(PAPER)
    assert (
        cli.main(
            [
                "source",
                str(tmp_path / "nowhere"),
                str(paper),
                "--id",
                "paper",
                "--kind",
                "paper",
                "--citation",
                "Doe 2026",
            ]
        )
        == 1
    )
    err = capsys.readouterr().err
    assert "project.yaml" in err and "Traceback" not in err


def test_param_without_basis_is_a_finding_in_the_report(proj_dir):
    edit(proj_dir, "params.yaml", lambda d: d["params"]["link_L"].pop("basis"))
    assert "param-basis" in errors(proj_dir)


def test_quote_from_a_non_text_source_is_a_finding(proj_dir, tmp_path):
    frame = tmp_path / "frame.png"
    frame.write_bytes(b"png")
    assert (
        cli.main(
            [
                "source",
                str(proj_dir),
                str(frame),
                "--id",
                "video",
                "--kind",
                "video",
                "--citation",
                "Doe 2026 Movie S1",
            ]
        )
        == 0
    )
    edit(proj_dir, "evidence.yaml", lambda d: d["evidence"][1].update(source="video"))
    assert "evidence-anchor" in errors(proj_dir)


def test_reregistering_one_source_leaves_the_others_untouched(proj_dir, tmp_path):
    notes = tmp_path / "notes.txt"
    notes.write_text("No dimensions here.\n")
    assert (
        cli.main(
            [
                "source",
                str(proj_dir),
                str(notes),
                "--id",
                "notes",
                "--kind",
                "other",
                "--citation",
                "Doe notes",
            ]
        )
        == 0
    )
    before = yaml.safe_load((proj_dir / "project.yaml").read_text())["sources"]
    (proj_dir / "sources" / "paper.txt").write_text(PAPER + "Received 1 March.\n")
    assert (
        cli.main(
            [
                "source",
                str(proj_dir),
                str(proj_dir / "sources" / "paper.txt"),
                "--id",
                "paper",
                "--kind",
                "paper",
                "--citation",
                "Doe 2026",
            ]
        )
        == 0
    )
    after = yaml.safe_load((proj_dir / "project.yaml").read_text())["sources"]
    assert after[1] == before[1]
    assert after[0] == {**before[0], "sha256": sha256(proj_dir / "sources" / "paper.txt")}


def _overlay(root: Path, **changes) -> None:
    from PIL import Image

    (root / "figures").mkdir(exist_ok=True)
    Image.new("RGB", (40, 20), "white").save(root / "figures" / "fig.png")
    overlay = {
        "id": "front",
        "image": "figures/fig.png",
        "part": "link",
        "view": "front",
        "origin": [20, 10],
        "calibration": {"pixels": [[5, 15], [35, 15]], "evidence": "pitch.pitch"},
    }
    write(root, "overlays.yaml", {"overlays": [{**overlay, **changes}]})


def _zero_pitch(root: Path) -> None:
    edit(
        root,
        "evidence.yaml",
        lambda d: d["evidence"].append(
            {
                "id": "zero",
                "source": "paper",
                "locator": "Table 1",
                "quote": "Link 40×8×5",
                "scope": "context",
                "reason": "test",
                "values": {"z": 0},
            }
        ),
    )
    _overlay(root, calibration={"pixels": [[5, 15], [35, 15]], "evidence": "zero.z"})


@pytest.mark.parametrize(
    "damage, rule",
    [
        (
            lambda r: edit(
                r,
                "params.yaml",
                lambda d: d["params"].update(
                    {1: {"basis": "proposed", "value": 1, "rationale": "x"}}
                ),
            ),
            "schema",
        ),
        (lambda r: _overlay(r, id="a/b"), "overlay-config"),
        (_zero_pitch, "overlay-config"),
        (lambda r: ((r / "model.py").unlink(), (r / "model.py").mkdir()), "model-missing"),
        (
            lambda r: write(
                r,
                "model.py",
                MODEL.replace("def build(p):", "raise SystemExit(3)\n\ndef build(p):"),
            ),
            "model-build",
        ),
        (
            lambda r: write(r, "model.py", MODEL.replace('{"link": link}', '{"a/b": link}')),
            "model-return",
        ),
        (lambda r: (r / "sources" / "paper.txt").write_bytes(b"\xff\xfe\x00broken"), "source-hash"),
    ],
)
def test_damaged_input_is_a_finding_not_a_crash(proj_dir, damage, rule):
    damage(proj_dir)
    code, report = verify(proj_dir)
    assert code == 1 and rule in [f["rule"] for f in report["findings"]]


@pytest.mark.parametrize(
    "name, content", [("paper.pdf", b"%PDF-1.4 not really"), ("paper.docx", b"PK not a zip")]
)
def test_unreadable_source_is_a_finding(proj_dir, tmp_path, name, content):
    broken = tmp_path / name
    broken.write_bytes(content)
    assert (
        cli.main(
            [
                "source",
                str(proj_dir),
                str(broken),
                "--id",
                "broken",
                "--kind",
                "other",
                "--citation",
                "Doe",
            ]
        )
        == 0
    )
    assert "source-unreadable" in errors(proj_dir)


def test_init_writes_the_current_format(proj_dir):
    assert yaml.safe_load((proj_dir / "project.yaml").read_text())["format"] == 1
    assert findings(proj_dir, "format-missing") == findings(proj_dir, "format-unknown") == []


def test_project_without_format_stops_the_run_and_writes_nothing(proj_dir, capsys):
    edit(proj_dir, "project.yaml", lambda d: d.pop("format"))
    assert cli.main(["check", str(proj_dir)]) == 1
    out = capsys.readouterr().out
    assert (
        "error: [format-missing] project.yaml: format is missing; this cadrev reads format: 1"
        in out
    )
    assert not (proj_dir / "build").exists()


@pytest.mark.parametrize("given", [2, 1.0, "1", True, [1], {"v": 1}])
def test_project_of_an_unknown_format_stops_the_run_and_writes_nothing(proj_dir, capsys, given):
    edit(proj_dir, "project.yaml", lambda d: d.update(format=given))
    assert cli.main(["check", str(proj_dir)]) == 1
    out = capsys.readouterr()
    assert out.out.count("[format-unknown] project.yaml: format ") == 1
    assert "Traceback" not in out.out + out.err
    assert not (proj_dir / "build").exists()


def test_project_of_an_unknown_format_has_no_other_file_read(proj_dir, capsys):
    edit(proj_dir, "project.yaml", lambda d: d.update(format=2))
    write(proj_dir, "params.yaml", "params: [unclosed\n")
    assert cli.main(["check", str(proj_dir)]) == 1
    assert [line for line in capsys.readouterr().out.splitlines() if line.startswith("error:")] == [
        "error: [format-unknown] project.yaml: format 2 is not one this cadrev reads (it reads format: 1)"
    ]


@pytest.mark.parametrize(
    "command",
    [
        ["coverage"],
        ["text", "paper"],
        ["figures", "paper"],
        ["source", "PAPER", "--id", "paper", "--kind", "paper", "--citation", "Doe 2026"],
    ],
)
def test_every_command_refuses_a_project_of_an_unknown_format(proj_dir, tmp_path, capsys, command):
    edit(proj_dir, "project.yaml", lambda d: d.update(format=2))
    before = (proj_dir / "project.yaml").read_text()
    args = [str(tmp_path / "paper.txt") if a == "PAPER" else a for a in command]
    assert cli.main([args[0], str(proj_dir), *args[1:]]) == 1
    assert "[format-unknown]" in capsys.readouterr().err
    assert (proj_dir / "project.yaml").read_text() == before


def test_readable_sources_raise_no_unreadable_finding(proj_dir):
    assert findings(proj_dir, "source-unreadable") == []


def _add_source(root: Path, sid: str, path: str) -> None:
    meta = root / "project.yaml"
    meta.write_text(
        meta.read_text() + f"  - id: {sid}\n    kind: paper\n    path: {path}\n"
        "    sha256: x\n    citation: c\n"
    )


def _replace(root: Path, name: str, old: str, new: str) -> None:
    (root / name).write_text((root / name).read_text().replace(old, new))


# Damage that once crashed, or plausibly could crash, a verification run. Add a case for every
# new way project input or user code enters the run.
DAMAGE = {
    "param named by a number": lambda r: edit(
        r,
        "params.yaml",
        lambda d: d["params"].update(
            {7: {"basis": "proposed", "value": 3, "rationale": "x", "gap": "G1"}}
        ),
    ),
    "overlay pixels in 3D": lambda r: _overlay(
        r, calibration={"pixels": [[0, 0, 0], [1, 1, 1]], "evidence": "pitch.pitch"}
    ),
    "source path is a directory": lambda r: _add_source(r, "d", "sources"),
    "source path outside the project": lambda r: _add_source(r, "e", "/etc/hosts"),
    "text source not UTF-8": lambda r: (
        (r / "sources" / "b.txt").write_bytes(b"\xff\xfe 30 mm"),
        _add_source(r, "b", "sources/b.txt"),
    ),
    "name is a number": lambda r: _replace(r, "project.yaml", "name:", "name: 5\noldname:"),
    "format is a mapping": lambda r: _replace(
        r, "project.yaml", "format:", "format: {v: 1}\nxformat:"
    ),
    "units is a number": lambda r: _replace(r, "project.yaml", "units:", "units: 5\nxunits:"),
    "unit is a list": lambda r: _replace(
        r, "project.yaml", "units:", "units: {length: [mm]}\nxunits:"
    ),
    "units keyed by a number": lambda r: _replace(
        r, "project.yaml", "units:", "units: {5: mm}\nxunits:"
    ),
    "unit is a null": lambda r: _replace(
        r, "project.yaml", "units:", "units: {length: null}\nxunits:"
    ),
    "reading is a number": lambda r: edit(
        r,
        "evidence.yaml",
        lambda d: d["evidence"].append(
            {
                "id": "im",
                "source": "paper",
                "locator": "F",
                "image": "x.png",
                "reading": 30,
                "values": {"v": 30},
            }
        ),
    ),
    "tolerance of zero": lambda r: _replace(
        r, "project.yaml", "tolerance:", "tolerance: {length: 0}\nxtolerance:"
    ),
    "model_literals is a number": lambda r: _replace(
        r, "project.yaml", "name:", "model_literals: 5\nname:"
    ),
    "deeply nested expr": lambda r: edit(
        r,
        "params.yaml",
        lambda d: d["params"].update(
            {"deep": {"basis": "derived", "expr": "(" * 300 + "pitch" + ")" * 300}}
        ),
    ),
    "expr overflows": lambda r: edit(
        r,
        "params.yaml",
        lambda d: d["params"].update({"big": {"basis": "derived", "expr": "pitch ** 1000"}}),
    ),
    "derived without inputs": lambda r: edit(
        r,
        "params.yaml",
        lambda d: d["params"].update({"q": {"basis": "derived", "expr": "pitch", "value": 30}}),
    ),
    "mass check counts not numbers": lambda r: edit(
        r,
        "checks.yaml",
        lambda d: d["checks"].append(
            {
                "id": "m",
                "kind": "mass",
                "density": "pitch",
                "evidence": "pitch",
                "key": "pitch",
                "tol_rel": 0.1,
                "counts": {"link": 2},
            }
        ),
    ),
    "check tol not a number": lambda r: edit(
        r, "checks.yaml", lambda d: d["checks"][1].update(tol="wide")
    ),
    "mass check tol_rel not a number": lambda r: edit(
        r,
        "checks.yaml",
        lambda d: d["checks"].append(
            {
                "id": "m",
                "kind": "mass",
                "density": "pitch",
                "evidence": "pitch",
                "key": "pitch",
                "tol_rel": "x",
            }
        ),
    ),
    "bbox along an unknown axis": lambda r: edit(
        r,
        "checks.yaml",
        lambda d: d["checks"].append(
            {"id": "q", "kind": "bbox", "part": "link", "evidence": "pitch", "axes": {"pitch": "w"}}
        ),
    ),
    "datum of booleans": lambda r: write(
        r, "model.py", MODEL.replace("(-p.pitch / 2, 0, 0)", "(True, 0, 0)")
    ),
    "part name is a number": lambda r: write(
        r, "model.py", MODEL.replace('{"link": link}', '{"link": link, 3: link}')
    ),
    "unhashable YAML key": lambda r: write(
        r, "params.yaml", "params:\n  ? [a, b]\n  : {basis: proposed}\n"
    ),
    "undefined YAML alias": lambda r: write(r, "gaps.yaml", "gaps: *nope\n"),
    "NUL byte in YAML": lambda r: (r / "gaps.yaml").write_bytes(b"gaps: []\x00\n"),
    "file is a top-level list": lambda r: write(r, "params.yaml", "- a\n- b\n"),
    "project file is a directory": lambda r: (
        (r / "evidence.yaml").unlink(),
        (r / "evidence.yaml").mkdir(),
    ),
    "evidence value keyed by a number": lambda r: edit(
        r, "evidence.yaml", lambda d: d["evidence"][1]["values"].update({3: 30})
    ),
    "skip by from without to": lambda r: edit(
        r,
        "evidence.yaml",
        lambda d: d["skipped"].append({"source": "paper", "from": "Tests", "reason": "r"}),
    ),
    "image evidence is a directory": lambda r: edit(
        r,
        "evidence.yaml",
        lambda d: d["evidence"].append(
            {"id": "im", "source": "paper", "locator": "F", "image": "sources", "reading": "3"}
        ),
    ),
    "duplicate gap ids": lambda r: write(r, "gaps.yaml", {"gaps": [{"id": "G1"}, {"id": "G1"}]}),
    "source registered after a PyYAML re-dump": lambda r: (
        edit(r, "project.yaml", lambda d: None),
        (r / "notes.txt").write_text("No dimensions.\n"),
        cli.main(
            [
                "source",
                str(r),
                str(r / "notes.txt"),
                "--id",
                "notes",
                "--kind",
                "other",
                "--citation",
                "Doe notes",
            ]
        ),
    ),
}


@pytest.mark.parametrize("damage", sorted(DAMAGE))
def test_no_damage_escapes_a_verification_run(proj_dir, capsys, damage):
    DAMAGE[damage](proj_dir)
    code = cli.main(["check", str(proj_dir)])
    out = capsys.readouterr()
    assert code in (0, 1) and "Traceback" not in out.out + out.err
    report = proj_dir / "build" / "report.json"
    # A refused project writes no report and says so; any other run reports a status.
    assert (
        json.loads(report.read_text())["status"]
        if report.exists()
        else ("the project was not read, so no report was written" in out.out)
    )


# Units read from the quote (ADR-0001).


def test_quote_in_centimetres_is_read_in_project_millimetres(proj_dir, tmp_path):
    add_quote(proj_dir, tmp_path, "The link is 4 cm long.", "is 4 cm long", {"L": 4})
    edit(proj_dir, "params.yaml", lambda d: d["params"]["link_L"].update({"from": "N1.L"}))
    edit(
        proj_dir,
        "checks.yaml",
        lambda d: d["checks"].append(
            {"id": "n1", "kind": "bbox", "part": "link", "evidence": "N1", "axes": {"L": "x"}}
        ),
    )
    code, report = verify(proj_dir)
    assert report["params"]["link_L"]["value"] == 40
    assert code == 0 and report["status"] == "VERIFIED"


# How a quote's units read: the value as printed and what it is in the default project units
# (mm, deg, g, N, s; torque in N·mm, pressure in N/mm², density in g/mm³, speed in mm/s). Add a
# row for every unit spelling the reader learns. Rows whose value is already in project units,
# and words that only look like units, run as guards.
UNITS = {
    "The link is 4 cm long": (4, 40),
    "a 3 centimetre boss": (3, 30),
    "a 0.5 in shaft": (0.5, 12.7),
    'a 0.5" shaft': (0.5, 12.7),
    "a 2 inch shaft": (2, 50.8),
    "a 1.5 ft boom": (1.5, 457.2),
    "a 2 feet boom": (2, 609.6),
    "a 2 m boom": (2, 2000),
    "a 2 metre boom": (2, 2000),
    "a 250 μm film": (250, 0.25),
    "a 250 um film": (250, 0.25),
    "a 250 micron film": (250, 0.25),
    "spaced 30 millimeters apart": (30, 30),
    "a 4 mm pin": (4, 4),
    "Link 37×6.5×5": (6.5, 6.5),
    "Walls 3–5 cm": (3, 30),
    "Link 40×8×5 cm": (8, 80),
    "3 m long links, 4 in total": (4, 4),
    "2 in each leg": (2, 2),
    "turned 0.5 rad": (0.5, 28.64788975654116),
    "turned 0.5 radians": (0.5, 28.64788975654116),
    "preset at 45◦": (45, 45),
    "rotated 90°": (90, 90),
    "rotated 30 degrees": (30, 30),
    "tilted from -10 to -5 deg": (-10, -10),
    "weighs 0.43 kg": (0.43, 430),
    "weighs 420 g": (420, 420),
    "weighs 2 grams": (2, 2),
    "a 50 mg shim": (50, 0.05),
    "a 5 N load": (5, 5),
    "a 2 kN load": (2, 2000),
    "a 30 mN load": (30, 0.03),
    "a 2 kgf load": (2, 19.6133),
    "torque of 1.2 kg ·cm": (1.2, 117.6798),
    "torque of 0.3 N·m": (0.3, 300),
    "torque of 0.3 Nm": (0.3, 300),
    "torque of 12 N·mm": (12, 12),
    "torque of 12 N·cm": (12, 120),
    "torque of 12 mN·m": (12, 12),
    "rated at 0.3 MPa": (0.3, 0.3),
    "rated at 0.3 N/mm²": (0.3, 0.3),
    "rated at 100 kPa": (100, 0.1),
    "rated at 2 GPa": (2, 2000),
    "rated at 5000 Pa": (5000, 0.005),
    "rated at 2 bar": (2, 0.2),
    "rated at 10 psi": (10, 0.0689475729),
    "a resin of 1.2 g/cm3": (1.2, 0.0012),
    "a resin of 1.2 g/cc": (1.2, 0.0012),
    "a resin of 1.2 g/ml": (1.2, 0.0012),
    "a resin of 1.2 g·cm−³": (1.2, 0.0012),
    "a resin of 1200 kg/m³": (1200, 0.0012),
    "a resin of 1200 kg·m−3": (1200, 0.0012),
    "a resin of 0.0012 g/mm3": (0.0012, 0.0012),
    "2 sec per stride": (2, 2),
    "a 3 s stride": (3, 3),
    "a 3 seconds stride": (3, 3),
    "a 40 ms stride": (40, 0.04),
    "a 4 min test": (4, 240),
    "a 2 h test": (2, 7200),
    "a 2 hours test": (2, 7200),
    "moving at 5 mm/s": (5, 5),
    "moving at 5 cm/s": (5, 50),
    "moving at 2 m/s": (2, 2000),
    "moving at 36 km/h": (36, 10000),
    "a 1/4 inch shaft": (0.25, 6.35),
    "a 2.5 mm² wire": (2.5, 2.5),
    "a 3 cm² pad": (3, 300),
    "a 10 cm3 cavity": (10, 10000),
    "a 10 ml cavity": (10, 10000),
    "spinning at 300 rpm": (300, 1800),
    "at 40% infill": (40, 0.4),
    "at 40 percent infill": (40, 0.4),
    "a 2.5 mm^2 wire": (2.5, 2.5),
    "a 2 m² panel": (2, 2e6),
    "a 5 mm³ void": (5, 5),
    "a 10 cm^3 cavity": (10, 10000),
    "a 10 cc cavity": (10, 10000),
    "a 2 m³ tank": (2, 2e9),
    "spinning at 300 r/min": (300, 1800),
    "turning at 2 rad/s": (2, 114.59155902616465),
    "wound 3 turns": (3, 3),
    "a 3300 mAh battery": (3300, 11880),
}


def _unit_read(root: Path, tmp_path: Path, quote: str) -> float:
    """The value of a source param from the quote's printed value, in project units."""
    add_quote(root, tmp_path, quote, quote, {"v": UNITS[quote][0]})
    edit(root, "params.yaml", lambda d: d["params"].update(n1={"basis": "source", "from": "N1.v"}))
    return verify(root)[1]["params"]["n1"]["value"]


@pytest.mark.parametrize("quote", sorted(q for q, (a, b) in UNITS.items() if a != b))
def test_quote_unit_converts_to_the_project_units(proj_dir, tmp_path, quote):
    assert _unit_read(proj_dir, tmp_path, quote) == pytest.approx(UNITS[quote][1])


@pytest.mark.parametrize("quote", sorted(q for q, (a, b) in UNITS.items() if a == b))
def test_guard_quote_in_project_units_keeps_its_value(proj_dir, tmp_path, quote):
    assert _unit_read(proj_dir, tmp_path, quote) == pytest.approx(UNITS[quote][1])


# Where each check uses an evidence value, and the quantity it expects there.
USES = {
    "bbox": (
        40,
        lambda r: edit(
            r,
            "checks.yaml",
            lambda d: d["checks"].append(
                {"id": "u", "kind": "bbox", "part": "link", "evidence": "N1", "axes": {"v": "x"}}
            ),
        ),
    ),
    "distance": (
        30,
        lambda r: edit(
            r,
            "checks.yaml",
            lambda d: d["checks"].append(
                {
                    "id": "u",
                    "kind": "distance",
                    "between": ["link.a", "link.b"],
                    "evidence": "N1",
                    "key": "v",
                }
            ),
        ),
    ),
    "overlay calibration": (
        30,
        lambda r: _overlay(r, calibration={"pixels": [[5, 15], [35, 15]], "evidence": "N1.v"}),
    ),
}


def _length_use(root: Path, tmp_path: Path, use: str, unit: str) -> list[str]:
    """unit-quantity findings when N1, printed in unit, is used as a length by use."""
    value, add_use = USES[use]
    value = value / 10 if unit == "cm" else value
    text = f"The link reads {value:g} {unit} on the scale."
    add_quote(root, tmp_path, text, text, {"v": value})
    add_use(root)
    return findings(root, "unit-quantity")


@pytest.mark.parametrize("use", sorted(USES))
@pytest.mark.parametrize("unit", ["g", "deg", "N"])
def test_value_of_another_quantity_where_a_length_is_expected_is_a_finding(
    proj_dir, tmp_path, use, unit
):
    messages = _length_use(proj_dir, tmp_path, use, unit)
    assert len(messages) == 1
    assert messages[0].startswith("N1.v") and "where a length is expected" in messages[0]


@pytest.mark.parametrize("use", sorted(USES))
@pytest.mark.parametrize("unit", ["mm", "cm", ""])
def test_guard_length_or_no_unit_where_a_length_is_expected(proj_dir, tmp_path, use, unit):
    assert _length_use(proj_dir, tmp_path, use, unit) == []


def _mass_check(root: Path, tmp_path: Path, text: str, values: dict) -> None:
    """Ledger text as N1 and check the link's mass, N1.m, with the density param rho from N1.rho."""
    add_quote(root, tmp_path, text, text, values)
    edit(
        root, "params.yaml", lambda d: d["params"].update(rho={"basis": "source", "from": "N1.rho"})
    )
    edit(
        root,
        "checks.yaml",
        lambda d: d["checks"].append(
            {
                "id": "m",
                "kind": "mass",
                "parts": ["link"],
                "density": "rho",
                "evidence": "N1",
                "key": "m",
                "tol_rel": 0.05,
            }
        ),
    )


def test_mass_check_reads_the_density_in_project_units(proj_dir, tmp_path):
    # The link is 1486.9 mm³; at 1.2 g/cm³ (0.0012 g/mm³) it weighs 1.78 g.
    _mass_check(
        proj_dir,
        tmp_path,
        "The link weighs 1.8 g, printed in resin of 1.2 g/cm3.",
        {"m": 1.8, "rho": 1.2},
    )
    code, report = verify(proj_dir)
    assert code == 0 and report["status"] == "VERIFIED"
    assert findings(proj_dir, "unit-quantity") == []


@pytest.mark.parametrize(
    "text, values, ref",
    [
        ("The link weighs 1.8 g; its wall is 0.0012 mm.", {"m": 1.8, "rho": 0.0012}, "N1.rho"),
        ("The link weighs 1.8 g; the resin is 0.0012 g.", {"m": 1.8, "rho": 0.0012}, "N1.rho"),
        ("The link is 1.8 mm; the resin is 1.2 g/cm3.", {"m": 1.8, "rho": 1.2}, "N1.m"),
    ],
)
def test_mass_check_on_a_value_of_another_quantity_is_a_finding(
    proj_dir, tmp_path, text, values, ref
):
    _mass_check(proj_dir, tmp_path, text, values)
    messages = findings(proj_dir, "unit-quantity")
    assert len(messages) == 1 and messages[0].startswith(ref)


def test_guard_mass_check_density_printed_without_a_unit_takes_the_project_units(
    proj_dir, tmp_path
):
    _mass_check(
        proj_dir, tmp_path, "The link weighs 1.8 g; density 0.0012.", {"m": 1.8, "rho": 0.0012}
    )
    code, report = verify(proj_dir)
    assert code == 0 and findings(proj_dir, "unit-quantity") == []


# Tolerance policy: a loosened check is capped and always shown.


def _set_tol(root: Path, check: str, **tol) -> None:
    edit(
        root, "checks.yaml", lambda d: next(c for c in d["checks"] if c["id"] == check).update(tol)
    )


@pytest.mark.parametrize(
    "change",
    [
        lambda root: _set_tol(root, "pitch", tol=1.51),  # pitch 30: cap 1.5
        lambda root: _set_tol(root, "env", tol=0.3),  # W 5 is the smallest: cap 0.25
        lambda root: edit(root, "project.yaml", lambda d: d.update(tolerance={"length": 1e9})),
    ],
    ids=["check-tol", "bbox-smallest-axis", "project-tolerance"],
)
def test_check_tolerance_above_5_percent_of_its_expected_value_is_a_finding(proj_dir, change):
    change(proj_dir)
    code, report = verify(proj_dir)
    assert code == 1 and report["status"] == "NOT VERIFIED"
    assert "tolerance-cap" in errors(proj_dir)


def test_guard_check_tolerance_at_5_percent_of_its_expected_value(proj_dir):
    _set_tol(proj_dir, "pitch", tol=1.5)
    _set_tol(proj_dir, "env", tol=0.25)
    code, _ = verify(proj_dir)
    assert code == 0 and findings(proj_dir, "tolerance-cap") == []


def test_mass_check_tol_rel_above_a_quarter_is_a_finding(proj_dir, tmp_path):
    _mass_check(
        proj_dir,
        tmp_path,
        "The link weighs 1.8 g, printed in resin of 1.2 g/cm3.",
        {"m": 1.8, "rho": 1.2},
    )
    _set_tol(proj_dir, "m", tol_rel=0.26)
    assert errors(proj_dir) == ["tolerance-cap"]


def test_guard_mass_check_tol_rel_of_a_quarter(proj_dir, tmp_path):
    _mass_check(
        proj_dir,
        tmp_path,
        "The link weighs 1.8 g, printed in resin of 1.2 g/cm3.",
        {"m": 1.8, "rho": 1.2},
    )
    _set_tol(proj_dir, "m", tol_rel=0.25)
    code, _ = verify(proj_dir)
    assert code == 0 and findings(proj_dir, "tolerance-cap") == []


def test_report_lists_each_non_default_tolerance_beside_its_check(proj_dir, tmp_path):
    _mass_check(
        proj_dir,
        tmp_path,
        "The link weighs 1.8 g, printed in resin of 1.2 g/cm3.",
        {"m": 1.8, "rho": 1.2},
    )
    _set_tol(proj_dir, "pitch", tol=0.5)
    code, report = verify(proj_dir)
    assert code == 0
    assert report["tolerances"] == [
        {"check": "pitch", "kind": "distance", "tol": 0.5},
        {"check": "m", "kind": "mass", "tol_rel": 0.05},
    ]
    md = (proj_dir / "build" / "report.md").read_text()
    assert "| pitch | distance | tol 0.5 |" in md and "| m | mass | tol_rel 0.05 |" in md


def test_report_lists_every_length_check_under_a_project_wide_tolerance(proj_dir):
    edit(proj_dir, "project.yaml", lambda d: d.update(tolerance={"length": 0.01}))
    _, report = verify(proj_dir)
    assert report["tolerances"] == [
        {"check": "env", "kind": "bbox", "tol": 0.01},
        {"check": "pitch", "kind": "distance", "tol": 0.01},
    ]


def test_check_at_the_default_tolerance_is_not_listed(proj_dir):
    _set_tol(proj_dir, "pitch", tol=0.001)
    _, report = verify(proj_dir)
    assert report["tolerances"] == []
    assert "| pitch | distance |" not in (proj_dir / "build" / "report.md").read_text()


# Overlap limit: not a tolerance, but a loosened interference check is shown all the same.


def test_report_lists_an_interference_check_with_its_max_volume(proj_dir):
    _set_tol(proj_dir, "clear", max_volume=0.5)
    code, report = verify(proj_dir)
    assert code == 0
    assert report["overlap_limits"] == [{"check": "clear", "max_volume": 0.5}]
    assert "| clear | 0.5 |" in (proj_dir / "build" / "report.md").read_text()


def test_report_lists_an_interference_check_under_a_project_wide_tolerance(proj_dir):
    edit(proj_dir, "project.yaml", lambda d: d.update(tolerance={"length": 0.01}))
    _, report = verify(proj_dir)
    assert [o["check"] for o in report["overlap_limits"]] == ["clear"]
    assert report["overlap_limits"][0]["max_volume"] == pytest.approx(1e-6)
    assert "| clear | 1e-06 |" in (proj_dir / "build" / "report.md").read_text()


@pytest.mark.parametrize(
    "change",
    [
        lambda root: None,
        lambda root: _set_tol(root, "clear", max_volume=1e-9),
        lambda root: edit(root, "project.yaml", lambda d: d.update(tolerance={"length": 0.001})),
    ],
    ids=["unset", "max_volume-at-default", "tolerance-length-at-default"],
)
def test_guard_interference_check_at_the_default_overlap_limit_is_not_listed(proj_dir, change):
    change(proj_dir)
    _, report = verify(proj_dir)
    assert report.get("overlap_limits", []) == []
    assert not re.search(
        r"^\| clear \| [\d.e+-]+ \|$", (proj_dir / "build" / "report.md").read_text(), re.M
    )


def _ambiguous(root: Path, tmp_path: Path, quote: str) -> list[str]:
    add_quote(root, tmp_path, quote, quote, {"v": 4})
    edit(root, "params.yaml", lambda d: d["params"].update(n1={"basis": "source", "from": "N1.v"}))
    return findings(root, "unit-ambiguous")


@pytest.mark.parametrize("quote", ["4 mm pins in 4 cm links", "4 mm pins in 4 links"])
def test_value_printed_in_two_units_in_its_quote_is_a_finding(proj_dir, tmp_path, quote):
    assert len(_ambiguous(proj_dir, tmp_path, quote)) == 1


@pytest.mark.parametrize("quote", ["4 mm pins in 4 mm holes", "4 mm pins in 4 millimetre holes"])
def test_guard_value_printed_twice_in_one_unit(proj_dir, tmp_path, quote):
    assert _ambiguous(proj_dir, tmp_path, quote) == []


def test_project_units_govern_the_conversion(proj_dir, tmp_path):
    add_quote(
        proj_dir,
        tmp_path,
        "The rod is 40 mm long and weighs 300 g.",
        "40 mm long and weighs 300 g",
        {"L": 40, "m": 300},
    )
    edit(proj_dir, "project.yaml", lambda d: d.update(units={"length": "cm", "mass": "kg"}))
    edit(
        proj_dir,
        "params.yaml",
        lambda d: d["params"].update(
            L={"basis": "source", "from": "N1.L"}, m={"basis": "source", "from": "N1.m"}
        ),
    )
    _, report = verify(proj_dir)
    assert report["params"]["L"]["value"] == pytest.approx(4)
    assert report["params"]["m"]["value"] == pytest.approx(0.3)


@pytest.mark.parametrize(
    "declared", [{"length": "furlong"}, {"length": "g"}, {"torque": "N·m"}, {"length": ["mm"]}]
)
def test_project_units_must_name_a_unit_of_each_quantity(proj_dir, declared):
    edit(proj_dir, "project.yaml", lambda d: d.update(units=declared))
    messages = findings(proj_dir, "units")
    assert len(messages) == 1 and messages[0].startswith(
        f"project.yaml units.{next(iter(declared))}:"
    )


@pytest.mark.parametrize("declared", [{"length": "millimetres"}, {"force": "kN", "time": "ms"}])
def test_guard_project_units_spelled_out_or_of_other_base_quantities(proj_dir, declared):
    edit(proj_dir, "project.yaml", lambda d: d.update(units=declared))
    assert findings(proj_dir, "units") == []


def _model_reads(root: Path, tmp_path: Path, text: str) -> None:
    """Ledger text as N1 (value 40) and feed it to the model as link_L, checked by the T1 envelope."""
    add_quote(root, tmp_path, text, text, {"v": 40})
    edit(root, "params.yaml", lambda d: d["params"]["link_L"].update({"from": "N1.v"}))


@pytest.mark.parametrize("unit", ["g", "N", "s"])
def test_param_the_model_reads_printed_in_neither_a_length_nor_an_angle_is_a_finding(
    proj_dir, tmp_path, unit
):
    _model_reads(proj_dir, tmp_path, f"The link reads 40 {unit} on the gauge.")
    messages = findings(proj_dir, "unit-quantity")
    assert len(messages) == 1 and messages[0].startswith("N1.v") and "param link_L" in messages[0]


@pytest.mark.parametrize("unit", ["mm", "deg", ""])
def test_guard_param_the_model_reads_printed_in_a_length_an_angle_or_no_unit(
    proj_dir, tmp_path, unit
):
    _model_reads(proj_dir, tmp_path, f"The link reads 40 {unit} on the gauge.")
    assert findings(proj_dir, "unit-quantity") == []


def _derived_density(root: Path, tmp_path: Path, text: str, expr: str) -> list[str]:
    """unit-quantity findings when the mass check's density is derived by expr from N1.rho."""
    _mass_check(root, tmp_path, text, {"m": 1.8, "rho": 1.2})
    edit(
        root,
        "params.yaml",
        lambda d: d["params"].update(
            rho_src={"basis": "source", "from": "N1.rho"}, rho={"basis": "derived", "expr": expr}
        ),
    )
    return findings(root, "unit-quantity")


@pytest.mark.parametrize("expr", ["rho_src", "rho_src * 1", "2 * rho_src / 2"])
def test_density_derived_from_one_param_traces_to_its_quote(proj_dir, tmp_path, expr):
    messages = _derived_density(
        proj_dir, tmp_path, "The link weighs 1.8 g; its wall is 1.2 mm.", expr
    )
    assert (
        len(messages) == 1 and messages[0].startswith("N1.rho") and "param rho_src" in messages[0]
    )


@pytest.mark.parametrize(
    "text, expr",
    [
        ("The link weighs 1.8 g; resin of 1.2 g/cm3.", "rho_src * 1"),
        ("The link weighs 1.8 g; its wall is 1.2 mm.", "rho_src ** 2"),
        ("The link weighs 1.8 g; its wall is 1.2 mm.", "rho_src / pitch"),
    ],
)
def test_guard_density_derived_from_a_density_or_by_a_change_of_quantity(
    proj_dir, tmp_path, text, expr
):
    assert _derived_density(proj_dir, tmp_path, text, expr) == []


# The coverage sweep, driven by the unit table the quote reader uses.


def swept(root: Path, tmp_path: Path, capsys, text: str) -> list[str]:
    """The candidates `cadrev coverage` lists in a notes source holding text, as printed."""
    notes = tmp_path / "notes.txt"
    notes.write_text(text)
    assert (
        cli.main(
            [
                "source",
                str(root),
                str(notes),
                "--id",
                "notes",
                "--kind",
                "paper",
                "--citation",
                "Doe 2026 notes",
            ]
        )
        == 0
    )
    capsys.readouterr()
    cli.main(["coverage", str(root)])
    lines = capsys.readouterr().out.splitlines()
    return [
        line.removeprefix("notes p1: ").split("  …")[0]
        for line in lines
        if line.startswith("notes p1: ")
    ]


# Each form a hardware paper states a quantity in, and the whole candidate the sweep lists for it.
SWEPT = {
    "0.5 in": "0.5 in",
    '2"': '2"',
    "1/4 inch": "1/4 inch",
    "3 ft": "3 ft",
    "5 millimeters": "5 millimeters",
    "5 um": "5 um",
    "M3": "m3",
    "10 cm3": "10 cm3",
    "2.5 mm²": "2.5 mm2",
    "30◦": "30◦",
    "2 rad": "2 rad",
    "5 MPa": "5 mpa",
    "1.2 kgf": "1.2 kgf",
    "1.2 kg·cm": "1.2 kg·cm",
    "300 rpm": "300 rpm",
    "9 s": "9 s",
    "40%": "40%",
    "3,5 mm": "3,5 mm",
    "3–5 mm": "3-5 mm",
    "1 1/2 in": "1 1/2 in",
    "10,20,30 mm": "10,20,30 mm",
}


@pytest.mark.parametrize("form", sorted(SWEPT))
def test_coverage_lists_each_quantity_form_whole(proj_dir, tmp_path, capsys, form):
    assert swept(proj_dir, tmp_path, capsys, f"The part is {form} here.") == [SWEPT[form]]


def test_guard_coverage_lists_a_degree_sign_angle(proj_dir, tmp_path, capsys):
    assert swept(proj_dir, tmp_path, capsys, "The part is 30° here.") == ["30°"]


def test_coverage_lists_nothing_where_no_quantity_is_stated(proj_dir, tmp_path, capsys):
    assert (
        swept(
            proj_dir,
            tmp_path,
            capsys,
            "Fig. 2 shows 2 in each leg of L14 at 30 °C beside an M3a cell (doi:10.1088/ada2cc).",
        )
        == []
    )


def test_source_with_coverage_off_is_a_warning_in_the_report(proj_dir):
    edit(proj_dir, "project.yaml", lambda d: d["sources"][0].update(coverage=False))
    code, report = verify(proj_dir)
    warnings = [f for f in report["findings"] if f["rule"] == "coverage-off"]
    assert code == 0 and len(warnings) == 1 and warnings[0]["level"] == "warning"
    assert (
        f"`coverage-off`: {warnings[0]['message']}"
        in (proj_dir / "build" / "report.md").read_text()
    )


def test_guard_source_with_coverage_on_raises_no_coverage_off_warning(proj_dir):
    edit(proj_dir, "project.yaml", lambda d: d["sources"][0].update(coverage=True))
    assert findings(proj_dir, "coverage-off") == []


EXAMPLE = Path(__file__).parents[4] / "examples" / "legclaw-links"


def documented_status() -> tuple[str, int, int, int, int]:
    """The example README's expected status: status, errors, warnings, checks passed, checks."""
    documented = re.search(
        r"^Expected status: `(.+): (\d+) errors, (\d+) warnings, (\d+)/(\d+) checks pass`$",
        (EXAMPLE / "README.md").read_text(),
        re.M,
    )
    assert documented, "the example README states no expected status"
    status, *numbers = documented.groups()
    errors, warnings, passed, checks = map(int, numbers)
    return status, errors, warnings, passed, checks


def test_guard_example_reaches_the_status_its_readme_documents(tmp_path):
    root = tmp_path / "legclaw-links"
    shutil.copytree(EXAMPLE, root, ignore=shutil.ignore_patterns("build", "__pycache__"))
    code, report = verify(root)
    status = documented_status()
    assert (
        report["status"],
        report["counts"]["errors"],
        report["counts"]["warnings"],
        report["counts"]["checks_passed"],
        report["counts"]["checks"],
    ) == status
    assert code == (0 if status[0] in ("VERIFIED", "VERIFIED PENDING REVIEW") else 1)
    headline = (root / "build" / "report.md").read_text().split("\n\n")[1]
    assert headline in (EXAMPLE.parents[1] / "README.md").read_text(), (
        "the root README shows another headline"
    )


def test_guard_root_readme_shows_the_status_the_example_readme_documents():
    status, errors, warnings, passed, checks = documented_status()
    root_readme = (EXAMPLE.parents[1] / "README.md").read_text()
    assert (
        f"{status}: {errors} errors, {warnings} warnings, {passed}/{checks} checks pass. Report:"
        in root_readme
    )
    assert (
        f"**{status}**: {errors} errors, {warnings} warnings. {passed}/{checks} geometry checks pass."
        in root_readme
    )


def gitignored(root: Path, name: str, license: str | None) -> bool:
    """Whether git ignores sources/<name> after it is registered with this license."""
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    paper = root.parent / name
    paper.write_text(PAPER)
    assert (
        cli.main(
            [
                "source",
                str(root),
                str(paper),
                "--id",
                "extra",
                "--kind",
                "paper",
                "--citation",
                "Doe 2026",
                *(["--license", license] if license else []),
            ]
        )
        == 0
    )
    return (
        subprocess.run(["git", "-C", str(root), "check-ignore", "-q", f"sources/{name}"]).returncode
        == 0
    )


@pytest.mark.parametrize("license", ["CC-BY-4.0", "CC-BY-SA-4.0", "CC0-1.0", "CC BY 4.0"])
def test_source_whose_license_allows_redistribution_is_committed(proj_dir, license):
    assert not gitignored(proj_dir, "open.txt", license)


@pytest.mark.parametrize("license", [None, "CC-BY-NC-4.0", "CC-BY-ND-4.0", "all rights reserved"])
def test_guard_source_whose_license_does_not_allow_redistribution_stays_gitignored(
    proj_dir, license
):
    assert gitignored(proj_dir, "closed.txt", license)


def test_redistributable_source_whose_name_is_a_glob_is_committed_alone(proj_dir):
    assert not gitignored(proj_dir, "open[1].txt", "CC-BY-4.0")
    (proj_dir / "sources" / "open1.txt").write_text(PAPER)
    assert (
        subprocess.run(
            ["git", "-C", str(proj_dir), "check-ignore", "-q", "sources/open1.txt"]
        ).returncode
        == 0
    )


def test_redistributable_source_is_committed_from_a_project_that_ignores_all_of_sources(proj_dir):
    # Projects made before sources could be committed ignore the whole directory.
    gitignore = proj_dir / ".gitignore"
    gitignore.write_text(re.sub(r"^sources/.*$", "sources/", gitignore.read_text(), flags=re.M))
    assert not gitignored(proj_dir, "open.txt", "CC-BY-4.0")


def test_example_sources_are_committed():
    names = [
        Path(s["path"]).name
        for s in yaml.safe_load((EXAMPLE / "project.yaml").read_text())["sources"]
    ]
    listed = subprocess.run(
        ["git", "-C", str(EXAMPLE), "ls-files", "sources"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    assert sorted(listed) == sorted(f"sources/{n}" for n in names)


# Real PDF and DOCX sources, and the commands that read them.

PAPER_PAGES = ("Table 1. Dimensions of key components\nLink 40x8x5", PAPER.split("\n", 3)[3])


def pdf(pages: list[str], image: bool = False) -> bytes:
    """A PDF with one page per text, each line drawn as text; image puts a 2x2 picture on page 1."""
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    if image:
        objects.append(
            b"<< /Type /XObject /Subtype /Image /Width 2 /Height 2 /ColorSpace /DeviceRGB "
            b"/BitsPerComponent 8 /Length 12 >>\nstream\n"
            + bytes(range(0, 240, 20))
            + b"\nendstream"
        )
    kids = []
    for n, text in enumerate(pages):
        lines = [
            line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            for line in text.splitlines()
        ]
        draw = "".join(
            f"BT /F1 10 Tf 72 {720 - 14 * i} Td ({line}) Tj ET\n" for i, line in enumerate(lines)
        )
        if image and n == 0:
            draw += "q 50 0 0 50 72 400 cm /Im1 Do Q\n"
        stream = draw.encode("latin-1")
        objects.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
        content = len(objects)
        xobject = b" /XObject << /Im1 4 0 R >>" if image and n == 0 else b""
        objects.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents %d 0 R "
            b"/Resources << /Font << /F1 3 0 R >>%s >> >>" % (content, xobject)
        )
        kids.append(len(objects))
    objects[1] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (
        b" ".join(b"%d 0 R" % k for k in kids),
        len(kids),
    )
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for i, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref,
    )
    return bytes(out)


def docx(text: str, image: bytes | None = None, media: str = "image1.png") -> bytes:
    """A DOCX with one paragraph per line of text, and image as word/media/<media>."""
    body = "".join(f"<w:p><w:r><w:t>{line}</w:t></w:r></w:p>" for line in text.splitlines())
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/'
        f'wordprocessingml/2006/main"><w:body>{body}</w:body></w:document>'
    )
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("word/document.xml", xml)
        if image is not None:
            z.writestr(f"word/media/{media}", image)
    return out.getvalue()


def png(format: str = "PNG") -> bytes:
    from PIL import Image

    out = io.BytesIO()
    Image.new("RGB", (4, 2), "red").save(out, format=format)
    return out.getvalue()


def add_source(root: Path, tmp_path: Path, name: str, content: bytes) -> None:
    """Register content, saved as name, as source doc."""
    path = tmp_path / name
    path.write_bytes(content)
    register = ["source", str(root), str(path), "--id", "doc", "--kind", "paper"]
    assert cli.main([*register, "--citation", "Doe 2026"]) == 0


def test_guard_text_prints_each_page_of_a_pdf_as_extracted(proj_dir, tmp_path):
    add_source(proj_dir, tmp_path, "paper.pdf", pdf(list(PAPER_PAGES)))
    code, out = run("text", str(proj_dir), "doc")
    assert code == 0
    assert "===== doc page 1/2 =====\nTable 1. Dimensions of key components\nLink 40x8x5" in out
    assert "===== doc page 2/2 =====" in out and "spaced 30 mm apart" in out


def test_guard_text_prints_one_page_or_the_lines_matching_a_pattern(proj_dir, tmp_path):
    add_source(proj_dir, tmp_path, "paper.pdf", pdf(list(PAPER_PAGES)))
    assert run("text", str(proj_dir), "doc", "--page", "1")[1].count("=====") == 2
    assert run("text", str(proj_dir), "doc", "--grep", "MM APART")[1] == (
        "p2: The pivot holes of the link are spaced 30 mm apart.\n"
    )


def test_guard_text_prints_a_docx_as_one_page_of_paragraphs(proj_dir, tmp_path):
    add_source(proj_dir, tmp_path, "paper.docx", docx(PAPER))
    code, out = run("text", str(proj_dir), "doc")
    assert (code, out) == (0, f"===== doc page 1/1 =====\n{PAPER.rstrip()}\n")


def test_guard_text_of_an_unregistered_source_is_refused(proj_dir, capsys):
    assert cli.main(["text", str(proj_dir), "notes"]) == 1
    assert "unknown source 'notes'; registered: paper" in capsys.readouterr().err


@pytest.mark.parametrize(
    "name, content, written",
    [
        ("paper.pdf", lambda: pdf(list(PAPER_PAGES), image=True), "figures/doc/p001_01"),
        ("paper.docx", lambda: docx(PAPER, image=png()), "figures/doc/image1.png"),
    ],
)
def test_guard_figures_extracts_each_embedded_image(proj_dir, tmp_path, name, content, written):
    add_source(proj_dir, tmp_path, name, content())
    code, out = run("figures", str(proj_dir), "doc")
    assert code == 0 and len(out.splitlines()) == 1 and out.startswith(written)
    assert (proj_dir / out.strip()).stat().st_size > 0


def test_figures_writes_an_image_a_viewer_cannot_show_as_png(proj_dir, tmp_path):
    from PIL import Image

    add_source(proj_dir, tmp_path, "supp.docx", docx(PAPER, image=png("TIFF"), media="image1.tiff"))
    code, out = run("figures", str(proj_dir), "doc")
    assert (code, out) == (0, "figures/doc/image1.png\n")
    with Image.open(proj_dir / "figures" / "doc" / "image1.png") as image:
        assert (image.format, image.size) == ("PNG", (4, 2))


def test_guard_figures_of_a_source_without_images_writes_nothing(proj_dir):
    assert run("figures", str(proj_dir), "paper") == (0, "")


def test_guard_crop_writes_the_region_zoomed_and_prints_its_sha256(proj_dir):
    from PIL import Image

    (proj_dir / "figures").mkdir(exist_ok=True)
    Image.new("RGB", (40, 20), "white").save(proj_dir / "figures" / "page2.png")
    code, out = run(
        "crop",
        str(proj_dir),
        "figures/page2.png",
        "0",
        "0",
        "10",
        "5",
        "--name",
        "c",
        "--zoom",
        "3",
    )
    crop = proj_dir / "figures" / "crops" / "c.png"
    assert (code, out) == (0, f"image: figures/crops/c.png\nimage_sha256: {sha256(crop)}\n")
    with Image.open(crop) as image:
        assert image.size == (30, 15)


# Trips from the dogfood run (docs/dogfood/legclaw-run-log.md): each is a place a fresh agent
# reconstructing the full LegClaw met a crash, a false finding or a silent wrong answer.


def _placed(*instances: str) -> str:
    """The fixture's model with the link placed at each Location in instances."""
    entries = ", ".join(f'"link_{i}": ("link", {loc})' for i, loc in enumerate(instances, 1))
    return MODEL.replace('{"link_1": ("link", Location())}', "{" + entries + "}")


def test_interference_between_overlapping_instances_fails_the_check_without_a_traceback(
    proj_dir,
):
    write(proj_dir, "model.py", _placed("Location()", "Location((p.pitch / 2, 0, 0))"))
    code, report = verify(proj_dir)
    assert code == 1
    clear = next(c for c in report["checks"] if c["id"] == "clear")
    assert not clear["ok"] and "link_1 ∩ link_2" in clear["measured"]
    assert "check-failed" in [f["rule"] for f in report["findings"]]


def test_interference_check_with_no_overlap_names_no_pair(proj_dir):
    write(proj_dir, "model.py", _placed("Location()", "Location((0, 0, p.link_H * 2))"))
    code, report = verify(proj_dir)
    clear = next(c for c in report["checks"] if c["id"] == "clear")
    assert code == 0 and clear["ok"] and "∩" not in clear["measured"]


def _mass_with_hardware(root: Path, tmp_path: Path, hardware: dict) -> None:
    """The link's mass check, with the density rho and the param hardware as its add."""
    values = {"m": 2.8, "rho": 1.2} | ({"screws": 1} if "from" in hardware else {})
    text = "The link weighs 2.8 g with 1 g of screws, printed in resin of 1.2 g/cm3."
    _mass_check(root, tmp_path, text, values)
    edit(root, "params.yaml", lambda d: d["params"].update(hardware=hardware))
    edit(root, "checks.yaml", lambda d: d["checks"][-1].update(add=["hardware"]))


def test_params_only_a_mass_check_reads_are_not_unused(proj_dir, tmp_path):
    _mass_with_hardware(
        proj_dir,
        tmp_path,
        {"basis": "proposed", "value": 1, "rationale": "screws by count", "gap": "G1"},
    )
    code, report = verify(proj_dir)
    assert code == 0, report["findings"]
    assert findings(proj_dir, "param-unused") == []


def test_source_param_a_mass_check_adds_is_checked_by_it(proj_dir, tmp_path):
    _mass_with_hardware(proj_dir, tmp_path, {"basis": "source", "from": "N1.screws"})
    code, report = verify(proj_dir)
    assert code == 0, report["findings"]
    assert findings(proj_dir, "unchecked-source") == []


_TWO_PARTS = MODEL.replace(
    '"parts": {"link": link},', '"parts": {"link": link, "pin": Cylinder(p.hole_d / 2, p.link_H)},'
).replace('"link.b": (p.pitch / 2, 0, 0)}', '"link.b": (p.pitch / 2, 0, 0), "pin.c": (0, 0, 0)}')


def test_distance_between_datums_of_two_parts_is_a_finding(proj_dir):
    write(proj_dir, "model.py", _TWO_PARTS)
    edit(proj_dir, "checks.yaml", lambda d: d["checks"][1].update(between=["link.a", "pin.c"]))
    messages = findings(proj_dir, "check-config")
    assert len(messages) == 1 and "link.a" in messages[0] and "pin.c" in messages[0]


def test_guard_distance_between_datums_of_one_part_beside_another_part(proj_dir):
    write(proj_dir, "model.py", _TWO_PARTS)
    assert findings(proj_dir, "check-config") == []


# Datums are confirmed on their part's solid (ADR-0006). The fixture's link is 40 x 5 x 8, centred
# on the origin, with its holes 3 across on the Z axis at x = ±15.


def _datum(at: str, model: str = MODEL):
    """The fixture's model returning one more datum, link.extra at the point expression at."""
    return model.replace(
        '"link.b": (p.pitch / 2, 0, 0)}', f'"link.b": (p.pitch / 2, 0, 0), "link.extra": {at}}}'
    )


def _datum_at(root: Path, at: str, model: str = MODEL) -> list[str]:
    """The datum-off-solid messages of a run whose model also returns link.extra at at."""
    write(root, "model.py", _datum(at, model))
    return findings(root, "datum-off-solid")


_SLOT = MODEL.replace(
    "    return {",
    "    link -= extrude(SlotCenterToCenter(p.pitch / 2, p.hole_d), p.link_H, both=True)\n"
    "    return {",
)


def test_guard_datum_at_a_hole_centre_on_its_axis_raises_no_finding(proj_dir):
    assert findings(proj_dir, "datum-off-solid") == []


def test_guard_datum_on_a_slot_end_axis_raises_no_finding(proj_dir):
    assert _datum_at(proj_dir, "(p.pitch / 2 / 2, 0, 0)", _SLOT) == []


def test_guard_datum_on_an_end_face_raises_no_finding(proj_dir):
    assert _datum_at(proj_dir, "(p.link_L / 2, 0, 0)") == []


def test_datum_inside_the_solid_where_no_hole_is_is_off_solid(proj_dir):
    messages = _datum_at(proj_dir, "(0, 0, 0)")
    assert len(messages) == 1
    assert "link.extra" in messages[0] and "part link" in messages[0] and "2.5" in messages[0]


def test_datum_in_mid_air_is_off_solid(proj_dir):
    messages = _datum_at(proj_dir, "(0, 0, p.link_L)")
    assert len(messages) == 1 and "link.extra" in messages[0] and "36" in messages[0]


def test_datum_on_a_hole_axis_beyond_the_hole_is_off_solid(proj_dir):
    messages = _datum_at(proj_dir, "(p.pitch / 2, 0, p.link_L)")
    assert len(messages) == 1 and "link.extra" in messages[0] and "36" in messages[0]


def test_datum_a_check_reads_is_off_solid_too(proj_dir):
    write(
        proj_dir, "model.py", MODEL.replace('"link.b": (p.pitch / 2, 0, 0)', '"link.b": (0, 0, 0)')
    )
    messages = findings(proj_dir, "datum-off-solid")
    assert len(messages) == 1 and "link.b" in messages[0]


def test_part_of_two_disjoint_solids_is_invalid(proj_dir):
    split = "link += Pos(p.link_L, 0, 0) * Box(p.link_W, p.link_W, p.link_H)\n    return {"
    write(proj_dir, "model.py", MODEL.replace("return {", split))
    messages = findings(proj_dir, "part-invalid")
    assert len(messages) == 1 and "2 solids" in messages[0]


def test_guard_part_of_two_touching_bodies_fused_into_one_solid(proj_dir):
    fused = "link += Pos(p.link_L / 2, 0, 0) * Box(p.link_W, p.link_W, p.link_H)\n    return {"
    write(proj_dir, "model.py", MODEL.replace("return {", fused))
    assert findings(proj_dir, "part-invalid") == []


def _skip_in_pdf(root: Path, tmp_path: Path, **skip) -> None:
    """Register the paper as a two-page PDF, source doc, skipping skip in it."""
    add_source(root, tmp_path, "paper.pdf", pdf(list(PAPER_PAGES)))
    skips = [{"source": "doc", "reason": "the paper again", **skip}]
    edit(root, "evidence.yaml", lambda d: d["skipped"].extend(skips))


@pytest.mark.parametrize(
    "skip",
    [
        {"from": "Link 40", "to": "diameter."},  # a block that runs onto the next page
        {"quote": "branches of 70 mm diameter"},
        {"quote": "spaced 30 mm apart", "page": 1},
    ],
    ids=["from-to-across-pages", "quote-not-in-source", "quote-on-another-page"],
)
def test_skip_that_matches_nothing_is_a_finding(proj_dir, tmp_path, skip):
    _skip_in_pdf(proj_dir, tmp_path, **skip)
    assert "skip-not-found" in rules(proj_dir)


@pytest.mark.parametrize(
    "skip",
    [
        {"from": "Link 40", "to": "8x5"},
        {"from": "pivot holes", "to": "diameter."},
        {"quote": "spaced 30 mm apart", "page": 2},
        {"pages": [1]},
    ],
)
def test_guard_skip_that_matches_on_one_page(proj_dir, tmp_path, skip):
    _skip_in_pdf(proj_dir, tmp_path, **skip)
    assert "skip-not-found" not in rules(proj_dir)


def _mass_of_two_links(root: Path, tmp_path: Path, count) -> None:
    """A mass check of two links, 1.78 g each, counting the link by count."""
    text = "Two links weigh 3.6 g, printed in resin of 1.2 g/cm3."
    _mass_check(root, tmp_path, text, {"m": 3.6, "rho": 1.2})
    edit(root, "checks.yaml", lambda d: d["checks"][-1].update(counts={"link": count}))


def test_mass_check_counts_a_part_by_the_param_it_names(proj_dir, tmp_path):
    _mass_of_two_links(proj_dir, tmp_path, "n_links")
    add_params(
        proj_dir,
        n_links={"basis": "proposed", "value": 2, "rationale": "'two links'", "gap": "G1"},
    )
    code, report = verify(proj_dir)
    assert code == 0, report["findings"]
    assert report["params"]["n_links"]["rests_on"] == "proposed"
    assert findings(proj_dir, "param-unused") == []


def test_mass_check_count_given_as_a_bare_number_is_a_finding(proj_dir, tmp_path):
    _mass_of_two_links(proj_dir, tmp_path, 2)
    messages = findings(proj_dir, "schema")
    assert len(messages) == 1 and "counts" in messages[0]


def test_report_md_labels_the_declared_bases_apart_from_what_params_rest_on(proj_dir):
    add_params(proj_dir, half={"basis": "derived", "expr": "hole_d / 2"})
    write(proj_dir, "model.py", MODEL.replace("p.hole_d / 2", "p.half"))
    verify(proj_dir)
    md = (proj_dir / "build" / "report.md").read_text()
    assert "Declared basis: source: 4 · derived: 1 · measured: 0 · proposed: 1" in md


def test_reregistering_a_source_takes_its_new_citation_url_and_license(proj_dir):
    subprocess.run(["git", "init", "-q", str(proj_dir)], check=True)
    paper = proj_dir / "sources" / "paper.txt"
    code, _ = run(
        "source",
        str(proj_dir),
        str(paper),
        "--id",
        "paper",
        "--kind",
        "paper",
        "--citation",
        "Doe 2026, Adv. Sci.",
        "--url",
        "https://doi.org/10.0/doe",
        "--license",
        "CC-BY-4.0",
    )
    (entry,) = yaml.safe_load((proj_dir / "project.yaml").read_text())["sources"]
    assert code == 0
    assert (entry["citation"], entry["url"], entry["license"]) == (
        "Doe 2026, Adv. Sci.",
        "https://doi.org/10.0/doe",
        "CC-BY-4.0",
    )
    ignored = subprocess.run(
        ["git", "-C", str(proj_dir), "check-ignore", "-q", "sources/paper.txt"]
    )
    assert ignored.returncode == 1


@pytest.mark.parametrize("sid", ["paper", "second"])
def test_source_citation_with_quotes_and_apostrophes_is_written_as_given(proj_dir, sid):
    citation = 'O\'Neil "LegClaw", 2026'
    paper = proj_dir / "sources" / "paper.txt"
    args = ["--id", sid, "--kind", "paper", "--citation", citation]
    code, _ = run("source", str(proj_dir), str(paper), *args, "--rename", f"{sid}.txt")
    entries = yaml.safe_load((proj_dir / "project.yaml").read_text())["sources"]
    assert code == 0 and [e["citation"] for e in entries if e["id"] == sid] == [citation]


def _flow_param(root: Path, rationale: str) -> None:
    """Add the param spare to params.yaml as a flow mapping, its rationale written as given."""
    flow = f"  spare: {{basis: proposed, value: 3, rationale: {rationale}, gap: G1}}\n"
    (root / "params.yaml").write_text((root / "params.yaml").read_text() + flow)


def test_unknown_key_in_an_entry_is_a_finding_naming_it(proj_dir):
    # An unquoted comma in a flow mapping splits the value: "or a washer" becomes a key.
    _flow_param(proj_dir, "a spacer, or a washer")
    messages = findings(proj_dir, "schema")
    assert len(messages) == 1 and "'or a washer'" in messages[0]


def test_guard_comma_inside_a_quoted_value_is_one_value(proj_dir):
    _flow_param(proj_dir, "'a spacer, or a washer'")
    assert findings(proj_dir, "schema") == []


def test_verification_run_writes_nothing_into_the_project_outside_build(proj_dir):
    before = {p for p in proj_dir.rglob("*")}
    verify(proj_dir)
    assert {p for p in proj_dir.rglob("*") if "build" not in p.relative_to(proj_dir).parts} == {
        p for p in before if "build" not in p.relative_to(proj_dir).parts
    }


# Every rule beside its near miss. scripts/rule-coverage fails CI unless each rule the tool emits is
# asserted present by one test and absent by another; a rule no other test covers both ways gets a
# row here: the change to the fixture that raises it, and the closest changes it must accept.


def rules(root: Path) -> list[str]:
    """The rule of every finding, error or warning, from a fresh verification run."""
    return [f["rule"] for f in verify(root)[1]["findings"]]


def _append(name: str, key: str, entry: dict):
    return lambda r, t: edit(r, name, lambda d: d.setdefault(key, []).append(entry))


def _check(cid: str, **changes):
    def change(r, t):
        edit(
            r,
            "checks.yaml",
            lambda d: next(c for c in d["checks"] if c["id"] == cid).update(changes),
        )

    return change


def _evidence(eid: str, **changes):
    """Change evidence eid's fields; a field changed to None is removed."""

    def change(r, t):
        def apply(d):
            item = next(e for e in d["evidence"] if e["id"] == eid)
            item.update(changes)
            for key in [k for k, v in changes.items() if v is None]:
                item.pop(key)

        edit(r, "evidence.yaml", apply)

    return change


def _param(name: str, **spec):
    """Set param name's fields, adding the param if it is new; a field set to None is removed."""

    def change(r, t):
        def apply(d):
            merged = {**d["params"].get(name, {}), **spec}
            d["params"][name] = {k: v for k, v in merged.items() if v is not None}

        edit(r, "params.yaml", apply)

    return change


def _source(**changes):
    return lambda r, t: edit(r, "project.yaml", lambda d: d["sources"][0].update(changes))


def _skip(**skip):
    """Replace the fixture's skip of its one test condition with skip."""
    return lambda r, t: edit(
        r, "evidence.yaml", lambda d: d.update(skipped=[{"source": "paper", **skip}])
    )


def _assembly(entry: str):
    return lambda r, t: write(
        r, "model.py", MODEL.replace('{"link_1": ("link", Location())}', entry)
    )


def _shell(faces: str):
    """The link rebuilt as a solid from a shell of its faces[faces]."""
    part = f'{{"link": Solid(Shell(link.faces(){faces}))}}'
    return lambda r, t: write(r, "model.py", MODEL.replace('{"link": link}', part))


def _reading(**fields):
    return lambda r, t: add_reading(r, **fields)


def _unpinned_reading(r, t):
    add_reading(r)
    (r / "figures" / "crops" / "fig2.png").unlink()


def _measured(*missing: str):
    def change(r, t):
        add_measured(r)
        edit(r, "params.yaml", lambda d: [d["params"]["foot_w"].pop(k) for k in missing])

    return change


def _weighs(grams: str):
    """A mass check of the link, 1.78 g in resin of 1.2 g/cm3, against a source giving grams."""
    text = f"The link weighs {grams} g, printed in resin of 1.2 g/cm3."
    return lambda r, t: _mass_check(r, t, text, {"m": float(grams), "rho": 1.2})


def _reregister(r, t):
    paper = t / "paper.txt"
    paper.write_text(PAPER + "Received 1 March.\n")
    register = ["source", str(r), str(paper), "--id", "paper", "--kind", "paper"]
    assert cli.main([*register, "--citation", "Doe 2026"]) == 0


def _quote_from(name: str, quote: str, page: int | None = None):
    """Register the paper as a two-page PDF or a DOCX, source doc, and ledger quote from it as N1."""

    def change(r, t):
        content = pdf(list(PAPER_PAGES)) if name.endswith(".pdf") else docx(PAPER)
        add_source(r, t, name, content)
        entry = {
            "id": "N1",
            "source": "doc",
            "locator": "Sec. 2",
            "quote": quote,
            "values": {"pitch": 30},
            "scope": "context",
            "reason": "the paper again",
        }
        edit(
            r,
            "evidence.yaml",
            lambda d: d["evidence"].append({**entry, **({"page": page} if page else {})}),
        )

    return change


_EXTRA = {
    "id": "extra",
    "source": "paper",
    "locator": "Sec. 3",
    "quote": "branches of 60 mm diameter",
}
_CONFLICT = {"id": "C1", "evidence": ["T1-link", "pitch"], "summary": "pitch exceeds the link"}
_MOVED = MODEL.replace("\n\n\n", "\n\n# v1\n")

FINDINGS = {
    "assembly-part": (
        _assembly('{"link_1": ("pin", Location())}'),
        [_assembly('{"pin": ("link", Location())}')],
    ),
    "check-config": (_check("pitch", along="w"), [_check("pitch", along="x")]),
    "check-failed": (_weighs("2.0"), [_weighs("1.8")]),
    "check-kind": (_check("clear", kind="overlap"), [_weighs("1.8")]),
    "conflict-open": (
        _append("evidence.yaml", "conflicts", _CONFLICT),
        [_append("evidence.yaml", "conflicts", {**_CONFLICT, "resolution": "Table 1 rules"})],
    ),
    "conflict-ref": (
        _append("evidence.yaml", "conflicts", {**_CONFLICT, "evidence": ["T2-link"]}),
        [_append("evidence.yaml", "conflicts", _CONFLICT)],
    ),
    "coverage": (
        _skip(quote="branches of", reason="test condition"),
        [
            _skip(pages=[1], reason="test conditions only"),
            _skip(**{"from": "Tests used", "to": "diameter."}, reason="test condition"),
        ],
    ),
    "datum-off-solid": (
        lambda r, t: write(r, "model.py", _datum("(0, 0, p.link_L)")),
        [
            lambda r, t: write(r, "model.py", _datum("(p.link_L / 2, 0, 0)")),
            lambda r, t: write(r, "model.py", _datum("(p.pitch / 2, 0, p.link_H / 2)")),
        ],
    ),
    "evidence-anchor": (_evidence("pitch", quote=None), [_reading()]),
    "evidence-id": (
        _append(
            "evidence.yaml",
            "evidence",
            {**_EXTRA, "id": "pitch", "scope": "context", "reason": "r"},
        ),
        [_append("evidence.yaml", "evidence", {**_EXTRA, "scope": "context", "reason": "r"})],
    ),
    "evidence-locator": (
        _evidence("pitch", locator=None),
        [_evidence("pitch", locator="p. 1, line 4")],
    ),
    "evidence-scope": (
        _append("evidence.yaml", "evidence", {**_EXTRA, "scope": "not-modeled"}),
        [
            _append(
                "evidence.yaml", "evidence", {**_EXTRA, "scope": "not-modeled", "reason": "a test"}
            )
        ],
    ),
    "evidence-source": (
        _evidence("pitch", source="notes"),
        [lambda r, t: add_quote(r, t, "spaced 30 mm apart", "30 mm", {"pitch": 30})],
    ),
    "evidence-unused": (
        _append("evidence.yaml", "evidence", {**_EXTRA, "values": {"d": 60}}),
        [
            _append(
                "evidence.yaml",
                "evidence",
                {
                    **_EXTRA,
                    "values": {"d": 60},
                    "scope": "not-modeled",
                    "reason": "a test condition",
                },
            )
        ],
    ),
    "evidence-values": (
        _append("evidence.yaml", "evidence", _EXTRA),
        [_append("evidence.yaml", "evidence", {**_EXTRA, "scope": "context", "reason": "a test"})],
    ),
    "image-hash": (_reading(image_sha256="0" * 64), [_reading()]),
    "image-missing": (_unpinned_reading, [_reading()]),
    "image-reading": (_reading(reading=""), [_reading(reading="70")]),
    "model-arithmetic": (
        lambda r, t: _model_with(r, line="extra = 2 * 2 - 0.5"),
        [lambda r, t: _model_with(r, line="extra = 2 * 2 - 2")],
    ),
    "model-build": (
        lambda r, t: _model_with(r, line="extra = p.pitch_2"),
        [lambda r, t: _model_with(r, line="extra = p.pitch")],
    ),
    "model-literal": (
        lambda r, t: _model_with(r, line="extra = 7.5"),
        [lambda r, t: _model_with(r, line="extra = 0.5")],
    ),
    "model-missing": (
        lambda r, t: (r / "model.py").rename(r / "model_v1.py"),
        [lambda r, t: (r / "model.py").write_text(_MOVED)],
    ),
    "overlay-config": (
        lambda r, t: _overlay(r, view="side"),
        [lambda r, t: _overlay(r, view="right")],
    ),
    "param-basis": (_param("hole_d", basis="assumed"), [lambda r, t: _no_proposed(r)]),
    "param-derived": (
        _param("half", basis="derived", expr="pitch /"),
        [_param("half", basis="derived", expr="pitch / 2")],
    ),
    "param-from": (
        _param("link_W", **{"from": "T1-link.D"}),
        [_param("half_L", basis="source", **{"from": "T1-link.L"})],
    ),
    "param-gap": (
        lambda r, t: write(r, "gaps.yaml", {"gaps": []}),
        [lambda r, t: write(r, "gaps.yaml", {"gaps": [{"id": "G1", "question": "pin diameter?"}]})],
    ),
    "param-measured": (_measured("uncertainty"), [_measured()]),
    "param-mismatch": (
        _param("half", basis="derived", expr="pitch / 2", value=14),
        [_param("half", basis="derived", expr="pitch / 2", value=15)],
    ),
    "param-proposed": (_param("hole_d", rationale=None), [_param("hole_d", rationale="an M3 pin")]),
    "param-unused": (
        _param("spare", basis="proposed", value=3, rationale="x", gap="G1"),
        [
            lambda r, t: (
                _param("base", basis="proposed", value=3, rationale="x", gap="G1")(r, t),
                _param(
                    "hole_d", basis="derived", expr="base * 1", value=None, rationale=None, gap=None
                )(r, t),
            )
        ],
    ),
    "part-invalid": (_shell("[1:]"), [_shell("")]),
    "quote-not-found": (
        _quote_from("paper.pdf", "spaced 30 mm apart", page=1),
        [_quote_from("paper.docx", "pivot holes of the link are spaced 30 mm")],
    ),
    "quote-page": (
        _quote_from("paper.pdf", "spaced 30 mm apart"),
        [
            _quote_from("paper.pdf", "spaced 30 mm apart", page=2),
            _quote_from("paper.docx", "30 mm apart"),
        ],
    ),
    "skip-anchor": (_skip(reason="test condition"), [_skip(pages=[1], reason="test condition")]),
    "skip-reason": (
        _skip(quote="branches of 60 mm diameter"),
        [_skip(quote="branches of 60 mm diameter", reason="a test load")],
    ),
    "source-citation": (_source(citation=""), [_source(citation="Doe")]),
    "source-hash": (
        lambda r, t: (r / "sources" / "paper.txt").write_text(PAPER + "Received 1 March.\n"),
        [_reregister],
    ),
    "source-kind": (_source(kind="book"), [_source(kind="other")]),
    "source-missing": (
        lambda r, t: (r / "sources" / "paper.txt").unlink(),
        [lambda r, t: ((r / "sources" / "paper.txt").unlink(), _reregister(r, t))],
    ),
    "target": (
        lambda r, t: edit(r, "project.yaml", lambda d: d.update(target="TODO name the object")),
        [
            lambda r, t: edit(
                r, "project.yaml", lambda d: d.update(target="A link, v1 (TODO: year)")
            )
        ],
    ),
    "unchecked-source": (
        lambda r, t: edit(r, "checks.yaml", lambda d: d["checks"].pop(1)),
        [_check("pitch", along="x")],
    ),
    "value-not-in-reading": (_reading(values={"w": 71}), [_reading(values={"w": 70})]),
}


@pytest.mark.parametrize("rule", sorted(FINDINGS))
def test_guard_change_raises_its_rule(proj_dir, tmp_path, rule):
    FINDINGS[rule][0](proj_dir, tmp_path)
    assert rule in rules(proj_dir)


@pytest.mark.parametrize(
    "rule, miss", [(rule, i) for rule in sorted(FINDINGS) for i in range(len(FINDINGS[rule][1]))]
)
def test_guard_near_miss_raises_no_rule(proj_dir, tmp_path, rule, miss):
    FINDINGS[rule][1][miss](proj_dir, tmp_path)
    assert rule not in rules(proj_dir)
