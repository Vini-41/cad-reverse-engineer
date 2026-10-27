"""scripts/check-kind-branches, run as CI runs it, on a small repo laid out like this one."""

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "check-kind-branches"
SRC = "skills/cad-reverse-engineer/tool/src/cadrev"
PROJECT = """
CHECK_KINDS = {"bbox": CheckKind("length", "length"), "mass": CheckKind("mass", None)}
OVERLAP_KINDS = ("interference",)
PROBE_KINDS = {"bbox": _probe_bbox, "angle": _probe_angle}
SOURCE_KINDS = ("paper", "geometry")
"""
GEOMETRY = """
def run_checks(p, c):
    kind = c.get("kind")
    if kind == "bbox":
        return 1
    elif kind in ("mass", "interference"):
        return 2
"""


def repo(tmp_path: Path, files: dict[str, str]) -> Path:
    for name, text in {"project.py": PROJECT, "geometry.py": GEOMETRY, **files}.items():
        (tmp_path / SRC / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / SRC / name).write_text(text)
    return tmp_path


def check(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), str(root)], capture_output=True, text=True)


def test_branches_on_a_check_or_probe_kind_outside_run_checks_are_named(tmp_path):
    root = repo(
        tmp_path,
        {
            "report.py": (
                "def f(c, e, r, kind):\n"
                '    if c.get("kind") == "interference":\n'
                "        pass\n"
                '    n = 2 if e["probe"] != "angle" else 3\n'
                '    if r.kind in {"mass", "other"}:\n'
                "        pass\n"
                '    if "bbox" == kind:\n'
                "        pass\n"
                "    match kind:\n"
                '        case "mass":\n'
                "            pass\n"
            ),
        },
    )
    result = check(root)
    assert result.returncode == 1
    assert result.stdout.splitlines() == [
        f'{SRC}/report.py:2: branches on kind "interference" outside run_checks',
        f'{SRC}/report.py:4: branches on kind "angle" outside run_checks',
        f'{SRC}/report.py:5: branches on kind "mass" outside run_checks',
        f'{SRC}/report.py:7: branches on kind "bbox" outside run_checks',
        f'{SRC}/report.py:10: branches on kind "mass" outside run_checks',
    ]


def test_guard_run_checks_tables_and_other_kinds_of_thing_pass(tmp_path):
    root = repo(
        tmp_path,
        {
            "report.py": (
                "def f(c, s, j, axis):\n"
                '    if c.get("kind") in CHECK_KINDS or c.get("kind") in OVERLAP_KINDS:\n'
                "        pass\n"
                '    if s.get("kind") == "geometry" or j.kind == "gear":\n'
                "        pass\n"
                '    if axis == "angle" or c.get("unit") == "mass":\n'
                "        pass\n"
                '    reader = PROBE_KINDS[c["probe"]]\n'
            ),
        },
    )
    result = check(root)
    assert (result.returncode, result.stdout) == (0, "")


def test_a_kind_table_missing_from_project_py_is_named_rather_than_checking_nothing(tmp_path):
    root = repo(tmp_path, {"project.py": "SOURCE_KINDS = ('paper',)\n"})
    result = check(root)
    assert result.returncode == 1
    assert "CHECK_KINDS" in result.stdout
