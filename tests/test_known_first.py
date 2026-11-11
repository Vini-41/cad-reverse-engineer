"""Known first: a project that builds only the parts the sources settle, and lists what waits."""

import contextlib
import io
import json
from pathlib import Path

import pytest
import yaml

from cadrev import cli

# The link's every dimension is stated; the pin's length is, but not its diameter, so it waits.
PAPER = """\
Table 1. Dimensions of key components
Name L×H×W (mm×mm×mm)
Link 40×8×5
The pivot holes of the link are spaced 30 mm apart and bored 3 mm in diameter.
Each pin is 12 mm long.
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
        "datums": {
            "link.a": (-p.pitch / 2, 0, 0),
            "link.b": (p.pitch / 2, 0, 0),
            "link.bore": (p.pitch / 2 + p.hole_d / 2, 0, 0),
        },
        "assembly": {"link_1": ("link", Location())},
    }
"""

PIN_WAITS = {"evidence": "pin", "key": "L", "value": 12, "source": "paper", "locator": "Sec. 3"}
PIN_GAP = {"gap": "G-pin", "question": "What diameter are the pins?", "ask": "authors"}


def write(root: Path, name: str, data) -> None:
    (root / name).write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
        if not isinstance(data, str)
        else data
    )


def edit(root: Path, name: str, change) -> None:
    data = yaml.safe_load((root / name).read_text())
    change(data)
    write(root, name, data)


def swap(text: str, old: str, new: str) -> str:
    """text with old replaced by new, failing when old is absent."""
    assert old in text, f"{old!r} is not in the text it should replace"
    return text.replace(old, new)


def run(*args: str) -> tuple[int, str]:
    """Run a cadrev command through the CLI; return its exit code and what it prints."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = cli.main(list(args))
    return code, out.getvalue()


def verify(root: Path) -> tuple[int, dict]:
    """Run a verification run through the CLI; return its exit code and report.json."""
    code, _ = run("check", str(root))
    return code, json.loads((root / "build" / "report.json").read_text())


def rules(report: dict, level: str = "error") -> list[str]:
    return [f["rule"] for f in report["findings"] if f["level"] == level]


@pytest.fixture
def project(tmp_path):
    """A known-first project: the link built and checked, the pin's length waiting on G-pin."""
    root = tmp_path / "demo"
    assert cli.main(["init", str(root)]) == 0
    meta = root / "project.yaml"
    meta.write_text(
        swap(
            meta.read_text(),
            "target: TODO one sentence naming the object, version and configuration being "
            "reconstructed",
            "target: A demo link with its pins\nknown_first: true",
        )
    )
    paper = tmp_path / "paper.txt"
    paper.write_text(PAPER)
    register = ["source", str(root), str(paper), "--id", "paper", "--kind", "paper"]
    assert cli.main([*register, "--citation", "Doe 2026"]) == 0
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
                    "id": "holes",
                    "source": "paper",
                    "locator": "Sec. 2",
                    "quote": "spaced 30 mm apart and bored 3 mm in diameter",
                    "values": {"pitch": 30, "d": 3},
                },
                {
                    "id": "pin",
                    "source": "paper",
                    "locator": "Sec. 3",
                    "quote": "Each pin is 12 mm long",
                    "values": {"L": 12},
                },
            ],
            "skipped": [
                {"source": "paper", "quote": "branches of 60 mm diameter", "reason": "test object"}
            ],
            "conflicts": [],
        },
    )
    write(
        root,
        "params.yaml",
        {
            "params": {
                "link_L": {"basis": "source", "from": "T1-link.L"},
                "link_H": {"basis": "source", "from": "T1-link.H"},
                "link_W": {"basis": "source", "from": "T1-link.W"},
                "pitch": {"basis": "source", "from": "holes.pitch"},
                "hole_d": {"basis": "source", "from": "holes.d"},
            }
        },
    )
    write(
        root,
        "gaps.yaml",
        {"gaps": [{"id": "G-pin", "question": PIN_GAP["question"], "ask": "authors"}]},
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
                    "evidence": "holes",
                    "key": "pitch",
                },
                {
                    "id": "bore",
                    "kind": "diameter",
                    "at": "link.bore",
                    "evidence": "holes",
                    "key": "d",
                },
            ]
        },
    )
    write(root, "model.py", MODEL)
    return root


