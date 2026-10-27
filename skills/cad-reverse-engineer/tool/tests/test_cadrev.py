import ast
import contextlib
import hashlib
import importlib
import io
import json
import math
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest
import yaml
from build123d import Axis, Box, Compound, Cylinder, Location, Pos, chamfer, export_step

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
    meta.write_text(swap(meta.read_text(), "TODO one sentence", "A demo link,"))
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


def swap(text: str, old: str, new: str, count: int = -1, *, regex: bool = False) -> str:
    """text with old replaced by new, failing when old is absent, so editing a fixture never leaves
    it as it was. With regex, old is a pattern matched line by line."""
    if regex:
        out, found = re.subn(old, new, text, count=max(count, 0), flags=re.M)
    else:
        out, found = text.replace(old, new, count), old in text
    assert found, f"{old!r} is not in the text it should replace"
    return out


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
        "physics_proposed": 0,
    }


def test_guard_report_json_has_the_keys_project_format_documents(proj_dir):
    doc = (Path(__file__).parents[2] / "references" / "project-format.md").read_text()
    rows = dict(re.findall(r"^\| `(\w+)` \| (.*) \|$", doc.split("## build/report.json")[1], re.M))
    _, report = verify(proj_dir)
    assert set(report) == set(rows), "report.json and project-format.md list different keys"
    assert set(report["counts"]) == set(re.findall(r"`(\w+)`", rows["counts"]))


def test_guard_project_format_examples_name_only_gaps_and_params_they_define():
    doc = (Path(__file__).parents[2] / "references" / "project-format.md").read_text()

    def example(heading: str) -> dict:
        section = doc.split(f"\n## {heading}\n")[1]
        return yaml.safe_load(section.split("```yaml\n")[1].split("```")[0])

    params, gaps = example("params.yaml")["params"], example("gaps.yaml")["gaps"]
    named = {s["gap"] for s in params.values() if "gap" in s}
    assert named <= {g["id"] for g in gaps}, "a param example names a gap the gaps.yaml lacks"
    read = {
        n.id
        for s in params.values()
        if "expr" in s
        for n in ast.walk(ast.parse(s["expr"]))
        if isinstance(n, ast.Name)
    }
    assert read <= params.keys(), "an expr example reads a param the params.yaml lacks"


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


@pytest.mark.parametrize(
    "text, quote",
    [
        ("and two dual-\naxis servos of 12 mm serve", "two dual-axis servos of 12 mm"),
        ("and two dual-\naxis servos of 12 mm serve", "two dual- axis servos of 12 mm"),
        ("with an inter-\ntoe gap of 12 mm", "with an inter- toe gap of 12 mm"),
    ],
)
def test_quote_copied_across_a_hyphenated_line_break_matches(proj_dir, tmp_path, text, quote):
    add_quote(proj_dir, tmp_path, text, quote, {"L": 12})
    rules = errors(proj_dir)
    assert "quote-not-found" not in rules and "coverage" not in rules


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


def add_quote(
    root: Path, tmp_path: Path, text: str, quote: str, values: dict, name: str = "notes.txt"
) -> None:
    """Register one more source holding text, saved as name, and ledger quote from it as evidence
    N1."""
    notes = tmp_path / name
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


DATASHEET_QUOTES = pytest.mark.parametrize(
    "quote, values", [("Weight 20.6 g", {"m": 20.6}), ("Servo & horn", {})], ids=["cells", "entity"]
)


@DATASHEET_QUOTES
def test_quote_across_an_html_sources_table_cells_or_entity_matches(
    proj_dir, tmp_path, quote, values
):
    add_quote(proj_dir, tmp_path, DATASHEET_HTML.decode(), quote, values, "ds.html")
    assert "quote-not-found" not in errors(proj_dir)


@DATASHEET_QUOTES
def test_guard_quote_of_the_datasheet_matches_its_txt_copy(proj_dir, tmp_path, quote, values):
    add_quote(proj_dir, tmp_path, "Servo & horn\nWeight\n20.6 g\n", quote, values, "ds.txt")
    assert "quote-not-found" not in errors(proj_dir)


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
    "a 1/4-in. bolt": ([0.25], [1, 4]),
    "Eight tension springs": ([8], [18]),
    "twenty-four bolts": ([24], [20, 4]),
    "twenty four bolts": ([24], [20, 4]),
    "twenty-\nfour bolts": ([24], [20, 4]),
    "eighteen springs": ([18], [8]),
    "the weight of the springs": ([], [8]),
    "seventy links": ([70], [7]),
    "the first link": ([], [1]),
    "a pair of pins": ([], [1, 2]),
    "one of the links": ([1], []),
    "the twenty-first link": ([], [20, 21]),
    "one hundred links": ([], [1, 100]),
    "two-thirds of the plate": ([], [2]),
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


@pytest.mark.parametrize(
    "quote, word, found",
    [
        ("Eight tension springs", "Eight", True),
        ("Eight tension springs", "eight", True),
        ("twenty-four bolts", "twenty-four", True),
        ("twenty-four bolts", "twenty four", True),
        ("Eight tension springs", "seven", False),
    ],
)
def test_number_word_value_is_read_as_the_number_it_names(proj_dir, tmp_path, quote, word, found):
    # A value written as printed, in words, is that number: it is matched against the quote like
    # digits, so "seven" is not in "Eight tension springs".
    add_quote(proj_dir, tmp_path, quote, quote, {"n": word})
    assert findings(proj_dir, "schema") == []
    assert ("N1.n" in " ".join(findings(proj_dir, "value-not-in-quote"))) is not found


@pytest.mark.parametrize("word", ["eighth", "twenty-first", "a pair", "dozen", "eight mm"])
def test_guard_value_in_words_that_is_no_cardinal_is_schema(proj_dir, tmp_path, word):
    add_quote(proj_dir, tmp_path, "Eight tension springs", "Eight tension springs", {"n": word})
    assert findings(proj_dir, "schema") == [
        f"evidence.yaml evidence[2].values.n: must be a number, not {word!r}"
    ]


def test_source_tampering_is_caught(proj_dir):
    (proj_dir / "sources" / "paper.txt").write_text(swap(PAPER, "40", "45"))
    assert "source-hash" in errors(proj_dir)


def test_source_rewritten_between_runs_is_read_afresh(proj_dir):
    assert verify(proj_dir)[0] == 0
    paper = proj_dir / "sources" / "paper.txt"
    paper.write_text(swap(PAPER, "30 mm apart", "32 mm apart"))
    register = ["source", str(proj_dir), str(paper), "--id", "paper", "--kind", "paper"]
    assert cli.main([*register, "--citation", "Doe 2026"]) == 0
    assert "quote-not-found" in errors(proj_dir)


def test_model_literal_is_rejected(proj_dir):
    write(proj_dir, "model.py", swap(MODEL, "p.link_H)\n    link -=", "7.5)\n    link -=", 1))
    assert "model-literal" in errors(proj_dir)


# The model lint closes every route a number could take into model.py.


def _model_with(root: Path, header: str = "", line: str = "") -> None:
    """model.py with header above it and line as the first statement of build(), on model.py
    line 5 + header's line count (an empty header counts as one blank line)."""
    body = swap(MODEL, "def build(p):\n", f"def build(p):\n    {line}\n") if line else MODEL
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


# A constant built from params hides its number as well as a literal does.


@pytest.mark.parametrize(
    "expr",
    [
        "atan2(p.link_H, p.link_H)",
        "p.link_W / p.link_W",
        "p.link_W - p.link_W",
        "atan2(2 * p.link_H, p.link_H + p.link_H)",
        "math.degrees(math.atan2(p.link_H, p.link_H)) * p.pitch / p.pitch",
    ],
)
def test_model_constant_built_from_params_is_a_finding_on_its_line(proj_dir, expr):
    _model_with(proj_dir, header="import math\nfrom math import atan2", line=f"extra = {expr}")
    messages = findings(proj_dir, "model-constant")
    assert errors(proj_dir) == ["model-constant"] and len(messages) == 1
    assert messages[0].startswith(f"model.py:7: {expr}")


@pytest.mark.parametrize(
    "expr, constant",
    [
        ("p.pitch * atan2(p.link_H, p.link_H)", "atan2(p.link_H, p.link_H)"),
        ("p.pitch + (p.link_W - p.link_W)", "p.link_W - p.link_W"),
        ("max(p.pitch, p.link_W / p.link_W)", "p.link_W / p.link_W"),
    ],
)
def test_model_constant_inside_a_relation_that_varies_is_a_finding(proj_dir, expr, constant):
    _model_with(proj_dir, header="import math\nfrom math import atan2", line=f"extra = {expr}")
    messages = findings(proj_dir, "model-constant")
    assert errors(proj_dir) == ["model-constant"] and len(messages) == 1
    assert messages[0].startswith(f"model.py:7: {constant} is")


def test_model_constant_through_a_local_alias_is_a_finding(proj_dir):
    _model_with(proj_dir, line="w = p.link_W; extra = w / w")
    messages = findings(proj_dir, "model-constant")
    assert errors(proj_dir) == ["model-constant"] and len(messages) == 1
    assert messages[0].startswith("model.py:6: w / w")


@pytest.mark.parametrize(
    "line",
    [
        "extra = p.link_L - p.link_L / 2",
        "extra = p.link_H - 1",
        "extra = -p.pitch / 2",
        "extra = p.link_H // 2, p.link_H % 2",
        "w = p.link_W; extra = w / p.link_H",
        "w = p.link_W; w = 1; extra = w / p.link_W",
        "extra = [h / h for h in (p.link_H,)]",
    ],
)
def test_guard_model_relation_that_varies_with_its_params(proj_dir, line):
    _model_with(proj_dir, line=line)
    code, _ = verify(proj_dir)
    assert code == 0 and findings(proj_dir, "model-constant") == []


# A factor respelled from allowed literals hides its number as well as the literal would.


@pytest.mark.parametrize(
    "line, expr, param, factor",
    [
        ("extra = p.link_H + p.link_H / 2", "p.link_H + p.link_H / 2", "link_H", "1.5"),
        ("w = p.link_W; extra = w + w / 2", "w + w / 2", "link_W", "1.5"),
        ("extra = p.link_L / 2 / 2", "p.link_L / 2 / 2", "link_L", "0.25"),
        ("extra = p.pitch + p.pitch + p.pitch", "p.pitch + p.pitch + p.pitch", "pitch", "3"),
        (
            "extra = p.link_W / 2 + p.link_W / 2 + p.link_W / 2",
            "p.link_W / 2 + p.link_W / 2 + p.link_W / 2",
            "link_W",
            "1.5",
        ),
        (
            "extra = math.sin(p.link_H + p.link_H / 2)",
            "p.link_H + p.link_H / 2",
            "link_H",
            "1.5",
        ),
        (
            "extra = (p.link_H + p.link_H / 2) * p.pitch",
            "p.link_H + p.link_H / 2",
            "link_H",
            "1.5",
        ),
    ],
)
def test_model_factor_respelled_from_allowed_literals_is_a_finding(
    proj_dir, line, expr, param, factor
):
    _model_with(proj_dir, header="import math", line=line)
    messages = findings(proj_dir, "model-arithmetic")
    assert errors(proj_dir) == ["model-arithmetic"] and len(messages) == 1
    assert messages[0].startswith(f"model.py:6: {expr} multiplies {param} by {factor},")


# Run 8 met a factor of -1.5 on a line that holds only / 2: the -2 came from a local name
# assigned on another line, so the finding names that name, its line and its own factor.
def test_model_factor_built_through_a_local_name_names_where_it_is_assigned(proj_dir):
    _model_with(proj_dir, line="fy = p.link_L - 2 * p.link_W\n    extra = fy + p.link_W / 2")
    messages = findings(proj_dir, "model-arithmetic")
    assert errors(proj_dir) == ["model-arithmetic"] and len(messages) == 1
    assert messages[0].startswith(
        "model.py:7: fy + p.link_W / 2 multiplies link_W by -1.5, not an allowed literal "
        "(fy, assigned on model.py:6, multiplies link_W by -2);"
    )


@pytest.mark.parametrize(
    "expr",
    [
        "p.link_L - p.link_L / 2",
        "-p.pitch / 2",
        "p.link_H - 1",
        "p.pitch + p.link_H / 2",
        "p.link_H / 2 + p.link_H / 2",
        "p.pitch + p.pitch",
        "(p.link_L - p.link_W) / 2",
        "2 * p.link_W - p.link_H",
        "p.link_L * math.cos(p.pitch)",
        "math.atan2(p.link_H, p.link_L)",
        "p.link_H ** 2",
        "p.pitch * math.pi",
        "min(p.link_H, p.link_W) / 2",
        "p.pitch / 90",
    ],
)
def test_guard_model_factor_that_is_an_allowed_literal_or_not_constant(proj_dir, expr):
    _model_with(proj_dir, header="import math", line=f"extra = {expr}")
    code, _ = verify(proj_dir)
    assert code == 0, findings(proj_dir, "model-arithmetic")


@pytest.mark.parametrize(
    "expr, rule",
    [
        ("3 * p.link_H / 2", "model-literal"),
        ("p.link_W / p.link_W", "model-constant"),
        ("2 * p.link_W * 2", "model-arithmetic"),
    ],
)
def test_guard_model_number_already_flagged_gets_no_factor_finding(proj_dir, expr, rule):
    _model_with(proj_dir, line=f"extra = {expr}")
    assert errors(proj_dir) == [rule] and len(findings(proj_dir, rule)) == 1


# 0 if p.link_H else keeps build() from running the expression, so only the lint evaluates it.
@pytest.mark.parametrize(
    "line",
    [
        "extra = 0 if p.link_H else math.asin(p.link_L / p.link_H + p.link_L / p.link_L)",
        "extra = 0 if p.link_H else (p.link_L + p.link_L / 2) / (p.pitch - p.pitch)",
    ],
)
def test_guard_model_expression_failing_to_evaluate_is_skipped(proj_dir, line):
    _model_with(proj_dir, header="import math", line=line)
    code, _ = verify(proj_dir)
    assert code == 0 and findings(proj_dir, "model-constant") == []


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
    write(proj_dir, "model.py", swap(MODEL, "Box(p.link_L,", "Box(p.link_L + p.hole_d,"))
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


def _front_overlay(root: Path, image) -> Path:
    """Render the fixture's link over image in a front-view overlay, 10 px per mm with model
    (0, 0) at pixel (200, 100) and the calibration span from (50, 150) to (350, 150); return the
    PNG."""
    (root / "figures").mkdir(exist_ok=True)
    image.save(root / "figures" / "fig.png")
    calibration = {"pixels": [[50, 150], [350, 150]], "evidence": "pitch.pitch"}
    overlay = {"id": "front", "image": "figures/fig.png", "part": "link", "view": "front"}
    write(
        root,
        "overlays.yaml",
        {"overlays": [overlay | {"origin": [200, 100], "calibration": calibration}]},
    )
    assert cli.main(["check", str(root)]) == 0
    return root / "build" / "overlays" / "front.png"


def test_overlay_draws_its_image_one_pixel_to_one_pixel_below_its_title(proj_dir):
    from PIL import Image

    source = Image.new("RGB", (400, 200), "white")
    source.putpixel((0, 0), (255, 0, 0))
    source.putpixel((399, 199), (0, 255, 0))
    png = Image.open(_front_overlay(proj_dir, source)).convert("RGB")
    strip = png.height - 200
    assert png.width == 400 and strip > 0, png.size
    assert png.getpixel((0, strip)) == (255, 0, 0)
    assert png.getpixel((399, strip + 199)) == (0, 255, 0)
    title = [png.getpixel((x, y)) for x in range(400) for y in range(strip)]
    assert any(c != (255, 255, 255) for c in title), "no title in the strip above the image"


def test_overlay_calibration_marker_lands_on_the_pixels_it_names(proj_dir):
    import numpy as np
    from PIL import Image

    png = np.asarray(Image.open(_front_overlay(proj_dir, Image.new("RGB", (400, 200), "white"))))
    image = png[png.shape[0] - 200 :, :, :3].astype(int)  # the image area, below the title strip
    ys, xs = np.nonzero((image[:, :, 2] > 150) & (image[:, :, 0] < 120))  # the blue marks
    assert abs(ys.mean() - 150) <= 0.5, ys.mean()
    assert xs.min() + xs.max() == 50 + 350 and 50 - 4 <= xs.min() < 50, (xs.min(), xs.max())


def test_overlay_title_wraps_inside_a_narrow_image(proj_dir):
    import numpy as np
    from PIL import Image

    png = np.asarray(Image.open(_front_overlay(proj_dir, Image.new("RGB", (120, 200), "white"))))
    strip = png[: png.shape[0] - 200, :, :3]
    assert png.shape[1] == 120 and (strip < 128).any(), "no title in the strip"
    assert (strip[:, [0, -1]] == 255).all(), "the title runs off the edge of the PNG"


def test_overlay_model_edges_land_on_the_pixels_their_scale_puts_them(proj_dir):
    import numpy as np
    from PIL import Image

    png = np.asarray(Image.open(_front_overlay(proj_dir, Image.new("RGB", (400, 200), "white"))))
    column = png[png.shape[0] - 200 :, 100, :3].astype(int)  # model x = -10, clear of the holes
    rows = np.nonzero((column[:, 0] > 150) & (column[:, 1] < 150))[0]  # the magenta edges
    # The link's top and bottom faces, z = ±4 at 10 px per mm about row 100.
    assert [rows[rows < 100].mean(), rows[rows > 100].mean()] == [60, 140], rows


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


_CENTRED = {
    "basis": "derived",
    "expr": "link_L - link_H",
    "gap": "G1",
    "interpretation": "pins at the centres of the rounded ends",
}


def test_derived_param_naming_a_gap_rests_on_proposed_and_so_do_params_derived_from_it(proj_dir):
    _no_proposed(proj_dir)
    add_params(proj_dir, centres=_CENTRED, half={"basis": "derived", "expr": "centres / 2"})
    code, report = verify(proj_dir)
    assert (code, report["status"], report["exact"]) == (0, "VERIFIED", False)
    assert report["counts"]["proposed"] == 2
    assert report["params"]["centres"]["rests_on"] == "proposed"
    assert report["params"]["half"]["rests_on"] == "proposed"
    assert report["rests_on_proposed"] == ["centres", "half"]
    md = (proj_dir / "build" / "report.md").read_text()
    assert "| centres | 32 | derived (rests on proposed) |" in md
    gaps = md.split("## Open gaps")[1].split("\n## ")[0]
    assert re.search(r"^\| G1 \|.*\| centres \|$", gaps, re.M)


@pytest.mark.parametrize(
    "change, rule",
    [({"gap": "G9"}, "param-gap"), ({"interpretation": None}, "param-derived")],
    ids=["unknown-gap", "no-interpretation"],
)
def test_derived_param_naming_a_gap_needs_a_known_gap_and_an_interpretation(proj_dir, change, rule):
    spec = {k: v for k, v in (_CENTRED | change).items() if v is not None}
    add_params(proj_dir, centres=spec)
    assert errors(proj_dir) == [rule]


def add_gap(root: Path, gid: str) -> None:
    edit(root, "gaps.yaml", lambda d: d["gaps"].append({"id": gid, "question": "foot width?"}))


def test_gap_no_param_names_is_a_gap_unused_warning(proj_dir):
    add_gap(proj_dir, "G2")
    assert findings(proj_dir, "gap-unused") == ["gap G2: no param names it"]


@pytest.mark.parametrize("field", ["summary", "resolution"])
def test_gap_named_only_in_a_conflicts_text_is_still_unused(proj_dir, field):
    add_gap(proj_dir, "G2")
    conflict = {"id": "C1", "evidence": ["pitch"], "summary": "pitch disputed"}
    conflict[field] = "foot width is open, see G2"
    edit(proj_dir, "evidence.yaml", lambda d: d["conflicts"].append(conflict))
    assert findings(proj_dir, "gap-unused") == ["gap G2: no param names it"]


def test_measured_param_naming_a_gap_clears_gap_unused_and_is_listed_under_it(proj_dir):
    add_gap(proj_dir, "G2")
    add_measured(proj_dir)
    assert findings(proj_dir, "gap-unused") == ["gap G2: no param names it"]
    edit(proj_dir, "params.yaml", lambda d: d["params"]["foot_w"].update(gap="G2"))
    code, report = verify(proj_dir)
    assert code == 0
    assert {f["rule"] for f in report["findings"]} & {"param-gap", "gap-unused"} == set()
    gaps = (proj_dir / "build" / "report.md").read_text().split("## Open gaps")[1].split("\n## ")[0]
    assert re.search(r"^\| G2 \|.*\| foot_w \|$", gaps, re.M)


def test_guard_measured_param_naming_no_gap_raises_no_param_gap(proj_dir):
    add_measured(proj_dir)
    assert findings(proj_dir, "param-gap") == []


def test_derived_param_naming_a_gap_clears_gap_unused(proj_dir):
    add_gap(proj_dir, "G2")
    assert findings(proj_dir, "gap-unused") == ["gap G2: no param names it"]
    add_params(proj_dir, centres=_CENTRED | {"gap": "G2"})
    _, report = verify(proj_dir)
    assert {f["rule"] for f in report["findings"]} & {"param-gap", "gap-unused"} == set()


@pytest.mark.parametrize(
    "name, change",
    [("foot_w", {"gap": "G9"}), ("pitch", {"gap": "G1"})],
    ids=["measured-unknown-gap", "source-with-gap"],
)
def test_param_gap_is_an_error_on_a_measured_unknown_gap_or_any_source_gap(proj_dir, name, change):
    add_measured(proj_dir)
    edit(proj_dir, "params.yaml", lambda d: d["params"][name].update(change))
    assert errors(proj_dir) == ["param-gap"]


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


def test_check_without_id_is_a_finding(proj_dir):
    edit(proj_dir, "checks.yaml", lambda d: d["checks"][1].pop("id"))
    assert findings(proj_dir, "schema") == ["checks.yaml checks[1]: id is required"]


def _ledger_also(root: Path, *ids: str) -> None:
    """Append to the fixture's ledger a context item under each of ids."""
    item = {"source": "paper", "locator": "Sec. 3", "quote": "branches of 60 mm diameter"}
    extra = [{"id": eid, **item, "scope": "context", "reason": "r"} for eid in ids]
    edit(root, "evidence.yaml", lambda d: d["evidence"].extend(extra))


def test_evidence_items_sharing_an_id_is_a_finding_naming_it(proj_dir):
    _ledger_also(proj_dir, "pitch")
    assert findings(proj_dir, "evidence-id") == ["evidence pitch: evidence ids must be unique"]


def test_two_repeated_evidence_ids_are_a_finding_naming_each(proj_dir):
    _ledger_also(proj_dir, "pitch", "T1-link", "pitch")
    assert findings(proj_dir, "evidence-id") == [
        "evidence T1-link: evidence ids must be unique",
        "evidence pitch: evidence ids must be unique",
    ]


def test_guard_evidence_ids_that_differ_in_case_or_suffix(proj_dir):
    _ledger_also(proj_dir, "Pitch", "pitch-2")
    assert findings(proj_dir, "evidence-id") == []


def test_run_without_the_build_reports_evidence_items_sharing_an_id_naming_it(proj_dir):
    _ledger_also(proj_dir, "pitch")
    assert "error: [evidence-id] evidence pitch: evidence ids must be unique" in _partial(
        proj_dir, "--no-build"
    )


def _repeat(root: Path, eid: str, **fields) -> None:
    """Append to the fixture's ledger a copy of item eid, under the same id, with fields changed."""

    def apply(d):
        d["evidence"].append({**next(e for e in d["evidence"] if e["id"] == eid), **fields})

    edit(root, "evidence.yaml", apply)


def test_earlier_item_under_a_repeated_id_still_has_its_quote_checked(proj_dir):
    _evidence("pitch", quote="spaced 31 mm apart")(proj_dir, None)
    _repeat(proj_dir, "pitch", quote="spaced 30 mm apart")
    assert findings(proj_dir, "quote-not-found") == [
        "pitch: quote not found in paper: 'spaced 31 mm apart'"
    ]


def test_guard_later_item_under_a_repeated_id_has_its_quote_checked(proj_dir):
    _repeat(proj_dir, "pitch", quote="spaced 31 mm apart")
    assert findings(proj_dir, "quote-not-found") == [
        "pitch: quote not found in paper: 'spaced 31 mm apart'"
    ]


def _repeat_link_as_context(root: Path) -> None:
    """Append a context item under the id T1-link, quoting other text than the original."""
    context = {"quote": "The pivot holes of the link", "values": {}, "scope": "context"}
    _repeat(root, "T1-link", **context, reason="r")


def test_earlier_item_under_a_repeated_id_still_covers_its_stated_quantity(proj_dir):
    _repeat_link_as_context(proj_dir)
    assert findings(proj_dir, "coverage") == []


def test_report_lists_every_item_under_a_repeated_id(proj_dir):
    _repeat_link_as_context(proj_dir)
    verify(proj_dir)
    rows = (proj_dir / "build" / "report.md").read_text().splitlines()
    listed = [row for row in rows if row.startswith("| T1-link |")]
    assert [row.split(" | ")[-1] for row in listed] == [
        "“Link 40×8×5” |",
        "“The pivot holes of the link” |",
    ]


def _pitch_proposed(r, t) -> None:
    """Choose the pitch, so the model builds though no param reads the ledgered pitch."""
    _param("pitch", basis="proposed", value=30, rationale="a guess", gap="G1", **{"from": None})(
        r, t
    )


@pytest.mark.parametrize(
    "setup, eid, rule, says",
    [
        (lambda r, t: None, "pitch", "param-from", "param pitch: from: 'pitch.pitch'"),
        (lambda r, t: add_measured(r), "F2", "param-from", "param foot_w: from: 'F2'"),
        (lambda r, t: None, "pitch", "check-config", "check pitch: pitch.pitch"),
        (lambda r, t: four_bar(r, t), "P30", "check-config", "check ac30: P30.turn"),
        (
            lambda r, t: _append("evidence.yaml", "conflicts", _CONFLICT)(r, t),
            "pitch",
            "conflict-ref",
            "conflict C1:",
        ),
        (
            lambda r, t: (_pitch_proposed(r, t), _overlay(r)),
            "pitch",
            "overlay-config",
            "overlay front: calibration pitch.pitch",
        ),
    ],
)
def test_citing_a_repeated_evidence_id_is_a_finding_naming_it(
    proj_dir, tmp_path, setup, eid, rule, says
):
    setup(proj_dir, tmp_path)
    _repeat(proj_dir, eid)
    assert f"{says} cites {eid}, a repeated evidence id" in findings(proj_dir, rule)


def test_run_without_the_build_reports_a_check_citing_a_repeated_evidence_id(proj_dir):
    _repeat(proj_dir, "pitch")
    assert "error: [check-config] check pitch: pitch.pitch cites pitch, a repeated evidence id" in (
        _partial(proj_dir, "--no-build")
    )


def test_param_citing_a_repeated_evidence_id_takes_neither_items_value(proj_dir):
    _repeat(proj_dir, "pitch", quote="Link 40×8×5", values={"pitch": 40})
    assert verify(proj_dir)[1]["params"]["pitch"]["value"] is None


def test_overlay_citing_a_repeated_evidence_id_is_scaled_by_neither_item(proj_dir, tmp_path):
    _pitch_proposed(proj_dir, tmp_path)
    _overlay(proj_dir)
    _repeat(proj_dir, "pitch")
    verify(proj_dir)
    assert not (proj_dir / "build" / "overlays" / "front.png").exists()


def test_check_citing_a_repeated_evidence_id_compares_with_neither_item(proj_dir, tmp_path):
    _pitch_proposed(proj_dir, tmp_path)
    _repeat(proj_dir, "pitch", quote="Link 40×8×5", values={"pitch": 40})
    assert set(_by_id(verify(proj_dir)[1])) == {"env.L", "env.H", "env.W", "clear"}


def test_guard_value_cited_by_a_repeated_evidence_id_is_used_on_both_items(proj_dir):
    _repeat(proj_dir, "pitch")
    assert findings(proj_dir, "evidence-unused") == []


def test_guard_run_on_a_ledger_with_a_repeated_evidence_id_builds_and_is_not_verified(
    proj_dir, tmp_path
):
    _pitch_proposed(proj_dir, tmp_path)
    _repeat(proj_dir, "pitch")
    code, report = verify(proj_dir)
    assert code == 1 and report["status"] == "NOT VERIFIED"
    assert "model-build" not in [f["rule"] for f in report["findings"]]
    assert all(_by_id(report)[cid]["ok"] for cid in ("env.L", "env.H", "env.W", "clear"))


def _rename_checks(root: Path, first, second) -> None:
    """Give the fixture's first two checks the ids first and second."""

    def rename(d):
        d["checks"][0]["id"], d["checks"][1]["id"] = first, second

    edit(root, "checks.yaml", rename)


@pytest.mark.parametrize("first, second, named", [("env", "env", "env"), (1, "1", "1")])
def test_checks_sharing_an_id_is_a_finding_naming_it(proj_dir, first, second, named):
    _rename_checks(proj_dir, first, second)
    assert findings(proj_dir, "check-id") == [f"check {named}: check ids must be unique"]


def test_guard_run_without_the_build_reports_checks_sharing_an_id(proj_dir):
    _rename_checks(proj_dir, "env", "env")
    assert "error: [check-id] check env: check ids must be unique" in _partial(
        proj_dir, "--no-build"
    )


@pytest.mark.parametrize("first, second", [("env", "Env"), ("env", "env-2")])
def test_guard_checks_whose_ids_differ_in_case_or_suffix(proj_dir, first, second):
    _rename_checks(proj_dir, first, second)
    assert findings(proj_dir, "check-id") == []


