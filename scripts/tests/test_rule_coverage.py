"""scripts/rule-coverage, run as CI runs it, on a small repo laid out like this one."""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "rule-coverage"
CADREV = SCRIPT.parents[1] / "plugin/skills/cad-reverse-engineer/tool/src/cadrev"

SOURCE = """\
def check(p):
    p.error("too-long", "the link is too long")
    p.warn("open-end", "the end is open")
"""
DOC = "A long link is `[too-long]`; an open end is `[open-end]`.\n"
SKILL_MD = "### 1. Model the link\n\nDone when `cadrev check` reports no `[too-long]`.\n"
TESTS = """\
from cadrev import cli
import pytest

UNITS = {"a 4 mm pin": (4, 4)}
FINDINGS = {
    "open-end": (lambda r: None, [lambda r: None]),
    "too-long": (lambda r: None, [lambda r: None]),
}


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


@pytest.mark.parametrize(
    "rule, miss", [(rule, i) for rule in sorted(FINDINGS) for i in range(len(FINDINGS[rule][1]))]
)
def test_guard_near_miss_raises_no_rule(tmp_path, rule, miss):
    FINDINGS[rule][1][miss](tmp_path)
    assert rule not in errors(tmp_path)
"""


def repo(
    tmp_path: Path, source=SOURCE, doc=DOC, tests=TESTS, unit_names=("mm",), skill_md=SKILL_MD
) -> Path:
    """A repo whose tool emits source's rules, documents doc, steps through skill_md and is tested
    by tests, with a unit table of the real cadrev's units named in unit_names."""
    src = tmp_path / "plugin/skills/cad-reverse-engineer/tool/src/cadrev"
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
    refs = tmp_path / "plugin/skills/cad-reverse-engineer/references"
    refs.mkdir(parents=True)
    (refs / "rules.md").write_text(doc)
    (refs.parent / "SKILL.md").write_text(skill_md)
    tool_tests = tmp_path / "tests"
    tool_tests.mkdir(parents=True)
    (tool_tests / "test_cadrev.py").write_text(tests)
    return tmp_path


def check(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), str(root)], capture_output=True, text=True)


def test_guard_rules_asserted_present_and_absent_documented_and_read_pass(tmp_path):
    result = check(repo(tmp_path))
    assert (result.returncode, result.stdout.splitlines()[1:]) == (0, [])


def test_guard_rule_asserted_through_a_helper_calling_one_defined_after_it_passes(tmp_path):
    # _long_of comes first and calls _too_long, so one reading in file order finds no rule in it.
    helper = "def _long_of(root):\n    return _too_long(root)\n\n\ndef _too_long(root):"
    tests = TESTS.replace("def _too_long(root):", helper).replace(
        'assert "too-long" in errors(tmp_path)', "assert _long_of(tmp_path)"
    )
    result = check(repo(tmp_path, tests=tests))
    assert (result.returncode, result.stdout.splitlines()[1:]) == (0, [])


def test_rule_asserted_absent_only_outside_its_findings_row_fails(tmp_path):
    # test_guard_short_link still asserts too-long absent, on no near miss.
    no_near_miss = '"too-long": (lambda r: None, []),'
    tests = TESTS.replace('"too-long": (lambda r: None, [lambda r: None]),', no_near_miss)
    result = check(repo(tmp_path, tests=tests))
    assert result.returncode == 1
    assert result.stdout.splitlines()[1:] == [
        "[too-long] no near miss in its FINDINGS row asserts it absent"
    ]


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


def test_error_no_done_line_of_skill_md_names_fails(tmp_path):
    result = check(repo(tmp_path, skill_md=SKILL_MD.replace("[too-long]", "[open-end]")))
    assert result.returncode == 1
    assert result.stdout.splitlines()[1:] == [
        "[too-long] is an error no completion criterion of SKILL.md names, "
        "as [too-long] or a [prefix-*]"
    ]


def test_guard_error_a_done_line_names_by_its_prefix_passes(tmp_path):
    result = check(repo(tmp_path, skill_md=SKILL_MD.replace("[too-long]", "[too-*]")))
    assert (result.returncode, result.stdout.splitlines()[1:]) == (0, [])


def test_guard_error_the_criteria_every_step_shares_names_passes(tmp_path):
    shared = "Each step ends on a criterion `cadrev` confirms, and at every step `[too-long]`.\n\n"
    result = check(repo(tmp_path, skill_md=shared + SKILL_MD.replace("[too-long]", "[open-end]")))
    assert (result.returncode, result.stdout.splitlines()[1:]) == (0, [])


def test_unit_no_units_row_reads_fails(tmp_path):
    result = check(repo(tmp_path, unit_names=("mm", "cm")))
    assert result.returncode == 1
    assert result.stdout.splitlines()[1:] == ["unit cm is read by no row of the tests' UNITS table"]


