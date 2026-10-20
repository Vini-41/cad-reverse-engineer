"""scripts/same-reports, on a small repo whose fake cadrev writes the report its source holds."""

import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "same-reports"
TOOL = "skills/cad-reverse-engineer/tool"
CLI = """import json, sys
from pathlib import Path

REPORT = {report}
PRINTED = {printed}


def main(argv):
    if "--no-build" in argv:  # a partial run prints its findings and writes no report
        print("\\n".join(PRINTED))
        return 1
    if REPORT is not None:
        (Path(argv[1]) / "build").mkdir(exist_ok=True)
        (Path(argv[1]) / "build" / "report.json").write_text(json.dumps(REPORT))
    return 0
"""
REPORT = {"checks": [{"id": "T1", "ok": True}], "findings": [{"rule": "a"}, {"rule": "b"}]}
PRINTED = ["error: [a] one", "warning: [b] two", "NOT VERIFIED: skipped the build"]


def git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t", *args],
        check=True,
        capture_output=True,
    )


def cli(root: Path, report: dict | None, printed: list[str] = PRINTED) -> None:
    text = CLI.format(report=repr(report), printed=repr(printed))
    (root / TOOL / "src" / "cadrev" / "cli.py").write_text(text)


def repo(tmp_path: Path) -> Path:
    """A repo with one example, ex, and a committed cadrev that writes REPORT."""
    root = tmp_path / "repo"
    (root / TOOL / "src" / "cadrev").mkdir(parents=True)
    (root / TOOL / "pyproject.toml").write_text(
        '[project]\nname = "fixture"\nversion = "0"\ndependencies = []\n'
    )
    (root / TOOL / "src" / "cadrev" / "__init__.py").write_text("")
    cli(root, REPORT)
    (root / "examples" / "ex").mkdir(parents=True)
    (root / "examples" / "ex" / "project.yaml").write_text("format: 1\n")
    git(root, "init", "-q")
    git(root, "add", ".")
    git(root, "commit", "-qm", "base")
    return root


def same_reports(root: Path, *args: str, base: str = "HEAD") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(SCRIPT), *args],
        cwd=root,
        env={**os.environ, "BASE": base},
        capture_output=True,
        text=True,
    )


def test_a_refactor_that_only_reorders_findings_is_same(tmp_path):
    root = repo(tmp_path)
    cli(root, {**REPORT, "findings": REPORT["findings"][::-1]})
    result = same_reports(root)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "examples/ex: same (1 checks, 2 findings)" in result.stdout


def test_a_changed_check_entry_differs_naming_the_check(tmp_path):
    root = repo(tmp_path)
    cli(root, {**REPORT, "checks": [{"id": "T1", "ok": False}]})
    result = same_reports(root)
    assert result.returncode == 1
    assert "examples/ex: differs, checks[0] (T1)" in result.stdout


def test_a_finding_gone_differs_naming_it(tmp_path):
    root = repo(tmp_path)
    cli(root, {**REPORT, "findings": REPORT["findings"][:1]})
    result = same_reports(root)
    assert result.returncode == 1
    assert """findings only at BASE: ['{"rule": "b"}']; only now: none""" in result.stdout


def test_a_run_that_writes_no_report_exits_2(tmp_path):
    root = repo(tmp_path)
    cli(root, None)
    result = same_reports(root)
    assert result.returncode == 2
    assert "examples/ex: no report.json with the tool source at head" in result.stdout


def test_the_tool_source_unchanged_since_base_exits_3(tmp_path):
    result = same_reports(repo(tmp_path))
    assert result.returncode == 3
    assert "nothing to compare" in result.stderr


def test_a_base_the_clone_lacks_exits_3(tmp_path):
    root = repo(tmp_path)
    cli(root, {**REPORT, "checks": []})
    result = same_reports(root, base="1" * 40)
    assert result.returncode == 3
    assert "not in this clone" in result.stderr


def test_a_partial_run_that_only_reorders_its_printed_findings_is_same(tmp_path):
    root = repo(tmp_path)
    cli(root, REPORT, [PRINTED[1], PRINTED[0], "NOT VERIFIED: skipped the build, now worded anew"])
    result = same_reports(root, "--no-build")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "examples/ex: same with --no-build (2 findings)" in result.stdout


def test_a_partial_run_whose_printed_finding_is_gone_differs_naming_it(tmp_path):
    root = repo(tmp_path)
    cli(root, REPORT, PRINTED[1:])
    result = same_reports(root, "--no-build")
    assert result.returncode == 1
    assert "findings only at BASE: ['error: [a] one']; only now: none" in result.stdout