def test_known_first_project_verifies_exact_and_lists_the_values_that_wait(project):
    code, report = verify(project)
    assert (code, report["status"], report["exact"]) == (0, "VERIFIED", True)
    assert report["known_first"] is True
    assert report["waiting"] == {"values": [PIN_WAITS], "gaps": [PIN_GAP]}
    assert report["findings"] == []


def test_without_known_first_the_same_project_raises_evidence_unused_as_today(project):
    edit(project, "project.yaml", lambda d: d.pop("known_first"))
    code, report = verify(project)
    assert (code, report["status"], report["known_first"], report["waiting"]) == (
        1,
        "NOT VERIFIED",
        False,
        None,
    )
    assert [(f["level"], f["rule"], f["message"]) for f in report["findings"]] == [
        (
            "error",
            "evidence-unused",
            "pin.L is neither used by a param nor checked "
            "(or mark the item scope: not-modeled with a reason)",
        ),
        ("warning", "gap-unused", "gap G-pin: no param names it"),
    ]


def _pitch_worked_out(root: Path) -> None:
    """Work the pitch out from the link's length and check it no more, so the stated pitch waits
    beside the pin's length."""
    pitch = {"basis": "derived", "expr": "link_L * 3 / 4"}
    edit(root, "params.yaml", lambda d: d["params"].update(pitch=pitch))
    edit(root, "checks.yaml", lambda d: d["checks"].pop(1))


def _pin_not_modeled(root: Path) -> None:
    pin = {"scope": "not-modeled", "reason": "pins are hardware"}
    edit(root, "evidence.yaml", lambda d: d["evidence"][2].update(pin))


@pytest.mark.parametrize(
    "change, says",
    [
        (None, "5/5 checks pass. Known first: 1 stated value waits."),
        (_pitch_worked_out, "4/4 checks pass. Known first: 2 stated values wait."),
        (_pin_not_modeled, "5/5 checks pass. Known first: 0 stated values wait."),
    ],
    ids=["one", "two", "none"],
)
def test_status_line_says_how_many_stated_values_wait_before_the_report(project, change, says):
    if change is not None:
        change(project)
    code, out = run("check", str(project))
    assert code == 0
    assert out.splitlines()[-1] == f"VERIFIED: 0 errors, 0 warnings, {says} Report: build/report.md"


def _known_first_says(name: str) -> str:
    return (
        f"param {name} rests on proposed, and a known-first project holds only what the sources "
        "settle: leave out what needs it, so its stated values wait, and ask for it in gaps.yaml"
    )


BORE_GAP = {"id": "G-bore", "question": "What diameter are the pivot holes?", "ask": "authors"}
PROPOSED_BORES = {
    "proposed": {
        "hole_d": {"basis": "proposed", "value": 3, "rationale": "M3 pin", "gap": "G-bore"}
    },
    "derived naming a gap": {
        "hole_d": {
            "basis": "derived",
            "expr": "pitch / 10",
            "gap": "G-bore",
            "interpretation": "a tenth of the pitch",
        }
    },
    "derived from proposed": {
        "play": {"basis": "proposed", "value": 0, "rationale": "a press fit", "gap": "G-bore"},
        "hole_d": {"basis": "derived", "expr": "pitch / 10 + play"},
    },
}


def _propose_bore(root: Path, params: dict) -> None:
    edit(root, "params.yaml", lambda d: d["params"].update(params))
    edit(root, "gaps.yaml", lambda d: d["gaps"].append(BORE_GAP))