@pytest.mark.parametrize(
    "name, change, where",
    [
        ("params.yaml", lambda d: d.update(params=[{"link_L": 40}]), "params.yaml params:"),
        ("params.yaml", lambda d: d["params"].update(link_L=40), "params.yaml params.link_L:"),
        (
            "evidence.yaml",
            lambda d: d["evidence"][0]["values"].update(L="40 mm"),
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
    write(proj_dir, "model.py", swap(MODEL, "def build(p):", "def build(p)"))
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


def _unresolved_pitch(root: Path) -> None:
    """Point source param pitch at a ledger value that does not exist, so it has no value."""
    edit(root, "params.yaml", lambda d: d["params"]["pitch"].update({"from": "pitch.nope"}))


def test_derived_param_using_a_source_param_whose_from_failed_names_it_as_having_no_value(
    proj_dir,
):
    _unresolved_pitch(proj_dir)
    add_params(proj_dir, half={"basis": "derived", "expr": "pitch / 2"})
    assert findings(proj_dir, "param-derived") == ["param half: input pitch has no value"]


def _half_without_a_value(root: Path) -> None:
    """Add derived param half, whose expr uses an undefined name, so it has no value."""
    add_params(root, half={"basis": "derived", "expr": "pitchh / 2"})


def test_model_reading_a_source_param_whose_from_failed_fails_naming_it_as_having_no_value(
    proj_dir,
):
    _unresolved_pitch(proj_dir)
    assert findings(proj_dir, "model-build") == [
        "model.build failed: AttributeError: param 'pitch' has no value"
    ]


def test_model_reading_a_derived_param_with_an_undefined_name_fails_naming_it_as_having_no_value(
    proj_dir,
):
    _half_without_a_value(proj_dir)
    _model_with(proj_dir, line="extra = p.half")
    assert findings(proj_dir, "model-build") == [
        "model.build failed: AttributeError: param 'half' has no value"
    ]


def test_guard_model_reading_a_name_params_yaml_does_not_declare_fails_naming_it_missing(proj_dir):
    _model_with(proj_dir, line="extra = p.pitch_2")
    assert findings(proj_dir, "model-build") == [
        "model.build failed: AttributeError: no parameter 'pitch_2' in params.yaml"
    ]


def test_guard_model_never_reading_a_param_without_a_value_builds_and_its_checks_run(proj_dir):
    _half_without_a_value(proj_dir)
    _, report = verify(proj_dir)
    assert "model-build" not in [f["rule"] for f in report["findings"]]
    assert report["checks"] and all(c["ok"] for c in report["checks"])


def test_derived_params_through_a_chain_each_name_their_direct_input_as_having_no_value(proj_dir):
    _unresolved_pitch(proj_dir)
    add_params(
        proj_dir,
        half={"basis": "derived", "expr": "pitch / 2"},
        quarter={"basis": "derived", "expr": "half / 2"},
    )
    assert sorted(findings(proj_dir, "param-derived")) == [
        "param half: input pitch has no value",
        "param quarter: input half has no value",
    ]


def test_derived_param_using_one_dropped_for_an_undefined_name_names_it_as_having_no_value(
    proj_dir,
):
    add_params(
        proj_dir,
        half={"basis": "derived", "expr": "pitchh / 2"},
        quarter={"basis": "derived", "expr": "half / 2"},
    )
    assert findings(proj_dir, "param-derived") == [
        "param half: expr uses undefined ['pitchh']",
        "param quarter: input half has no value",
    ]


def test_derived_param_with_several_inputs_without_a_value_names_each_in_sorted_order(proj_dir):
    _unresolved_pitch(proj_dir)
    add_params(
        proj_dir,
        half={"basis": "derived", "expr": "pitchh / 2"},
        both={"basis": "derived", "expr": "pitch + half + link_H"},
    )
    assert sorted(findings(proj_dir, "param-derived")) == [
        "param both: inputs half, pitch have no value",
        "param half: expr uses undefined ['pitchh']",
    ]


def test_derived_param_using_a_member_of_a_cycle_it_is_not_on_names_that_member(proj_dir):
    add_params(
        proj_dir,
        probe={"basis": "derived", "expr": "loop_a * 2"},
        loop_a={"basis": "derived", "expr": "loop_b + 1"},
        loop_b={"basis": "derived", "expr": "loop_a + 1"},
    )
    assert sorted(findings(proj_dir, "param-derived")) == [
        "param loop_a: circular dependency",
        "param loop_b: circular dependency",
        "param probe: input loop_a has no value",
    ]


def test_guard_both_members_of_a_two_param_cycle_are_a_circular_dependency(proj_dir):
    add_params(
        proj_dir,
        loop_a={"basis": "derived", "expr": "loop_b + 1"},
        loop_b={"basis": "derived", "expr": "loop_a + 1"},
    )
    assert sorted(findings(proj_dir, "param-derived")) == [
        "param loop_a: circular dependency",
        "param loop_b: circular dependency",
    ]


def test_guard_a_self_referencing_derived_param_is_a_circular_dependency(proj_dir):
    add_params(proj_dir, a={"basis": "derived", "expr": "a + 1"})
    assert findings(proj_dir, "param-derived") == ["param a: circular dependency"]


@pytest.mark.parametrize(
    "returned",
    ["[]", "None", '{"parts": []}', '{"parts": {}, "datums": {"a": 1}}', '{"parts": {"link": 3}}'],
)
def test_build_returning_the_wrong_shape_is_a_finding(proj_dir, returned):
    write(
        proj_dir, "model.py", swap(MODEL, "    return {", f"    return {returned}\n    _ = {{", 1)
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


def _redump(root: Path, sort_keys: bool) -> None:
    """Write project.yaml back as PyYAML would: lists unindented, keys sorted if asked."""
    meta = root / "project.yaml"
    meta.write_text(yaml.safe_dump(yaml.safe_load(meta.read_text()), sort_keys=sort_keys))


@pytest.mark.parametrize("sort_keys", [False, True], ids=["in-order", "sorted"])
def test_source_registered_after_a_pyyaml_redump_joins_the_sources_list(
    proj_dir, tmp_path, sort_keys
):
    _redump(proj_dir, sort_keys)
    before = yaml.safe_load((proj_dir / "project.yaml").read_text())
    notes = tmp_path / "notes.txt"
    notes.write_text("No dimensions.\n")
    code, _ = run(
        "source", str(proj_dir), str(notes), "--id", "notes", "--kind", "other", "--citation", "N"
    )
    after = yaml.safe_load((proj_dir / "project.yaml").read_text())
    assert code == 0
    assert [s["id"] for s in after.pop("sources")] == ["paper", "notes"]
    assert after == {k: v for k, v in before.items() if k != "sources"}
    assert verify(proj_dir)[0] == 0


def _reregister_after_redump(root: Path, sort_keys: bool, citation: str) -> None:
    _redump(root, sort_keys)
    paper = root / "sources" / "paper.txt"
    paper.write_text(PAPER + "Received 1 March.\n")
    code, _ = run(
        "source", str(root), str(paper), "--id", "paper", "--kind", "paper", "--citation", citation
    )
    (entry,) = yaml.safe_load((root / "project.yaml").read_text())["sources"]
    assert code == 0 and (entry["sha256"], entry["citation"]) == (sha256(paper), citation)


def test_guard_source_reregistered_after_an_in_order_pyyaml_redump_is_refreshed(proj_dir):
    _reregister_after_redump(proj_dir, sort_keys=False, citation="D")


def test_source_reregistered_after_a_sorted_pyyaml_redump_is_refreshed(proj_dir):
    # Sorted keys put citation before id, so the entry no longer opens with "- id:".
    _reregister_after_redump(proj_dir, sort_keys=True, citation="D")


def _block_citation(root: Path) -> None:
    meta = root / "project.yaml"
    text = swap(
        meta.read_text(),
        r"citation: .*",
        "citation: |\n      Doe 2026\n\n      Adv. Sci.",
        regex=True,
    )
    meta.write_text(text)


# A citation written over several lines, and how it got that way. Re-registering replaces it whole.
MULTILINE_CITATIONS = {
    "PyYAML wrapped a long one": lambda r: edit(
        r, "project.yaml", lambda d: d["sources"][0].update(citation="word " * 30)
    ),
    "PyYAML quoted one holding a newline": lambda r: edit(
        r, "project.yaml", lambda d: d["sources"][0].update(citation="Doe 2026\nAdv. Sci.")
    ),
    "block scalar with a blank line": _block_citation,
}


@pytest.mark.parametrize("written", sorted(MULTILINE_CITATIONS))
def test_reregistering_replaces_a_citation_written_over_several_lines(proj_dir, written):
    MULTILINE_CITATIONS[written](proj_dir)
    _reregister_after_redump(proj_dir, sort_keys=False, citation="D")


def test_source_into_a_flow_style_sources_list_is_refused_leaving_it_intact(
    proj_dir, tmp_path, capsys
):
    meta = proj_dir / "project.yaml"
    data = yaml.safe_load(meta.read_text())
    meta.write_text(yaml.safe_dump(data, default_flow_style=True))
    before = meta.read_text()
    notes = tmp_path / "notes.txt"
    notes.write_text("No dimensions.\n")
    code, _ = run(
        "source", str(proj_dir), str(notes), "--id", "notes", "--kind", "other", "--citation", "N"
    )
    assert code == 1 and meta.read_text() == before
    assert "sources" in capsys.readouterr().err


def _to_crlf(path: Path) -> None:
    path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))


def _lines_end_crlf(path: Path) -> bool:
    data = path.read_bytes()
    return data.endswith(b"\r\n") and data.count(b"\n") == data.count(b"\r\n")


def _register_notes(root: Path, *flags: str) -> int:
    notes = root.parent / "notes.txt"
    notes.write_text("No dimensions.\n")
    code, _ = run(
        "source",
        str(root),
        str(notes),
        "--id",
        "notes",
        "--kind",
        "other",
        "--citation",
        "N",
        *flags,
    )
    return code


def _refresh_paper(root: Path) -> int:
    """Re-register the paper source after its file changed, as from a fresh download."""
    paper = root / "sources" / "paper.txt"
    paper.write_text(PAPER + "Received 1 March.\n")
    code, _ = run(
        "source",
        str(root),
        str(paper),
        "--id",
        "paper",
        "--kind",
        "paper",
        "--citation",
        "Doe 2026",
    )
    return code


def _loaded_sources(root: Path) -> list[dict]:
    """The project's sources, once a verification run shows project.yaml still loads."""
    assert findings(root, "yaml-syntax") == []
    return yaml.safe_load((root / "project.yaml").read_text())["sources"]


def _source_ids(root: Path) -> list[str]:
    return [s["id"] for s in _loaded_sources(root)]


def test_source_registered_into_a_crlf_project_yaml_keeps_it_crlf(proj_dir):
    meta = proj_dir / "project.yaml"
    _to_crlf(meta)
    assert _register_notes(proj_dir) == 0
    assert _lines_end_crlf(meta)
    assert _source_ids(proj_dir) == ["paper", "notes"]


def test_source_refreshed_in_a_crlf_project_yaml_keeps_it_crlf(proj_dir):
    meta = proj_dir / "project.yaml"
    _to_crlf(meta)
    assert _refresh_paper(proj_dir) == 0
    assert _lines_end_crlf(meta)
    (entry,) = _loaded_sources(proj_dir)
    assert entry["sha256"] == sha256(proj_dir / "sources" / "paper.txt")


def test_redistributable_source_registered_with_a_crlf_gitignore_keeps_it_crlf(proj_dir):
    gitignore = proj_dir / ".gitignore"
    _to_crlf(gitignore)
    assert _register_notes(proj_dir, "--license", "CC-BY-4.0") == 0
    assert _lines_end_crlf(gitignore)
    assert "!sources/notes.txt" in gitignore.read_text().splitlines()


def test_source_into_a_project_yaml_of_mixed_endings_writes_its_first_lines_ending(proj_dir):
    meta = proj_dir / "project.yaml"
    first, rest = meta.read_bytes().split(b"\n", 1)
    meta.write_bytes(first + b"\r\n" + rest)
    assert _register_notes(proj_dir) == 0
    assert _lines_end_crlf(meta)
    assert _source_ids(proj_dir) == ["paper", "notes"]


def test_guard_source_into_a_project_yaml_of_mixed_endings_lf_first_writes_lf(proj_dir):
    meta = proj_dir / "project.yaml"
    first, rest = meta.read_bytes().split(b"\n", 1)
    meta.write_bytes(first + b"\n" + rest.replace(b"\n", b"\r\n"))
    assert _register_notes(proj_dir) == 0
    assert b"\r" not in meta.read_bytes()
    assert _source_ids(proj_dir) == ["paper", "notes"]


def test_source_joins_an_empty_sources_list_with_a_comment_keeping_it(tmp_path):
    root = tmp_path / "demo"
    assert cli.main(["init", str(root)]) == 0
    meta = root / "project.yaml"
    meta.write_text(swap(meta.read_text(), "sources: []", "sources: []  # none yet"))
    assert _register_notes(root) == 0
    assert _source_ids(root) == ["notes"]
    assert "sources:  # none yet" in meta.read_text().splitlines()


def test_source_joins_a_sources_list_whose_head_has_a_comment_after_its_entries(proj_dir):
    meta = proj_dir / "project.yaml"
    meta.write_text(swap(meta.read_text(), r"^sources:$", "sources:  # papers", regex=True))
    assert _register_notes(proj_dir) == 0
    assert _source_ids(proj_dir) == ["paper", "notes"]


def _set_paper_id_line(root: Path, id_line: str) -> None:
    meta = root / "project.yaml"
    meta.write_text(swap(meta.read_text(), r"^(\s*)- id: paper$", rf"\g<1>{id_line}", regex=True))


@pytest.mark.parametrize("id_line", ["- id: paper  # main", '- id: "paper"  # main'])
def test_source_whose_id_line_has_a_comment_is_refreshed_in_place_keeping_it(proj_dir, id_line):
    _set_paper_id_line(proj_dir, id_line)
    assert _refresh_paper(proj_dir) == 0
    (entry,) = _loaded_sources(proj_dir)
    assert entry["sha256"] == sha256(proj_dir / "sources" / "paper.txt")
    meta = proj_dir / "project.yaml"
    assert id_line in [line.strip() for line in meta.read_text().splitlines()]


# Look-alikes of `- id: paper  # main`: ids that only begin with paper, so refreshing paper leaves
# their entries alone.
@pytest.mark.parametrize("id_line", ['- id: "paper  # main"', "- id: paper#main"])
def test_guard_refreshing_a_source_leaves_an_entry_whose_id_only_begins_with_its_id(
    proj_dir, id_line
):
    _set_paper_id_line(proj_dir, id_line)
    paper = proj_dir / "sources" / "paper.txt"
    code, _ = run(
        "source", str(proj_dir), str(paper), "--id", "paper", "--kind", "paper", "--citation", "D"
    )
    assert code == 0
    look_alike, _ = before = _loaded_sources(proj_dir)
    assert _refresh_paper(proj_dir) == 0
    after = _loaded_sources(proj_dir)
    assert after[0] == look_alike and after[0]["id"] != "paper"
    assert after[1] == {**before[1], "sha256": sha256(paper), "citation": "Doe 2026"}


def test_guard_source_registered_into_an_lf_project_appends_only_its_lines(proj_dir):
    meta, gitignore = proj_dir / "project.yaml", proj_dir / ".gitignore"
    meta_before, gitignore_before = meta.read_bytes(), gitignore.read_bytes()
    assert _register_notes(proj_dir, "--license", "CC-BY-4.0") == 0
    digest = sha256(proj_dir / "sources" / "notes.txt")
    assert (
        meta.read_bytes()
        == meta_before
        + (
            "  - id: notes\n    kind: other\n    path: sources/notes.txt\n"
            f'    sha256: {digest}\n    citation: "N"\n    license: CC-BY-4.0\n'
        ).encode()
    )
    assert gitignore.read_bytes() == gitignore_before + b"!sources/notes.txt\n"


def test_guard_source_refreshed_in_an_lf_project_changes_only_its_hash(proj_dir):
    meta = proj_dir / "project.yaml"
    old = sha256(proj_dir / "sources" / "paper.txt")
    before = meta.read_bytes()
    assert _refresh_paper(proj_dir) == 0
    new = sha256(proj_dir / "sources" / "paper.txt")
    assert meta.read_bytes() == before.replace(old.encode(), new.encode())


def test_guard_source_into_a_project_yaml_with_a_second_document_is_refused_leaving_it_intact(
    proj_dir, capsys
):
    meta = proj_dir / "project.yaml"
    meta.write_text(meta.read_text() + "---\nnotes: later\n")
    before = meta.read_bytes()
    assert _register_notes(proj_dir) == 1
    assert meta.read_bytes() == before
    assert "[yaml-syntax]" in capsys.readouterr().err


def test_guard_source_into_a_project_yaml_ending_in_a_document_end_marker_lands_before_it(
    proj_dir,
):
    meta = proj_dir / "project.yaml"
    meta.write_text(meta.read_text() + "...\n")
    assert _register_notes(proj_dir) == 0
    assert meta.read_text().endswith('citation: "N"\n...\n')
    assert _source_ids(proj_dir) == ["paper", "notes"]


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
                swap(MODEL, "def build(p):", "raise SystemExit(3)\n\ndef build(p):"),
            ),
            "model-build",
        ),
        (
            lambda r: write(r, "model.py", swap(MODEL, '{"link": link}', '{"a/b": link}')),
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
        "error: [format-unknown] project.yaml: format 2 is not one this cadrev reads "
        "(it reads format: 1)"
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
    (root / name).write_text(swap((root / name).read_text(), old, new))


# Damage that once crashed, or plausibly could crash, a verification run. Add a case for every
# new way project input or user code enters the run.
def _expect_instead(root: Path, expr) -> None:
    """The pitch check compared with expect expr in place of its evidence and key."""

    def change(d):
        pitch = d["checks"][1]
        del pitch["evidence"], pitch["key"]
        pitch["expect"] = expr

    edit(root, "checks.yaml", change)


DAMAGE = {
    "expect is a list": lambda r: _expect_instead(r, ["pitch.pitch"]),
    "expect nested past the parser": lambda r: _expect_instead(r, "-" * 100_000 + "pitch.pitch"),
    "expect raising a power past any float": lambda r: _expect_instead(r, "9 ** 9 ** 9"),
    "expect calling a math function wrongly": lambda r: _expect_instead(r, "sqrt(x=pitch.pitch)"),
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
    "check claim a list": lambda r: edit(
        r, "checks.yaml", lambda d: d["checks"][1].update(claim=["shortens"])
    ),
    "check claim on a distance check": lambda r: edit(
        r, "checks.yaml", lambda d: d["checks"][1].update(claim="shortens")
    ),
    "check from a number": lambda r: edit(
        r, "checks.yaml", lambda d: d["checks"][1].update({"from": 3})
    ),
    "check from value a number": lambda r: edit(
        r, "checks.yaml", lambda d: d["checks"][1].update({"from": {"input": 3}})
    ),
    "stroke check with no cable joints": lambda r: edit(
        r,
        "checks.yaml",
        lambda d: d["checks"].append(
            {"id": "s", "kind": "stroke", "cable": "c", "evidence": "pitch", "claim": "shortens"}
            | {"from": {"input": "pitch.pitch"}}
        ),
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
        r, "model.py", swap(MODEL, "(-p.pitch / 2, 0, 0)", "(True, 0, 0)")
    ),
    "part name is a number": lambda r: write(
        r, "model.py", swap(MODEL, '{"link": link}', '{"link": link, 3: link}')
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
    "check without an id": lambda r: edit(r, "checks.yaml", lambda d: d["checks"][0].pop("id")),
    "duplicate gap ids": lambda r: write(r, "gaps.yaml", {"gaps": [{"id": "G1"}, {"id": "G1"}]}),
    "geometry source of text": lambda r: (
        (r / "sources" / "g.step").write_text("30 mm\n"),
        _add_source(r, "g", "sources/g.step"),
        edit(r, "project.yaml", lambda d: d["sources"][-1].update(kind="geometry")),
    ),
    "released datum of two numbers": lambda r: (
        released(r, r.parent),
        edit(r, "evidence.yaml", lambda d: d["datums"].update({"link_step.a": [1, 2]})),
    ),
    "datums is a list": lambda r: edit(r, "evidence.yaml", lambda d: d.update(datums=[1, 2])),
    "probe of an unregistered source": lambda r: edit(
        r, "evidence.yaml", lambda d: d["evidence"].append(PROBE | {"source": "nowhere"})
    ),
    "probe between one datum": lambda r: probed(
        r, r.parent, probe="angle", between=["link_step.a"], values={"v": 1}
    ),
    "probe with values in words": lambda r: probed(r, r.parent, values={"L": "forty"}),
    "shape check of an unknown part": lambda r: released(r, r.parent, part="pin"),
    "shape check pairs of one datum": lambda r: released(r, r.parent, pairs=[["link.a"]] * 3),
    "shape check without pairs or body": lambda r: edit(
        r, "checks.yaml", lambda d: d["checks"].append({"id": "s", "kind": "shape", "part": "link"})
    ),
    "shape check of a source that is no geometry": lambda r: (
        released(r, r.parent),
        edit(r, "checks.yaml", lambda d: d["checks"][-1].update(body="paper")),
    ),
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
    "a 2-in. plate": (2, 50.8),
    "a 2-inch plate": (2, 50.8),
    "a 1/4-in. bolt": (0.25, 6.35),
    "a 5-mm pin": (5, 5),
    "a 2-cm pin": (2, 20),
    "a 2-in-1 tool": (2, 2),
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
    "a spring of 0.25 N·m/rad": (0.25, 250),
    "a spring of 4 N·mm/rad": (4, 4),
    "a damper of 0.002 Nms/rad": (0.002, 2),
    "a damper of 2 N·mm·s/rad": (2, 2),
    "a cord of 300 N/m": (300, 0.3),
    "a cord of 3 N/mm": (3, 3),
    "a damper of 2 N·s/m": (2, 0.002),
    "a damper of 2 N·s/mm": (2, 2),
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


@pytest.mark.parametrize("value", [1250, 1.25, 250, 1])
def test_value_from_a_thousands_comma_is_a_finding(proj_dir, tmp_path, value):
    add_quote(proj_dir, tmp_path, "a 1,250 mm rail", "a 1,250 mm rail", {"v": value})
    (message,) = findings(proj_dir, "number-ambiguous")
    assert message.startswith("N1.v = ") and "1,250" in message
    assert "value-not-in-quote" not in errors(proj_dir)


def test_reading_with_a_thousands_comma_is_a_finding(proj_dir):
    add_reading(proj_dir, reading="1,250 mm", values={"v": 1250})
    (message,) = findings(proj_dir, "number-ambiguous")
    assert message.startswith("F2.v = ") and "1,250" in message


@pytest.mark.parametrize(
    "quote", ["Walls 3,5 mm", "widths 1,5,10 mm", "a 1,2500 mm rail", "a 1,250.5 mm rail"]
)
def test_guard_comma_that_is_not_a_thousands_comma(proj_dir, tmp_path, quote):
    add_quote(proj_dir, tmp_path, quote, quote, {"v": 5})
    assert findings(proj_dir, "number-ambiguous") == []


@pytest.mark.parametrize(("value", "rule"), [(5, None), (7, "value-not-in-quote")])
def test_guard_value_beside_a_thousands_comma_is_checked_as_usual(proj_dir, tmp_path, value, rule):
    quote = "a 1,250 rpm motor on a 5 mm shaft"
    add_quote(proj_dir, tmp_path, quote, quote, {"v": value})
    assert findings(proj_dir, "number-ambiguous") == []
    assert ("value-not-in-quote" in errors(proj_dir)) == (rule is not None)


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
    """Ledger text as N1 (value 40) and feed it to the model as link_L, checked by the T1
    envelope."""
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


def swept(root: Path, tmp_path: Path, capsys, text: str, name: str = "notes.txt") -> list[str]:
    """The candidates `cadrev coverage` lists in a notes source holding text, saved as name, as
    printed."""
    notes = tmp_path / name
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
    "2-in.": "2-in",
    "1/4-in.": "1/4-in",
    "5-mm": "5-mm",
    "5-10 mm": "5-10 mm",
    "six turns": "six turns",
    "three degrees": "three degrees",
}


@pytest.mark.parametrize("form", sorted(SWEPT))
def test_coverage_lists_each_quantity_form_whole(proj_dir, tmp_path, capsys, form):
    assert swept(proj_dir, tmp_path, capsys, f"The part is {form} here.") == [SWEPT[form]]


def test_coverage_lists_an_html_sources_stated_quantity_and_no_number_from_its_markup(
    proj_dir, tmp_path, capsys
):
    assert swept(proj_dir, tmp_path, capsys, DATASHEET_HTML.decode(), "ds.html") == ["20.6 g"]


def test_coverage_lists_no_number_from_an_html_sources_title(proj_dir, tmp_path, capsys):
    page = "<html><head><title>Servo 5 mm</title></head><body><p>Weight 20.6 g</p></body></html>"
    assert swept(proj_dir, tmp_path, capsys, page, "ds.html") == ["20.6 g"]


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


# Look-alikes of a quantity: a number before a unit's spelling that names something else.
NOT_SWEPT = {
    "four-bar": "The shin is a four-bar linkage.",
    "4-bar": "The shin is a 4-bar linkage.",
    "8G": "An onboard computer (8G; NVIDIA) runs it.",
    "2S": "A lithium-ion battery (2S, HUAYPG) powers it.",
    "4S": "A lithium polymer battery (4S, ACE) powers it.",
    "T=0s": "(A) T=0s, BLCM in the initial state.",
    "t = 2 s": "At t = 2 s the toes close.",
}


@pytest.mark.parametrize("form", sorted(NOT_SWEPT))
def test_coverage_lists_no_look_alike_of_a_quantity(proj_dir, tmp_path, capsys, form):
    assert swept(proj_dir, tmp_path, capsys, NOT_SWEPT[form]) == []


# Each look-alike's near miss: the same unit stating a quantity.
STILL_SWEPT = {
    "rated at 2 bar": "2 bar",
    "rated at 2bar": "2bar",
    "weighs 8g": "8g",
    "weighs 8 g": "8 g",
    "closes in 2s": "2s",
    "a Δt = 2 s step": "2 s",
    "a wall of t = 2 mm": "2 mm",
}


@pytest.mark.parametrize("form", sorted(STILL_SWEPT))
def test_guard_coverage_lists_the_near_miss_of_each_look_alike(proj_dir, tmp_path, capsys, form):
    assert swept(proj_dir, tmp_path, capsys, f"The part is {form} here.") == [STILL_SWEPT[form]]


def test_guard_coverage_lists_no_number_word_without_a_unit(proj_dir, tmp_path, capsys):
    assert swept(proj_dir, tmp_path, capsys, "Eight tension springs hold one of the links.") == []


def test_coverage_counts_a_number_word_with_a_unit_as_ledgered_by_its_value(proj_dir, tmp_path):
    add_quote(proj_dir, tmp_path, "The spring has six turns.", "six turns", {"n": 6})
    assert findings(proj_dir, "coverage") == []
    assert "value-not-in-quote" not in errors(proj_dir)


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
        f"**{status}**: {errors} errors, {warnings} warnings. "
        f"{passed}/{checks} geometry checks pass." in root_readme
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
    gitignore.write_text(swap(gitignore.read_text(), r"^sources/.*$", "sources/", regex=True))
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


# A saved datasheet page: markup, a style, a script, an entity and a table row.
DATASHEET_HTML = (
    b'<html><head><meta name="viewport" content="width=1"><style>td{width:32px}</style>'
    b"<script>var w=32;</script></head><body><p>Servo &amp; horn</p>"
    b"<table><tr><td>Weight</td><td>20.6 g</td></tr></table></body></html>"
)


def test_text_prints_an_html_source_as_its_rendered_lines(proj_dir, tmp_path):
    add_source(proj_dir, tmp_path, "ds.html", DATASHEET_HTML)
    code, out = run("text", str(proj_dir), "doc")
    assert (code, out) == (0, "===== doc page 1/1 =====\nServo & horn\nWeight\n20.6 g\n")


def test_text_keeps_an_html_sources_inline_tags_on_one_line(proj_dir, tmp_path):
    add_source(proj_dir, tmp_path, "ds.html", b"<p>Weight <b>20</b>.6&nbsp;g<br/>Servo</p>")
    assert (
        run("text", str(proj_dir), "doc")[1] == "===== doc page 1/1 =====\nWeight 20.6 g\nServo\n"
    )


def test_guard_text_prints_markup_in_a_txt_source_verbatim(proj_dir, tmp_path):
    add_source(proj_dir, tmp_path, "ds.txt", DATASHEET_HTML)
    code, out = run("text", str(proj_dir), "doc")
    assert (code, out) == (0, f"===== doc page 1/1 =====\n{DATASHEET_HTML.decode()}\n")


@pytest.mark.parametrize("grep", [["--grep", "x"], []], ids=["grep", "whole"])
def test_text_whose_reader_closes_the_pipe_stops_without_a_traceback(proj_dir, tmp_path, grep):
    # Far more than one pipe buffer, so the command is still writing when its reader stops.
    add_source(proj_dir, tmp_path, "notes.txt", b"x\n" * 200_000)
    command = [sys.executable, "-m", "cadrev.cli", "text", str(proj_dir), "doc", *grep]
    child = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert child.stdout is not None and child.stderr is not None
    child.stdout.readline()
    child.stdout.close()
    err = child.stderr.read().decode()
    child.wait()
    assert "Traceback" not in err and "BrokenPipeError" not in err, err


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


def test_crop_help_says_what_name_and_zoom_do(capsys):
    with pytest.raises(SystemExit):
        cli.main(["crop", "--help"])
    out = " ".join(capsys.readouterr().out.split())
    assert "--name NAME the crop's name: it is written to figures/crops/<NAME>.png" in out
    assert "--zoom ZOOM enlarge the crop by this whole-number factor (default 1)" in out


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
    return swap(MODEL, '{"link_1": ("link", Location())}', "{" + entries + "}")


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


def _three_links(root: Path, pairs: list | None = None) -> dict:
    """The clear check over three links, link_2 overlapping link_1 and link_3 clear of both;
    return its entry in report.json."""
    write(
        root,
        "model.py",
        _placed("Location()", "Location((p.pitch / 2, 0, 0))", "Location((0, 0, p.link_H * 2))"),
    )
    if pairs is not None:
        edit(root, "checks.yaml", lambda d: d["checks"][-1].update(pairs=pairs))
    _, report = verify(root)
    return next(c for c in report["checks"] if c["id"] == "clear")


def test_interference_check_without_pairs_states_it_evaluated_every_pair(proj_dir):
    clear = _three_links(proj_dir)
    assert clear["measured"].endswith(" link_1 ∩ link_2 over 3 pairs (all)"), clear["measured"]
    assert clear["pairs"] == 3 and type(clear["pairs"]) is int


def test_interference_check_with_pairs_states_it_evaluated_its_list(proj_dir):
    clear = _three_links(proj_dir, [["link_1", "link_3"], ["link_2", "link_3"]])
    assert clear["measured"] == "0 over 2 pairs (listed)" and clear["ok"]
    assert clear["pairs"] == 2
    assert "| 0 over 2 pairs (listed) |" in (proj_dir / "build" / "report.md").read_text()


def test_interference_check_over_one_listed_pair_says_pair(proj_dir):
    clear = _three_links(proj_dir, [["link_1", "link_2"]])
    assert clear["measured"].endswith(" link_1 ∩ link_2 over 1 pair (listed)"), clear["measured"]
    assert not clear["ok"] and clear["pairs"] == 1


def test_only_interference_results_carry_a_pair_count(proj_dir):
    _, report = verify(proj_dir)
    assert [c["id"] for c in report["checks"] if "pairs" in c] == ["clear"]
    env = next(c for c in report["checks"] if c["id"] == "env.L")
    assert env["measured"] == "40 along x"


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


_TWO_PARTS = swap(
    swap(
        MODEL,
        '"parts": {"link": link},',
        '"parts": {"link": link, "pin": Cylinder(p.hole_d / 2, p.link_H)},',
    ),
    '"link.b": (p.pitch / 2, 0, 0)}',
    '"link.b": (p.pitch / 2, 0, 0), "pin.c": (0, 0, 0)}',
)


def test_distance_between_datums_of_two_parts_is_a_finding(proj_dir):
    write(proj_dir, "model.py", _TWO_PARTS)
    edit(proj_dir, "checks.yaml", lambda d: d["checks"][1].update(between=["link.a", "pin.c"]))
    messages = findings(proj_dir, "check-config")
    assert len(messages) == 1 and "link.a" in messages[0] and "pin.c" in messages[0]
    assert "instances: [" in messages[0]


def test_guard_distance_between_datums_of_one_part_beside_another_part(proj_dir):
    write(proj_dir, "model.py", _TWO_PARTS)
    assert findings(proj_dir, "check-config") == []


# Angle checks: the angle at one datum between the directions to two others, in degrees.

# link.c sits on hole b's axis at the top face, so link.a - link.b - link.c is a right angle.
_CORNER = swap(
    MODEL,
    '"link.b": (p.pitch / 2, 0, 0)}',
    '"link.b": (p.pitch / 2, 0, 0), "link.c": (p.pitch / 2, 0, p.link_H / 2)}',
)


def _angle_check(root: Path, tmp_path: Path, text: str, value: float, **changes) -> None:
    """Ledger text as N1 (its angle a = value) and check the angle at link.b against it."""
    add_quote(root, tmp_path, text, text, {"a": value})
    write(root, "model.py", _CORNER)
    check = {
        "id": "ang",
        "kind": "angle",
        "between": ["link.a", "link.b", "link.c"],
        "evidence": "N1",
        "key": "a",
    }
    edit(root, "checks.yaml", lambda d: d["checks"].append({**check, **changes}))


def _angle(report: dict) -> dict:
    return next(c for c in report["checks"] if c["id"] == "ang")


def test_angle_check_on_a_right_angle_passes_against_90_degrees(proj_dir, tmp_path):
    _angle_check(proj_dir, tmp_path, "The arms meet at 90° at the pivot.", 90)
    code, report = verify(proj_dir)
    assert code == 0, report["findings"]
    assert _angle(report)["ok"] and _angle(report)["measured"].startswith("90°")


def test_angle_check_on_a_right_angle_fails_against_80_degrees(proj_dir, tmp_path):
    _angle_check(proj_dir, tmp_path, "The arms meet at 80° at the pivot.", 80)
    code, report = verify(proj_dir)
    assert code == 1 and not _angle(report)["ok"]
    assert "check-failed" in errors(proj_dir)


def test_angle_check_compares_a_value_stated_in_radians_in_degrees(proj_dir, tmp_path):
    _angle_check(proj_dir, tmp_path, "The arms meet at 1.5708 rad at the pivot.", 1.5708)
    code, report = verify(proj_dir)
    assert code == 0, report["findings"]
    assert _angle(report)["ok"] and _angle(report)["expected"].startswith("90.0002 ")


def test_angle_check_against_a_length_is_a_finding(proj_dir, tmp_path):
    _angle_check(proj_dir, tmp_path, "The arms reach 90 mm from the pivot.", 90)
    messages = findings(proj_dir, "unit-quantity")
    assert len(messages) == 1 and messages[0].startswith("N1.a") and "check ang" in messages[0]


def test_angle_check_tolerance_defaults_to_a_hundredth_of_a_degree(proj_dir, tmp_path):
    _angle_check(proj_dir, tmp_path, "The arms meet at 90.02° at the pivot.", 90.02)
    code, report = verify(proj_dir)
    assert code == 1 and not _angle(report)["ok"]
    assert "check-failed" in errors(proj_dir)


@pytest.mark.parametrize(
    "change",
    [
        lambda root: _set_tol(root, "ang", tol=0.05),
        lambda root: edit(root, "project.yaml", lambda d: d.update(tolerance={"angle": 0.05})),
    ],
    ids=["check-tol", "tolerance-angle"],
)
def test_angle_check_tolerance_is_set_by_tol_or_tolerance_angle(proj_dir, tmp_path, change):
    _angle_check(proj_dir, tmp_path, "The arms meet at 90.02° at the pivot.", 90.02)
    change(proj_dir)
    code, report = verify(proj_dir)
    assert code == 0, report["findings"]
    assert _angle(report)["ok"]


@pytest.mark.parametrize(
    "change, where",
    [
        (lambda root: _set_tol(root, "ang", tol=4.51), "tol 4.51 is"),
        (
            lambda root: edit(root, "project.yaml", lambda d: d.update(tolerance={"angle": 4.51})),
            "tol 4.51 (tolerance.angle)",
        ),
    ],
    ids=["check-tol", "tolerance-angle"],
)
def test_angle_check_tolerance_above_5_percent_of_its_value_is_a_finding(
    proj_dir, tmp_path, change, where
):
    _angle_check(proj_dir, tmp_path, "The arms meet at 90° at the pivot.", 90)  # cap 4.5°
    change(proj_dir)
    messages = findings(proj_dir, "tolerance-cap")
    assert len(messages) == 1 and "check ang" in messages[0] and where in messages[0]


def test_guard_angle_check_tolerance_at_5_percent_of_its_value(proj_dir, tmp_path):
    _angle_check(proj_dir, tmp_path, "The arms meet at 90° at the pivot.", 90, tol=4.5)
    assert findings(proj_dir, "tolerance-cap") == []


@pytest.mark.parametrize(
    "change, tol",
    [
        (lambda root: _set_tol(root, "ang", tol=0.5), 0.5),
        (
            lambda root: edit(root, "project.yaml", lambda d: d.update(tolerance={"angle": 0.05})),
            0.05,
        ),
    ],
    ids=["check-tol", "tolerance-angle"],
)
def test_report_lists_a_non_default_angle_tolerance_beside_its_check(
    proj_dir, tmp_path, change, tol
):
    _angle_check(proj_dir, tmp_path, "The arms meet at 90° at the pivot.", 90)
    change(proj_dir)
    _, report = verify(proj_dir)
    assert report["tolerances"] == [{"check": "ang", "kind": "angle", "tol": tol}]
    assert f"| ang | angle | tol {tol:g} |" in (proj_dir / "build" / "report.md").read_text()


@pytest.mark.parametrize(
    "change",
    [
        lambda root: None,
        lambda root: _set_tol(root, "ang", tol=0.01),
        lambda root: edit(root, "project.yaml", lambda d: d.update(tolerance={"length": 0.01})),
    ],
    ids=["unset", "tol-at-default", "tolerance-length"],
)
def test_guard_angle_check_at_the_default_angle_tolerance_is_not_listed(proj_dir, tmp_path, change):
    _angle_check(proj_dir, tmp_path, "The arms meet at 90° at the pivot.", 90)
    change(proj_dir)
    _, report = verify(proj_dir)
    assert "ang" not in [t["check"] for t in report["tolerances"]]


def test_guard_source_angle_an_angle_check_covers_is_checked_by_it(proj_dir, tmp_path):
    _angle_check(proj_dir, tmp_path, "The arms meet at 90° at the pivot.", 90)
    edit(
        proj_dir,
        "params.yaml",
        lambda d: d["params"].update(ang={"basis": "source", "from": "N1.a"}),
    )
    assert findings(proj_dir, "unchecked-source") == []


def test_angle_check_at_a_vertex_its_datum_coincides_with_is_a_finding(proj_dir, tmp_path):
    _angle_check(
        proj_dir,
        tmp_path,
        "The arms meet at 90° at the pivot.",
        90,
        between=["link.a", "link.b", "link.b"],
    )
    code, report = verify(proj_dir)
    messages = findings(proj_dir, "check-config")
    assert code == 1 and len(messages) == 1 and "coincides" in messages[0]


def test_angle_check_between_datums_of_two_parts_is_a_finding(proj_dir, tmp_path):
    _angle_check(
        proj_dir,
        tmp_path,
        "The arms meet at 90° at the pivot.",
        90,
        between=["link.a", "link.b", "pin.c"],
    )
    write(proj_dir, "model.py", _TWO_PARTS)
    messages = findings(proj_dir, "check-config")
    assert len(messages) == 1 and "link.a" in messages[0] and "pin.c" in messages[0]


# Checks over instances: read in the assembly frame, where the assembly places each instance.


def _over_instances(root: Path, tmp_path: Path, text: str, values: dict, check: dict) -> None:
    """Two links, link_1 at the origin and link_2 20 above it; text ledgered as N1, and check,
    over link_1 and link_2, comparing with it."""
    add_quote(root, tmp_path, text, text, values)
    write(root, "model.py", _placed("Location()", "Location((0, 0, p.link_L / 2))"))
    full = {"id": "inst", "instances": ["link_1", "link_2"], "evidence": "N1", **check}
    edit(root, "checks.yaml", lambda d: d["checks"].append(full))


def _inst(report: dict) -> list[dict]:
    return [c for c in report["checks"] if c["id"].startswith("inst")]


def test_bbox_over_two_instances_reads_their_union_in_the_assembly_frame(proj_dir, tmp_path):
    # link_1 spans z -4..4 and link_2 z 16..24, so their union is 28 high.
    text = "The two links stack 28 mm high."
    _over_instances(proj_dir, tmp_path, text, {"h": 28}, {"kind": "bbox", "axes": {"h": "z"}})
    code, report = verify(proj_dir)
    assert code == 0, report["findings"]
    assert [c["ok"] for c in _inst(report)] == [True]
    assert _inst(report)[0]["measured"].startswith("28 ")


def test_distance_between_datums_of_two_instances_reads_their_placed_distance(proj_dir, tmp_path):
    # link.a is the same point of each link's part, so only link_2's Location sets them apart.
    check = {"kind": "distance", "between": ["link_1.a", "link_2.a"], "key": "gap"}
    _over_instances(proj_dir, tmp_path, "The links sit 20 mm apart.", {"gap": 20}, check)
    code, report = verify(proj_dir)
    assert code == 0, report["findings"]
    assert [c["ok"] for c in _inst(report)] == [True]
    assert _inst(report)[0]["measured"].startswith("20 link_1.a - link_2.a")


def test_angle_over_three_instance_datums_reads_their_placed_angle(proj_dir, tmp_path):
    # link_2.b sits 20 above link_1.b, so the angle at link_1.b from link_1.a to it is square.
    check = {"kind": "angle", "between": ["link_1.a", "link_1.b", "link_2.b"], "key": "a"}
    _over_instances(proj_dir, tmp_path, "The links meet at 90° at the pivot.", {"a": 90}, check)
    code, report = verify(proj_dir)
    assert code == 0, report["findings"]
    assert [c["ok"] for c in _inst(report)] == [True]
    assert _inst(report)[0]["measured"].startswith("90° at link_1.b")


def test_instance_sharing_its_part_name_resolves_as_the_instance(proj_dir, tmp_path):
    check = {"kind": "distance", "between": ["link_1.a", "link.a"], "key": "gap"}
    _over_instances(proj_dir, tmp_path, "The links sit 20 mm apart.", {"gap": 20}, check)
    placed = '{"link_1": ("link", Location()), "link": ("link", Location((0, 0, p.link_L / 2)))}'
    write(proj_dir, "model.py", swap(MODEL, '{"link_1": ("link", Location())}', placed))
    edit(proj_dir, "checks.yaml", lambda d: d["checks"][-1].update(instances=["link_1", "link"]))
    code, report = verify(proj_dir)
    assert code == 0, report["findings"]
    assert [c["ok"] for c in _inst(report)] == [True]


@pytest.mark.parametrize(
    "change, named",
    [
        ({"instances": ["link_1", "link_9"]}, "link_9"),
        ({"between": ["link_1.a", "link_2.z"]}, "link_2.z"),
        ({"instances": []}, "empty"),
    ],
    ids=["unknown-instance", "unknown-feature", "empty"],
)
def test_check_over_an_unknown_instance_or_feature_or_no_instances_is_a_finding(
    proj_dir, tmp_path, change, named
):
    check = {"kind": "distance", "between": ["link_1.a", "link_2.a"], "key": "gap", **change}
    _over_instances(proj_dir, tmp_path, "The links sit 20 mm apart.", {"gap": 20}, check)
    code, report = verify(proj_dir)
    messages = findings(proj_dir, "check-config")
    assert code == 1 and len(messages) == 1 and named in messages[0]


def test_check_naming_both_part_and_instances_is_a_schema_finding(proj_dir, tmp_path):
    check = {"kind": "bbox", "part": "link", "axes": {"h": "z"}}
    _over_instances(proj_dir, tmp_path, "The two links stack 28 mm high.", {"h": 28}, check)
    messages = findings(proj_dir, "schema")
    assert len(messages) == 1 and "part" in messages[0] and "instances" in messages[0]


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


_SLOT = swap(
    MODEL,
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
    write(proj_dir, "model.py", swap(MODEL, '"link.b": (p.pitch / 2, 0, 0)', '"link.b": (0, 0, 0)'))
    messages = findings(proj_dir, "datum-off-solid")
    assert len(messages) == 1 and "link.b" in messages[0]


def test_part_of_two_disjoint_solids_is_invalid(proj_dir):
    split = "link += Pos(p.link_L, 0, 0) * Box(p.link_W, p.link_W, p.link_H)\n    return {"
    write(proj_dir, "model.py", swap(MODEL, "return {", split))
    messages = findings(proj_dir, "part-invalid")
    assert len(messages) == 1 and "2 solids" in messages[0]


def test_guard_part_of_two_touching_bodies_fused_into_one_solid(proj_dir):
    fused = "link += Pos(p.link_L / 2, 0, 0) * Box(p.link_W, p.link_W, p.link_H)\n    return {"
    write(proj_dir, "model.py", swap(MODEL, "return {", fused))
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
    write(root, "model.py", _links(2))
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


def _links(n: int) -> str:
    """The fixture's model with up to six links, link_1 to link_<n>, clear of each other: in two
    columns a link's length apart, each three links stacked a link's length apart."""
    xs, zs = ("0", "p.link_L * 2"), ("0", "p.link_L", "-p.link_L")
    return _placed(*[f"Location(({x}, 0, {z}))" for x in xs for z in zs][:n])


def _two_weighed_links(root: Path, tmp_path: Path, check=()) -> dict:
    """Two links, each 3 g by the mass model from N1.each, and check total, updated by check,
    against their stated 6 g together; report.json."""
    text = "Each link weighs 3 g; the two links weigh 6 g together."
    add_quote(root, tmp_path, text, text.rstrip("."), {"each": 3, "m": 6})
    write(root, "model.py", _links(2))
    add_params(root, link_m={"basis": "source", "from": "N1.each"})
    _parts(link={"mass": "link_m"})(root, tmp_path)
    total = {"id": "total", "kind": "mass", "evidence": "N1", "key": "m", "tol_rel": 0.01}
    edit(root, "checks.yaml", lambda d: d["checks"].append(total | dict(check)))
    return verify(root)[1]


def test_mass_check_naming_no_instances_or_parts_weighs_every_instance(proj_dir, tmp_path):
    report = _two_weighed_links(proj_dir, tmp_path)
    assert report["status"] == "VERIFIED", report["findings"]
    total = _by_id(report)["total"]
    assert total["ok"] and total["measured"] == "6"
    assert (total["rests_on"], total["uncounted"]) == ("proposed", {"link": 2})


def test_report_md_names_a_part_weighed_in_several_uncounted_instances(proj_dir, tmp_path):
    _two_weighed_links(proj_dir, tmp_path)
    assert "rests on proposed: link (2 instances uncounted)" in _check_row(proj_dir, "total")


def test_mass_check_over_one_instance_weighs_it_alone_and_rests_on_source(proj_dir, tmp_path):
    _two_weighed_links(proj_dir, tmp_path)
    one = {"id": "one", "kind": "mass", "instances": ["link_1"], "evidence": "N1", "key": "each"}
    edit(proj_dir, "checks.yaml", lambda d: d["checks"].append(one | {"tol_rel": 0.01}))
    code, report = verify(proj_dir)
    assert code == 0, report["findings"]
    one = _by_id(report)["one"]
    assert one["ok"] and one["measured"] == "3"
    assert (one["rests_on"], one["uncounted"]) == ("source", {})


def test_mass_check_count_agreeing_with_the_instances_rests_on_its_basis(proj_dir, tmp_path):
    add_params(
        proj_dir,
        n_links={"basis": "proposed", "value": 2, "rationale": "'two links'", "gap": "G1"},
    )
    report = _two_weighed_links(proj_dir, tmp_path, {"counts": {"link": "n_links"}})
    assert report["status"] == "VERIFIED", report["findings"]
    total = _by_id(report)["total"]
    assert total["ok"] and total["uncounted"] == {}
    assert (total["rests_on"], total["rests_on_params"]) == ("proposed", ["n_links"])


def test_mass_check_count_other_than_the_instances_it_weighs_is_check_config(proj_dir, tmp_path):
    add_params(
        proj_dir,
        n_links={"basis": "proposed", "value": 3, "rationale": "'three links'", "gap": "G1"},
    )
    report = _two_weighed_links(proj_dir, tmp_path, {"counts": {"link": "n_links"}})
    assert [f["message"] for f in report["findings"] if f["rule"] == "check-config"] == [
        "check total: counts link as n_links (3), but it weighs 2 instances of it"
    ]
    assert "total" not in _by_id(report)


@pytest.mark.parametrize(
    "check, message",
    [
        ({"instances": ["link_9"]}, "check total: link_9 is not an instance of the assembly"),
        (
            {"instances": ["link_1"], "parts": ["link", "pin"]},
            "check total: parts names pin, but it weighs no instance of it",
        ),
    ],
    ids=["unknown-instance", "part-with-no-instance-weighed"],
)
def test_mass_check_naming_what_it_weighs_none_of_is_check_config(
    proj_dir, tmp_path, check, message
):
    report = _two_weighed_links(proj_dir, tmp_path, check)
    assert [f["message"] for f in report["findings"] if f["rule"] == "check-config"] == [message]


# What a check rests on: the weakest basis among the params it reads.


def _check_row(root: Path, check: str) -> str:
    """The row of check in report.md's checks table."""
    md = (root / "build" / "report.md").read_text()
    return next(line for line in md.splitlines() if line.startswith(f"| {check} |"))


_RESIN = {"basis": "proposed", "value": 0.0012, "rationale": "a typical resin", "gap": "G1"}


def _weighed(
    root: Path, tmp_path: Path, text: str, values: dict, check=(), links: int = 1, **params
) -> dict:
    """Ledger text as N1, add params, place links links, and check their mass N1.m with the
    density param rho, its check entry updated by check; report.json."""
    add_quote(root, tmp_path, text, text, values)
    if links > 1:
        write(root, "model.py", _links(links))
    add_params(root, **params)
    mass = {
        "id": "m",
        "kind": "mass",
        "parts": ["link"],
        "density": "rho",
        "evidence": "N1",
        "key": "m",
        "tol_rel": 0.05,
    }
    edit(root, "checks.yaml", lambda d: d["checks"].append(mass | dict(check)))
    return verify(root)[1]


def _mass_result(report: dict) -> dict:
    assert report["status"] == "VERIFIED", report["findings"]
    return next(r for r in report["checks"] if r["id"] == "m")


_MEASURED = {
    "basis": "measured",
    "from": "F2",
    "value": 0.0012,
    "method": "weighed offcut",
    "uncertainty": "±5%",
}


@pytest.mark.parametrize(
    "rho, rests_on",
    [
        (_RESIN, "proposed"),
        (_MEASURED, "measured"),
        ({"basis": "derived", "expr": "foot_w * 0.0012 / 5.5"}, "measured"),
        ({"basis": "derived", "expr": "hole_d * 0.0004"}, "proposed"),
        (
            {
                "basis": "derived",
                "expr": "foot_w * 0.0012 / 5.5",
                "gap": "G1",
                "interpretation": "density scales with the foot width",
            },
            "proposed",
        ),
    ],
    ids=[
        "proposed",
        "measured",
        "derived-from-measured",
        "derived-from-proposed",
        "derived-naming-a-gap",
    ],
)
def test_mass_check_rests_on_the_basis_its_density_rests_on(proj_dir, tmp_path, rho, rests_on):
    add_measured(proj_dir)
    m = _mass_result(_weighed(proj_dir, tmp_path, "The link weighs 1.8 g.", {"m": 1.8}, rho=rho))
    assert m["ok"] and m["rests_on"] == rests_on
    assert f"rests on {rests_on}: rho" in _check_row(proj_dir, "m")


def test_guard_failing_mass_check_on_a_proposed_density_still_fails(proj_dir, tmp_path):
    rho = _RESIN | {"value": 0.002}
    report = _weighed(proj_dir, tmp_path, "The link weighs 1.8 g.", {"m": 1.8}, rho=rho)
    assert report["status"] == "NOT VERIFIED"
    assert [f["rule"] for f in report["findings"] if f["level"] == "error"] == ["check-failed"]


def test_mass_check_on_source_density_add_and_counts_rests_on_source(proj_dir, tmp_path):
    text = "3 links weigh 6.4 g with 1 g of screws, printed in resin of 1.2 g/cm3."
    report = _weighed(
        proj_dir,
        tmp_path,
        text,
        {"n": 3, "m": 6.4, "screws": 1, "rho": 1.2},
        check={"add": ["hardware"], "counts": {"link": "n_links"}},
        links=3,
        rho={"basis": "source", "from": "N1.rho"},
        hardware={"basis": "source", "from": "N1.screws"},
        n_links={"basis": "source", "from": "N1.n"},
    )
    assert _mass_result(report)["rests_on"] == "source"
    assert "rests on" not in _check_row(proj_dir, "m")


def test_mass_check_counts_a_part_by_a_count_its_source_states_in_words(proj_dir, tmp_path):
    report = _weighed(
        proj_dir,
        tmp_path,
        "Three links weigh 6.4 g with 1 g of screws, printed in resin of 1.2 g/cm3.",
        {"n": 3, "m": 6.4, "screws": 1, "rho": 1.2},
        check={"add": ["hardware"], "counts": {"link": "n_links"}},
        links=3,
        rho={"basis": "source", "from": "N1.rho"},
        hardware={"basis": "source", "from": "N1.screws"},
        n_links={"basis": "source", "from": "N1.n"},
    )
    assert report["params"]["n_links"]["rests_on"] == "source"
    assert _mass_result(report)["rests_on"] == "source"


def _counted_through(root: Path, tmp_path: Path, counted: bool) -> dict:
    """The link counted, where counted, by n_links, derived from two stated counts; report.json."""
    return _weighed(
        root,
        tmp_path,
        "The 2 legs carry 3 links each, together 10.8 g, printed in resin of 1.2 g/cm3.",
        {"legs": 2, "n": 3, "m": 10.8, "rho": 1.2},
        check={"counts": {"link": "n_links"}} if counted else {},
        links=6,
        rho={"basis": "source", "from": "N1.rho"},
        legs={"basis": "source", "from": "N1.legs"},
        n_each={"basis": "source", "from": "N1.n"},
        n_links={"basis": "derived", "expr": "legs * n_each"},
    )


def _unchecked_in(report: dict) -> list[str]:
    """The params report.json names [unchecked-source], as `param <name>`."""
    return [
        f["message"].split(":")[0] for f in report["findings"] if f["rule"] == "unchecked-source"
    ]


def _unchecked(root: Path) -> list[str]:
    """The params a fresh verification run names [unchecked-source]; where the test has already
    run one, _unchecked_in reads its report."""
    return _unchecked_in(verify(root)[1])


def _unchecked_printed(printed: list[str]) -> list[str]:
    """The params a run's printed findings name [unchecked-source], where a partial run writes no
    report."""
    prefix = "warning: [unchecked-source] "
    return [line.removeprefix(prefix).split(":")[0] for line in printed if line.startswith(prefix)]


def test_stated_counts_a_mass_check_reads_through_a_derived_param_are_covered(proj_dir, tmp_path):
    report = _counted_through(proj_dir, tmp_path, counted=True)
    assert _mass_result(report)["ok"]
    assert {"param legs", "param n_each"}.isdisjoint(_unchecked_in(report))


def test_guard_stated_counts_feeding_a_param_no_check_reads_are_unchecked_source(
    proj_dir, tmp_path
):
    report = _counted_through(proj_dir, tmp_path, counted=False)
    assert {"param legs", "param n_each"} <= set(_unchecked_in(report))


def test_mass_check_names_each_param_it_reads_resting_on_less_than_source(proj_dir, tmp_path):
    report = _weighed(
        proj_dir,
        tmp_path,
        "The link weighs 2.8 g, printed in resin of 1.2 g/cm3.",
        {"m": 2.8, "rho": 1.2},
        check={"add": ["hardware"]},
        rho={"basis": "source", "from": "N1.rho"},
        hardware=_RESIN | {"value": 1, "rationale": "screws by count"},
    )
    assert _mass_result(report)["rests_on"] == "proposed"
    row = _check_row(proj_dir, "m")
    assert "rests on proposed: hardware" in row and "rho" not in row


def test_report_json_names_the_params_a_check_rests_on(proj_dir, tmp_path):
    report = _weighed(
        proj_dir,
        tmp_path,
        "3 links weigh 6.4 g with 1 g of screws.",
        {"n": 3, "m": 6.4},
        check={"add": ["hardware"], "counts": {"link": "n_links"}},
        links=3,
        rho=_RESIN,
        hardware=_RESIN | {"value": 1, "rationale": "screws by count"},
        n_links={"basis": "source", "from": "N1.n"},
    )
    m = _mass_result(report)
    assert (m["rests_on"], m["rests_on_params"]) == ("proposed", ["rho", "hardware"])
    assert all(r["rests_on_params"] == [] for r in report["checks"] if r["id"] != "m")


def test_bbox_distance_and_interference_checks_rest_on_source(proj_dir):
    _, report = verify(proj_dir)
    assert {r["kind"]: r["rests_on"] for r in report["checks"]} == {
        "bbox": "source",
        "distance": "source",
        "interference": "source",
    }
    assert all("rests on" not in _check_row(proj_dir, c) for c in ("env.L", "pitch", "clear"))


def test_report_md_labels_the_declared_bases_apart_from_what_params_rest_on(proj_dir):
    add_params(proj_dir, half={"basis": "derived", "expr": "hole_d / 2"})
    write(proj_dir, "model.py", swap(MODEL, "p.hole_d / 2", "p.half"))
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


# Motion: a four-bar posed through MuJoCo, its checks evaluated on cadrev's own geometry (ADR-0008).

# Crank a, coupler b, rocker c and ground d, in mm: a crank-rocker, so the crank turns fully.
BAR = {"crank": 15, "coupler": 35, "rocker": 30, "ground": 40}
RESIN = 1.2  # g/cm³: 0.0012 g/mm³ in the project's units

FOUR_BAR = """\
import math

from build123d import *


def bar(p, length):
    body = Pos(length / 2, 0, 0) * Box(length + p.link_W, p.link_W, p.link_H)
    body -= Cylinder(p.hole_d / 2, p.link_H)
    body -= Pos(length, 0, 0) * Cylinder(p.hole_d / 2, p.link_H)
    return body


def build(p):
    a, b, c, d = p.crank, p.coupler, p.rocker, p.ground
    # As built the crank stands upright, B = (0, a), and the coupler and rocker close the loop.
    reach = math.hypot(d, a)
    along = (b * b - c * c + reach * reach) / (2 * reach)
    up = math.sqrt(b * b - along * along)
    ux, uy = d / reach, -a / reach
    cx, cy = along * ux - up * uy, a + along * uy + up * ux
    lengths = {"ground": d, "crank": a, "coupler": b, "rocker": c}
    datums = {}
    for name, length in lengths.items():
        datums[f"{name}.a"] = (0, 0, 0)
        datums[f"{name}.a_up"] = (0, 0, p.link_H / 2)
        datums[f"{name}.d"] = (length, 0, 0)
    coupler_at = math.degrees(math.atan2(cy - a, cx))
    rocker_at = math.degrees(math.atan2(-cy, d - cx))
    return {
        "parts": {name: bar(p, length) for name, length in lengths.items()},
        "datums": datums,
        "assembly": {
            "ground_1": ("ground", Location()),
            "crank_1": ("crank", Location((0, 0, 0), (0, 0, 90))),
            "coupler_1": ("coupler", Location((0, a, 0), (0, 0, coupler_at))),
            "rocker_1": ("rocker", Location((cx, cy, 0), (0, 0, rocker_at))),
        },
        "joints": {
            "input": {
                "type": "revolute",
                "parent": "ground_1",
                "child": "crank_1",
                "axis": ["crank_1.a", "crank_1.a_up"],
                "range": ["input_min", "input_max"],
                "drive": "actuated",
            },
            "knee": {
                "type": "revolute",
                "parent": "crank_1",
                "child": "coupler_1",
                "axis": ["coupler_1.a", "coupler_1.a_up"],
                "drive": "passive",
            },
            "elbow": {
                "type": "revolute",
                "parent": "coupler_1",
                "child": "rocker_1",
                "axis": ["rocker_1.a", "rocker_1.a_up"],
                "drive": "passive",
            },
        },
        "loops": {"closure": ["rocker_1.d", "ground_1.d"]},
    }
"""


def bar_pivot(turn: float) -> tuple[float, float]:
    """The four-bar's closed form: where the coupler meets the rocker (C) with the crank turned
    turn degrees from upright, on the branch the model is built on."""
    a, b, c, d = (BAR[n] for n in ("crank", "coupler", "rocker", "ground"))
    theta = math.radians(90 + turn)
    bx, by = a * math.cos(theta), a * math.sin(theta)
    reach = math.hypot(d - bx, -by)
    along = (b * b - c * c + reach * reach) / (2 * reach)
    up = math.sqrt(b * b - along * along)
    ux, uy = (d - bx) / reach, -by / reach
    return bx + along * ux - up * uy, by + along * uy + up * ux


def bar_text(turns: tuple[int, ...]) -> str:
    """The four-bar's source: its link lengths, and for each turn of the crank from upright how far
    C lies from the crank pivot and the rocker's angle to the ground link, from the closed form;
    last, the density of the resin the bars are printed in."""
    lines = [
        "The crank is {crank} mm, the coupler {coupler} mm, the rocker {rocker} mm "
        "and the ground link {ground} mm long.".format(**BAR)
    ]
    for turn in turns:
        cx, cy = bar_pivot(turn)
        rock = math.degrees(math.atan2(cy, BAR["ground"] - cx))
        lines.append(
            f"Turned {turn}° from upright, the crank puts the rocker pivot "
            f"{math.hypot(cx, cy):.4f} mm from the crank pivot, "
            f"the rocker at {rock:.3f}° to the ground link."
        )
    lines.append(f"The bars are printed in a resin of {RESIN} g/cm3.")
    return "\n".join(lines) + "\n"


def four_bar(root: Path, tmp_path: Path, turns: tuple[int, ...] = (30, 60)) -> None:
    """Replace the project with the four-bar, built upright with one actuated joint, input, and one
    loop, closure; each bar weighs its volume times the resin's density, ledgered R. For each
    turn, ledger P<turn> and check C's distance from the crank pivot and the rocker's angle, posed
    at that turn: by the ledger key for the first turn, by a param for the rest."""
    edit(root, "project.yaml", lambda d: d.update(sources=[]))
    (root / "sources" / "paper.txt").unlink()
    text = tmp_path / "bar.txt"
    text.write_text(bar_text(turns))
    register = ["source", str(root), str(text), "--id", "bar", "--kind", "paper"]
    assert cli.main([*register, "--citation", "Roe 2026"]) == 0
    lines = text.read_text().splitlines()
    lengths = {"a": "crank", "b": "coupler", "c": "rocker", "d": "ground"}
    evidence = [
        {
            "id": "L",
            "source": "bar",
            "locator": "Sec. 1",
            "quote": lines[0].rstrip("."),
            "values": {key: BAR[name] for key, name in lengths.items()},
        },
        {
            "id": "R",
            "source": "bar",
            "locator": "Sec. 3",
            "quote": lines[-1].rstrip("."),
            "values": {"rho": RESIN},
        },
    ]
    params = {name: {"basis": "source", "from": f"L.{key}"} for key, name in lengths.items()}
    params["density"] = {"basis": "source", "from": "R.rho"}
    chosen = {"link_W": 5, "link_H": 4, "hole_d": 2, "input_min": -180, "input_max": 180}
    params |= {
        name: {"basis": "proposed", "value": value, "rationale": "a printable bar", "gap": "G1"}
        for name, value in chosen.items()
    }
    checks = []
    for i, (turn, line) in enumerate(zip(turns, lines[1:])):
        eid = f"P{turn}"
        _, dist, rock = (float(v) for v in re.findall(r"\d+(?:\.\d+)?", line))
        evidence.append(
            {
                "id": eid,
                "source": "bar",
                "locator": "Sec. 2",
                "quote": line.rstrip("."),
                "values": {"turn": turn, "AC": dist, "rock": rock},
            }
        )
        pose = f"{eid}.turn"
        if i:
            pose = f"turn_{turn}"
            params[pose] = {"basis": "source", "from": f"{eid}.turn"}
        over = {"instances": ["ground_1", "rocker_1"], "evidence": eid, "pose": {"input": pose}}
        checks += [
            {
                "id": f"ac{turn}",
                "kind": "distance",
                "between": ["ground_1.a", "rocker_1.a"],
                "key": "AC",
                **over,
            },
            {
                "id": f"rock{turn}",
                "kind": "angle",
                "between": ["ground_1.a", "ground_1.d", "rocker_1.a"],
                "key": "rock",
                **over,
            },
        ]
    write(root, "evidence.yaml", {"evidence": evidence, "skipped": [], "conflicts": []})
    parts = {name: {"density": "density"} for name in lengths.values()}
    write(root, "params.yaml", {"params": params, "parts": parts})
    write(root, "gaps.yaml", {"gaps": [{"id": "G1", "question": "bar section?", "ask": "authors"}]})
    write(root, "checks.yaml", {"checks": checks})
    write(root, "model.py", FOUR_BAR)


def _by_id(report: dict) -> dict[str, dict]:
    return {c["id"]: c for c in report["checks"]}


def test_four_bar_posed_at_two_input_angles_matches_its_closed_form(proj_dir, tmp_path):
    four_bar(proj_dir, tmp_path)
    code, report = verify(proj_dir)
    assert code == 0, report["findings"]
    # Only the link lengths no check compares are flagged: the range and pose params are read.
    assert {f["rule"] for f in report["findings"]} == {"unchecked-source"}
    checks = _by_id(report)
    assert set(checks) == {"ac30", "rock30", "ac60", "rock60"}
    assert all(c["ok"] for c in checks.values()), checks
    # Each check compares with the closed form at its pose, which differs from pose to pose.
    assert checks["ac30"]["expected"] != checks["ac60"]["expected"]


def test_report_json_gives_each_posed_check_its_pose(proj_dir, tmp_path):
    four_bar(proj_dir, tmp_path)
    checks = _by_id(verify(proj_dir)[1])
    assert checks["ac30"]["pose"] == {"input": {"from": "P30.turn", "value": 30}}
    assert checks["rock60"]["pose"] == {"input": {"from": "turn_60", "value": 60}}
    md = (proj_dir / "build" / "report.md").read_text()
    assert "| posed: input at 60 (turn_60) |" in md


def _coupler(length: float):
    """The four-bar with its coupler proposed at length: at 20 the crank turned 60° pulls B 53.5
    from D, beyond the coupler and rocker's reach of 50; turned 30°, 49.2, within it."""

    def change(r, t):
        four_bar(r, t)
        spec = {"basis": "proposed", "value": length, "rationale": "x", "from": None}
        _param("coupler", **spec)(r, t)

    return change


def test_loop_that_cannot_close_at_a_pose_is_loop_open_naming_loop_and_pose(proj_dir, tmp_path):
    _coupler(20)(proj_dir, tmp_path)
    code, report = verify(proj_dir)
    opened = [f["message"] for f in report["findings"] if f["rule"] == "loop-open"]
    assert code == 1 and len(opened) == 1, opened
    assert opened[0].startswith("loop closure: rocker_1.d and ground_1.d stay ")
    assert "with input at 60 (turn_60)" in opened[0]
    # The checks at the pose that closes are evaluated; those at the open one are not.
    assert set(_by_id(report)) == {"ac30", "rock30"}


def test_loop_open_in_the_assembly_as_built_is_loop_open_saying_so(proj_dir, tmp_path):
    _bar(
        '"rocker_1": ("rocker", Location((cx, cy, 0)',
        '"rocker_1": ("rocker", Location((cx + 1, cy, 0)',
    )(proj_dir, tmp_path)
    as_built = [m for m in findings(proj_dir, "loop-open") if "as built" in m]
    assert as_built == [
        "loop closure: rocker_1.d and ground_1.d stay 1 apart as built; build the assembly "
        "closed, with every loop's datums together"
    ]


def test_model_with_joints_exports_mjcf_and_a_mesh_per_part_that_mujoco_loads(proj_dir, tmp_path):
    mujoco = importlib.import_module("mujoco")

    four_bar(proj_dir, tmp_path)
    code, report = verify(proj_dir)
    assert code == 0, report["findings"]
    build = proj_dir / "build"
    assert sorted(f.name for f in (build / "meshes").iterdir()) == [
        "coupler.stl",
        "crank.stl",
        "ground.stl",
        "rocker.stl",
    ]
    model = mujoco.MjModel.from_xml_path(str(build / "model.mjcf"))
    assert (model.njnt, model.neq, model.nu) == (3, 1, 1)
    assert report["motion"]["joints"]["input"] == {
        "type": "revolute",
        "parent": "ground_1",
        "child": "crank_1",
        "drive": "actuated",
        "range": {"from": ["input_min", "input_max"], "value": [-180, 180]},
    }
    assert "**Kinematic**: 3 joints and 1 loop" in (build / "report.md").read_text()


def test_report_json_gives_the_joint_ranges_and_physics_values_the_mjcf_exports(proj_dir, tmp_path):
    mujoco = importlib.import_module("mujoco")

    physical(proj_dir, tmp_path)
    code, report = verify(proj_dir)
    assert code == 0, report["findings"]
    m = mujoco.MjModel.from_xml_path(str(proj_dir / "build" / "model.mjcf"))
    joints, cord = report["motion"]["joints"], report["motion"]["tendons"]["cord"]
    joint = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, "input")
    assert joints["input"]["range"] == {"from": ["input_min", "input_max"], "value": [-180, 180]}
    assert list(m.jnt_range[joint]) == pytest.approx([-math.pi, math.pi])
    knee = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, "knee")
    assert joints["knee"]["damping"] == {"from": "knee_damping", "value": PHYSICS["knee_damping"]}
    assert m.dof_damping[m.jnt_dofadr[knee]] == pytest.approx(
        joints["knee"]["damping"]["value"] * MJCF_PER_N
    )
    assert m.jnt_stiffness[knee] == pytest.approx(joints["knee"]["stiffness"]["value"] * MJCF_PER_N)
    assert cord["path"] == ["crank_1.d", "rocker_1.a"]
    assert m.tendon_stiffness[0] == pytest.approx(cord["stiffness"]["value"] * MJCF_PER_N)


def test_model_with_no_joints_writes_no_mjcf_and_its_report_says_it_is_static(proj_dir):
    code, report = verify(proj_dir)
    assert code == 0
    assert not (proj_dir / "build" / "model.mjcf").exists()
    assert report["motion"] == {
        "joints": {},
        "loops": {},
        "gears": {},
        "tendons": {},
        "cables": {},
        "dropped": False,
    }
    assert (
        "**Static**: model.py returns no joints" in (proj_dir / "build" / "report.md").read_text()
    )


def _density(value: float):
    """The four-bar, its export weighing each part by a proposed density of value."""

    def change(r, t):
        four_bar(r, t)
        spec = {"basis": "proposed", "value": value, "rationale": "resin", "from": None}
        _param("density", gap="G1", **spec)(r, t)

    return change


def _parts(**entries):
    """Set params.yaml's mass model entries: part -> {mass or density: param}, None removing one."""

    def apply(d):
        d.setdefault("parts", {}).update(entries)
        d["parts"] = {k: v for k, v in d["parts"].items() if v is not None}

    return lambda r, t: edit(r, "params.yaml", apply)


def _servo_crank(r: Path, t: Path) -> None:
    """The four-bar with its crank a purchased part: 7.5 g from its datasheet."""
    four_bar(r, t)
    _param("crank_mass", basis="proposed", value=7.5, rationale="datasheet", gap="G1")(r, t)
    _parts(crank={"mass": "crank_mass"})(r, t)


def _inertials(root: Path) -> dict[str, dict[str, list[float]]]:
    """Each body's <inertial> in build/model.mjcf: attribute -> its numbers."""
    tree = ET.parse(root / "build" / "model.mjcf")
    return {
        body.get("name", ""): {k: [float(v) for v in x.split()] for k, x in inertial.items()}
        for body in tree.iter("body")
        for inertial in body.iter("inertial")
        if inertial in list(body)
    }


def test_export_weighs_a_part_by_its_datasheet_mass_or_its_volume_times_density(proj_dir, tmp_path):
    _servo_crank(proj_dir, tmp_path)
    code, report = verify(proj_dir)
    assert code == 0, report["findings"]
    inertials = _inertials(proj_dir)
    assert inertials["crank_1"]["mass"] == [7.5]
    # The ground bar is 45 × 5 × 4 less two 2 mm holes: 874.867 mm³, at 0.0012 g/mm³.
    assert inertials["ground_1"]["mass"][0] == pytest.approx(1.049841, rel=1e-6)


def test_exported_inertia_is_the_solids_at_its_mass(proj_dir, tmp_path):
    """MuJoCo, given each mesh and its body's mass but no <inertial>, computes the inertia the
    export should state: the two agree to 0.1%, the error of the meshes' tessellated holes."""
    mujoco = importlib.import_module("mujoco")

    _servo_crank(proj_dir, tmp_path)
    assert verify(proj_dir)[0] == 0
    build = proj_dir / "build"
    exported = mujoco.MjModel.from_xml_path(str(build / "model.mjcf"))
    tree = ET.parse(build / "model.mjcf")
    for mesh in tree.iter("mesh"):
        mesh.set("inertia", "exact")
    for body in tree.iter("body"):
        inertial = body.find("inertial")
        assert inertial is not None
        body.remove(inertial)
        geom = body.find("geom")
        assert geom is not None
        geom.set("mass", inertial.get("mass", ""))
    tree.write(build / "from-meshes.mjcf")
    meshed = mujoco.MjModel.from_xml_path(str(build / "from-meshes.mjcf"))
    assert exported.nbody == 5
    for body in range(1, exported.nbody):
        assert exported.body_mass[body] == pytest.approx(meshed.body_mass[body], rel=1e-9)
        assert exported.body_ipos[body] == pytest.approx(meshed.body_ipos[body], abs=1e-3)
        assert sorted(exported.body_inertia[body]) == pytest.approx(
            sorted(meshed.body_inertia[body]), rel=1e-3
        )


def test_report_json_gives_the_masses_and_inertias_the_mjcf_exports(proj_dir, tmp_path):
    _servo_crank(proj_dir, tmp_path)
    report = verify(proj_dir)[1]
    masses = report["masses"]
    assert masses["crank"]["from"] == {"mass": "crank_mass"}
    assert masses["ground"]["from"] == {"density": "density"}
    for inst, inertial in _inertials(proj_dir).items():
        weighed = masses[inst.removesuffix("_1")]  # each bar's one instance
        assert inertial["mass"] == [weighed["mass"]]
        assert inertial["pos"] == weighed["center"]
        assert inertial["fullinertia"] == weighed["inertia"]


def _unweighed_rocker(r: Path, t: Path) -> None:
    """The four-bar with its rocker left out of the mass model."""
    four_bar(r, t)
    _parts(rocker=None)(r, t)


def test_part_of_a_model_with_joints_weighed_by_nothing_is_part_mass_naming_it(proj_dir, tmp_path):
    _unweighed_rocker(proj_dir, tmp_path)
    code, report = verify(proj_dir)
    assert code == 1
    assert findings(proj_dir, "part-mass") == [
        "part rocker: params.yaml parts gives it no mass or density, so the MJCF export "
        "cannot weigh it"
    ]
    assert "rocker" not in report["masses"]


def test_part_mass_names_the_param_a_parts_entry_names_but_params_lacks(proj_dir, tmp_path):
    four_bar(proj_dir, tmp_path)
    _parts(rocker={"density": "resin"})(proj_dir, tmp_path)
    assert findings(proj_dir, "part-mass") == [
        "part rocker: params.yaml parts names density resin, which params.yaml does not define"
    ]


def test_parts_entry_naming_no_part_of_the_model_is_part_mass(proj_dir, tmp_path):
    four_bar(proj_dir, tmp_path)
    _parts(servo={"mass": "density"})(proj_dir, tmp_path)
    assert findings(proj_dir, "part-mass") == [
        "params.yaml parts servo: model.build returns no part servo"
    ]


def test_parts_entry_giving_both_mass_and_density_is_a_schema_finding(proj_dir, tmp_path):
    four_bar(proj_dir, tmp_path)
    _parts(rocker={"mass": "density", "density": "density"})(proj_dir, tmp_path)
    assert findings(proj_dir, "schema") == [
        "params.yaml parts.rocker: give mass or density, not both"
    ]


def _total_mass(stated: str):
    """The four-bar with its servo crank, and a mass check with no density, which weighs every part
    by the mass model, against a stated total. The bars weigh 1.0498, 0.9298 and 0.8098 g by
    volume × density, the crank 7.5 g: 10.2895 g."""

    def change(r, t):
        _servo_crank(r, t)
        text = f"The four-bar weighs {stated} g."
        add_quote(r, t, text, text.rstrip("."), {"m": float(stated)})
        total = {"id": "total", "kind": "mass", "evidence": "N1", "key": "m", "tol_rel": 0.01}
        edit(r, "checks.yaml", lambda d: d["checks"].append(total))

    return change


def test_mass_check_without_a_density_weighs_the_parts_by_the_mass_model(proj_dir, tmp_path):
    _total_mass("10.3")(proj_dir, tmp_path)
    code, report = verify(proj_dir)
    assert code == 0, report["findings"]
    total = _by_id(report)["total"]
    assert total["ok"] and total["measured"].startswith("10.29")
    assert (total["rests_on"], total["rests_on_params"]) == ("proposed", ["crank_mass"])


def test_mass_check_over_the_mass_model_off_its_stated_total_fails(proj_dir, tmp_path):
    _total_mass("12")(proj_dir, tmp_path)
    assert findings(proj_dir, "check-failed") == ["total: expected 12 ±1% (N1.m), measured 10.29"]


def test_mass_check_naming_nothing_weighs_what_the_mjcf_export_weighs(proj_dir, tmp_path):
    """The four-bar with a second ground bar fixed a ground bar's length above the first: the
    check's total is the sum of the exported bodies' masses, the ground bar weighed twice."""
    mujoco = importlib.import_module("mujoco")

    _total_mass("11.3")(proj_dir, tmp_path)
    model = swap(
        FOUR_BAR,
        '"ground_1": ("ground", Location()),',
        '"ground_1": ("ground", Location()),\n'
        '            "ground_2": ("ground", Location((0, 0, p.ground))),',
    )
    stack = '"joints": {\n            "stack": {"type": "fixed", "parent": "ground_1", "child": '
    write(proj_dir, "model.py", swap(model, '"joints": {\n', stack + '"ground_2"},\n'))
    code, report = verify(proj_dir)
    assert code == 0, report["findings"]
    total = _by_id(report)["total"]
    m = mujoco.MjModel.from_xml_path(str(proj_dir / "build" / "model.mjcf"))
    assert float(total["measured"]) == pytest.approx(sum(m.body_mass), rel=1e-3)
    assert total["uncounted"] == {"ground": 2}


def test_mass_check_without_a_density_on_a_part_the_mass_model_lacks_is_check_config(proj_dir):
    total = {"id": "total", "kind": "mass", "evidence": "T1-link", "key": "L", "tol_rel": 0.1}
    edit(proj_dir, "checks.yaml", lambda d: d["checks"].append(total))
    assert findings(proj_dir, "check-config") == [
        "check total: names no density, and the mass model in params.yaml parts weighs no link"
    ]


def _rocker_weighed_by(by: str, text: str):
    """The four-bar, its rocker weighed by the param rho, by mass or density, ledgered from text."""

    def change(r, t):
        four_bar(r, t)
        add_quote(r, t, text, text.rstrip("."), {"rho": 1.2})
        _param("rho", basis="source", **{"from": "N1.rho"})(r, t)
        _parts(rocker={by: "rho"})(r, t)

    return change


@pytest.mark.parametrize(
    "by, text",
    [("density", "The resin is 1.2 g."), ("mass", "The rocker is 1.2 mm.")],
)
def test_mass_model_param_of_another_quantity_is_unit_quantity(proj_dir, tmp_path, by, text):
    _rocker_weighed_by(by, text)(proj_dir, tmp_path)
    messages = findings(proj_dir, "unit-quantity")
    assert len(messages) == 1 and messages[0].startswith("N1.rho")
    assert "in params.yaml parts.rocker" in messages[0]


@pytest.mark.parametrize(
    "by, text",
    [("density", "The resin is 1.2 g/cm3."), ("mass", "The rocker is 1.2 g.")],
)
def test_guard_mass_model_param_of_its_quantity_is_no_unit_finding(proj_dir, tmp_path, by, text):
    _rocker_weighed_by(by, text)(proj_dir, tmp_path)
    assert findings(proj_dir, "unit-quantity") == []


# A mass check covers the mass model's params for the parts it weighs, however it names them.

SERVO = "The crank servo weighs 7.5 g and the ground bar 1.05 g."


def _ground_weighed(root: Path, tmp_path: Path, over: dict) -> None:
    """The four-bar with its crank weighed by crank_mass, a source param from N1.servo, and one mass
    check, ground-mass, of what over names against the ground bar's 1.05 g."""
    four_bar(root, tmp_path)
    add_quote(root, tmp_path, SERVO, SERVO.rstrip("."), {"servo": 7.5, "g": 1.05})
    _param("crank_mass", basis="source", **{"from": "N1.servo"})(root, tmp_path)
    _parts(crank={"mass": "crank_mass"})(root, tmp_path)
    check = {"id": "ground-mass", "kind": "mass", "evidence": "N1", "key": "g", "tol_rel": 0.01}
    _append("checks.yaml", "checks", check | over)(root, tmp_path)


def _found(root: Path, *flags: str) -> tuple[int, list[str]]:
    """A check run's exit code and its findings as printed, one per line."""
    code, out = run("check", str(root), *flags)
    return code, [line for line in out.splitlines() if line.startswith(("error:", "warning:"))]


UNCHECKED_CRANK_MASS = (
    "warning: [unchecked-source] param crank_mass: N1.servo feeds the model but no check "
    "confirms the geometry realises it"
)


def test_mass_check_over_instances_covers_only_the_parts_it_weighs(proj_dir, tmp_path):
    _ground_weighed(proj_dir, tmp_path, {"instances": ["ground_1"]})
    runs = {"instances": _found(proj_dir)}

    def by_part(d):
        d["checks"][-1].pop("instances")
        d["checks"][-1]["parts"] = ["ground"]

    edit(proj_dir, "checks.yaml", by_part)
    runs["parts"] = _found(proj_dir)
    assert all(code == 0 for code, _ in runs.values()), runs
    printed = {key: lines for key, (_, lines) in runs.items()}
    assert UNCHECKED_CRANK_MASS in printed["instances"]
    assert sorted(printed["instances"]) == sorted(printed["parts"])
    assert len(set(printed["instances"])) == len(printed["instances"])


@pytest.mark.parametrize(
    "over", [{"instances": ["crank_1"]}, {}], ids=["crank-instance", "every-instance"]
)
def test_guard_mass_check_weighing_the_crank_covers_its_mass_param(proj_dir, tmp_path, over):
    _ground_weighed(proj_dir, tmp_path, over)
    _, printed = _found(proj_dir)
    assert UNCHECKED_CRANK_MASS not in printed


def test_guard_mass_check_stopped_by_a_counts_param_naming_no_param_reads_only_what_it_weighs(
    proj_dir, tmp_path
):
    _ground_weighed(proj_dir, tmp_path, {"instances": ["ground_1"], "counts": {"ground": "n"}})
    _, printed = _found(proj_dir)
    assert "error: [check-config] check ground-mass: missing or unknown 'n'" in printed
    # It weighed the ground bar, by density, before it stopped; crank_mass, the source param of
    # the crank it does not weigh, is unchecked.
    assert "param density" not in _unchecked_printed(printed)
    assert UNCHECKED_CRANK_MASS in printed


def _partial(root: Path, flag: str) -> list[str]:
    """What a partial run with flag prints, after showing it is partial: exit 1, no report."""
    code, printed = _found(root, flag)
    assert code == 1 and not (root / "build" / "report.json").exists(), printed
    assert not (root / "build" / "report.md").exists()
    return printed


def test_guard_run_without_the_build_leaves_a_mass_check_over_instances_checking_every_part(
    proj_dir, tmp_path
):
    _ground_weighed(proj_dir, tmp_path, {"instances": ["ground_1"]})
    assert UNCHECKED_CRANK_MASS not in _partial(proj_dir, "--no-build")


def test_run_without_the_coverage_sweep_still_checks_only_the_parts_a_mass_check_weighs(
    proj_dir, tmp_path
):
    _ground_weighed(proj_dir, tmp_path, {"instances": ["ground_1"]})
    assert _partial(proj_dir, "--no-coverage").count(UNCHECKED_CRANK_MASS) == 1


def test_source_param_feeding_only_an_unweighed_parts_mass_through_a_derived_one_is_unchecked(
    proj_dir, tmp_path
):
    _ground_weighed(proj_dir, tmp_path, {"instances": ["ground_1"]})
    _param("servo", basis="source", **{"from": "N1.servo"})(proj_dir, tmp_path)
    _param("crank_mass", basis="derived", expr="servo", **{"from": None})(proj_dir, tmp_path)
    assert "param servo" in _unchecked(proj_dir)


def test_param_feeding_physics_and_model_py_but_only_an_unweighed_parts_mass_is_unchecked(
    proj_dir, tmp_path
):
    """hole_d, from N1.d, sets the crank's mass and through it the knee's damping, and model.py
    reads it: it feeds only a physics value and the geometry, and only the crank's mass is checked
    against a source it rests on."""
    physical(proj_dir, tmp_path)
    text = "The holes are 2 mm across and the ground bar weighs 1.05 g."
    add_quote(proj_dir, tmp_path, text, text.rstrip("."), {"d": 2, "g": 1.05})
    unproposed = {"value": None, "rationale": None, "gap": None}
    _param("hole_d", basis="source", **{"from": "N1.d"}, **unproposed)(proj_dir, tmp_path)
    guess = {"basis": "proposed", "rationale": "a guess", "gap": "G1"}
    _param("mass_per_mm", value=3.75, **guess)(proj_dir, tmp_path)
    _param("damping_per_g", value=0.007, **guess)(proj_dir, tmp_path)
    _param("crank_mass", basis="derived", expr="hole_d * mass_per_mm")(proj_dir, tmp_path)
    spec = {"expr": "crank_mass * damping_per_g", **unproposed}
    _param("knee_damping", basis="derived", **spec)(proj_dir, tmp_path)
    _parts(crank={"mass": "crank_mass"})(proj_dir, tmp_path)
    check = {"id": "ground-mass", "kind": "mass", "evidence": "N1", "key": "g", "tol_rel": 0.01}
    _append("checks.yaml", "checks", check | {"instances": ["ground_1"]})(proj_dir, tmp_path)
    code, printed = _found(proj_dir)
    assert code == 0, printed
    assert [line for line in printed if "param hole_d" in line] == [
        "warning: [unchecked-source] param hole_d: N1.d feeds the model but no check confirms "
        "the geometry realises it"
    ]


def test_static_project_reports_no_masses_without_a_mass_model(proj_dir):
    assert verify(proj_dir)[1]["masses"] == {}


def test_export_mujoco_rejects_is_mjcf_load_naming_why(proj_dir, tmp_path):
    _density(0)(proj_dir, tmp_path)
    messages = findings(proj_dir, "mjcf-load")
    assert len(messages) == 1
    assert messages[0].startswith("MuJoCo rejects build/model.mjcf, so no check with a pose")
    assert "inertia must have positive eigenvalues" in messages[0]


def test_pose_value_that_is_a_bare_number_is_a_schema_finding(proj_dir, tmp_path):
    four_bar(proj_dir, tmp_path)
    edit(proj_dir, "checks.yaml", lambda d: d["checks"][0].update(pose={"input": 30}))
    assert findings(proj_dir, "schema") == [
        "checks.yaml checks[0].pose.input: must be text, not 30"
    ]


def test_pose_of_a_static_model_is_a_check_config_finding(proj_dir):
    edit(proj_dir, "checks.yaml", lambda d: d["checks"][1].update(pose={"input": "pitch.pitch"}))
    assert findings(proj_dir, "check-config") == [
        "check pitch: its pose names input, but model.build returns no joints"
    ]


@pytest.mark.parametrize(
    "pose, says",
    [
        ({"hip": "P30.turn"}, "pose names hip, which is not a joint"),
        ({"input": "P30.spin"}, "pose input: P30.spin names neither a param nor a ledger value"),
    ],
)
def test_pose_naming_an_unknown_joint_or_value_is_a_check_config_finding(
    proj_dir, tmp_path, pose, says
):
    four_bar(proj_dir, tmp_path)
    edit(proj_dir, "checks.yaml", lambda d: d["checks"][0].update(pose=pose))
    assert findings(proj_dir, "check-config") == [f"check ac30: {says}"]


def test_guard_check_with_no_pose_is_evaluated_on_the_assembly_as_built(proj_dir, tmp_path):
    four_bar(proj_dir, tmp_path)
    edit(proj_dir, "checks.yaml", lambda d: d["checks"][0].pop("pose"))
    ac30 = _by_id(verify(proj_dir)[1])["ac30"]
    assert not ac30["ok"] and "pose" not in ac30
    assert ac30["measured"].startswith(f"{math.hypot(*bar_pivot(0)):.4g} ")


def test_guard_bbox_check_stopped_at_a_later_axis_keeps_its_earlier_axes_results(
    proj_dir, tmp_path
):
    four_bar(proj_dir, tmp_path)
    box = {"id": "box", "kind": "bbox", "evidence": "L", "instances": ["ground_1", "rocker_1"]}
    box["pose"] = {"input": "turn_60"}
    _append("checks.yaml", "checks", box | {"axes": {"d": "x"}})(proj_dir, tmp_path)
    whole = _by_id(verify(proj_dir)[1])["box.d"]
    _check("box", axes={"d": "x", "a": "q"})(proj_dir, tmp_path)
    report = verify(proj_dir)[1]
    assert [f["message"] for f in report["findings"] if f["rule"] == "check-config"] == [
        "check box: missing or unknown 'q'"
    ]
    kept = _by_id(report)["box.d"]
    assert "box.a" not in _by_id(report)
    # The axis read before it stopped carries what the check rests on and the pose it was taken at.
    assert kept["pose"] == {"input": {"from": "turn_60", "value": 60}} == whole["pose"]
    rests_on = (kept["rests_on"], kept["rests_on_params"])
    assert rests_on == ("source", ["turn_60"]) == (whole["rests_on"], whole["rests_on_params"])


def _bar(old: str, new: str, count: int = -1):
    """The four-bar with old replaced by new in its model.py."""

    def change(r, t):
        four_bar(r, t)
        write(r, "model.py", swap(FOUR_BAR, old, new, count))

    return change


def _input_range(low: float, high: float):
    """The four-bar with its input joint's range proposed from low to high."""

    def change(r, t):
        four_bar(r, t)
        for name, value in (("input_min", low), ("input_max", high)):
            _param(name, basis="proposed", value=value, rationale="x", gap="G1")(r, t)

    return change


_INPUT_AXIS = '"axis": ["crank_1.a", "crank_1.a_up"]'


@pytest.mark.parametrize(
    "change, says",
    [
        (
            _bar('"parent": "ground_1"', '"parent": "base_1"'),
            "joint input: parent base_1 is not an instance of the assembly",
        ),
        (
            _bar('"child": "rocker_1"', '"child": "rocker_2"'),
            "joint elbow: child rocker_2 is not an instance of the assembly",
        ),
        (
            _bar(_INPUT_AXIS, '"axis": ["crank_1.a", "crank_1.top"]'),
            "joint input: axis crank_1.top is not a datum of its child crank_1",
        ),
        (
            _bar(_INPUT_AXIS, '"axis": ["crank_1.a", "ground_1.a_up"]'),
            "joint input: axis ground_1.a_up is not a datum of its child crank_1",
        ),
        (
            _bar(_INPUT_AXIS, '"axis": ["crank_1.a", "crank_1.a"]'),
            "joint input: axis crank_1.a and crank_1.a coincide, "
            "so they give the hinge no direction",
        ),
        (
            _bar('"input_max"', '"input_top"'),
            "joint input: range names input_top, which params.yaml does not define",
        ),
        (_input_range(90, -90), "joint input: range input_min 90 exceeds input_max -90"),
        (
            _bar('"child": "rocker_1"', '"child": "coupler_1"'),
            "joint elbow: coupler_1 is already the child of joint knee",
        ),
        (
            _bar('"parent": "ground_1"', '"parent": "rocker_1"'),
            "joint input: crank_1 moves itself through joints input, elbow and knee; "
            "close a ring of joints with a loop instead",
        ),
    ],
    ids=[
        "unknown-parent",
        "unknown-child",
        "unknown-axis-datum",
        "axis-datum-of-another-instance",
        "coincident-axis",
        "undefined-range-param",
        "range-low-above-high",
        "child-of-two-joints",
        "ring-of-joints",
    ],
)
def test_joint_the_model_cannot_hinge_is_model_joint_naming_it(proj_dir, tmp_path, change, says):
    change(proj_dir, tmp_path)
    _, report = verify(proj_dir)
    errors = [(f["rule"], f["message"]) for f in report["findings"] if f["level"] == "error"]
    assert errors == [("model-joint", says)]
    # Nothing is posed or exported as MJCF, and the posed checks are not evaluated.
    assert report["checks"] == [] and not (proj_dir / "build" / "model.mjcf").exists()


def test_report_of_a_model_whose_joints_were_dropped_says_so_and_not_static(proj_dir, tmp_path):
    _bar('"parent": "ground_1"', '"parent": "base_1"')(proj_dir, tmp_path)
    _, report = verify(proj_dir)
    md = (proj_dir / "build" / "report.md").read_text()
    assert report["motion"]["dropped"] and "**Static**" not in md
    assert "**Motion dropped**: model.py returns joints or loops the assembly cannot hold" in md


@pytest.mark.parametrize("datum", ["base_1.d", "ground_1.e"], ids=["instance", "feature"])
def test_loop_naming_an_unknown_datum_is_model_loop_naming_it(proj_dir, tmp_path, datum):
    _bar('"ground_1.d"]}', f'"{datum}"]}}')(proj_dir, tmp_path)
    _, report = verify(proj_dir)
    errors = [(f["rule"], f["message"]) for f in report["findings"] if f["level"] == "error"]
    says = f"loop closure: {datum} names no <instance>.<feature> datum of the assembly"
    assert errors == [("model-loop", says)]


def test_every_bad_joint_and_loop_is_its_own_finding(proj_dir, tmp_path):
    four_bar(proj_dir, tmp_path)
    model = swap(FOUR_BAR, '"parent": "ground_1"', '"parent": "base_1"')
    model = swap(model, '"rocker_1.a_up"]', '"rocker_1.top"]')
    write(proj_dir, "model.py", swap(model, '"ground_1.d"]}', '"ground_1.e"]}'))
    _, report = verify(proj_dir)
    named = [(f["rule"], f["message"].split(":")[0]) for f in report["findings"]]
    assert [n for n in named if n[0] in ("model-joint", "model-loop")] == [
        ("model-joint", "joint input"),
        ("model-joint", "joint elbow"),
        ("model-loop", "loop closure"),
    ]


@pytest.mark.parametrize(
    "old, new, says",
    [
        ('"joints": {', '"joints": 3, "_": {', "joints must be a mapping of names, not int"),
        (
            '"joints": {',
            '"joints": ["input"], "_": {',
            "joints must be a mapping of names, not list",
        ),
        ('"loops": {', '"loops": 3, "_": {', "loops must be a mapping of names, not int"),
        (
            '{"closure": ["rocker_1.d", "ground_1.d"]}',
            '[["rocker_1.d", "ground_1.d"]]',
            "loops must be a mapping of names, not list",
        ),
        ('"knee": {', '"knee": 3, "_": {', "joint knee must be a mapping, not int"),
        ('"type": "revolute"', '"type": "slider"', "joint input: type must be 'revolute'"),
        (
            '"drive": "actuated"',
            '"drive": "motor"',
            "joint input: drive must be actuated or passive",
        ),
        ('"closure": [', '"closure": "rocker_1.d", "_": [', "loop closure must be two"),
    ],
    ids=[
        "joints-number",
        "joints-list",
        "loops-number",
        "loops-list",
        "joint-number",
        "unknown-kind",
        "unknown-drive",
        "loop-text",
    ],
)
def test_joints_or_loops_of_the_wrong_shape_are_model_return(proj_dir, tmp_path, old, new, says):
    _bar(old, new, 1)(proj_dir, tmp_path)
    messages = findings(proj_dir, "model-return")
    assert len(messages) == 1 and messages[0].startswith(f"model.build {says}"), messages


@pytest.mark.parametrize(
    "old, new, says",
    [
        ('"closure": [', "1: [", "loop 1: its name must be text, not int"),
        ('"knee": {', "2: {", "joint 2: its name must be text, not int"),
    ],
    ids=["loop", "joint"],
)
def test_joint_or_loop_named_by_a_number_is_model_return(proj_dir, tmp_path, old, new, says):
    _bar(old, new)(proj_dir, tmp_path)
    assert findings(proj_dir, "model-return") == [f"model.build {says}"]


# Physics values: params with a basis and physics: true, written into the MJCF where they apply,
# counted apart from the headline and left out of exact (ADR-0008).

# Each physics slot the four-bar fills, the param it names and that param's value.
PHYSICS = {
    "knee_damping": 0.05,
    "knee_spring": 0.4,
    "knee_friction": 0.01,
    "cord_k": 0.2,
    "cord_damping": 0.03,
}
# One N in the project's units is 10⁶ of the MJCF's g·mm/s², so with mm each value is 10⁶ MJCF
# units.
MJCF_PER_N = 1e6


def physical(root: Path, tmp_path: Path) -> None:
    """The four-bar with a damped, sprung and rubbing knee, and an elastic cord from the crank tip
    to the rocker pivot: every physics param proposed, in the project's units (N·mm/rad, N·mm·s/rad,
    N·mm, N/mm and N·s/mm)."""
    four_bar(root, tmp_path)
    model = swap(
        FOUR_BAR,
        '"axis": ["coupler_1.a", "coupler_1.a_up"],\n',
        '"axis": ["coupler_1.a", "coupler_1.a_up"],\n'
        '                "damping": "knee_damping",\n'
        '                "stiffness": "knee_spring",\n'
        '                "friction": "knee_friction",\n',
    )
    model = swap(
        model,
        '        "loops": {"closure": ["rocker_1.d", "ground_1.d"]},\n',
        '        "loops": {"closure": ["rocker_1.d", "ground_1.d"]},\n'
        '        "tendons": {"cord": {"path": ["crank_1.d", "rocker_1.a"],\n'
        '                             "stiffness": "cord_k", "damping": "cord_damping"}},\n',
    )
    write(root, "model.py", model)
    add_params(
        root,
        **{
            name: {
                "basis": "proposed",
                "value": value,
                "rationale": "a guess",
                "gap": "G1",
                "physics": True,
            }
            for name, value in PHYSICS.items()
        },
    )


def _exact_bar(root: Path) -> None:
    """Make the four-bar's geometry rest on sources alone: its bar section and holes derived from
    the crank length, and no joint range."""
    model = (root / "model.py").read_text()
    write(root, "model.py", swap(model, '"range": ["input_min", "input_max"],\n', ""))

    def apply(d):
        for name in ("input_min", "input_max"):
            del d["params"][name]
        exprs = {"link_W": "crank / 3", "link_H": "crank * 4 / 15", "hole_d": "crank * 2 / 15"}
        for name, expr in exprs.items():
            d["params"][name] = {"basis": "derived", "expr": expr}

    edit(root, "params.yaml", apply)


def test_physics_params_are_written_into_the_mjcf_on_the_joint_and_tendon_they_apply_to(
    proj_dir, tmp_path
):
    mujoco = importlib.import_module("mujoco")

    physical(proj_dir, tmp_path)
    code, report = verify(proj_dir)
    assert code == 0, report["findings"]
    m = mujoco.MjModel.from_xml_path(str(proj_dir / "build" / "model.mjcf"))
    knee = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, "knee")
    dof = m.jnt_dofadr[knee]
    assert m.dof_damping[dof] == pytest.approx(PHYSICS["knee_damping"] * MJCF_PER_N)
    assert m.jnt_stiffness[knee] == pytest.approx(PHYSICS["knee_spring"] * MJCF_PER_N)
    assert m.dof_frictionloss[dof] == pytest.approx(PHYSICS["knee_friction"] * MJCF_PER_N)
    cord = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_TENDON, "cord")
    assert m.tendon_stiffness[cord] == pytest.approx(PHYSICS["cord_k"] * MJCF_PER_N)
    assert m.tendon_damping[cord] == pytest.approx(PHYSICS["cord_damping"] * MJCF_PER_N)
    # A joint no physics param names keeps MuJoCo's default.
    assert (
        m.dof_damping[m.jnt_dofadr[mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, "elbow")]] == 0
    )


