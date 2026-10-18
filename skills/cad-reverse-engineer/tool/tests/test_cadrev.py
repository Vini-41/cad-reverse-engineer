import json
import re
import shutil
import subprocess
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


def test_report_json_has_the_keys_project_format_documents(proj_dir):
    doc = (Path(__file__).parents[2] / "references" / "project-format.md").read_text()
    rows = dict(re.findall(r"^\| `(\w+)` \| (.*) \|$", doc.split("## build/report.json")[1], re.M))
    _, report = verify(proj_dir)
    assert set(report) == set(rows), "report.json and project-format.md list different keys"
    assert set(report["counts"]) == set(re.findall(r"`(\w+)`", rows["counts"]))


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
    sources.pages.cache_clear()
    assert "source-hash" in errors(proj_dir)


def test_model_literal_is_rejected(proj_dir):
    write(proj_dir, "model.py", MODEL.replace("p.link_H)\n    link -=", "7.5)\n    link -=", 1))
    assert "model-literal" in errors(proj_dir)


def test_unledgered_stated_quantity_is_reported(proj_dir):
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
    """Ledger a pinned Fig. 2 crop whose reading no human has confirmed; return its entry."""
    crop = root / "figures" / "crops" / "fig2.png"
    crop.parent.mkdir(parents=True, exist_ok=True)
    crop.write_bytes(b"a figure label")
    entry = {
        "id": "F2",
        "source": "paper",
        "locator": "Fig. 2",
        "scope": "context",
        "reason": "label",
        "image": "figures/crops/fig2.png",
        "image_sha256": sources.sha256(crop),
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
        ("paper", "sources/paper-v2.txt", sources.sha256(paper))
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
    assert after[0] == {**before[0], "sha256": sources.sha256(proj_dir / "sources" / "paper.txt")}


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
    sources.pages.cache_clear()
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
                "counts": {"link": "x"},
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
    sources.pages.cache_clear()
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


def test_example_reaches_the_status_its_readme_documents(tmp_path):
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