@pytest.mark.parametrize("bore", PROPOSED_BORES)
def test_param_resting_on_proposed_in_a_known_first_project_is_known_first_naming_it(project, bore):
    _propose_bore(project, PROPOSED_BORES[bore])
    code, report = verify(project)
    assert (code, report["status"]) == (1, "NOT VERIFIED")
    assert sorted(f["message"] for f in report["findings"] if f["rule"] == "known-first") == [
        _known_first_says(name) for name in sorted(PROPOSED_BORES[bore])
    ]
    assert rules(report) == ["known-first"] * len(PROPOSED_BORES[bore])


@pytest.mark.parametrize("bore", PROPOSED_BORES)
def test_without_known_first_a_param_resting_on_proposed_raises_no_known_first(project, bore):
    _propose_bore(project, PROPOSED_BORES[bore])
    _pin_not_modeled(project)
    edit(project, "project.yaml", lambda d: d.pop("known_first"))
    code, report = verify(project)
    assert (code, report["status"], report["exact"]) == (0, "VERIFIED", False)
    assert "known-first" not in rules(report) + rules(report, "warning")


def test_known_first_is_raised_by_a_run_without_the_build(project):
    _propose_bore(project, PROPOSED_BORES["proposed"])
    code, out = run("check", str(project), "--no-build")
    assert code == 1
    assert f"error: [known-first] {_known_first_says('hole_d')}" in out.splitlines()


def _measured_width(root: Path) -> None:
    """Scale the link's width off a confirmed Fig. 2 crop instead of reading it, naming the gap
    G-width whose answer would replace the measurement."""
    from PIL import Image

    (root / "figures").mkdir(exist_ok=True)
    Image.new("RGB", (40, 20), "white").save(root / "figures" / "page2.png")
    code, out = run("crop", str(root), "figures/page2.png", "0", "0", "20", "10", "--name", "fig2")
    assert code == 0
    crop = {
        "id": "F2",
        "source": "paper",
        "locator": "Fig. 2",
        "image": "figures/crops/fig2.png",
        "image_sha256": out.split("image_sha256: ")[1].strip(),
        "reading": "no printed labels; scaled on the link's length",
        "confirmed_by": "A. Reviewer",
    }
    edit(root, "evidence.yaml", lambda d: d["evidence"].append(crop))
    width = {
        "basis": "measured",
        "from": "F2",
        "value": 5,
        "method": "link length as scale, 10 px/mm",
        "uncertainty": "±0.3 mm",
        "gap": "G-width",
    }
    edit(root, "params.yaml", lambda d: d["params"].update(link_W=width))
    gap = {"id": "G-width", "question": "How wide is the link?", "ask": "authors"}
    edit(root, "gaps.yaml", lambda d: d["gaps"].append(gap))


def test_known_first_project_may_measure_a_value_and_stays_exact(project):
    _measured_width(project)
    code, report = verify(project)
    assert (code, report["status"], report["exact"]) == (0, "VERIFIED", True)
    assert report["counts"]["measured"] == 1
    assert report["waiting"] == {"values": [PIN_WAITS], "gaps": [PIN_GAP]}


def _section(md: str, heading: str) -> str:
    return md.split(f"\n## {heading}\n")[1].split("\n## ")[0]


def test_report_md_says_known_first_and_lists_what_waits_apart_from_the_open_gaps(project):
    _measured_width(project)
    verify(project)
    md = (project / "build" / "report.md").read_text()
    head = md.split("\n## ")[0]
    assert (
        "**Known first**: 1 stated value waits, with 1 gap no param names, listed under Waiting."
    ) in head.splitlines()
    waiting = _section(md, "Waiting")
    assert "| pin.L | 12 | paper | Sec. 3 |" in waiting.splitlines()
    assert "| G-pin | What diameter are the pins? | authors |" in waiting.splitlines()
    gaps = _section(md, "Open gaps")
    assert "| G-width | How wide is the link? | authors | link_W |" in gaps.splitlines()
    assert "G-pin" not in gaps