def test_guard_physics_value_typed_into_model_py_is_a_model_literal(proj_dir, tmp_path):
    four_bar(proj_dir, tmp_path)
    model = swap(
        FOUR_BAR,
        '"axis": ["coupler_1.a", "coupler_1.a_up"],\n',
        '"axis": ["coupler_1.a", "coupler_1.a_up"],\n                "damping": 0.05,\n',
    )
    write(proj_dir, "model.py", model)
    assert "model-literal" in errors(proj_dir)


def test_report_counts_proposed_physics_params_apart_from_the_headline(proj_dir, tmp_path):
    physical(proj_dir, tmp_path)
    _, report = verify(proj_dir)
    counts = report["counts"]
    # The bar section, its holes and the input range stay proposed; the six physics params do not
    # join them.
    assert (counts["proposed"], counts["physics_proposed"]) == (5, len(PHYSICS))
    assert (
        counts["source"] + counts["measured"] + counts["proposed"] + len(PHYSICS)
        == (counts["params"])
    )
    md = (proj_dir / "build" / "report.md").read_text()
    assert "and 5 on proposed values; 5 more are proposed physics values." in md


def test_verified_project_whose_only_proposed_params_are_physics_params_is_exact(
    proj_dir, tmp_path
):
    physical(proj_dir, tmp_path)
    _exact_bar(proj_dir)
    code, report = verify(proj_dir)
    assert (code, report["status"], report["exact"]) == (0, "VERIFIED", True), report["findings"]
    assert report["counts"]["proposed"] == 0
    md = (proj_dir / "build" / "report.md").read_text()
    assert (
        "**Exact**: no geometry or kinematic parameter rests on a proposed value; "
        "5 physics values are proposed." in md
    )