FIXTURE_EDITS = """

MODEL = "def build(p):\\n"


def test_edits(tmp_path):
    a = MODEL.replace("build", "make").replace("p", "q")
    b = re.sub(r"^def", "async def", (tmp_path / "m.py").read_text(), flags=re.M)
    c = "a(b)".replace("(", "[")
"""
SWAPPED_EDITS = """

MODEL = "def build(p):\\n"


def test_edits(tmp_path):
    a = swap(swap(MODEL, "build", "make"), "p", "q")
    b = swap((tmp_path / "m.py").read_text(), r"^def", "async def", regex=True)
    c = "a(b)".replace("(", "[")
"""


def test_test_editing_a_fixture_without_swap_fails(tmp_path):
    tests = TESTS + FIXTURE_EDITS
    result = check(repo(tmp_path, tests=tests))
    a, b = (
        n for n, line in enumerate(tests.splitlines(), 1) if line.startswith(("    a =", "    b ="))
    )
    where = "tests/test_cadrev.py"
    use = "use swap, which fails when the text it replaces is absent"
    assert result.returncode == 1
    assert result.stdout.splitlines()[1:] == [
        f"{where}:{a}: edits a fixture with replace; {use}",
        f"{where}:{a}: edits a fixture with replace; {use}",
        f"{where}:{b}: edits a fixture with re.sub; {use}",
    ]


def test_guard_test_editing_a_fixture_with_swap_passes(tmp_path):
    result = check(repo(tmp_path, tests=TESTS + SWAPPED_EDITS))
    assert (result.returncode, result.stdout.splitlines()[1:]) == (0, [])


def test_findings_rows_the_case_list_cannot_read_assert_no_rule_absent(tmp_path):
    unread = '"open-end": (lambda r: None, [lambda r: None for _ in range(1)]),'
    tests = TESTS.replace('"open-end": (lambda r: None, [lambda r: None]),', unread)
    result = check(repo(tmp_path, tests=tests))
    assert result.returncode == 1
    assert result.stdout.splitlines()[1:] == [
        "[open-end] no near miss in its FINDINGS row asserts it absent",
        "[too-long] no near miss in its FINDINGS row asserts it absent",
    ]


def test_findings_rows_out_of_order_fail(tmp_path):
    rows = TESTS.split("FINDINGS = {\n")[1].split("}\n")[0]
    first, second = rows.splitlines(keepends=True)
    result = check(repo(tmp_path, tests=TESTS.replace(rows, second + first)))
    assert result.returncode == 1
    assert result.stdout.splitlines()[1:] == [
        "FINDINGS row [open-end] sorts before [too-long] above it; move it first, above [too-long]"
    ]


@pytest.mark.parametrize(
    "old, new, missing",
    [
        (
            '@pytest.mark.parametrize(\n    "rule, miss"',
            '@pytest.mark.skip(reason="slow")\n@pytest.mark.parametrize(\n    "rule, miss"',
            [
                "[open-end] no near miss in its FINDINGS row asserts it absent",
                "[too-long] no near miss in its FINDINGS row asserts it absent",
            ],
        ),
        (
            "def test_long_link",
            "@pytest.mark.xfail\ndef test_long_link",
            ["[too-long] no test asserts it present"],
        ),
        (
            '["open-end"]',
            '[pytest.param("open-end", marks=pytest.mark.xfail)]',
            ["[open-end] no test asserts it present"],
        ),
    ],
)
def test_rule_asserted_only_by_a_skipped_or_xfail_test_fails(tmp_path, old, new, missing):
    result = check(repo(tmp_path, tests=TESTS.replace(old, new)))
    assert result.returncode == 1
    assert result.stdout.splitlines()[1:] == missing


def test_guard_rule_asserted_by_a_case_beside_a_skipped_case_passes(tmp_path):
    rows = '[pytest.param("too-long", marks=pytest.mark.skip), "open-end"]'
    result = check(repo(tmp_path, tests=TESTS.replace('["open-end"]', rows)))
    assert (result.returncode, result.stdout.splitlines()[1:]) == (0, [])


def test_rule_asserted_in_one_branch_of_a_conditional_assert_fails(tmp_path):
    old = "assert rule not in errors(tmp_path)"
    new = "assert (rule not in errors(tmp_path)) if tmp_path.exists() else True"
    result = check(repo(tmp_path, tests=TESTS.replace(old, new)))
    assert result.returncode == 1
    assert result.stdout.splitlines()[1:] == [
        "[open-end] no near miss in its FINDINGS row asserts it absent",
        "[too-long] no near miss in its FINDINGS row asserts it absent",
    ]


def test_guard_rule_asserted_in_both_branches_of_a_conditional_assert_passes(tmp_path):
    old = "assert rule not in errors(tmp_path)"
    new = "assert (rule not in errors(tmp_path)) if tmp_path.exists() else (rule not in [])"
    result = check(repo(tmp_path, tests=TESTS.replace(old, new)))
    assert (result.returncode, result.stdout.splitlines()[1:]) == (0, [])