def test_guard_report_md_of_a_project_not_known_first_has_no_waiting_section(project):
    edit(project, "project.yaml", lambda d: d.pop("known_first"))
    verify(project)
    md = (project / "build" / "report.md").read_text()
    assert "Known first" not in md
    assert "\n## Waiting\n" not in md
    assert "| G-pin | What diameter are the pins? | authors |  |" in _section(md, "Open gaps")


def test_known_first_project_with_nothing_settled_still_reports_what_waits(project):
    """No part has its every dimension stated: model.py builds nothing, and the ledger waits."""
    write(project, "params.yaml", {"params": {}})
    write(project, "checks.yaml", {"checks": []})
    write(
        project,
        "model.py",
        'def build(p):\n    return {"parts": {}, "datums": {}, "assembly": {}}\n',
    )
    code, out = run("check", str(project))
    assert out.splitlines()[-1] == (
        "VERIFIED: 0 errors, 0 warnings, 0/0 checks pass. Known first: 6 stated values wait. "
        "Report: build/report.md"
    )
    report = json.loads((project / "build" / "report.json").read_text())
    assert [f"{v['evidence']}.{v['key']}" for v in report["waiting"]["values"]] == [
        "T1-link.L",
        "T1-link.H",
        "T1-link.W",
        "holes.pitch",
        "holes.d",
        "pin.L",
    ]
    md = (project / "build" / "report.md").read_text()
    assert "| holes.d | 3 | paper | Sec. 2 |" in _section(md, "Waiting").splitlines()
    assert "| T1-link | paper | Table 1 | L=40, H=8, W=5 |" in _section(md, "Evidence")


# Two links, the second hinged on the first's pivot b and stacked on it; pin_part adds a pin the
# sources settle the shape of but place nowhere.
JOINTED = """\
from build123d import *


def build(p):
    link = Box(p.link_L, p.link_W, p.link_H)
    link -= Pos(-p.pitch / 2, 0, 0) * Cylinder(p.hole_d / 2, p.link_H)
    link -= Pos(p.pitch / 2, 0, 0) * Cylinder(p.hole_d / 2, p.link_H)
    parts = {"link": link}
    datums = {
        "link.a": (-p.pitch / 2, 0, 0),
        "link.a_top": (-p.pitch / 2, 0, p.link_H / 2),
        "link.b": (p.pitch / 2, 0, 0),
        "link.bore": (p.pitch / 2 + p.hole_d / 2, 0, 0),
    }
    return {
        "parts": parts,
        "datums": datums,
        "assembly": {
            "link_1": ("link", Location()),
            "link_2": ("link", Location((p.pitch, 0, p.link_H))),
        },
        "joints": {
            "swing": {
                "type": "revolute",
                "parent": "link_1",
                "child": "link_2",
                "axis": ["link_2.a", "link_2.a_top"],
                "range": ["swing"],
                "drive": "actuated",
                "damping": "swing_c",
            }
        },
    }
"""

MOTION = """\
The second link swings through 40 degrees on the first.
The links are printed in resin of 1.2 g/cm³.
"""