def test_project_with_a_proposed_param_besides_physics_params_is_not_exact(proj_dir, tmp_path):
    physical(proj_dir, tmp_path)
    _exact_bar(proj_dir)
    _param("hole_d", basis="proposed", value=2, rationale="a drill", gap="G1", expr=None)(
        proj_dir, tmp_path
    )
    code, report = verify(proj_dir)
    assert (code, report["status"], report["exact"]) == (0, "VERIFIED", False)


def test_source_physics_param_needs_no_check_and_its_quoted_value_is_exported(proj_dir, tmp_path):
    mujoco = importlib.import_module("mujoco")

    physical(proj_dir, tmp_path)
    add_quote(
        proj_dir, tmp_path, "The cord stiffness is 0.25.", "cord stiffness is 0.25", {"k": 0.25}
    )
    _param("cord_k", basis="source", value=None, rationale=None, gap=None, **{"from": "N1.k"})(
        proj_dir, tmp_path
    )
    code, report = verify(proj_dir)
    assert code == 0, report["findings"]
    unchecked = [f["message"] for f in report["findings"] if f["rule"] == "unchecked-source"]
    assert unchecked and not [m for m in unchecked if "cord_k" in m]
    m = mujoco.MjModel.from_xml_path(str(proj_dir / "build" / "model.mjcf"))
    assert m.tendon_stiffness[0] == pytest.approx(0.25 * MJCF_PER_N)


