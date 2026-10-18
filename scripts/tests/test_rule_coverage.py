"""scripts/rule-coverage, run as CI runs it, on a small repo laid out like this one."""

import shutil
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "rule-coverage"
CADREV = SCRIPT.parents[1] / "skills/cad-reverse-engineer/tool/src/cadrev"

SOURCE = """\
def check(p):
    p.error("too-long", "the link is too long")
    p.warn("open-end", "the end is open")
"""
DOC = "A long link is `[too-long]`; an open end is `[open-end]`.\n"
TESTS = """\
from cadrev import cli
import pytest

UNITS = {"a 4 mm pin": (4, 4)}


def errors(root):
    return []


def _too_long(root):
    messages = errors(root)
    return [m for m in messages if m == "too-long"]


def test_long_link(tmp_path):
    assert "too-long" in errors(tmp_path)


def test_guard_short_link(tmp_path):
    assert _too_long(tmp_path) == []


@pytest.mark.parametrize("rule", ["open-end"])
def test_open_end(tmp_path, capsys, rule):
    assert cli.main(["check", str(tmp_path)]) == 1
    assert f"warning: [{rule}]" in capsys.readouterr().out


def test_guard_closed_end(tmp_path):
    assert "open-end" not in errors(tmp_path)
"""


def repo(tmp_path: Path, source=SOURCE, doc=DOC, tests=TESTS, unit_names=("mm",)) -> Path:
    """A repo whose tool emits source's rules, documents doc and is tested by tests, with a unit
    table of the real cadrev's units named in unit_names."""
    src = tmp_path / "skills/cad-reverse-engineer/tool/src/cadrev"
    src.mkdir(parents=True)
    for name in ("__init__.py", "sources.py", "units.py"):
        shutil.copy(CADREV / name, src / name)
    units = (src / "units.py").read_text()
    table = units.index("UNITS: dict[str, Unit] = {")
    end = units.index("\n}\n", table)
    kept = [
        line
        for line in units[table:end].splitlines()[1:]
        if line.strip().split(":")[0].strip('"') in unit_names
    ]
    head = "UNITS: dict[str, Unit] = {\n"
    (src / "units.py").write_text(units[:table] + head + "\n".join(kept) + units[end:])
    (src / "check.py").write_text(source)
    refs = tmp_path / "skills/cad-reverse-engineer/references"
    refs.mkdir(parents=True)
    (refs / "rules.md").write_text(doc)
    tool_tests = tmp_path / "skills/cad-reverse-engineer/tool/tests"
    tool_tests.mkdir(parents=True)
    (tool_tests / "test_cadrev.py").write_text(tests)
    return tmp_path


def check(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), str(root)], capture_output=True, text=True)


def test_guard_rules_asserted_present_and_absent_documented_and_read_pass(tmp_path):
    result = check(repo(tmp_path))
    assert (result.returncode, result.stdout.splitlines()[1:]) == (0, [])


def test_rule_no_test_asserts_absent_fails(tmp_path):
    result = check(repo(tmp_path, tests=TESTS.split("\n\n\ndef test_guard_closed_end")[0]))
    assert result.returncode == 1
    assert result.stdout.splitlines()[1:] == ["[open-end] no test asserts it absent"]


def test_rule_no_test_asserts_present_fails(tmp_path):
    result = check(repo(tmp_path, tests=TESTS.replace('"too-long" in', '"too-long" not in')))
    assert result.returncode == 1
    assert result.stdout.splitlines()[1:] == ["[too-long] no test asserts it present"]


def test_undocumented_rule_fails(tmp_path):
    result = check(repo(tmp_path, doc="A long link is `[too-long]`; an open end is open-end.\n"))
    assert result.returncode == 1
    assert result.stdout.splitlines()[1:] == [
        "[open-end] is not documented as [open-end] in references/*.md"
    ]


def test_unit_no_units_row_reads_fails(tmp_path):
    result = check(repo(tmp_path, unit_names=("mm", "cm")))
    assert result.returncode == 1
    assert result.stdout.splitlines()[1:] == ["unit cm is read by no row of the tests' UNITS table"]


def test_test_importing_a_cadrev_module_but_the_cli_fails(tmp_path):
    tests = TESTS.replace(
        "from cadrev import cli", "from cadrev import cli, sources\nimport cadrev.units"
    )
    result = check(repo(tmp_path, tests=tests))
    assert result.returncode == 1
    assert result.stdout.splitlines()[1:] == [
        "skills/cad-reverse-engineer/tool/tests/test_cadrev.py:1: imports cadrev.sources;"
        " tests import only cadrev.cli",
        "skills/cad-reverse-engineer/tool/tests/test_cadrev.py:2: imports cadrev.units;"
        " tests import only cadrev.cli",
    ]