def _jointed(root: Path, tmp_path: Path) -> None:
    """Hinge a second link on the first through a stated swing, weigh both by the stated resin,
    damp the hinge by a proposed physics value and sweep interference across the swing at a
    proposed resolution."""
    text = tmp_path / "motion.txt"
    text.write_text(MOTION)
    register = ["source", str(root), str(text), "--id", "motion", "--kind", "paper"]
    assert cli.main([*register, "--citation", "Doe 2026b"]) == 0
    stated = [
        {
            "id": "swing",
            "source": "motion",
            "locator": "Sec. 4",
            "quote": "swings through 40 degrees",
            "values": {"turn": 40},
        },
        {
            "id": "resin",
            "source": "motion",
            "locator": "Sec. 5",
            "quote": "resin of 1.2 g/cm³",
            "values": {"rho": 1.2},
        },
    ]
    edit(root, "evidence.yaml", lambda d: d["evidence"].extend(stated))

    def params(d):
        d["params"] |= {
            "swing": {"basis": "source", "from": "swing.turn"},
            "density": {"basis": "source", "from": "resin.rho"},
            "swing_c": {
                "basis": "proposed",
                "value": 50,
                "rationale": "light damping",
                "gap": "G-damping",
                "physics": True,
            },
            "sweep_steps": {"basis": "proposed", "value": 3, "rationale": "ends and middle"},
        }
        d["parts"] = {"link": {"density": "density"}}

    edit(root, "params.yaml", params)
    gap = {"id": "G-damping", "question": "How damped is the hinge?", "ask": "test"}
    edit(root, "gaps.yaml", lambda d: d["gaps"].append(gap))
    checks = [
        {"id": "reach", "kind": "range", "joint": "swing", "ends": ["swing.turn"]},
        {
            "id": "clear",
            "kind": "interference",
            "pairs": [["link_1", "link_2"]],
            "sweep": {"joint": "swing", "steps": "sweep_steps"},
        },
    ]
    edit(root, "checks.yaml", lambda d: d["checks"].extend(checks))
    write(root, "model.py", JOINTED)


def test_known_first_sets_proposed_physics_values_and_sweep_steps_aside_as_exact_does(
    project, tmp_path
):
    _jointed(project, tmp_path)
    code, out = run("check", str(project), "--no-build")
    assert "[known-first]" not in out
    code, report = verify(project)
    assert (code, report["status"], report["exact"]) == (0, "VERIFIED", True)
    assert report["rests_on_proposed"] == ["sweep_steps", "swing_c"]
    assert report["counts"]["physics_proposed"] == 1
    assert report["motion"]["joints"]["swing"]["damping"] == {"from": "swing_c", "value": 50}


def _unplaced_pin(root: Path, tmp_path: Path) -> None:
    """Build the pin, its length stated and its diameter the bore's, in its own frame: the sources
    say what it is but not where along its hole it sits, so no instance places it."""
    _jointed(root, tmp_path)
    pin = '    parts = {"link": link, "pin": Cylinder(p.hole_d / 2, p.pin_L)}\n'
    write(root, "model.py", swap(JOINTED, '    parts = {"link": link}\n', pin))
    edit(
        root,
        "params.yaml",
        lambda d: d["params"].update(pin_L={"basis": "source", "from": "pin.L"}),
    )
    check = {
        "id": "pin-length",
        "kind": "bbox",
        "part": "pin",
        "evidence": "pin",
        "axes": {"L": "z"},
    }
    edit(root, "checks.yaml", lambda d: d["checks"].append(check))
    placed = {"question": "Where along its hole does each pin sit?", "ask": "authors"}
    edit(root, "gaps.yaml", lambda d: d["gaps"][0].update(placed))


@pytest.mark.parametrize("known_first", [True, False])
def test_part_no_instance_places_is_exported_in_its_own_frame_and_needs_no_mass(
    project, tmp_path, known_first
):
    _unplaced_pin(project, tmp_path)
    if not known_first:
        edit(project, "project.yaml", lambda d: d.pop("known_first"))
    code, report = verify(project)
    assert "part-mass" not in rules(report)
    assert (project / "build" / "parts" / "pin.step").is_file()
    assert "pin" not in report["masses"]
    assert next(r for r in report["checks"] if r["id"] == "pin-length.L")["ok"]
    if known_first:
        assert (code, report["status"], report["exact"]) == (0, "VERIFIED", True)
        assert report["waiting"] == {
            "values": [],
            "gaps": [PIN_GAP | {"question": "Where along its hole does each pin sit?"}],
        }
    else:
        assert "gap-unused" in rules(report, "warning")