CORD = "The cord is 0.5 mm thick and 4 mm wide."


def _cord_from_its_size(root: Path, tmp_path: Path) -> None:
    """The physical four-bar with the cord's stiffness derived from its stated size: source params
    cord_t and cord_w (N1.t, N1.w) feed only cord_k, a physics value, through cord_area."""
    physical(root, tmp_path)
    add_quote(root, tmp_path, CORD, CORD.rstrip("."), {"t": 0.5, "w": 4})
    for name, key in (("cord_t", "t"), ("cord_w", "w")):
        _param(name, basis="source", **{"from": f"N1.{key}"})(root, tmp_path)
    _param("cord_area", basis="derived", expr="cord_t * cord_w")(root, tmp_path)
    spec = {"value": None, "rationale": None, "gap": None, "expr": "cord_area / 10"}
    _param("cord_k", basis="derived", **spec)(root, tmp_path)


def test_source_params_that_feed_only_a_physics_value_are_not_unchecked_source(proj_dir, tmp_path):
    _cord_from_its_size(proj_dir, tmp_path)
    assert {"param cord_t", "param cord_w"}.isdisjoint(_unchecked(proj_dir))


def test_guard_source_param_feeding_physics_and_the_geometry_through_a_param_is_unchecked(
    proj_dir, tmp_path
):
    _cord_from_its_size(proj_dir, tmp_path)
    _param("hole_d", basis="derived", expr="cord_t * 4", value=None, rationale=None, gap=None)(
        proj_dir, tmp_path
    )
    assert "param cord_t" in _unchecked(proj_dir)


def test_guard_source_param_feeding_physics_that_model_py_also_reads_is_unchecked_source(
    proj_dir, tmp_path
):
    _cord_from_its_size(proj_dir, tmp_path)
    model = (proj_dir / "model.py").read_text()
    write(proj_dir, "model.py", swap(model, "Cylinder(p.hole_d / 2,", "Cylinder(p.cord_w / 2,"))
    assert "param cord_w" in _unchecked(proj_dir)


KNEE = "The knee spring is 0.25 N·m/rad and its damper 0.002 N·m·s/rad."


def _quoted_knee(text: str):
    """The physical four-bar, its knee's spring and damper source params from text (N1.k, N1.c)."""

    def change(r, t):
        physical(r, t)
        add_quote(r, t, text, text.rstrip("."), {"k": 0.25, "c": 0.002})
        for name, key in (("knee_spring", "k"), ("knee_damping", "c")):
            spec = {"from": f"N1.{key}", "value": None, "rationale": None, "gap": None}
            _param(name, basis="source", **spec)(r, t)

    return change


def test_physics_value_quoted_in_si_reaches_the_mjcf_in_its_units(proj_dir, tmp_path):
    mujoco = importlib.import_module("mujoco")

    _quoted_knee(KNEE)(proj_dir, tmp_path)
    code, report = verify(proj_dir)
    assert code == 0, report["findings"]
    m = mujoco.MjModel.from_xml_path(str(proj_dir / "build" / "model.mjcf"))
    knee = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, "knee")
    # 0.25 N·m/rad is 0.25 kg·m²/s² per rad: 0.25 × 10³ g × 10⁶ mm² = 2.5 × 10⁸ g·mm²/s².
    assert m.jnt_stiffness[knee] == pytest.approx(2.5e8)
    assert m.dof_damping[m.jnt_dofadr[knee]] == pytest.approx(2e6)


def test_physics_value_quoted_in_a_unit_of_another_quantity_is_unit_quantity(proj_dir, tmp_path):
    _quoted_knee(swap(KNEE, "0.25 N·m/rad", "0.25 N·m"))(proj_dir, tmp_path)
    messages = findings(proj_dir, "unit-quantity")
    assert len(messages) == 1 and messages[0].startswith("N1.k is printed in N·m, a unit of torque")
    assert "as joint knee's stiffness" in messages[0]


def _physical_model(old: str, new: str):
    """The physical four-bar with old replaced by new in its model.py."""

    def change(r, t):
        physical(r, t)
        write(r, "model.py", swap((r / "model.py").read_text(), old, new))

    return change


_CORD = '"cord": {"path": ["crank_1.d", "rocker_1.a"],'


@pytest.mark.parametrize(
    "old, new, says",
    [
        ('"cord": {', '"cord": 3, "_": {', "tendon cord must be a mapping, not int"),
        (_CORD, '"cord": {"path": ["crank_1.d"],', "tendon cord: path must be two or more datums"),
        (_CORD, _CORD + ' "length": "cord_k",', "tendon cord: unknown key 'length'"),
        ('"stiffness": "cord_k"', '"stiffness": ["cord_k"]', "tendon cord: stiffness must be a"),
        (
            '"rocker_1.a"],',
            '"rocker_1.e"],',
            "tendon cord: rocker_1.e names no <instance>.<feature>",
        ),
        ('"stiffness": "cord_k"', '"stiffness": "cord_q"', "tendon cord's stiffness names cord_q,"),
    ],
    ids=[
        "not-mapping",
        "short-path",
        "unknown-key",
        "not-a-name",
        "unknown-datum",
        "unknown-param",
    ],
)
def test_tendon_of_the_wrong_shape_or_naming_nothing_is_model_return(
    proj_dir, tmp_path, old, new, says
):
    _physical_model(old, new)(proj_dir, tmp_path)
    messages = findings(proj_dir, "model-return")
    assert len(messages) == 1 and messages[0].startswith(f"model.build {says}"), messages


def test_physics_slot_naming_a_param_without_physics_true_is_param_physics(proj_dir, tmp_path):
    physical(proj_dir, tmp_path)
    _param("knee_damping", physics=None)(proj_dir, tmp_path)
    assert findings(proj_dir, "param-physics") == [
        "param knee_damping: joint knee's damping is a physics value, so mark the param "
        "physics: true"
    ]


# A spring's rest: the joint value where it exerts no torque, a physics value in the joint's own
# quantity, exported as MuJoCo's springref.

PRESET = "The knee spring is preset at 45°."
_KNEE_SPRING = '"stiffness": "knee_spring",\n'


def _resting(model: str, joint_spring: str, rest: str) -> str:
    """model with rest named as the spring_rest of the joint whose stiffness line is
    joint_spring."""
    return swap(model, joint_spring, f'{joint_spring}                "spring_rest": "{rest}",\n')


def sprung_rest(text: str = PRESET, preset: float = 45):
    """The physical four-bar, its knee's spring resting at knee_rest, derived as -knee_preset from
    a source param quoted in text (N1.p): the knee opens in +, its spring pushes it back."""

    def change(r, t):
        physical(r, t)
        add_quote(r, t, text, text.rstrip("."), {"p": preset})
        _param("knee_preset", basis="source", **{"from": "N1.p"})(r, t)
        why = "the knee opens in +, and its spring pushes it back"
        spec = {"expr": "-knee_preset", "interpretation": why, "physics": True}
        _param("knee_rest", basis="derived", **spec)(r, t)
        write(r, "model.py", _resting((r / "model.py").read_text(), _KNEE_SPRING, "knee_rest"))

    return change


def _qpos_spring(root: Path, joint: str) -> float:
    mujoco = importlib.import_module("mujoco")
    m = mujoco.MjModel.from_xml_path(str(root / "build" / "model.mjcf"))
    return m.qpos_spring[m.jnt_qposadr[mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, joint)]]


def test_spring_rest_from_a_quoted_preset_is_the_joints_springref_in_radians(proj_dir, tmp_path):
    sprung_rest()(proj_dir, tmp_path)
    code, report = verify(proj_dir)
    assert code == 0, report["findings"]
    assert not [f for f in report["findings"] if "knee_preset" in f["message"]]
    assert not [f for f in report["findings"] if "knee_rest" in f["message"]]
    assert _qpos_spring(proj_dir, "knee") == pytest.approx(-math.pi / 4)
    knee = report["motion"]["joints"]["knee"]
    assert knee["spring_rest"] == {"from": "knee_rest", "value": -45}


def test_spring_rest_under_a_radian_angle_unit_is_exported_unchanged(proj_dir, tmp_path):
    sprung_rest("The knee spring is preset at 0.7854 rad.", 0.7854)(proj_dir, tmp_path)
    edit(proj_dir, "project.yaml", lambda d: d.update(units={"angle": "rad"}))
    code, report = verify(proj_dir)
    assert code == 0, report["findings"]
    assert _qpos_spring(proj_dir, "knee") == pytest.approx(-0.7854)
    assert report["motion"]["joints"]["knee"]["spring_rest"]["value"] == -0.7854


_SLIDE_RANGE = '"range": ["slide_min", "slide_max"],\n'


def sprung_slide(root: Path, tmp_path: Path) -> None:
    """The slider-crank, its slider on a spring, slide_k, resting 5 mm out, slide_rest: both
    proposed physics values."""
    slider_crank(root, tmp_path)
    sprung = (
        '                "stiffness": "slide_k",\n                "spring_rest": "slide_rest",\n'
    )
    write(root, "model.py", swap(SLIDER_CRANK, _SLIDE_RANGE, _SLIDE_RANGE + sprung))
    for name, value in (("slide_k", 0.1), ("slide_rest", 5)):
        spec = {"value": value, "rationale": "a guess", "gap": "G1", "physics": True}
        _param(name, basis="proposed", **spec)(root, tmp_path)


def test_slide_spring_rest_is_exported_as_a_length_in_the_projects_unit(proj_dir, tmp_path):
    sprung_slide(proj_dir, tmp_path)
    code, report = verify(proj_dir)
    assert code == 0, report["findings"]
    assert _qpos_spring(proj_dir, "slide") == pytest.approx(5)
    assert report["motion"]["joints"]["slide"]["spring_rest"] == {"from": "slide_rest", "value": 5}


def test_slide_spring_rest_quoted_as_an_angle_is_unit_quantity(proj_dir, tmp_path):
    sprung_slide(proj_dir, tmp_path)
    add_quote(proj_dir, tmp_path, "The slider spring rests at 5°.", "rests at 5°", {"r": 5})
    spec = {"from": "N1.r", "value": None, "rationale": None, "gap": None}
    _param("slide_rest", basis="source", **spec)(proj_dir, tmp_path)
    messages = findings(proj_dir, "unit-quantity")
    assert len(messages) == 1 and messages[0].startswith("N1.r is printed in deg, a unit of angle")
    assert "as joint slide's spring_rest" in messages[0]


def test_spring_rest_param_without_physics_true_is_param_physics(proj_dir, tmp_path):
    sprung_rest()(proj_dir, tmp_path)
    _param("knee_rest", physics=None)(proj_dir, tmp_path)
    assert findings(proj_dir, "param-physics") == [
        "param knee_rest: joint knee's spring_rest is a physics value, so mark the param "
        "physics: true"
    ]


def test_proposed_spring_rest_is_counted_apart_and_leaves_the_project_exact(proj_dir, tmp_path):
    physical(proj_dir, tmp_path)
    write(
        proj_dir,
        "model.py",
        _resting((proj_dir / "model.py").read_text(), _KNEE_SPRING, "knee_rest"),
    )
    spec = {"value": -45, "rationale": "a guess", "gap": "G1", "physics": True}
    _param("knee_rest", basis="proposed", **spec)(proj_dir, tmp_path)
    _exact_bar(proj_dir)
    code, report = verify(proj_dir)
    assert (code, report["status"], report["exact"]) == (0, "VERIFIED", True), report["findings"]
    assert report["counts"]["physics_proposed"] == len(PHYSICS) + 1


def test_spring_rest_outside_its_joints_range_is_no_finding(proj_dir, tmp_path):
    """The knee, which the crank turns negative, ranged -90 to 0, its spring resting at +45."""
    sprung_rest()(proj_dir, tmp_path)
    _param("knee_rest", expr="knee_preset")(proj_dir, tmp_path)
    knee = '"axis": ["coupler_1.a", "coupler_1.a_up"],\n'
    model = (proj_dir / "model.py").read_text()
    write(proj_dir, "model.py", swap(model, knee, knee + '"range": ["knee_min", "knee_max"],\n'))
    for name, value in (("knee_min", -90), ("knee_max", 0)):
        _param(name, basis="proposed", value=value, rationale="x", gap="G1")(proj_dir, tmp_path)
    code, report = verify(proj_dir)
    assert code == 0, report["findings"]
    assert not [f for f in report["findings"] if "knee_rest" in f["message"]]
    assert _qpos_spring(proj_dir, "knee") == pytest.approx(math.pi / 4)


def test_spring_rest_without_a_stiffness_is_model_joint(proj_dir, tmp_path):
    sprung_rest()(proj_dir, tmp_path)
    write(proj_dir, "model.py", swap((proj_dir / "model.py").read_text(), _KNEE_SPRING, ""))
    assert findings(proj_dir, "model-joint") == [
        "joint knee: spring_rest names no spring without a stiffness"
    ]


# Ranges and sweeps: a joint posed at the ends of its stated range, interference across it.

RANGE = "The crank turns from 0° to 60° and back."


def ranged(root: Path, tmp_path: Path, checked: bool = True) -> None:
    """The four-bar posed at 30°, its input's range ledgered as N1 (lo 0°, hi 60°) and read by
    the source params input_min and input_max; checked, a range check reach confirms it."""
    four_bar(root, tmp_path, (30,))
    add_quote(root, tmp_path, RANGE + "\n", RANGE.rstrip("."), {"lo": 0, "hi": 60})
    for name, end in (("input_min", "lo"), ("input_max", "hi")):
        spec = {"from": f"N1.{end}", "value": None, "rationale": None, "gap": None}
        _param(name, basis="source", **spec)(root, tmp_path)
    if checked:
        reach = {"id": "reach", "kind": "range", "joint": "input", "ends": ["N1.lo", "N1.hi"]}
        _append("checks.yaml", "checks", reach)(root, tmp_path)


def test_range_check_passes_when_the_joint_reaches_both_ledgered_ends(proj_dir, tmp_path):
    ranged(proj_dir, tmp_path)
    code, report = verify(proj_dir)
    assert code == 0, report["findings"]
    checks = _by_id(report)
    low, high = checks["reach.input_min"], checks["reach.input_max"]
    assert low["ok"] and high["ok"]
    assert low["expected"].endswith("(N1.lo)") and high["expected"].endswith("(N1.hi)")
    # Posed at the stated ends, where the loop closes, and each range param compared with its end.
    assert low["pose"] == {"input": {"from": "N1.lo", "value": 0}}
    assert high["pose"] == {"input": {"from": "N1.hi", "value": 60}}
    assert high["measured"] == "60° input's range end (input_max)"


def test_source_range_param_a_range_check_covers_is_not_unchecked_source(proj_dir, tmp_path):
    ranged(proj_dir, tmp_path)
    assert {"param input_min", "param input_max"}.isdisjoint(_unchecked(proj_dir))


def test_guard_source_range_param_no_check_covers_is_unchecked_source(proj_dir, tmp_path):
    ranged(proj_dir, tmp_path, checked=False)
    assert {"param input_min", "param input_max"} <= set(_unchecked(proj_dir))


def test_range_end_the_model_stops_short_of_is_check_failed(proj_dir, tmp_path):
    ranged(proj_dir, tmp_path)
    _param("input_max", basis="proposed", value=50, rationale="x", gap="G1", **{"from": None})(
        proj_dir, tmp_path
    )
    code, report = verify(proj_dir)
    failed = [f["message"] for f in report["findings"] if f["rule"] == "check-failed"]
    assert code == 1 and failed == [
        "reach.input_max: expected 60 (N1.hi), measured 50° input's range end (input_max)"
    ]
    # The mechanism is still posed at the stated end, where its range param stops short.
    assert _by_id(report)["reach.input_max"]["pose"] == {"input": {"from": "N1.hi", "value": 60}}


def test_range_end_the_loop_cannot_close_at_is_loop_open(proj_dir, tmp_path):
    ranged(proj_dir, tmp_path)
    _param("coupler", basis="proposed", value=20, rationale="x", **{"from": None})(
        proj_dir, tmp_path
    )
    code, report = verify(proj_dir)
    opened = [f["message"] for f in report["findings"] if f["rule"] == "loop-open"]
    assert code == 1 and len(opened) == 1 and "with input at 60 (N1.hi)" in opened[0]
    assert "reach.input_max" not in _by_id(report) and _by_id(report)["reach.input_min"]["ok"]


def _knee_range(low: float, high: float, base=four_bar):
    """The four-bar, as base sets it up, with its passive knee ranged from low to high, proposed:
    the crank turned 30° swings the knee by about 30°."""

    def change(r, t):
        base(r, t)
        knee = '"axis": ["coupler_1.a", "coupler_1.a_up"],\n'
        write(r, "model.py", swap(FOUR_BAR, knee, knee + '"range": ["knee_min", "knee_max"],\n'))
        for name, value in (("knee_min", low), ("knee_max", high)):
            _param(name, basis="proposed", value=value, rationale="x", gap="G1")(r, t)

    return change


def test_joint_pushed_past_its_range_at_a_pose_is_joint_range_naming_joint_and_pose(
    proj_dir, tmp_path
):
    _knee_range(-1, 1)(proj_dir, tmp_path)
    code, report = verify(proj_dir)
    messages = findings(proj_dir, "joint-range")
    assert code == 1 and len(messages) == 2, messages
    assert messages[0].startswith("joint knee: turns ")
    assert "with input at 30 (P30.turn), outside its range knee_min -1 to knee_max 1" in messages[0]
    # No check is evaluated at a pose the mechanism cannot reach.
    assert report["checks"] == []


def test_range_end_a_passive_joint_cannot_reach_within_its_range_is_joint_range(proj_dir, tmp_path):
    _knee_range(-1, 1, base=ranged)(proj_dir, tmp_path)
    edit(proj_dir, "checks.yaml", lambda d: d.update(checks=d["checks"][-1:]))  # reach alone
    assert any("with input at 60 (N1.hi)" in m for m in findings(proj_dir, "joint-range"))
    assert "reach.input_max" not in _by_id(verify(proj_dir)[1])


def test_range_check_between_datums_compares_their_angle_at_each_end(proj_dir, tmp_path):
    four_bar(proj_dir, tmp_path, (0, 60))
    for name, end in (("input_min", "P0"), ("input_max", "P60")):
        spec = {"from": f"{end}.turn", "value": None, "rationale": None, "gap": None}
        _param(name, basis="source", **spec)(proj_dir, tmp_path)
    rock = {
        "id": "rock",
        "kind": "range",
        "joint": "input",
        "ends": ["P0.rock", "P60.rock"],
        "instances": ["ground_1", "rocker_1"],
        "between": ["ground_1.a", "ground_1.d", "rocker_1.a"],
    }
    _append("checks.yaml", "checks", rock)(proj_dir, tmp_path)
    code, report = verify(proj_dir)
    assert code == 0, report["findings"]
    checks = _by_id(report)
    # The rocker swings from one stated angle to the other as the crank turns 60°.
    assert checks["rock.input_min"]["expected"] != checks["rock.input_max"]["expected"]
    assert checks["rock.input_max"]["measured"].endswith(
        "° at ground_1.d between ground_1.a and rocker_1.a"
    )


@pytest.mark.parametrize(
    "change, says",
    [
        ({"joint": "hip"}, "hip is not a joint"),
        ({"joint": "knee"}, "joint knee has no range"),
        ({"ends": ["N1.hi"]}, "ends names 1 values, not [low, high]"),
    ],
)
def test_range_check_naming_no_ranged_joint_or_not_two_ends_is_check_config(
    proj_dir, tmp_path, change, says
):
    ranged(proj_dir, tmp_path)
    _check("reach", **change)(proj_dir, tmp_path)
    assert findings(proj_dir, "check-config") == [f"check reach: {says}"]


def test_range_check_on_a_static_model_is_check_config(proj_dir):
    reach = {"id": "reach", "kind": "range", "joint": "input", "ends": ["pitch.pitch"] * 2}
    _append("checks.yaml", "checks", reach)(proj_dir, None)
    assert "check reach: names joint input, but model.build returns no joints" in findings(
        proj_dir, "check-config"
    )


def test_guard_range_check_stopped_at_a_missing_second_end_value_still_checks_both_ends(
    proj_dir, tmp_path
):
    ranged(proj_dir, tmp_path)
    _check("reach", ends=["N1.lo", "N1.mid"])(proj_dir, tmp_path)
    report = verify(proj_dir)[1]
    assert [f["message"] for f in report["findings"] if f["rule"] == "check-config"] == [
        "check reach: missing or unknown 'N1.mid'"
    ]
    # It stopped after reading its joint's range, so neither end is left unchecked.
    assert {"param input_min", "param input_max"}.isdisjoint(_unchecked_in(report))


TURN = "The crank turns through 385° from upright."


def one_ended(root: Path, tmp_path: Path, checked: bool = True) -> None:
    """The four-bar posed at 30°, its input ranged by one param, input_max, from the source's
    one-ended turn N1.turn (385°, past a full turn); checked, a range check reach confirms it."""
    four_bar(root, tmp_path, (30,))
    write(root, "model.py", swap(FOUR_BAR, '["input_min", "input_max"]', '["input_max"]'))
    edit(root, "params.yaml", lambda d: d["params"].pop("input_min"))
    add_quote(root, tmp_path, TURN + "\n", TURN.rstrip("."), {"turn": 385})
    spec = {"from": "N1.turn", "value": None, "rationale": None, "gap": None}
    _param("input_max", basis="source", **spec)(root, tmp_path)
    if checked:
        reach = {"id": "reach", "kind": "range", "joint": "input", "ends": ["N1.turn"]}
        _append("checks.yaml", "checks", reach)(root, tmp_path)


def test_one_ended_range_check_passes_at_its_one_stated_end_past_a_full_turn(proj_dir, tmp_path):
    one_ended(proj_dir, tmp_path)
    code, report = verify(proj_dir)
    assert code == 0, report["findings"]
    assert "param input_max" not in _unchecked(proj_dir)
    reach = _by_id(report)["reach.input_max"]
    assert reach["ok"] and reach["expected"].endswith("(N1.turn)")
    assert reach["pose"] == {"input": {"from": "N1.turn", "value": 385}}
    assert reach["measured"] == "385° input's range end (input_max)"
    # The other end is the assembly as built, a turn of 0 that no param needs to state.
    assert report["motion"]["joints"]["input"]["range"] == {
        "from": ["as built", "input_max"],
        "value": [0, 385],
    }


def test_one_ended_range_param_short_of_its_stated_end_is_check_failed(proj_dir, tmp_path):
    one_ended(proj_dir, tmp_path)
    _param("input_max", basis="proposed", value=380, rationale="x", gap="G1", **{"from": None})(
        proj_dir, tmp_path
    )
    assert findings(proj_dir, "check-failed") == [
        "reach.input_max: expected 385 (N1.turn), measured 380° input's range end (input_max)"
    ]


def test_one_ended_range_check_naming_two_ends_is_check_config(proj_dir, tmp_path):
    one_ended(proj_dir, tmp_path)
    _check("reach", ends=["N1.turn", "N1.turn"])(proj_dir, tmp_path)
    assert findings(proj_dir, "check-config") == ["check reach: ends names 2 values, not [end]"]


def test_one_ended_range_exports_from_as_built_to_its_end_in_the_mjcf(proj_dir, tmp_path):
    one_ended(proj_dir, tmp_path)
    _param("input_max", basis="proposed", value=-90, rationale="x", gap="G1", **{"from": None})(
        proj_dir, tmp_path
    )
    edit(proj_dir, "checks.yaml", lambda d: d.update(checks=d["checks"][:-1]))
    mujoco = importlib.import_module("mujoco")
    code, report = verify(proj_dir)
    assert report["motion"]["joints"]["input"]["range"] == {
        "from": ["input_max", "as built"],
        "value": [-90, 0],
    }
    m = mujoco.MjModel.from_xml_path(str(proj_dir / "build" / "model.mjcf"))
    joint = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, "input")
    assert list(m.jnt_range[joint]) == pytest.approx([-math.pi / 2, 0])


def post_beside(
    root: Path, tmp_path: Path, post_x: float, steps: int = 5, ranged_by_source: bool = False
) -> None:
    """The four-bar beside a post fixed at (post_x, 0), and an interference check of the post with
    the crank and coupler swept at steps poses across the input's range, -180° to 180°, or with
    ranged_by_source the stated 0° to 60° a range check covers. Turned 90°, the crank points at
    (-15, 0); turned -180°, 0 or 180°, it points along y, clear of x < -12."""
    if ranged_by_source:
        ranged(root, tmp_path)
    else:
        four_bar(root, tmp_path, (30,))
    model = swap(
        FOUR_BAR,
        '"parts": {name: bar(p, length) for name, length in lengths.items()},',
        '"parts": {**{name: bar(p, length) for name, length in lengths.items()}, '
        '"post": Box(p.link_W, p.link_W, p.link_H)},',
    )
    model = swap(
        model,
        '"ground_1": ("ground", Location()),',
        '"ground_1": ("ground", Location()), "post_1": ("post", Location((p.post_x, 0, 0))),',
    )
    write(root, "model.py", model)
    _parts(post={"density": "density"})(root, tmp_path)
    for name, value in (("post_x", post_x), ("sweep_steps", steps)):
        _param(name, basis="proposed", value=value, rationale="a test post", gap="G1")(
            root, tmp_path
        )
    sweep = {
        "id": "clear",
        "kind": "interference",
        "pairs": [["crank_1", "post_1"], ["coupler_1", "post_1"]],
        "sweep": {"joint": "input", "steps": "sweep_steps"},
    }
    _append("checks.yaml", "checks", sweep)(root, tmp_path)


def test_swept_interference_catches_a_collision_only_mid_range_naming_pair_and_pose(
    proj_dir, tmp_path
):
    post_beside(proj_dir, tmp_path, -15)
    code, report = verify(proj_dir)
    clear = _by_id(report)["clear"]
    assert code == 1 and not clear["ok"]
    assert "post_1" in clear["measured"] and "at input 90" in clear["measured"]
    assert clear["pose"] == {"input": {"from": "input_min..input_max", "value": 90}}
    assert clear["sweep"] == {
        "joint": "input",
        "from": ["input_min", "input_max"],
        "range": [-180, 180],
        "poses": 5,
    }


def test_guard_interference_with_no_sweep_misses_a_collision_only_mid_range(proj_dir, tmp_path):
    post_beside(proj_dir, tmp_path, -15)
    edit(proj_dir, "checks.yaml", lambda d: d["checks"][-1].pop("sweep"))
    _param("sweep_steps", value=None, basis=None, rationale=None, gap=None)(proj_dir, tmp_path)
    assert _by_id(verify(proj_dir)[1])["clear"]["ok"]


def test_clear_sweep_passes_and_says_how_many_poses_it_evaluated(proj_dir, tmp_path):
    post_beside(proj_dir, tmp_path, -30, steps=9)
    code, report = verify(proj_dir)
    clear = _by_id(report)["clear"]
    assert code == 0, report["findings"]
    assert clear["ok"] and "pose" not in clear
    assert clear["measured"].endswith("across 9 poses of input")
    md = (proj_dir / "build" / "report.md").read_text()
    assert "swept: input -180 to 180 (input_min to input_max), 9 poses" in md


def test_proposed_sweep_steps_leave_a_project_exact_and_are_named_beside_it(proj_dir, tmp_path):
    post_beside(proj_dir, tmp_path, -30, ranged_by_source=True)
    exprs = {
        "link_W": "crank / 3",
        "link_H": "crank * 4 / 15",
        "hole_d": "crank * 2 / 15",
        "post_x": "-ground * 3 / 4",
    }
    for name, expr in exprs.items():
        spec = {"value": None, "rationale": None, "gap": None}
        _param(name, basis="derived", expr=expr, **spec)(proj_dir, tmp_path)
    code, report = verify(proj_dir)
    assert (code, report["status"], report["exact"]) == (0, "VERIFIED", True), report["findings"]
    assert report["counts"]["proposed"] == 1  # sweep_steps, still counted
    assert _by_id(report)["clear"]["rests_on"] == "source"
    md = (proj_dir / "build" / "report.md").read_text()
    assert (
        "**Exact**: no geometry or kinematic parameter rests on a proposed value; "
        "the sweep resolution sweep_steps is proposed." in md
    )


def test_source_range_ends_only_a_swept_check_reads_are_not_unchecked_source(proj_dir, tmp_path):
    post_beside(proj_dir, tmp_path, -30, ranged_by_source=True)
    edit(proj_dir, "checks.yaml", lambda d: d["checks"].remove(_by_id(d)["reach"]))
    _, report = verify(proj_dir)
    assert _by_id(report)["clear"]["sweep"]["from"] == ["input_min", "input_max"]
    assert {"param input_min", "param input_max"}.isdisjoint(_unchecked_in(report))


def test_proposed_sweep_steps_naming_no_gap_raise_no_param_gap(proj_dir, tmp_path):
    post_beside(proj_dir, tmp_path, -30)
    _param("sweep_steps", gap=None)(proj_dir, tmp_path)
    assert findings(proj_dir, "param-gap") == []


def test_guard_proposed_param_the_model_reads_beside_a_sweep_still_names_a_gap(proj_dir, tmp_path):
    post_beside(proj_dir, tmp_path, -30)
    _param("post_x", gap=None)(proj_dir, tmp_path)
    assert findings(proj_dir, "param-gap") == [
        "param post_x: proposed value names no gap to close it"
    ]


def test_sweep_steps_as_a_bare_number_is_a_schema_finding(proj_dir, tmp_path):
    post_beside(proj_dir, tmp_path, -30)
    edit(proj_dir, "checks.yaml", lambda d: d["checks"][-1]["sweep"].update(steps=5))
    assert findings(proj_dir, "schema") == [
        "checks.yaml checks[2].sweep.steps: must be text, not 5"
    ]


@pytest.mark.parametrize("steps", [1, 2.5])
def test_sweep_steps_not_a_whole_number_of_two_or_more_is_check_config(proj_dir, tmp_path, steps):
    post_beside(proj_dir, tmp_path, -30, steps=steps)
    assert findings(proj_dir, "check-config") == [
        f"check clear: sweep steps sweep_steps is {steps:g}; sweep at least 2 poses, a whole number"
    ]


# Joint kinds: a slide moves its child along an axis, a fixed joint carries it with its parent,
# and a gear couples two joints by a ratio.

# Crank a and connecting rod b of a slider-crank, in mm, the slider on the line through the crank
# pivot.
SLIDER = {"crank": 15, "rod": 35}

SLIDER_CRANK = """\
import math

from build123d import *


def bar(p, length):
    body = Pos(length / 2, 0, 0) * Box(length + p.link_W, p.link_W, p.link_H)
    body -= Cylinder(p.hole_d / 2, p.link_H)
    body -= Pos(length, 0, 0) * Cylinder(p.hole_d / 2, p.link_H)
    return body


def build(p):
    a, b = p.crank, p.rod
    # As built the crank stands upright, B = (0, a), and the rod reaches the slider on the x axis.
    reach = math.sqrt(b * b - a * a)
    lengths = {"ground": a, "crank": a, "rod": b}
    datums = {"slider.a": (0, 0, 0), "slider.e": (p.link_W, 0, 0)}
    for name, length in lengths.items():
        datums[f"{name}.a"] = (0, 0, 0)
        datums[f"{name}.a_up"] = (0, 0, p.link_H / 2)
        datums[f"{name}.d"] = (length, 0, 0)
    slider = Box(p.link_W * 2, p.link_W, p.link_H) - Cylinder(p.hole_d / 2, p.link_H)
    return {
        "parts": {**{name: bar(p, length) for name, length in lengths.items()}, "slider": slider},
        "datums": datums,
        "assembly": {
            "ground_1": ("ground", Location()),
            "crank_1": ("crank", Location((0, 0, 0), (0, 0, 90))),
            "rod_1": ("rod", Location((0, a, 0), (0, 0, math.degrees(math.atan2(-a, reach))))),
            "slider_1": ("slider", Location((reach, 0, 0))),
        },
        "joints": {
            "input": {
                "type": "revolute",
                "parent": "ground_1",
                "child": "crank_1",
                "axis": ["crank_1.a", "crank_1.a_up"],
                "range": ["input_min", "input_max"],
                "drive": "actuated",
            },
            "knee": {
                "type": "revolute",
                "parent": "crank_1",
                "child": "rod_1",
                "axis": ["rod_1.a", "rod_1.a_up"],
                "drive": "passive",
            },
            "slide": {
                "type": "slide",
                "parent": "ground_1",
                "child": "slider_1",
                "axis": ["slider_1.a", "slider_1.e"],
                "range": ["slide_min", "slide_max"],
                "drive": "passive",
            },
        },
        "loops": {"closure": ["rod_1.d", "slider_1.a"]},
    }
"""


def slider_at(turn: float) -> float:
    """The slider-crank's closed form: how far the slider pin lies from the crank pivot with the
    crank turned turn degrees from upright."""
    a, b = SLIDER["crank"], SLIDER["rod"]
    theta = math.radians(90 + turn)
    return a * math.cos(theta) + math.sqrt(b * b - (a * math.sin(theta)) ** 2)


def slider_crank(root: Path, tmp_path: Path, turns: tuple[int, ...] = (30, 60)) -> None:
    """Replace the project with the slider-crank, built upright: an actuated crank, input, a
    passive rod and a passive slider, slide, ranged -15 to 20 mm, and one loop, closure. For each
    turn, ledger S<turn> and check the slider pin's distance from the crank pivot along x, posed
    at that turn."""
    edit(root, "project.yaml", lambda d: d.update(sources=[]))
    (root / "sources" / "paper.txt").unlink()
    lines = ["The crank is {crank} mm and the connecting rod {rod} mm long.".format(**SLIDER)]
    lines += [
        f"Turned {turn}° from upright, the crank puts the slider pin {slider_at(turn):.4f} mm "
        "from the crank pivot."
        for turn in turns
    ]
    lines.append(f"The parts are printed in a resin of {RESIN} g/cm3.")
    text = tmp_path / "slider.txt"
    text.write_text("\n".join(lines) + "\n")
    register = ["source", str(root), str(text), "--id", "slider", "--kind", "paper"]
    assert cli.main([*register, "--citation", "Roe 2026"]) == 0
    quote = {"source": "slider", "locator": "Sec. 1"}
    evidence = [
        {"id": "L", **quote, "quote": lines[0].rstrip("."), "values": {"a": 15, "b": 35}},
        {"id": "R", **quote, "quote": lines[-1].rstrip("."), "values": {"rho": RESIN}},
    ]
    params = {
        "crank": {"basis": "source", "from": "L.a"},
        "rod": {"basis": "source", "from": "L.b"},
        "density": {"basis": "source", "from": "R.rho"},
    }
    chosen = {"link_W": 5, "link_H": 4, "hole_d": 2, "input_min": -180, "input_max": 180}
    chosen |= {"slide_min": -15, "slide_max": 20}
    params |= {
        name: {"basis": "proposed", "value": value, "rationale": "a printable part", "gap": "G1"}
        for name, value in chosen.items()
    }
    checks = []
    for turn, line in zip(turns, lines[1:-1]):
        eid = f"S{turn}"
        values = {"turn": turn, "x": round(slider_at(turn), 4)}
        evidence.append({"id": eid, **quote, "quote": line.rstrip("."), "values": values})
        checks.append(
            {
                "id": f"x{turn}",
                "kind": "distance",
                "instances": ["ground_1", "slider_1"],
                "between": ["ground_1.a", "slider_1.a"],
                "along": "x",
                "evidence": eid,
                "key": "x",
                "pose": {"input": f"{eid}.turn"},
            }
        )
    write(root, "evidence.yaml", {"evidence": evidence, "skipped": [], "conflicts": []})
    parts = {name: {"density": "density"} for name in ("ground", "crank", "rod", "slider")}
    write(root, "params.yaml", {"params": params, "parts": parts})
    write(root, "gaps.yaml", {"gaps": [{"id": "G1", "question": "part size?", "ask": "authors"}]})
    write(root, "checks.yaml", {"checks": checks})
    write(root, "model.py", SLIDER_CRANK)


def test_slider_crank_posed_at_two_crank_angles_puts_the_slider_where_its_closed_form_does(
    proj_dir, tmp_path
):
    mujoco = importlib.import_module("mujoco")

    slider_crank(proj_dir, tmp_path)
    code, report = verify(proj_dir)
    assert code == 0, report["findings"]
    checks = _by_id(report)
    # Each check compares with the closed form at its pose within tolerance.length; the slider
    # moves between the two poses, along a slide joint in the MJCF.
    for turn in (30, 60):
        assert checks[f"x{turn}"]["ok"]
        assert checks[f"x{turn}"]["expected"] == f"{round(slider_at(turn), 4):g} (S{turn}.x)"
    assert slider_at(30) - slider_at(60) > 1
    m = mujoco.MjModel.from_xml_path(str(proj_dir / "build" / "model.mjcf"))
    slide = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, "slide")
    assert m.jnt_type[slide] == mujoco.mjtJoint.mjJNT_SLIDE
    assert list(m.jnt_range[slide]) == pytest.approx([-15, 20])


_PIN = """\
            "pin": {"type": "fixed", "parent": "crank_1", "child": "pin_1"},
"""


def pinned(root: Path, tmp_path: Path, pin: str = _PIN) -> None:
    """The slider-crank with a pin at the crank's tip, its own part fixed to the crank by the
    joint pin, and the rod hinged on the pin rather than on the crank."""
    slider_crank(root, tmp_path)
    model = swap(
        SLIDER_CRANK,
        '"slider": slider},',
        '"slider": slider, "pin": Cylinder(p.hole_d / 2, p.link_H)},',
    )
    model = swap(
        model, '"slider.e": (p.link_W, 0, 0)}', '"slider.e": (p.link_W, 0, 0), "pin.c": (0, 0, 0)}'
    )
    model = swap(
        model,
        '"slider_1": ("slider", Location((reach, 0, 0))),',
        '"slider_1": ("slider", Location((reach, 0, 0))),\n'
        '            "pin_1": ("pin", Location((0, a, 0))),',
    )
    model = swap(model, '"parent": "crank_1"', '"parent": "pin_1"')
    write(root, "model.py", swap(model, '        "joints": {\n', '        "joints": {\n' + pin))
    _parts(pin={"density": "density"})(root, tmp_path)


def test_fixed_child_follows_its_parent_at_every_pose_with_no_joint_or_motor_in_the_mjcf(
    proj_dir, tmp_path
):
    mujoco = importlib.import_module("mujoco")

    pinned(proj_dir, tmp_path)
    code, report = verify(proj_dir)
    # The rod hangs on the pin, so the slider reaches its closed form only if the pin turns with
    # the crank.
    assert code == 0, report["findings"]
    assert all(c["ok"] for c in report["checks"]) and len(report["checks"]) == 2
    m = mujoco.MjModel.from_xml_path(str(proj_dir / "build" / "model.mjcf"))
    assert (m.njnt, m.nu) == (3, 1)
    assert mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, "pin") == -1
    assert report["motion"]["joints"]["pin"] == {
        "type": "fixed",
        "parent": "crank_1",
        "child": "pin_1",
    }


@pytest.mark.parametrize(
    "extra, named",
    [
        ('"axis": ["pin_1.c", "pin_1.c"]', "axis"),
        ('"range": ["slide_min", "slide_max"]', "range"),
        ('"drive": "passive"', "drive"),
    ],
)
def test_fixed_joint_given_an_axis_range_or_drive_is_model_joint_naming_it(
    proj_dir, tmp_path, extra, named
):
    pinned(proj_dir, tmp_path, swap(_PIN, '"pin_1"}', f'"pin_1", {extra}}}'))
    assert findings(proj_dir, "model-joint") == [
        f"joint pin: a fixed joint moves pin_1 with crank_1, so it takes no {named}; "
        "make it revolute or slide if it moves"
    ]


def _quoted_range(joint: str, text: str):
    """The slider-crank with joint's range params read from text, ledgered as N1 (lo, hi)."""
    names = {"input": ("input_min", "input_max"), "slide": ("slide_min", "slide_max")}[joint]

    def change(r, t):
        slider_crank(r, t)
        add_quote(r, t, text + "\n", text.rstrip("."), {"lo": -15, "hi": 20})
        for name, end in zip(names, ("lo", "hi")):
            spec = {"from": f"N1.{end}", "value": None, "rationale": None, "gap": None}
            _param(name, basis="source", **spec)(r, t)

    return change


@pytest.mark.parametrize(
    "joint, text, quantity",
    [
        ("slide", "The slider travels from -15° to 20°.", "length"),
        ("input", "The crank turns from -15 mm to 20 mm.", "angle"),
    ],
    ids=["slide-in-degrees", "revolute-in-mm"],
)
def test_joint_range_quoted_in_a_unit_of_another_quantity_is_unit_quantity(
    proj_dir, tmp_path, joint, text, quantity
):
    _quoted_range(joint, text)(proj_dir, tmp_path)
    messages = findings(proj_dir, "unit-quantity")
    assert len(messages) == 2 and all(f"where a {quantity} is expected" in m for m in messages)


def test_guard_slide_range_quoted_in_mm_is_no_unit_finding(proj_dir, tmp_path):
    _quoted_range("slide", "The slider travels from -15 mm to 20 mm.")(proj_dir, tmp_path)
    assert findings(proj_dir, "unit-quantity") == []


STROKE = "The slider travels from -10 mm to 15 mm."


def slide_driven(root: Path, tmp_path: Path) -> None:
    """The slider-crank driven by its slider: slide actuated, its stated stroke ledgered as N1 (lo,
    hi) and read by the source params slide_min and slide_max, and the crank passive; one check,
    stroke, a range check of slide over N1."""
    slider_crank(root, tmp_path, turns=())
    model = swap(SLIDER_CRANK, '"drive": "actuated"', '"drive": "passive"')
    ranged = '"range": ["slide_min", "slide_max"],\n                "drive": '
    write(root, "model.py", swap(model, ranged + '"passive"', ranged + '"actuated"'))
    add_quote(root, tmp_path, STROKE + "\n", STROKE.rstrip("."), {"lo": -10, "hi": 15})
    for name, end in (("slide_min", "lo"), ("slide_max", "hi")):
        spec = {"from": f"N1.{end}", "value": None, "rationale": None, "gap": None}
        _param(name, basis="source", **spec)(root, tmp_path)
    stroke = {"id": "stroke", "kind": "range", "joint": "slide", "ends": ["N1.lo", "N1.hi"]}
    _append("checks.yaml", "checks", stroke)(root, tmp_path)


def test_range_check_on_a_slide_joint_compares_its_length_range_with_the_stated_stroke(
    proj_dir, tmp_path
):
    slide_driven(proj_dir, tmp_path)
    code, report = verify(proj_dir)
    assert code == 0, report["findings"]
    checks = _by_id(report)
    low, high = checks["stroke.slide_min"], checks["stroke.slide_max"]
    assert low["ok"] and high["ok"]
    assert high["pose"] == {"slide": {"from": "N1.hi", "value": 15}}
    assert high["measured"] == "15 slide's range end (slide_max)"
    # Compared in the length unit: 15.002 mm is outside tolerance.length.
    _param("slide_max", basis="proposed", value=15.002, rationale="x", gap="G1", **{"from": None})(
        proj_dir, tmp_path
    )
    assert findings(proj_dir, "check-failed") == [
        "stroke.slide_max: expected 15 (N1.hi), measured 15 slide's range end (slide_max)"
    ]


WIDTH = "The slider pin sits from 25 mm to 45 mm from the crank pivot."


def width_ranged(root: Path, tmp_path: Path) -> None:
    """The slider-crank driven by its slider, with a stated range of a distance the slide changes,
    not of its travel: the slider pin 25 to 45 mm from the crank pivot (N1 lo, hi), read by source
    params D_lo and D_hi, from which the slide's range params are derived. One check, width, a
    range check of slide between the crank pivot and the slider pin along x."""
    slider_crank(root, tmp_path, turns=())
    model = swap(SLIDER_CRANK, '"drive": "actuated"', '"drive": "passive"')
    ranged = '"range": ["slide_min", "slide_max"],\n                "drive": '
    write(root, "model.py", swap(model, ranged + '"passive"', ranged + '"actuated"'))
    add_quote(root, tmp_path, WIDTH + "\n", WIDTH.rstrip("."), {"lo": 25, "hi": 45})
    for end in ("lo", "hi"):
        _param(f"D_{end}", basis="source", **{"from": f"N1.{end}"})(root, tmp_path)
    for name, end in (("slide_min", "lo"), ("slide_max", "hi")):
        spec = {"value": None, "rationale": None, "gap": None}
        expr = f"D_{end} - sqrt(rod ** 2 - crank ** 2)"
        _param(name, basis="derived", expr=expr, **spec)(root, tmp_path)
    width = {
        "id": "width",
        "kind": "range",
        "joint": "slide",
        "instances": ["ground_1", "slider_1"],
        "between": ["ground_1.a", "slider_1.a"],
        "along": "x",
        "ends": ["N1.lo", "N1.hi"],
    }
    _append("checks.yaml", "checks", width)(root, tmp_path)


def test_range_check_between_two_datums_compares_the_distance_at_each_end_of_the_range(
    proj_dir, tmp_path
):
    width_ranged(proj_dir, tmp_path)
    code, report = verify(proj_dir)
    assert code == 0, report["findings"]
    checks = _by_id(report)
    low, high = checks["width.slide_min"], checks["width.slide_max"]
    assert low["ok"] and high["ok"]
    assert low["expected"] == "25 (N1.lo)" and high["expected"] == "45 (N1.hi)"
    assert high["measured"].endswith(" ground_1.a - slider_1.a")
    assert high["pose"]["slide"]["from"] == "slide_max"
    assert {"param D_lo", "param D_hi"}.isdisjoint(_unchecked(proj_dir))
    # The slide stopping short of the stated end leaves the distance there short of it.
    short = {"basis": "proposed", "value": 12, "rationale": "x", "gap": "G1", "expr": None}
    _param("slide_max", **short)(proj_dir, tmp_path)
    assert [m.split(":")[0] for m in findings(proj_dir, "check-failed")] == ["width.slide_max"]


def test_swept_interference_on_a_slide_joint_catches_a_collision_mid_stroke(proj_dir, tmp_path):
    slide_driven(proj_dir, tmp_path)
    model = (proj_dir / "model.py").read_text()
    model = swap(
        model, '"slider": slider},', '"slider": slider, "post": Box(p.link_W, p.link_W, p.link_H)},'
    )
    model = swap(
        model,
        '"ground_1": ("ground", Location()),',
        '"ground_1": ("ground", Location()), "post_1": ("post", Location((p.post_x, 0, 0))),',
    )
    write(proj_dir, "model.py", model)
    _parts(post={"density": "density"})(proj_dir, tmp_path)
    # The slider spans 10 mm, from x = 21.6 to 46.6 across the stroke: clear of a post at 33.6 at
    # either end, through it mid-stroke.
    for name, value in (("post_x", 33.6), ("sweep_steps", 3)):
        _param(name, basis="proposed", value=value, rationale="a test post", gap="G1")(
            proj_dir, tmp_path
        )
    sweep = {
        "id": "clear",
        "kind": "interference",
        "pairs": [["slider_1", "post_1"]],
        "sweep": {"joint": "slide", "steps": "sweep_steps"},
    }
    _append("checks.yaml", "checks", sweep)(proj_dir, tmp_path)
    code, report = verify(proj_dir)
    clear = _by_id(report)["clear"]
    assert code == 1 and not clear["ok"]
    assert clear["pose"] == {"slide": {"from": "slide_min..slide_max", "value": 2.5}}
    assert clear["sweep"]["range"] == [-10, 15]


_WHEEL = """\
            "wheel": {
                "type": "revolute",
                "parent": "ground_1",
                "child": "wheel_1",
                "axis": ["wheel_1.a", "wheel_1.a_up"],
                "drive": "passive",
            },
"""
_MESH = (
    '        "gears": {"mesh": {"driver": "input", "driven": "wheel", "ratio": "gear_ratio"}},\n'
)


def wheel_tips(turn: float, ratio: float = 0.5) -> float:
    """The geared slider-crank's closed form: how far the crank's tip lies from the wheel's with
    the crank turned turn degrees from upright and the wheel ratio times as far."""
    a, turned = SLIDER["crank"], math.radians(turn)
    crank_tip = (-a * math.sin(turned), a * math.cos(turned))
    wheel_tip = (a + a * math.cos(ratio * turned), a * math.sin(ratio * turned))
    return math.dist(crank_tip, wheel_tip)


def geared(root: Path, tmp_path: Path, mesh: str = _MESH) -> None:
    """The slider-crank with a wheel, a crank-long bar hinged at the ground link's far end and
    lying along it as built, turned by the gear mesh at gear_ratio (proposed 0.5) times the crank;
    its tip checked from the crank's tip, posed with the crank turned 30°."""
    slider_crank(root, tmp_path, turns=(30,))
    model = swap(SLIDER_CRANK, '"ground": a, "crank": a,', '"ground": a, "crank": a, "wheel": a,')
    model = swap(
        model,
        '"slider_1": ("slider", Location((reach, 0, 0))),',
        '"slider_1": ("slider", Location((reach, 0, 0))),\n'
        '            "wheel_1": ("wheel", Location((a, 0, 0))),',
    )
    model = swap(model, '        "joints": {\n', '        "joints": {\n' + _WHEEL)
    model = swap(model, '        "loops": {', mesh + '        "loops": {')
    write(root, "model.py", model)
    _parts(wheel={"density": "density"})(root, tmp_path)
    spec = {"basis": "proposed", "value": 0.5, "rationale": "a guess", "gap": "G1"}
    _param("gear_ratio", **spec)(root, tmp_path)
    tips = {
        "id": "tips",
        "kind": "distance",
        "instances": ["crank_1", "wheel_1"],
        "between": ["crank_1.d", "wheel_1.d"],
        "evidence": "N1",
        "key": "tips",
        "pose": {"input": "S30.turn"},
    }
    _append("checks.yaml", "checks", tips)(root, tmp_path)
    text = f"There the crank's tip lies {wheel_tips(30):.4f} mm from the wheel's tip."
    add_quote(root, tmp_path, text + "\n", text.rstrip("."), {"tips": round(wheel_tips(30), 4)})


def test_joints_coupled_by_a_gear_move_in_its_ratio_and_the_mjcf_and_report_carry_it(
    proj_dir, tmp_path
):
    mujoco = importlib.import_module("mujoco")

    geared(proj_dir, tmp_path)
    code, report = verify(proj_dir)
    # The wheel turns 15°, half the crank's 30°, the same way: not as built, nor the other way.
    assert code == 0, report["findings"]
    assert _by_id(report)["tips"]["ok"]
    assert min(abs(wheel_tips(30) - wheel_tips(30, r)) for r in (0, -0.5)) > 1
    m = mujoco.MjModel.from_xml_path(str(proj_dir / "build" / "model.mjcf"))
    mesh = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_EQUALITY, "mesh")
    assert m.eq_type[mesh] == mujoco.mjtEq.mjEQ_JOINT
    joint = mujoco.mjtObj.mjOBJ_JOINT
    assert (m.eq_obj1id[mesh], m.eq_obj2id[mesh]) == (
        mujoco.mj_name2id(m, joint, "wheel"),
        mujoco.mj_name2id(m, joint, "input"),
    )
    assert list(m.eq_data[mesh][:5]) == pytest.approx([0, 0.5, 0, 0, 0])
    assert report["motion"]["gears"] == {
        "mesh": {
            "driver": "input",
            "driven": "wheel",
            "ratio": {"from": "gear_ratio", "value": 0.5},
        }
    }


@pytest.mark.parametrize(
    "old, new, says",
    [
        ('"driven": "wheel"', '"driven": "axle"', "driven axle is not a joint"),
        (
            '"ratio": "gear_ratio"',
            '"ratio": "gear_teeth"',
            "ratio names gear_teeth, which params.yaml does not define",
        ),
        (
            '"driven": "wheel"',
            '"driven": "slide"',
            "couples a revolute joint with a slide one; a gear couples two of one type",
        ),
        (
            '"driven": "wheel"',
            '"driven": "input"',
            "driver and driven are both input; a gear couples two joints",
        ),
    ],
    ids=["unknown-joint", "undefined-ratio", "two-types", "one-joint"],
)
def test_gear_naming_an_unknown_joint_or_undefined_ratio_is_model_gear_naming_it(
    proj_dir, tmp_path, old, new, says
):
    geared(proj_dir, tmp_path, swap(_MESH, old, new))
    _, report = verify(proj_dir)
    errors = [(f["rule"], f["message"]) for f in report["findings"] if f["level"] == "error"]
    assert errors == [("model-gear", f"gear mesh: {says}")]
    # Like a joint the assembly cannot hinge, it drops the motion: no MJCF, no posed check.
    assert report["checks"] == [] and not (proj_dir / "build" / "model.mjcf").exists()


def test_pose_setting_both_joints_of_a_gear_out_of_its_ratio_is_check_config(proj_dir, tmp_path):
    geared(proj_dir, tmp_path)
    _check("tips", pose={"input": "S30.turn", "wheel": "S30.turn"})(proj_dir, tmp_path)
    assert findings(proj_dir, "check-config") == [
        "check tips: pose input at 30 (S30.turn), wheel at 30 (S30.turn): gear mesh moves wheel "
        "0.5 times input, so set one of them and the gear moves the other"
    ]


def test_gear_ratio_typed_into_model_py_is_model_return(proj_dir, tmp_path):
    geared(proj_dir, tmp_path, swap(_MESH, '"gear_ratio"', "3"))
    assert findings(proj_dir, "model-return") == [
        "model.build gear mesh: ratio must be a param name, not 3"
    ]


def test_guard_gear_ratio_typed_into_model_py_is_a_model_literal(proj_dir, tmp_path):
    geared(proj_dir, tmp_path, swap(_MESH, '"gear_ratio"', "3"))
    assert "model-literal" in errors(proj_dir)


# A cable wound on a wheel closes the joints it names toward their closed pose, in proportion to the
# wheel's turn, and a stroke check reads how far its path shortens.

_SPOOL = """\
            "spool": {
                "type": "revolute",
                "parent": "ground_1",
                "child": "spool_1",
                "axis": ["spool_1.a", "spool_1.a_up"],
                "range": ["turn"],
                "drive": "actuated",
            },
"""
_TOE2 = """\
            "toe2": {
                "type": "revolute",
                "parent": "toe_1",
                "child": "tip_1",
                "axis": ["tip_1.a", "tip_1.a_up"],
                "drive": "passive",
            },
"""
_TOES = """\
            "shift": {
                "type": "slide",
                "parent": "ground_1",
                "child": "base_1",
                "axis": ["base_1.a", "base_1.d"],
                "range": ["shift_min", "shift_max"],
                "drive": "passive",
            },
            "toe1": {
                "type": "revolute",
                "parent": "base_1",
                "child": "toe_1",
                "axis": ["toe_1.a", "toe_1.a_up"],
                "drive": "passive",
            },
"""
_PULL = '"path": ["ground_1.d", "spool_1.d", "tip_1.d"]'
_CABLE = (
    '        "cables": {"pull": {' + _PULL + ', "wheel": "spool",'
    ' "closes": {"toe1": "c1", "toe2": "c2"}}},\n'
)
# The ledger's spool turn and closed toe angles, in degrees.
CLOSED = {"turn": 120, "c1": 90, "c2": 60}


def pull_length(spool: float = 0, toe1: float = 0, toe2: float = 0, shift: float = 0) -> float:
    """The cabled slider-crank's closed form: the length of cable pull, from the ground link's far
    end round the spool's tip to the second toe's tip, with the spool, toes and slide at those
    values (degrees, mm) from as built."""
    w, c1, c12 = (math.radians(v) for v in (spool, toe1, toe1 + toe2))
    tip = (
        10 + shift + 10 * (math.cos(c1) + math.cos(c12)),
        -30 + 10 * (math.sin(c1) + math.sin(c12)),
    )
    points = [(15, 0), (5 * math.cos(w), -15 + 5 * math.sin(w)), tip]
    return sum(math.dist(a, b) for a, b in zip(points, points[1:]))


def pull_stroke(fraction: float = 1, **pose: float) -> float:
    """How far pull shortens with the spool at fraction of its full turn, the toes following."""
    turned = {k: fraction * v for k, v in zip(("spool", "toe1", "toe2"), CLOSED.values())}
    return pull_length() - pull_length(**(turned | pose))


def _shortening(check: dict) -> float:
    """A stroke check's measured shortening, without what it measured."""
    return float(check["measured"].split()[0])


def cabled(root: Path, tmp_path: Path, cable: str = _CABLE, *, sourced: bool = False) -> None:
    """The slider-crank with a toe pair beside it, each bar toe_L (10 mm) long: a base on slide
    shift, toe1 hinged on its tip and toe2 on toe1's tip, and cable pull wound on actuated spool
    (one-ended range turn), closing toe1 to c1 and toe2 to c2. Turn, c1 and c2 are proposed at
    CLOSED, or sourced from N1. Checks full and half read pull's stroke at the spool's full turn
    and at half_turn."""
    slider_crank(root, tmp_path, turns=(30,))
    model = swap(
        SLIDER_CRANK,
        '"ground": a, "crank": a,',
        '"ground": a, "crank": a, "spool": p.link_W, "base": p.toe_L, "toe": p.toe_L, '
        '"tip": p.toe_L,',
    )
    model = swap(
        model,
        '"slider_1": ("slider", Location((reach, 0, 0))),',
        '"slider_1": ("slider", Location((reach, 0, 0))),\n'
        '            "spool_1": ("spool", Location((0, -a, 0))),\n'
        '            "base_1": ("base", Location((0, -2 * a, 0))),\n'
        '            "toe_1": ("toe", Location((p.toe_L, -2 * a, 0))),\n'
        '            "tip_1": ("tip", Location((2 * p.toe_L, -2 * a, 0))),',
    )
    model = swap(model, '        "joints": {\n', '        "joints": {\n' + _SPOOL + _TOES + _TOE2)
    model = swap(model, '        "loops": {', cable + '        "loops": {')
    write(root, "model.py", model)
    _parts(**{n: {"density": "density"} for n in ("spool", "base", "toe", "tip")})(root, tmp_path)
    text = (
        f"Turned {CLOSED['turn']}° the spool closes the first toe {CLOSED['c1']}° and the second "
        f"{CLOSED['c2']}°, shortening the cable {pull_stroke():.4f} mm; turned halfway, "
        f"{pull_stroke(0.5):.4f} mm."
    )
    values = {"full": round(pull_stroke(), 4), "half": round(pull_stroke(0.5), 4)}
    values |= CLOSED if sourced else {}
    add_quote(root, tmp_path, text + "\n", text.rstrip("."), values)
    guess = {"basis": "proposed", "rationale": "a guess", "gap": "G1"}
    for name, value in CLOSED.items():
        spec = {"basis": "source", "from": f"N1.{name}"} if sourced else guess | {"value": value}
        _param(name, **spec)(root, tmp_path)
    halves = {"half_turn": CLOSED["turn"] / 2, "half_c1": CLOSED["c1"] / 2}
    for name, value in (halves | {"shift_min": -5, "shift_max": 5, "toe_L": 10}).items():
        _param(name, **guess, value=value)(root, tmp_path)
    stroke = {"kind": "stroke", "cable": "pull", "evidence": "N1"}
    _append("checks.yaml", "checks", stroke | {"id": "full", "key": "full"})(root, tmp_path)
    half = stroke | {"id": "half", "key": "half", "pose": {"spool": "half_turn"}}
    _append("checks.yaml", "checks", half)(root, tmp_path)


def test_a_cable_wound_on_a_wheel_closes_its_joints_in_proportion_to_its_turn(proj_dir, tmp_path):
    cabled(proj_dir, tmp_path)
    code, report = verify(proj_dir)
    checks = _by_id(report)
    # At the full turn the toes reach c1 and c2, at half of it half of each: not as built, nor
    # each other's closed angle.
    assert code == 0, report["findings"]
    assert checks["full"]["ok"] and checks["half"]["ok"]
    assert checks["full"]["pose"] == {"spool": {"from": "turn", "value": 120}}
    assert abs(pull_stroke() - pull_stroke(toe1=60, toe2=90)) > 0.01
    assert abs(pull_stroke(0.5) - pull_stroke(0.5, toe1=0, toe2=0)) > 0.01


def test_posing_a_closed_joint_alone_sets_its_wheel_and_the_cables_other_joints(proj_dir, tmp_path):
    cabled(proj_dir, tmp_path)
    # toe1 at half its closed angle turns the spool halfway, and the spool turns toe2 halfway.
    _check("half", pose={"toe1": "half_c1"})(proj_dir, tmp_path)
    code, report = verify(proj_dir)
    assert code == 0, report["findings"]
    assert _by_id(report)["half"]["ok"]
    assert abs(pull_stroke(0.5) - pull_stroke(0.5, spool=0)) > 0.01
    assert abs(pull_stroke(0.5) - pull_stroke(0.5, toe2=0)) > 0.01


def test_guard_a_passive_slide_may_be_a_cables_wheel(proj_dir, tmp_path):
    cabled(proj_dir, tmp_path)
    passive_slide = swap(swap(_SPOOL, "revolute", "slide"), "actuated", "passive")
    write(proj_dir, "model.py", swap((proj_dir / "model.py").read_text(), _SPOOL, passive_slide))
    by_toe = {"kind": "stroke", "cable": "pull", "evidence": "N1", "key": "half"}
    _append("checks.yaml", "checks", by_toe | {"id": "by_toe", "pose": {"toe1": "half_c1"}})(
        proj_dir, tmp_path
    )
    _, report = verify(proj_dir)
    assert not [f for f in report["findings"] if f["rule"].startswith("model-")]
    assert (proj_dir / "build" / "model.mjcf").exists()
    assert report["motion"]["cables"]["pull"]["wheel"] == "spool"
    spool = report["motion"]["joints"]["spool"]
    assert (spool["type"], spool["drive"]) == ("slide", "passive")
    # toe1 at half its closed angle puts the slide halfway along its stroke, as check half poses
    # it, and that move shortens the cable by more than the toes' share alone.
    checks = _by_id(report)
    assert _shortening(checks["by_toe"]) == pytest.approx(_shortening(checks["half"]))
    assert abs(_shortening(checks["half"]) - pull_stroke(0.5, spool=0)) > 0.01


def test_pose_setting_two_joints_of_a_cable_out_of_proportion_is_check_config(proj_dir, tmp_path):
    cabled(proj_dir, tmp_path)
    _check("half", pose={"toe1": "half_c1", "toe2": "c2"})(proj_dir, tmp_path)
    assert findings(proj_dir, "check-config") == [
        "check half: pose toe1 at 45 (half_c1), toe2 at 60 (c2): cable pull closes toe2 to 60 as "
        "spool turns to 120, so set one of them and the cable moves the other"
    ]


def test_pose_setting_alone_a_joint_a_cable_closes_to_0_is_check_config(proj_dir, tmp_path):
    cabled(proj_dir, tmp_path)
    _param("c2", value=0)(proj_dir, tmp_path)
    _check("half", pose={"toe2": "half_c1"})(proj_dir, tmp_path)
    assert findings(proj_dir, "check-config") == [
        "check half: pose toe2 at 45 (half_c1): cable pull closes toe2 to 0 as spool turns to "
        "120, so toe2 cannot set spool; set spool"
    ]


_FIXED_SPOOL = '            "spool": {"type": "fixed", "parent": "ground_1", "child": "spool_1"},\n'
_FIXED_TOE2 = '            "toe2": {"type": "fixed", "parent": "toe_1", "child": "tip_1"},\n'
_PULL2 = '"pull2": {"path": ["ground_1.d", "tip_1.d"], "wheel": "spool", "closes": {"toe2": "c2"}}'


@pytest.mark.parametrize(
    "model, cable, says",
    [
        (
            None,
            ("tip_1.d", "tip_1.zz"),
            "pull: tip_1.zz names no <instance>.<feature> datum of the assembly",
        ),
        (None, ('"wheel": "spool"', '"wheel": "reel"'), "pull: wheel reel is not a joint"),
        ((_SPOOL, _FIXED_SPOOL), None, "pull: wheel spool is a fixed joint"),
        (
            ('                "range": ["turn"],\n', ""),
            None,
            "pull: wheel spool needs a one-ended range, its full turn from as built; it has none",
        ),
        (
            ('"range": ["turn"]', '"range": ["c2", "turn"]'),
            None,
            "pull: wheel spool needs a one-ended range, its full turn from as built; it has "
            "['c2', 'turn']",
        ),
        (
            None,
            ('"ground_1.d", "spool_1.d"', '"spool_1.d", "ground_1.d"'),
            "pull: its path starts at spool_1.d, on the wheel; start it where the cable leaves "
            "the wheel, on an instance the wheel does not turn",
        ),
        (None, ('"toe2": "c2"', '"toe3": "c2"'), "pull: closes toe3, which is not a joint"),
        ((_TOE2, _FIXED_TOE2), None, "pull: closes toe2, which is a fixed joint"),
        (None, ('"toe2": "c2"', '"spool": "c2"'), "pull: closes its own wheel spool"),
        (
            None,
            (
                '"cables": {',
                '"gears": {"mesh": {"driver": "input", "driven": "toe2", '
                '"ratio": "half_c1"}},\n        "cables": {',
            ),
            "pull: closes toe2, which a gear couples",
        ),
        (
            None,
            ('"cables": {', '"cables": {' + _PULL2 + ", "),
            "pull: closes toe2, which cable pull2 closes too",
        ),
        (
            None,
            ('"toe2": "c2"', '"toe2": "c9"'),
            "pull: closes toe2 to c9, which params.yaml does not define",
        ),
    ],
    ids=[
        "unknown-datum",
        "wheel-not-a-joint",
        "wheel-fixed",
        "wheel-no-range",
        "wheel-two-ended",
        "starts-on-wheel",
        "closes-not-a-joint",
        "closes-fixed",
        "closes-wheel",
        "closes-geared",
        "closed-twice",
        "undefined-closed",
    ],
)
def test_cable_that_cannot_be_laid_or_close_its_joints_is_model_cable_naming_it(
    proj_dir, tmp_path, model, cable, says
):
    cabled(proj_dir, tmp_path, swap(_CABLE, *cable) if cable else _CABLE)
    if model:
        write(proj_dir, "model.py", swap((proj_dir / "model.py").read_text(), *model))
    _, report = verify(proj_dir)
    errors = [(f["rule"], f["message"]) for f in report["findings"] if f["level"] == "error"]
    assert errors == [("model-cable", f"cable {says}")]
    # Like a gear that cannot couple, it drops the motion: no MJCF, no stroke or posed check.
    assert report["checks"] == [] and not (proj_dir / "build" / "model.mjcf").exists()
    assert report["motion"]["dropped"] and report["motion"]["cables"] == {}


def test_two_cables_wound_on_one_wheel_each_close_their_joints(proj_dir, tmp_path):
    shared = swap(_CABLE, '"toe1": "c1", "toe2": "c2"', '"toe1": "c1"')
    cabled(proj_dir, tmp_path, swap(shared, '"cables": {', '"cables": {' + _PULL2 + ", "))
    code, report = verify(proj_dir)
    assert code == 0, report["findings"]
    assert _by_id(report)["full"]["ok"] and _by_id(report)["half"]["ok"]


@pytest.mark.parametrize(
    "old, new, says",
    [
        ('"cables": {"pull": ', '"cables": [', "cables must be a mapping of names, not list"),
        ('"pull": {', '"pull": 3, "_": {', "cable pull must be a mapping, not int"),
        ('"pull": {', "1: {", "cable 1: its name must be text, not int"),
        (
            '"wheel": "spool",',
            '"wheel": "spool", "stroke": "full",',
            "cable pull: unknown key 'stroke'",
        ),
        (' "wheel": "spool",', "", "cable pull: wheel and closes go together"),
        (
            ', "closes": {"toe1": "c1", "toe2": "c2"}',
            "",
            "cable pull: wheel and closes go together",
        ),
        (
            _PULL,
            '"path": ["ground_1.d"]',
            "cable pull: path must be two or more datums, not ['ground_1.d']",
        ),
        ('"c1"', "90", "cable pull: closes must map joint names to param names"),
    ],
    ids=[
        "cables-not-a-mapping",
        "not-a-mapping",
        "name-not-text",
        "unknown-key",
        "closes-without-wheel",
        "wheel-without-closes",
        "one-datum",
        "closed-literal",
    ],
)
def test_cable_of_the_wrong_shape_is_model_return(proj_dir, tmp_path, old, new, says):
    cable = swap(_CABLE, old, new)
    if new == '"cables": [':
        cable = swap(cable, "}}},\n", "}}],\n")
    cabled(proj_dir, tmp_path, cable)
    messages = findings(proj_dir, "model-return")
    assert len(messages) == 1 and messages[0].startswith(f"model.build {says}")


def test_cable_mjcf_couples_each_closed_joint_and_its_tendon_measures_cadrevs_path(
    proj_dir, tmp_path
):
    mujoco = importlib.import_module("mujoco")

    cabled(proj_dir, tmp_path)
    code, report = verify(proj_dir)
    assert code == 0, report["findings"]
    m = mujoco.MjModel.from_xml_path(str(proj_dir / "build" / "model.mjcf"))
    joint, equality = mujoco.mjtObj.mjOBJ_JOINT, mujoco.mjtObj.mjOBJ_EQUALITY
    for toe, closed in (("toe1", "c1"), ("toe2", "c2")):
        eq = mujoco.mj_name2id(m, equality, f"pull_{toe}")
        assert m.eq_type[eq] == mujoco.mjtEq.mjEQ_JOINT
        assert (m.eq_obj1id[eq], m.eq_obj2id[eq]) == (
            mujoco.mj_name2id(m, joint, toe),
            mujoco.mj_name2id(m, joint, "spool"),
        )
        assert m.eq_data[eq][1] == pytest.approx(CLOSED[closed] / CLOSED["turn"])
    assert m.neq == 3  # the slider-crank's loop and one per closed joint
    pull = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_TENDON, "pull")
    assert m.tendon_stiffness[pull] == 0
    # At cadrev's pose for the full turn, MuJoCo's tendon is as long as cadrev's path.
    data = mujoco.MjData(m)
    for name in ("spool", "toe1", "toe2"):
        value = CLOSED["c1" if name == "toe1" else "c2" if name == "toe2" else "turn"]
        data.qpos[m.jnt_qposadr[mujoco.mj_name2id(m, joint, name)]] = math.radians(value)
    mujoco.mj_forward(m, data)
    full = pull_length(CLOSED["turn"], CLOSED["c1"], CLOSED["c2"])
    assert data.ten_length[pull] == pytest.approx(full, abs=0.001)
    assert _by_id(report)["full"]["ok"]  # against pull_length() - full


def test_cable_mjcf_names_clear_a_loop_or_tendon_of_the_same_name(proj_dir, tmp_path):
    mujoco = importlib.import_module("mujoco")

    cord = '        "tendons": {"pull": {"path": ["ground_1.a", "tip_1.d"]}},\n'
    cabled(proj_dir, tmp_path, cord + _CABLE)
    model = swap((proj_dir / "model.py").read_text(), '"closure": [', '"pull_toe1": [')
    write(proj_dir, "model.py", model)
    code, report = verify(proj_dir)
    assert code == 0, report["findings"]
    m = mujoco.MjModel.from_xml_path(str(proj_dir / "build" / "model.mjcf"))
    names = {
        kind: [mujoco.mj_id2name(m, kind, i) for i in range(count)]
        for kind, count in (
            (mujoco.mjtObj.mjOBJ_EQUALITY, m.neq),
            (mujoco.mjtObj.mjOBJ_TENDON, m.ntendon),
        )
    }
    assert names[mujoco.mjtObj.mjOBJ_EQUALITY] == ["pull_toe1", "pull_toe1_2", "pull_toe2"]
    assert names[mujoco.mjtObj.mjOBJ_TENDON] == ["pull", "pull_2"]


def test_stroke_check_fails_when_the_ledger_is_off_by_more_than_its_tol(proj_dir, tmp_path):
    cabled(proj_dir, tmp_path)
    _check("full", tol=0.01)(proj_dir, tmp_path)
    _check("half", tol=0.01, key="full", pose={"spool": "turn"})(proj_dir, tmp_path)
    off = round(pull_stroke() + 0.02, 4)
    _evidence("N1", values={"full": round(pull_stroke(), 4), "half": off})(proj_dir, tmp_path)
    _check("half", key="half")(proj_dir, tmp_path)
    code, report = verify(proj_dir)
    assert _by_id(report)["full"]["ok"]
    assert code == 1 and not _by_id(report)["half"]["ok"]


@pytest.mark.parametrize(
    "sourced, rests_on, params",
    [(False, "proposed", ["turn", "c1", "c2"]), (True, "source", ["turn", "c1", "c2"])],
    ids=["proposed", "source"],
)
def test_stroke_check_rests_on_the_wheels_turn_and_closed_angles(
    proj_dir, tmp_path, sourced, rests_on, params
):
    cabled(proj_dir, tmp_path, sourced=sourced)
    code, report = verify(proj_dir)
    full = _by_id(report)["full"]
    assert code == 0, report["findings"]
    assert (full["rests_on"], full["rests_on_params"]) == (rests_on, params)


_TURN_AND_CLOSED = {"param turn", "param c1", "param c2"}


def test_source_turn_and_closed_angles_a_stroke_check_rests_on_are_not_unchecked_source(
    proj_dir, tmp_path
):
    cabled(proj_dir, tmp_path, sourced=True)
    _, report = verify(proj_dir)
    full = _by_id(report)["full"]
    assert (full["rests_on"], full["rests_on_params"]) == ("source", ["turn", "c1", "c2"])
    assert _TURN_AND_CLOSED.isdisjoint(_unchecked_in(report))


def test_guard_run_without_the_build_leaves_source_closed_angles_unchecked_source(
    proj_dir, tmp_path
):
    # With nothing built, the model gives no check its wheel's turn or closed angles.
    cabled(proj_dir, tmp_path, sourced=True)
    assert _TURN_AND_CLOSED <= set(_unchecked_printed(_partial(proj_dir, "--no-build")))


def test_stroke_check_posed_through_a_gear_on_its_wheel_rests_on_the_closed_angles(
    proj_dir, tmp_path
):
    mesh = (
        '        "gears": '
        '{"mesh": {"driver": "input", "driven": "spool", "ratio": "spool_ratio"}},\n'
    )
    cabled(proj_dir, tmp_path, mesh + _CABLE)
    _param("spool_ratio", basis="proposed", value=1, rationale="a guess", gap="G1")(
        proj_dir, tmp_path
    )
    # The pose names only the crank, which turns the spool through the gear, and the toes with it.
    _check("half", pose={"input": "S30.turn"}, tol=0.5)(proj_dir, tmp_path)
    _, report = verify(proj_dir)
    half = _by_id(report)["half"]
    assert (half["rests_on"], half["rests_on_params"]) == ("proposed", ["turn", "c1", "c2"])


# A check of each kind posed at the spool's full turn, besides a stroke check.
_AT_FULL_TURN = {"evidence": "N1", "key": "half", "tol": 0.5, "pose": {"spool": "turn"}}
_POSED_AT_THE_SPOOL = {
    "distance": {"between": ["ground_1.d", "tip_1.d"], "instances": ["ground_1", "tip_1"]}
    | _AT_FULL_TURN,
    "angle": {
        "between": ["ground_1.d", "spool_1.d", "tip_1.d"],
        "instances": ["ground_1", "spool_1", "tip_1"],
    }
    | _AT_FULL_TURN,
    "interference": {"pairs": [["ground_1", "tip_1"]], "pose": {"spool": "turn"}},
    "bbox": {"instances": ["ground_1", "tip_1"], "evidence": "N1", "axes": {"half": "x"}}
    | {"tol": 0.5, "pose": {"spool": "turn"}},
}


def _posed(report: dict) -> dict:
    """The result of check posed, as report.json gives it: a bbox check's under posed.<key>."""
    return next(c for c in report["checks"] if c["id"].split(".")[0] == "posed")


def _only_posed_at_the_spool(kind: str):
    """Replace cabled's stroke checks with one check of kind, posed at the spool's full turn."""
    check = {"id": "posed", "kind": kind, **_POSED_AT_THE_SPOOL[kind]}
    return lambda r, t: edit(r, "checks.yaml", lambda d: d.update(checks=[check]))


@pytest.mark.parametrize("kind", list(_POSED_AT_THE_SPOOL))
def test_a_check_posed_at_a_cables_wheel_reads_its_turn_and_closed_values(proj_dir, tmp_path, kind):
    cabled(proj_dir, tmp_path, sourced=True)
    _only_posed_at_the_spool(kind)(proj_dir, tmp_path)
    _, report = verify(proj_dir)
    posed = _posed(report)
    assert (posed["rests_on"], posed["rests_on_params"]) == ("source", ["turn", "c1", "c2"])
    assert _TURN_AND_CLOSED.isdisjoint(_unchecked_in(report))


@pytest.mark.parametrize("kind", list(_POSED_AT_THE_SPOOL))
def test_a_check_posed_at_a_cables_wheel_rests_on_its_proposed_closed_values(
    proj_dir, tmp_path, kind
):
    cabled(proj_dir, tmp_path)
    _only_posed_at_the_spool(kind)(proj_dir, tmp_path)
    _, report = verify(proj_dir)
    posed = _posed(report)
    assert (posed["rests_on"], posed["rests_on_params"]) == ("proposed", ["turn", "c1", "c2"])


def test_a_distance_check_posed_at_part_of_a_cables_turn_leaves_no_source_closed_value_unchecked(
    proj_dir, tmp_path
):
    cabled(proj_dir, tmp_path, sourced=True)
    _only_posed_at_the_spool("distance")(proj_dir, tmp_path)
    _check("posed", pose={"spool": "half_turn"})(proj_dir, tmp_path)
    _, report = verify(proj_dir)
    # half_turn is proposed, so the check rests on it; the source turn and closed values are read.
    posed = _posed(report)
    assert (posed["rests_on"], posed["rests_on_params"]) == ("proposed", ["half_turn"])
    assert _TURN_AND_CLOSED.isdisjoint(_unchecked_in(report))


def test_guard_a_check_posed_at_a_joint_no_cables_wheel_moves_reads_no_turn_or_closed_value(
    proj_dir, tmp_path
):
    cabled(proj_dir, tmp_path, sourced=True)
    _only_posed_at_the_spool("distance")(proj_dir, tmp_path)
    _check("posed", pose={"input": "S30.turn"})(proj_dir, tmp_path)
    _, report = verify(proj_dir)
    posed = _posed(report)
    assert (posed["rests_on"], posed["rests_on_params"]) == ("source", [])
    assert {"param c1", "param c2"} <= set(_unchecked_in(report))


def test_an_interference_check_swept_over_a_cables_wheel_reads_its_closed_values(
    proj_dir, tmp_path
):
    cabled(proj_dir, tmp_path, sourced=True)
    _param("steps", basis="proposed", value=3, rationale="a resolution", gap="G1")(
        proj_dir, tmp_path
    )
    swept = {"id": "posed", "kind": "interference", "pairs": [["ground_1", "tip_1"]]}
    swept["sweep"] = {"joint": "spool", "steps": "steps"}
    edit(proj_dir, "checks.yaml", lambda d: d.update(checks=[swept]))
    _, report = verify(proj_dir)
    posed = _posed(report)
    assert (posed["rests_on"], posed["rests_on_params"]) == ("source", ["turn", "c1", "c2"])
    assert _TURN_AND_CLOSED.isdisjoint(_unchecked_in(report))


def test_a_slide_the_cable_crosses_but_the_pose_does_not_set_leaves_its_stroke_unchanged(
    proj_dir, tmp_path
):
    cabled(proj_dir, tmp_path)
    code, report = verify(proj_dir)
    # The toes ride slide shift, which the stroke's pose leaves as built; moved, it would change
    # the stroke.
    assert code == 0, report["findings"]
    assert _by_id(report)["full"]["ok"]  # against pull_stroke(), with shift as built
    assert abs(pull_stroke() - pull_stroke(shift=5)) > 0.01


def test_stroke_check_on_a_cable_with_no_wheel_needs_a_pose(proj_dir, tmp_path):
    path_only = '        "cables": {"pull": {' + _PULL + "}},\n"
    cabled(proj_dir, tmp_path, path_only)
    _check("half", pose={"toe1": "half_c1"})(proj_dir, tmp_path)
    _, report = verify(proj_dir)
    messages = [f["message"] for f in report["findings"] if f["rule"] == "check-config"]
    assert messages == [
        "check full: cable pull has no wheel, so name the pose its stroke is taken at"
    ]
    # Posed, it evaluates: toe1 alone, the spool and toe2 as built.
    assert _shortening(_by_id(report)["half"]) == pytest.approx(
        pull_length() - pull_length(toe1=CLOSED["c1"] / 2), abs=0.01
    )


def _stopped_after_its_pose(root: Path, tmp_path: Path, **changes) -> dict:
    """The report of cabled with sourced turn and closed values and stroke check full alone, its
    key naming no value in N1, so a finding stops it once it is posed."""
    cabled(root, tmp_path, sourced=True)
    edit(
        root,
        "checks.yaml",
        lambda d: d.update(checks=[c for c in d["checks"] if c["id"] == "full"]),
    )
    _check("full", key="none", **changes)(root, tmp_path)
    report = verify(root)[1]
    assert [f["message"] for f in report["findings"] if f["rule"] == "check-config"] == [
        "check full: missing or unknown 'evidence value N1.none'"
    ]
    return report


def test_stroke_check_with_no_pose_stopped_after_its_wheels_full_turn_reads_turn_and_closed(
    proj_dir, tmp_path
):
    report = _stopped_after_its_pose(proj_dir, tmp_path)
    assert _TURN_AND_CLOSED.isdisjoint(_unchecked_in(report))


def test_guard_stroke_check_posed_at_the_full_turn_stopped_after_it_reads_turn_and_closed(
    proj_dir, tmp_path
):
    report = _stopped_after_its_pose(proj_dir, tmp_path, pose={"spool": "turn"})
    assert _TURN_AND_CLOSED.isdisjoint(_unchecked_in(report))


def test_cable_through_a_datum_on_the_axis_of_a_joint_it_closes_is_cable_on_axis(
    proj_dir, tmp_path
):
    # toe_1.a_up lies on toe1's hinge: turning toe1 leaves it, and so the cable, where it was.
    cabled(proj_dir, tmp_path, swap(_CABLE, '"spool_1.d", "tip_1.d"', '"spool_1.d", "toe_1.a_up"'))
    assert findings(proj_dir, "cable-on-axis") == [
        "cable pull: toe_1.a_up lies on the axis of toe1, which it closes, so turning toe1 leaves "
        "the cable's length unchanged; lay the path through a datum off that axis, such as a "
        "guide's eye on a face"
    ]


def test_report_carries_each_cable_with_its_wheel_and_closed_values(proj_dir, tmp_path):
    cabled(proj_dir, tmp_path)
    _, report = verify(proj_dir)
    assert report["motion"]["cables"] == {
        "pull": {
            "path": ["ground_1.d", "spool_1.d", "tip_1.d"],
            "wheel": "spool",
            "closes": {
                "toe1": {"from": "c1", "value": 90},
                "toe2": {"from": "c2", "value": 60},
            },
        }
    }
    assert (
        "- Cable `pull` through ground_1.d → spool_1.d → tip_1.d, wound on spool; "
        "its full turn closes toe1 to 90 (c1), toe2 to 60 (c2)."
    ) in (proj_dir / "build" / "report.md").read_text()


# A stroke check may claim its cable shortens or lengthens between two poses, where a source states
# a direction but prints no length (ADR-0010).

_CORD = '"cord": {"path": ["ground_1.d", "tip_1.d"]}'


def cord_length(toe1: float = 0, toe2: float = 0) -> float:
    """The length of path-only cable cord, from the ground link's far end straight to the second
    toe's tip, with the toes at those angles (degrees) from as built."""
    c1, c12 = math.radians(toe1), math.radians(toe1 + toe2)
    tip = (10 + 10 * (math.cos(c1) + math.cos(c12)), -30 + 10 * (math.sin(c1) + math.sin(c12)))
    return math.dist((15, 0), tip)


def cord_at(fraction: float) -> float:
    """cord's length with the spool at fraction of its full turn, the toes closing with it."""
    return cord_length(fraction * CLOSED["c1"], fraction * CLOSED["c2"])


# The ledger item the claim cites: a quote that states no number.
_STATES = {"id": "N2", "source": "notes", "locator": "Sec. 1", "quote": "the spool closes"}


def claimed(
    root: Path, tmp_path: Path, check: dict | None = None, *, sourced: bool = False
) -> None:
    """cabled with a second, path-only cable cord beside pull, ledger item N2 stating a direction
    with no values, and claim check perch on cord: by default that it shortens from the spool's
    full turn (from) to half of it (pose), as the toes open; check changes its keys, None removing
    one."""
    cabled(
        root, tmp_path, swap(_CABLE, '"cables": {', '"cables": {' + _CORD + ", "), sourced=sourced
    )
    _append("evidence.yaml", "evidence", _STATES)(root, tmp_path)
    perch = {"id": "perch", "kind": "stroke", "cable": "cord", "evidence": "N2"}
    perch |= {"claim": "shortens", "from": {"spool": "turn"}, "pose": {"spool": "half_turn"}}
    _append(
        "checks.yaml", "checks", {k: v for k, v in (perch | (check or {})).items() if v is not None}
    )(root, tmp_path)


def test_claim_check_passes_where_its_cable_shortens_between_its_two_poses(proj_dir, tmp_path):
    claimed(proj_dir, tmp_path)
    code, report = verify(proj_dir)
    perch = _by_id(report)["perch"]
    assert code == 0, report["findings"]
    assert perch["ok"]
    assert _shortening(perch) == pytest.approx(cord_at(1) - cord_at(0.5), abs=1e-3)
    assert cord_at(1) - cord_at(0.5) > 1  # the toes open: as built to full turn would not do
    assert perch["expected"] == "shortens by more than 0.001 (N2)"
    assert perch["from_pose"] == {"spool": {"from": "turn", "value": 120}}
    assert perch["pose"] == {"spool": {"from": "half_turn", "value": 60}}
    assert (
        "| perch | pass | shortens by more than 0.001 (N2) | "
        f"{cord_at(1) - cord_at(0.5):.4g} shortening of cord | "
        "from: spool at 120 (turn); posed: spool at 60 (half_turn);"
    ) in (proj_dir / "build" / "report.md").read_text()


def test_claim_check_the_other_way_is_check_failed_naming_its_change_poses_and_claim(
    proj_dir, tmp_path
):
    claimed(proj_dir, tmp_path, {"claim": "lengthens"})
    code, report = verify(proj_dir)
    assert code == 1 and not _by_id(report)["perch"]["ok"]
    assert [f["message"] for f in report["findings"] if f["rule"] == "check-failed"] == [
        "perch: expected lengthens by more than 0.001 (N2), measured "
        f"{cord_at(1) - cord_at(0.5):.4g} shortening of cord "
        "from spool at 120 (turn) to spool at 60 (half_turn)"
    ]


@pytest.mark.parametrize("tolerance, ok", [(None, True), (0.5, False)], ids=["default", "0.5"])
def test_claim_check_passes_only_on_a_change_beyond_tolerance_length(
    proj_dir, tmp_path, tolerance, ok
):
    # From the full turn to a degree short of it, the cord shortens by more than the default
    # tolerance.length but no more than 0.5.
    claimed(proj_dir, tmp_path, {"pose": {"spool": "near_turn"}})
    _param("near_turn", basis="proposed", value=119, rationale="a guess", gap="G1")(
        proj_dir, tmp_path
    )
    if tolerance is not None:
        edit(proj_dir, "project.yaml", lambda d: d.update(tolerance={"length": tolerance}))
    change = cord_at(1) - cord_at(119 / 120)
    assert 0.001 < change <= 0.5
    _, report = verify(proj_dir)
    perch = _by_id(report)["perch"]
    assert _shortening(perch) == pytest.approx(change, abs=1e-3)
    assert perch["ok"] is ok


@pytest.mark.parametrize(
    "check, rule, says",
    [
        (
            {"key": "full"},
            "check-config",
            "check perch: give key or claim, not both",
        ),
        (
            {"claim": None},
            "check-config",
            "check perch: give key, the ledger value its stroke is compared with, "
            "or claim: shortens or lengthens",
        ),
        (
            {"claim": "grows"},
            "check-config",
            "check perch: claim grows is neither shortens nor lengthens",
        ),
        (
            {"tol": 0.5},
            "check-config",
            "check perch: a claim passes only beyond tolerance.length, so it takes no tol",
        ),
        (
            {"tol_rel": 0.1},
            "check-config",
            "check perch: a claim passes only beyond tolerance.length, so it takes no tol_rel",
        ),
        (
            {"evidence": None},
            "check-config",
            "check perch: a claim cites the evidence item that states it",
        ),
        (
            {"evidence": "N9"},
            "check-config",
            "check perch: evidence N9 is not an evidence item",
        ),
        (
            {"claim": 3},
            "schema",
            "checks.yaml checks[3].claim: must be text, not 3",
        ),
        (
            {"from": ["spool"]},
            "schema",
            "checks.yaml checks[3].from: must be a mapping, not a list",
        ),
    ],
    ids=[
        "key-and-claim",
        "neither",
        "unknown-claim",
        "tol",
        "tol_rel",
        "no-evidence",
        "unknown-evidence",
        "claim-not-text",
        "from-not-a-mapping",
    ],
)
def test_claim_check_configured_wrong_is_a_finding_and_not_evaluated(
    proj_dir, tmp_path, check, rule, says
):
    claimed(proj_dir, tmp_path, check)
    _, report = verify(proj_dir)
    assert [f["message"] for f in report["findings"] if f["rule"] == rule] == [says]
    assert "perch" not in _by_id(report)


@pytest.mark.parametrize("kind", ["distance", "angle", "bbox"])
@pytest.mark.parametrize("key", ["claim", "from"])
def test_claim_or_from_on_a_check_of_another_kind_is_check_config(proj_dir, tmp_path, kind, key):
    cabled(proj_dir, tmp_path)
    _only_posed_at_the_spool(kind)(proj_dir, tmp_path)
    _check("posed", **{key: {"claim": "shortens", "from": {"spool": "half_turn"}}[key]})(
        proj_dir, tmp_path
    )
    assert findings(proj_dir, "check-config") == [
        f"check posed: {key} is for a stroke check; kind {kind} takes none"
    ]


def test_quote_with_no_values_cited_only_by_a_claim_check_needs_none(proj_dir, tmp_path):
    claimed(proj_dir, tmp_path)
    _, report = verify(proj_dir)
    assert not [f for f in report["findings"] if f["rule"] == "evidence-values"]


def test_guard_quote_with_no_values_cited_by_nothing_still_needs_values(proj_dir, tmp_path):
    cabled(proj_dir, tmp_path)
    _append("evidence.yaml", "evidence", _STATES)(proj_dir, tmp_path)
    assert findings(proj_dir, "evidence-values") == ["N2: needs values (or scope: context)"]


def test_guard_quote_with_no_values_a_keyed_check_cites_besides_a_claim_still_needs_values(
    proj_dir, tmp_path
):
    claimed(proj_dir, tmp_path)
    keyed = {"id": "keyed", "kind": "stroke", "cable": "pull", "evidence": "N2", "key": "full"}
    _append("checks.yaml", "checks", keyed)(proj_dir, tmp_path)
    assert findings(proj_dir, "evidence-values") == ["N2: needs values (or scope: context)"]


def test_guard_claim_checks_quote_is_still_matched_against_its_source(proj_dir, tmp_path):
    claimed(proj_dir, tmp_path)
    _evidence("N2", quote="the spool opens")(proj_dir, tmp_path)
    assert findings(proj_dir, "quote-not-found") == [
        "N2: quote not found in notes: 'the spool opens'"
    ]


def test_claim_check_rests_on_the_closed_values_its_from_pose_moves_through_a_cable(
    proj_dir, tmp_path
):
    # Its pose moves only slide shift, so the closed values come from its from pose alone.
    claimed(proj_dir, tmp_path, {"pose": {"shift": "shift_max"}})
    _, report = verify(proj_dir)
    perch = _by_id(report)["perch"]
    assert perch["rests_on"] == "proposed"
    assert perch["rests_on_params"] == ["turn", "shift_max", "c1", "c2"]


def test_claim_check_whose_from_pose_a_loop_cannot_close_at_is_loop_open_and_unevaluated(
    proj_dir, tmp_path
):
    # The slider pushed along its slide with the crank held as built: the rod cannot reach it.
    claimed(proj_dir, tmp_path, {"from": {"slide": "shift_max"}})
    _, report = verify(proj_dir)
    opened = [f["message"] for f in report["findings"] if f["rule"] == "loop-open"]
    assert len(opened) == 1 and "with slide at 5 (shift_max)" in opened[0], opened
    assert "perch" not in _by_id(report)


def test_claim_check_whose_from_pose_leaves_a_joint_past_its_range_is_joint_range_and_unevaluated(
    proj_dir, tmp_path
):
    claimed(proj_dir, tmp_path, {"from": {"shift": "far_shift"}})
    _param("far_shift", basis="proposed", value=10, rationale="a guess", gap="G1")(
        proj_dir, tmp_path
    )
    _, report = verify(proj_dir)
    beyond = [f["message"] for f in report["findings"] if f["rule"] == "joint-range"]
    assert len(beyond) == 1 and beyond[0].startswith(
        "joint shift: slides 10 with shift at 10 (far_shift), outside its range"
    ), beyond
    assert "perch" not in _by_id(report)


def test_from_pose_naming_no_joint_is_check_config_naming_from(proj_dir, tmp_path):
    claimed(proj_dir, tmp_path, {"from": {"heel": "turn"}})
    assert findings(proj_dir, "check-config") == [
        "check perch: from names heel, which is not a joint"
    ]


def test_claim_citing_a_repeated_evidence_id_is_check_config_and_unevaluated(proj_dir, tmp_path):
    claimed(proj_dir, tmp_path)
    _append("evidence.yaml", "evidence", _STATES)(proj_dir, tmp_path)
    _, report = verify(proj_dir)
    assert [f["message"] for f in report["findings"] if f["rule"] == "check-config"] == [
        "check perch: N2 cites N2, a repeated evidence id"
    ]
    assert "perch" not in _by_id(report)


def test_stroke_check_with_a_key_is_taken_from_its_from_pose(proj_dir, tmp_path):
    cabled(proj_dir, tmp_path)
    _check("full", **{"from": {"spool": "half_turn"}}, pose={"spool": "turn"})(proj_dir, tmp_path)
    _, report = verify(proj_dir)
    full = _by_id(report)["full"]
    # From half the turn to the full turn: the full stroke less the half one, not the full stroke.
    assert _shortening(full) == pytest.approx(pull_stroke() - pull_stroke(0.5), abs=1e-3)
    assert full["from_pose"] == {"spool": {"from": "half_turn", "value": 60}}


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
    return lambda r, t: write(r, "model.py", swap(MODEL, '{"link_1": ("link", Location())}', entry))


def _shell(faces: str):
    """The link rebuilt as a solid from a shell of its faces[faces]."""
    part = f'{{"link": Solid(Shell(link.faces(){faces}))}}'
    return lambda r, t: write(r, "model.py", swap(MODEL, '{"link": link}', part))


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
    """Register the paper as a two-page PDF or a DOCX, source doc, and ledger quote from it as
    N1."""

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
_MOVED = swap(MODEL, "\n\n\n", "\n\n# v1\n")

FINDINGS = {
    "assembly-part": (
        _assembly('{"link_1": ("pin", Location())}'),
        [_assembly('{"pin": ("link", Location())}')],
    ),
    "cable-on-axis": (
        lambda r, t: cabled(r, t, swap(_CABLE, '"tip_1.d"', '"toe_1.a_up", "tip_1.d"')),
        [
            # off the axis, on the joint's child; on the axis of the wheel, which no cable closes
            cabled,
            lambda r, t: cabled(r, t, swap(_CABLE, '"spool_1.d"', '"spool_1.a"')),
        ],
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
    "gap-unused": (
        lambda r, t: add_gap(r, "G2"),
        [
            lambda r, t: (
                add_gap(r, "G2"),
                _param("spare", basis="proposed", value=3, rationale="x", gap="G2")(r, t),
            )
        ],
    ),
    "image-hash": (_reading(image_sha256="0" * 64), [_reading()]),
    "image-missing": (_unpinned_reading, [_reading()]),
    "image-reading": (_reading(reading=""), [_reading(reading="70")]),
    "joint-range": (_knee_range(-1, 1), [_knee_range(-180, 180)]),
    "loop-open": (_coupler(20), [_coupler(25)]),
    "mjcf-load": (_density(0), [_density(0.0012)]),
    "model-arithmetic": (
        lambda r, t: _model_with(r, line="extra = 2 * 2 - 0.5"),
        [lambda r, t: _model_with(r, line="extra = 2 * 2 - 2")],
    ),
    "model-build": (
        lambda r, t: _model_with(r, line="extra = p.pitch_2"),
        [lambda r, t: _model_with(r, line="extra = p.pitch")],
    ),
    "model-cable": (
        lambda r, t: cabled(r, t, swap(_CABLE, '"toe2": "c2"', '"spool": "c2"')),
        [lambda r, t: cabled(r, t, swap(_CABLE, '"toe2": "c2"', '"toe2": "c1"'))],
    ),
    "model-constant": (
        lambda r, t: _model_with(r, line="extra = p.pitch / p.pitch"),
        [lambda r, t: _model_with(r, line="extra = p.pitch / p.link_H")],
    ),
    "model-gear": (
        lambda r, t: geared(r, t, swap(_MESH, '"driven": "wheel"', '"driven": "axle"')),
        [lambda r, t: geared(r, t, swap(_MESH, '"driver": "input"', '"driver": "knee"'))],
    ),
    "model-joint": (
        _bar(_INPUT_AXIS, '"axis": ["crank_1.a", "crank_1.a"]'),
        [_bar(_INPUT_AXIS, '"axis": ["crank_1.a_up", "crank_1.a"]')],
    ),
    "model-literal": (
        lambda r, t: _model_with(r, line="extra = 7.5"),
        [lambda r, t: _model_with(r, line="extra = 0.5")],
    ),
    "model-loop": (
        _bar('"ground_1.d"]}', '"ground_1.e"]}'),
        [_bar('["rocker_1.d", "ground_1.d"]}', '["ground_1.d", "rocker_1.d"]}')],
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
    "param-physics": (_param("hole_d", physics=True), [physical]),
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
    # The static project, its part weighed by nothing, is no finding.
    "part-mass": (_unweighed_rocker, [lambda r, t: None, four_bar, _servo_crank]),
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
def test_change_raises_its_rule(proj_dir, tmp_path, rule):
    FINDINGS[rule][0](proj_dir, tmp_path)
    assert rule in rules(proj_dir)


@pytest.mark.parametrize(
    "rule, miss", [(rule, i) for rule in sorted(FINDINGS) for i in range(len(FINDINGS[rule][1]))]
)
def test_guard_near_miss_raises_no_rule(proj_dir, tmp_path, rule, miss):
    FINDINGS[rule][1][miss](proj_dir, tmp_path)
    assert rule not in rules(proj_dir)


# Released geometry (ADR-0011): the link as its authors released it, a STEP exported from a
# build123d solid and placed where the file puts it, a quarter turn about Z and moved off the
# origin, so a shape check must align it by its datum pairs.

RELEASED_AT = Location((100, 50, 20), (0, 0, 1), 90)
# The link's datums, a and b on its hole axes and c at the top of a's, where the built link and
# the released one have them in the link's own frame.
LINK_DATUMS = {"a": (-15, 0, 0), "b": (15, 0, 0), "c": (-15, 0, 4)}
_THREE_DATUMS = swap(
    MODEL,
    '"link.b": (p.pitch / 2, 0, 0)}',
    '"link.b": (p.pitch / 2, 0, 0), "link.c": (-p.pitch / 2, 0, p.link_H / 2)}',
)


def link_body(pitch: float = 30, extra_hole: bool = False):
    """The link as released: 40×5×8 with its two 3 mm holes pitch apart, and with extra_hole a
    2 mm hole at its middle that the built link lacks."""
    body = Box(40, 5, 8)
    for x in (-pitch / 2, pitch / 2) + ((0,) if extra_hole else ()):
        body -= Pos(x, 0, 0) * Cylinder(1 if x == 0 else 1.5, 8)
    return body


def placed_at(at, point) -> list[float]:
    return list((at * Location(point)).position)


def released(root: Path, tmp_path: Path, body=None, at=RELEASED_AT, check=True, **shape) -> Path:
    """Register body (the link by default), placed at at, as geometry source link_step, declare
    its datums a, b and c where at puts the link's, give the built link datum c, and with check
    compare the built link with it by a shape check (shape gives its other keys). Returns the
    STEP."""
    path = tmp_path / "link.step"
    export_step((link_body() if body is None else body).moved(at), str(path))
    register = ["source", str(root), str(path), "--id", "link_step", "--kind", "geometry"]
    assert cli.main([*register, "--citation", "Doe 2026, link.step"]) == 0
    datums = {f"link_step.{k}": placed_at(at, v) for k, v in LINK_DATUMS.items()}
    edit(root, "evidence.yaml", lambda d: d.update(datums=datums))
    write(root, "model.py", _THREE_DATUMS)
    if check:
        pairs = [[f"link.{k}", f"link_step.{k}"] for k in LINK_DATUMS]
        entry = {"id": "shape", "kind": "shape", "part": "link", "body": "link_step"}
        edit(root, "checks.yaml", lambda d: d["checks"].append(entry | {"pairs": pairs} | shape))
    return path


def test_released_step_registers_as_geometry_pinned_by_its_sha256(proj_dir, tmp_path):
    path = released(proj_dir, tmp_path)
    (entry,) = [s for s in _loaded_sources(proj_dir) if s["id"] == "link_step"]
    assert (entry["kind"], entry["sha256"]) == ("geometry", sha256(path))
    found = rules(proj_dir)
    assert "source-kind" not in found and "source-unreadable" not in found


def test_released_step_rewritten_after_registering_is_a_source_hash(proj_dir, tmp_path):
    released(proj_dir, tmp_path)
    export_step(link_body(pitch=32), str(proj_dir / "sources" / "link.step"))
    assert "source-hash" in errors(proj_dir)


def test_geometry_source_whose_file_is_no_step_is_unreadable(proj_dir, tmp_path):
    released(proj_dir, tmp_path)
    step = proj_dir / "sources" / "link.step"
    step.write_text("not a STEP file\n")
    edit(proj_dir, "project.yaml", lambda d: d["sources"][1].update(sha256=sha256(step)))
    assert "source-unreadable" in errors(proj_dir)


def _shape_result(report: dict) -> dict:
    (result,) = [r for r in report["checks"] if r["id"] == "shape"]
    return result


def test_shape_check_on_a_part_built_to_match_its_released_body_passes(proj_dir, tmp_path):
    released(proj_dir, tmp_path)
    code, report = verify(proj_dir)
    result = _shape_result(report)
    assert result["ok"] and result["shape"]["residual"] < 1e-9
    assert result["shape"]["distance"] < 1e-9
    assert (code, report["status"]) == (0, "VERIFIED")


def test_shape_check_on_a_part_missing_a_feature_fails_at_its_worst_point(proj_dir, tmp_path):
    released(proj_dir, tmp_path, body=link_body(extra_hole=True), at=Location())
    code, report = verify(proj_dir)
    result = _shape_result(report)
    x, y, _ = result["shape"]["worst_point"]
    # The worst point lies on the 2 mm hole the built link lacks, 2.5 mm from its nearest face.
    assert not result["ok"] and math.hypot(x, y) == pytest.approx(1, abs=1e-6)
    assert result["shape"]["distance"] == pytest.approx(2.5, abs=1e-6)
    assert code == 1 and any(
        f["rule"] == "check-failed" and "largest surface distance" in f["message"]
        for f in report["findings"]
    )


def test_shape_check_whose_datum_pairs_fit_beyond_the_length_tolerance_fails(proj_dir, tmp_path):
    # The released holes are 32 mm apart and the built ones 30, so a and b cannot both fit.
    released(proj_dir, tmp_path, body=link_body(pitch=32), at=Location())
    wide = {"link_step.a": [-16, 0, 0], "link_step.b": [16, 0, 0], "link_step.c": [-16, 0, 4]}
    edit(proj_dir, "evidence.yaml", lambda d: d["datums"].update(wide))
    _, report = verify(proj_dir)
    result = _shape_result(report)
    assert not result["ok"] and result["shape"]["residual"] > 0.5
    assert "distance" not in result["shape"]
    (failed,) = [f["message"] for f in report["findings"] if f["rule"] == "check-failed"]
    assert "datum pairs fit within" in failed


@pytest.mark.parametrize(
    "pairs",
    [
        [["link.a", "link_step.a"], ["link.b", "link_step.b"]],
        [["link.a", "link_step.a"], ["link.b", "link_step.b"], ["link.a", "link_step.a"]],
    ],
    ids=["two pairs", "three on one line"],
)
def test_shape_check_with_fewer_than_three_pairs_off_one_line_is_check_config(
    proj_dir, tmp_path, pairs
):
    released(proj_dir, tmp_path, pairs=pairs)
    assert any(
        f["rule"] == "check-config" and "aligns by" in f["message"]
        for f in verify(proj_dir)[1]["findings"]
    )
    assert "shape" not in [r["id"] for r in verify(proj_dir)[1]["checks"]]


@pytest.mark.parametrize(
    "name, point",
    [("link_step.a", [-14, 0, 0]), ("other.a", [-15, 0, 0])],
    ids=["off the body", "on no body"],
)
def test_datum_declared_off_its_released_body_is_datum_off_solid(proj_dir, tmp_path, name, point):
    released(proj_dir, tmp_path, at=Location())
    edit(proj_dir, "evidence.yaml", lambda d: d["datums"].update({name: point}))
    assert any(
        f["rule"] == "datum-off-solid" and name in f["message"]
        for f in verify(proj_dir)[1]["findings"]
    )


def test_released_datum_of_two_numbers_is_schema(proj_dir, tmp_path):
    released(proj_dir, tmp_path)
    edit(proj_dir, "evidence.yaml", lambda d: d["datums"].update({"link_step.a": [1, 2]}))
    found = [f for f in verify(proj_dir)[1]["findings"] if "link_step.a" in f["message"]]
    assert [f["rule"] for f in found if f["rule"] in ("schema", "datum-off-solid")] == ["schema"]


def test_datums_declared_on_the_axes_of_a_released_body_lie_on_its_solid(proj_dir, tmp_path):
    released(proj_dir, tmp_path)
    assert "datum-off-solid" not in rules(proj_dir)


# The released link's bbox diagonal, √(40² + 5² + 8²) = 41.10 mm, caps a shape check's tol at 0.411.
@pytest.mark.parametrize("tol, capped", [(0.5, True), (0.4, False)])
def test_shape_check_tol_above_one_percent_of_its_bodys_diagonal_is_tolerance_cap(
    proj_dir, tmp_path, tol, capped
):
    released(proj_dir, tmp_path, tol=tol)
    found = [f["message"] for f in verify(proj_dir)[1]["findings"] if f["rule"] == "tolerance-cap"]
    capping = "check shape: tol 0.5 is above 1% of body link_step's bbox diagonal, 41.1"
    assert found == ([capping] if capped else [])


# The released link's envelope in the file's frame, where a quarter turn about Z lays its length
# along Y: a probe that restates Table 1.
PROBE = {
    "id": "P-link",
    "source": "link_step",
    "locator": "the released link",
    "probe": "bbox",
    "axes": {"L": "y", "W": "x", "H": "z"},
    "values": {"L": 40, "W": 5, "H": 8},
    "scope": "context",
    "reason": "restates T1-link",
}


def probed(root: Path, tmp_path: Path, **entry) -> None:
    """The link released, and probed by PROBE with entry's changes."""
    released(root, tmp_path)
    edit(root, "evidence.yaml", lambda d: d["evidence"].append(PROBE | entry))


def _mismatches(report: dict) -> list[str]:
    return [f["message"] for f in report["findings"] if f["rule"] == "probe-mismatch"]


def test_bbox_probe_whose_recorded_value_matches_the_file_passes(proj_dir, tmp_path):
    probed(proj_dir, tmp_path)
    code, report = verify(proj_dir)
    assert "probe-mismatch" not in [f["rule"] for f in report["findings"]]
    assert (code, report["status"]) == (0, "VERIFIED")


def test_bbox_probe_off_by_more_than_the_length_tolerance_is_probe_mismatch(proj_dir, tmp_path):
    probed(proj_dir, tmp_path, values={"L": 40.002, "W": 5, "H": 8})
    code, report = verify(proj_dir)
    assert _mismatches(report) == [
        "probe P-link.L: evaluates to 40 on body link_step, but records 40.002 (tolerance 0.001)"
    ]
    assert "probe-mismatch" in [f["rule"] for f in report["findings"]] and code == 1


def test_bbox_probe_mismatch_is_raised_without_the_build(proj_dir, tmp_path, capsys):
    probed(proj_dir, tmp_path, values={"L": 41, "W": 5, "H": 8})
    cli.main(["check", str(proj_dir), "--no-build"])
    assert "[probe-mismatch] probe P-link.L" in capsys.readouterr().out


def test_project_whose_only_released_value_is_a_probe_is_verified_not_pending_review(
    proj_dir, tmp_path
):
    probed(proj_dir, tmp_path)
    _, report = verify(proj_dir)
    assert report["status"] == "VERIFIED" and report["awaiting_confirmation"] == []


def test_param_from_a_probe_takes_its_value_and_rests_on_source(proj_dir, tmp_path):
    probed(proj_dir, tmp_path, axes={"L": "y"}, values={"L": 40}, scope=None, reason=None)
    edit(proj_dir, "params.yaml", lambda d: d["params"]["link_L"].update({"from": "P-link.L"}))
    code, report = verify(proj_dir)
    assert report["params"]["link_L"]["value"] == 40
    assert report["params"]["link_L"]["rests_on"] == "source"
    assert (code, report["status"]) == (0, "VERIFIED")


def test_report_json_lists_each_probe_with_its_evaluated_value(proj_dir, tmp_path):
    probed(proj_dir, tmp_path, values={"L": 40, "W": 5.0004, "H": 8})
    _, report = verify(proj_dir)
    by_key = {p["key"]: p for p in report["probes"]}
    assert by_key["W"] == {
        "evidence": "P-link",
        "key": "W",
        "body": "link_step",
        "probe": "bbox",
        "recorded": 5.0004,
        "value": pytest.approx(5),
        "tol": 0.001,
        "ok": True,
    }
    assert sorted(by_key) == ["H", "L", "W"]


_PITCH_PROBE = {"probe": "distance", "between": ["link_step.a", "link_step.b"], "axes": None}
_SQUARE_PROBE = {"probe": "angle", "between": ["link_step.b", "link_step.a", "link_step.c"]}


@pytest.mark.parametrize(
    "entry, recorded, mismatched",
    [
        (_PITCH_PROBE, 30, False),
        (_PITCH_PROBE, 30.01, True),
        (_PITCH_PROBE | {"along": "y"}, 30, False),
        (_PITCH_PROBE | {"along": "x"}, 30, True),
        (_SQUARE_PROBE | {"axes": None}, 90, False),
        (_SQUARE_PROBE | {"axes": None}, 90.1, True),
    ],
    ids=["distance", "distance off", "along", "along another axis", "angle", "angle off"],
)
def test_distance_and_angle_probes_compare_the_datums_declared_on_the_body(
    proj_dir, tmp_path, entry, recorded, mismatched
):
    probed(proj_dir, tmp_path, **entry, values={"v": recorded})
    _, report = verify(proj_dir)
    assert bool(_mismatches(report)) == mismatched
    assert "evidence-anchor" not in [f["rule"] for f in report["findings"]]


@pytest.mark.parametrize(
    "entry, why",
    [
        ({"source": "paper"}, "a probe reads a geometry source, and paper is not one"),
        ({"body": "link_step#2"}, "link_step#2 is not a body of link_step"),
        ({"probe": "volume"}, "probe must be bbox, distance, angle, not 'volume'"),
        ({"axes": {"L": "y", "W": "x"}}, "H names no axis x, y or z in axes"),
        (
            _PITCH_PROBE | {"between": ["link_step.a", "link_step.d"], "values": {"v": 30}},
            "link_step.d is not a datum",
        ),
    ],
    ids=["paper", "body", "kind", "axis", "datum"],
)
def test_probe_that_cannot_be_evaluated_is_evidence_anchor(proj_dir, tmp_path, entry, why):
    probed(proj_dir, tmp_path, **entry)
    anchors = [
        f["message"] for f in verify(proj_dir)[1]["findings"] if f["rule"] == "evidence-anchor"
    ]
    assert len(anchors) == 1 and why in anchors[0]


@pytest.mark.parametrize("tol, capped", [(0.3, True), (0.25, False)])
def test_probe_tol_above_five_percent_of_its_value_is_tolerance_cap(
    proj_dir, tmp_path, tol, capped
):
    probed(proj_dir, tmp_path, tol=tol)
    found = [f["message"] for f in verify(proj_dir)[1]["findings"] if f["rule"] == "tolerance-cap"]
    assert found == (["probe P-link: tol 0.3 is above 5% of P-link.W, 5"] if capped else [])


def _coverage(report: dict) -> list[str]:
    return [f["message"] for f in report["findings"] if f["rule"] == "coverage"]


def test_released_body_neither_shape_checked_nor_skipped_is_coverage(proj_dir, tmp_path):
    released(proj_dir, tmp_path, check=False)
    assert _coverage(verify(proj_dir)[1]) == [
        "link_step body link_step: no shape check compares it and no skip sets it aside"
    ]


def test_released_body_skipped_with_a_reason_is_covered_and_its_file_is_not_swept(
    proj_dir, tmp_path
):
    released(proj_dir, tmp_path, check=False)
    skip = {"source": "link_step", "body": "link_step", "reason": "a fit tester, not the link"}
    edit(proj_dir, "evidence.yaml", lambda d: d["skipped"].append(skip))
    code, report = verify(proj_dir)
    assert _coverage(report) == [] and (code, report["status"]) == (0, "VERIFIED")


@pytest.mark.parametrize(
    "skip, rule",
    [
        ({"body": "link_step"}, "skip-reason"),
        ({"reason": "a fit tester"}, "skip-anchor"),
        ({"body": "link_step#2", "reason": "a fit tester"}, "skip-not-found"),
    ],
    ids=["no reason", "no body", "unknown body"],
)
def test_skip_of_a_released_body_needs_a_reason_and_a_body_of_its_source(
    proj_dir, tmp_path, skip, rule
):
    released(proj_dir, tmp_path)
    edit(proj_dir, "evidence.yaml", lambda d: d["skipped"].append({"source": "link_step"} | skip))
    assert rule in errors(proj_dir)


def test_passing_shape_check_rests_on_source_and_checks_none_of_its_parts_params(
    proj_dir, tmp_path
):
    released(proj_dir, tmp_path)
    # The envelope and pitch checks go, leaving the shape check the only one on the link.
    edit(proj_dir, "checks.yaml", lambda d: d.update(checks=d["checks"][2:]))
    edit(
        proj_dir,
        "evidence.yaml",
        lambda d: [e.update(scope="context", reason="r") for e in d["evidence"]],
    )
    _, report = verify(proj_dir)
    result = _shape_result(report)
    assert result["ok"] and (result["rests_on"], result["rests_on_params"]) == ("source", [])
    unchecked = [
        f["message"].split(":")[0] for f in report["findings"] if f["rule"] == "unchecked-source"
    ]
    assert unchecked == ["param link_L", "param link_H", "param link_W", "param pitch"]


# A 0.05 mm chamfer on the released link's outer edges lies about 0.035 from the built link's
# corners: inside a tol of 0.1, outside tolerance.length.
@pytest.mark.parametrize("tol, ok", [(0.1, True), (None, False)])
def test_shape_check_passes_on_a_surface_distance_within_its_tol(proj_dir, tmp_path, tol, ok):
    chamfered = chamfer(link_body().edges().filter_by(Axis.Z), 0.05)
    released(proj_dir, tmp_path, body=chamfered, **({"tol": tol} if tol else {}))
    result = _shape_result(verify(proj_dir)[1])
    assert result["ok"] == ok and 0.02 < result["shape"]["distance"] < 0.05


def test_file_of_several_bodies_names_each_by_its_place_in_the_file(proj_dir, tmp_path):
    # The link, then a 4 mm cube beside it: link_step#1 and link_step#2.
    both = Compound(children=[link_body(), Pos(0, 20, 0) * Box(4, 4, 4)])
    released(proj_dir, tmp_path, body=both, at=Location(), check=False)
    first = {f"link_step#1.{k}": list(v) for k, v in LINK_DATUMS.items()}
    edit(proj_dir, "evidence.yaml", lambda d: d.update(datums=first))
    pairs = [[f"link.{k}", f"link_step#1.{k}"] for k in LINK_DATUMS]
    shape = {"id": "shape", "kind": "shape", "part": "link", "body": "link_step#1"}
    edit(proj_dir, "checks.yaml", lambda d: d["checks"].append(shape | {"pairs": pairs}))
    cube = PROBE | {"body": "link_step#2", "axes": {"s": "x"}, "values": {"s": 4}}
    skip = {"source": "link_step", "body": "link_step#2", "reason": "a spacer, not the link"}
    edit(
        proj_dir, "evidence.yaml", lambda d: (d["evidence"].append(cube), d["skipped"].append(skip))
    )
    code, report = verify(proj_dir)
    assert [(q["body"], q["ok"]) for q in report["probes"]] == [("link_step#2", True)]
    assert _shape_result(report)["ok"] and (code, report["status"]) == (0, "VERIFIED")


def test_probe_recording_no_values_is_evidence_values_whatever_its_scope(proj_dir, tmp_path):
    probed(proj_dir, tmp_path, values=None)
    assert "evidence-values" in errors(proj_dir)


# A check compares with a value worked out from the ledger: expect (ADR-0014).

GEAR_QUOTE = "a module of 1.5 mm and 20 teeth"
PITCH_CHECK = {"kind": "distance", "between": ["link.a", "link.b"]}


def expecting(root: Path, tmp_path: Path, expr: str, quote: str = GEAR_QUOTE, **check) -> None:
    """Ledger quote as N1, its module m and teeth z, and add check pitch-expect, a distance
    check of the link's pitch against expr."""
    values = {"m": 1.5, "z": int(re.findall(r"(\d+) teeth", quote)[0])}
    add_quote(root, tmp_path, f"The gear has {quote}.", quote, values)
    pitch = {"id": "pitch-expect", **PITCH_CHECK, "expect": expr, **check}
    edit(root, "checks.yaml", lambda d: d["checks"].append(pitch))


def _result(report: dict, cid: str) -> dict:
    return next(r for r in report["checks"] if r["id"] == cid)


def _config(root: Path, cid: str) -> list[str]:
    """The [check-config] messages a fresh verification run gives check cid."""
    return [m for m in findings(root, "check-config") if m.startswith(f"check {cid}:")]


@pytest.mark.parametrize(
    "quote, ok", [(GEAR_QUOTE, True), ("a module of 1.5 mm and 21 teeth", False)]
)
def test_expect_multiplying_two_ledger_values_passes_only_on_geometry_matching_the_product(
    proj_dir, tmp_path, quote, ok
):
    # The link's pivots are 30 mm apart: 1.5 × 20, not 1.5 × 21.
    expecting(proj_dir, tmp_path, "N1.m * N1.z", quote)
    code, report = verify(proj_dir)
    assert _result(report, "pitch-expect")["ok"] == ok
    assert (code, report["status"]) == ((0, "VERIFIED") if ok else (1, "NOT VERIFIED"))
    failed = [f["message"] for f in report["findings"] if f["rule"] == "check-failed"]
    measured = "measured 30 link.a - link.b"
    assert failed == ([] if ok else [f"pitch-expect: expected 31.5 (N1.m * N1.z), {measured}"])


def test_report_json_shows_each_checks_expect_expression_and_its_value(proj_dir, tmp_path):
    expecting(proj_dir, tmp_path, "N1.m * N1.z")
    _, report = verify(proj_dir)
    assert _result(report, "pitch-expect")["expect"] == {"expr": "N1.m * N1.z", "value": 30}
    assert "expect" not in _result(report, "pitch")


def test_entry_an_expect_names_counts_as_compared_so_its_source_param_is_checked(proj_dir):
    edit(proj_dir, "checks.yaml", lambda d: d["checks"].pop(1))  # the pitch check
    assert "param pitch" in _unchecked(proj_dir)
    pitch = {"id": "pitch-2", **PITCH_CHECK, "expect": "pitch.pitch"}
    edit(proj_dir, "checks.yaml", lambda d: d["checks"].append(pitch))
    code, report = verify(proj_dir)
    assert _unchecked_in(report) == [] and (code, report["status"]) == (0, "VERIFIED")
    assert _result(report, "pitch-2")["rests_on"] == "source"


@pytest.mark.parametrize(
    "expr, reason",
    [
        ("hole_d * 10", "names param hole_d"),
        ("N9.m * N1.z", "N9 is not a ledger entry"),
        ("N1.d * N1.z", "N1 records no d"),
        ("N1.m * * N1.z", "does not parse"),
        ("N1.m.x", "does not parse"),
        ("N1.m * N1.z / 0", "does not evaluate"),
        ("sqrt(N1.m - N1.z)", "does not evaluate"),
        ("open(N1.m)", "names open"),
    ],
)
def test_expect_that_cannot_be_evaluated_is_check_config_naming_why(
    proj_dir, tmp_path, expr, reason
):
    expecting(proj_dir, tmp_path, expr)
    messages = _config(proj_dir, "pitch-expect")
    assert len(messages) == 1 and reason in messages[0], messages


def test_expect_naming_a_ledger_entry_that_shares_a_params_name_reads_the_entry(proj_dir, tmp_path):
    # pitch is both a param and an evidence id; pitch.pitch is the ledger value.
    expecting(proj_dir, tmp_path, "pitch.pitch * N1.m * N1.z / (N1.m * N1.z)")
    _, report = verify(proj_dir)
    assert _result(report, "pitch-expect")["ok"] and report["status"] == "VERIFIED"


def test_run_without_the_build_reports_an_expect_naming_an_unknown_entry(proj_dir, tmp_path):
    expecting(proj_dir, tmp_path, "N9.m * N1.z")
    _, printed = run("check", str(proj_dir), "--no-build")
    assert "[check-config] check pitch-expect: expect 'N9.m * N1.z': N9 is not a ledger entry" in (
        printed
    )


@pytest.mark.parametrize("check", [{"evidence": "pitch", "key": "pitch"}, {"evidence": "pitch"}])
def test_check_naming_both_expect_and_evidence_is_check_config(proj_dir, tmp_path, check):
    expecting(proj_dir, tmp_path, "N1.m * N1.z", **check)
    messages = _config(proj_dir, "pitch-expect")
    assert len(messages) == 1 and "give expect or evidence, not both" in messages[0], messages


def test_check_naming_neither_expect_nor_evidence_is_check_config(proj_dir):
    edit(proj_dir, "checks.yaml", lambda d: [d["checks"][1].pop(k) for k in ("evidence", "key")])
    messages = _config(proj_dir, "pitch")
    assert len(messages) == 1 and "give evidence and key, or expect" in messages[0], messages


@pytest.mark.parametrize("kind", ["bbox", "range", "shape", "interference"])
def test_expect_on_a_kind_that_compares_no_one_value_is_check_config(proj_dir, kind):
    check = {"id": "other", "kind": kind, "expect": "pitch.pitch"}
    edit(proj_dir, "checks.yaml", lambda d: d["checks"].append(check))
    assert any(f"kind {kind} takes none" in m for m in _config(proj_dir, "other"))


def test_guard_ratio_printed_n_to_1_ledgers_as_a_fraction(proj_dir, tmp_path):
    # "7.2:1" is ledgered as {ratio: 7.2}, with no unit, and the sweep lists nothing in it.
    text = "The gearbox reduces 7.2:1 overall."
    add_quote(proj_dir, tmp_path, text, "reduces 7.2:1", {"ratio": 7.2})
    add_params(proj_dir, ratio={"basis": "source", "from": "N1.ratio"})
    _, report = verify(proj_dir)
    assert report["params"]["ratio"]["value"] == 7.2
    rules = {f["rule"] for f in report["findings"] if f["level"] == "error"}
    assert not rules & {"value-not-in-quote", "unit-quantity", "coverage"}, rules


def test_expect_reads_a_ratio_printed_n_to_1_as_a_fraction(proj_dir, tmp_path):
    # 30 = 7.2 × 25 / 6, so the check passes only where "7.2:1" reads as 7.2.
    text = "The gearbox reduces 7.2:1 overall."
    add_quote(proj_dir, tmp_path, text, "reduces 7.2:1", {"ratio": 7.2})
    pitch = {"id": "pitch-ratio", **PITCH_CHECK, "expect": "N1.ratio * 25 / 6"}
    edit(proj_dir, "checks.yaml", lambda d: d["checks"].append(pitch))
    code, report = verify(proj_dir)
    assert _result(report, "pitch-ratio")["ok"] and (code, report["status"]) == (0, "VERIFIED")
