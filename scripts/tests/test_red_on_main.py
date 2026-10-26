"""scripts/red-on-main, run on a small git repo laid out like this one, with a fix in its last
commit."""

import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "red-on-main"
TOOL = "skills/cad-reverse-engineer/tool"
BASE_TESTS = (
    "from double import double\n\n\ndef test_double_of_zero():\n    assert double(0) == 0\n"
)


def git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t", *args],
        check=True,
        capture_output=True,
    )


def write(root: Path, files: dict[str, str]) -> None:
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)


def repo(tmp_path: Path, dependencies: str) -> Path:
    """A tool whose last commit fixes double() and adds a test that fails before the fix."""
    root = tmp_path / "repo"
    write(
        root,
        {
            f"{TOOL}/pyproject.toml": (
                f'[project]\nname = "fixture"\nversion = "0"\ndependencies = [{dependencies}]\n'
            ),
            f"{TOOL}/src/double.py": "def double(x):\n    return x\n",
            f"{TOOL}/tests/test_double.py": BASE_TESTS,
        },
    )
    git(root, "init", "-q", "-b", "master")  # not main, whatever the machine's default
    git(root, "add", ".")
    git(root, "commit", "-qm", "base")
    write(
        root,
        {
            f"{TOOL}/src/double.py": "def double(x):\n    return 2 * x\n",
            f"{TOOL}/tests/test_double.py": (
                f"{BASE_TESTS}\n\ndef test_double_doubles():\n    assert double(2) == 4\n"
            ),
        },
    )
    git(root, "commit", "-qam", "fix")
    return root


def red_on_main(
    root: Path, *args: str, base: str | None = "HEAD~1", **env_vars: str
) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k != "BASE"} | env_vars
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=root,
        env=env if base is None else {**env, "BASE": base},
        capture_output=True,
        text=True,
    )


def commit(root: Path, files: dict[str, str]) -> None:
    write(root, files)
    git(root, "commit", "-qam", "change")


def test_guard_pytest_that_cannot_run_exits_2(tmp_path):
    result = red_on_main(repo(tmp_path, dependencies=""))
    assert result.returncode == 2
    assert "pytest" in result.stderr


def test_guard_pytest_that_selects_no_test_exits_2(tmp_path):
    result = red_on_main(repo(tmp_path, dependencies='"pytest"'), "-k", "no_such_test")
    assert result.returncode == 2
    assert "pytest" in result.stderr


def test_base_at_head_with_the_tool_source_unchanged_exits_3(tmp_path):
    result = red_on_main(repo(tmp_path, dependencies='"pytest"'), base="HEAD")
    assert result.returncode == 3
    assert "no fix to compare" in result.stderr


def test_a_fix_with_no_new_or_changed_test_exits_3(tmp_path):
    root = repo(tmp_path, dependencies='"pytest"')
    commit(root, {f"{TOOL}/src/double.py": "def double(x):\n    return x + x\n"})
    result = red_on_main(root)
    assert result.returncode == 3
    assert "no test function is new or changed" in result.stderr


def test_the_null_commit_as_base_exits_3(tmp_path):
    result = red_on_main(repo(tmp_path, dependencies='"pytest"'), base="0" * 40)
    assert result.returncode == 3
    assert "null commit" in result.stderr


def test_a_base_the_clone_lacks_exits_3(tmp_path):
    result = red_on_main(repo(tmp_path, dependencies='"pytest"'), base="1" * 40)
    assert result.returncode == 3
    assert "not in this clone" in result.stderr


def test_guard_a_new_green_test_without_the_guard_name_exits_1(tmp_path):
    root = repo(tmp_path, dependencies='"pytest"')
    commit(
        root,
        {
            f"{TOOL}/tests/test_double.py": (
                f"{BASE_TESTS}\n\ndef test_double_of_one():\n    assert double(1) != 0\n"
            )
        },
    )
    result = red_on_main(root)
    assert result.returncode == 1
    assert "green, not a guard (name it test_guard_): " in result.stdout
    assert "test_double_of_one" in result.stdout


def test_guard_list_prints_each_test_red_or_green(tmp_path):
    root = repo(tmp_path, dependencies='"pytest"')
    result = red_on_main(root, "-k", "double", LIST="1")
    assert result.returncode == 0, result.stderr
    assert "red    tests/test_double.py::test_double_doubles" in result.stdout
    assert "green  tests/test_double.py::test_double_of_zero" in result.stdout
    assert "1 red (holes), 1 green" in result.stdout


def test_guard_hole_test_counts_red(tmp_path):
    result = red_on_main(repo(tmp_path, dependencies='"pytest"'))
    assert result.returncode == 0, result.stderr
    assert "1 red (holes), 0 green" in result.stdout


def test_guard_branch_with_no_upstream_or_reflog_compares_against_its_merge_base_with_main(
    tmp_path,
):
    root = repo(tmp_path, dependencies='"pytest"')
    git(root, "-c", "core.logAllRefUpdates=false", "switch", "-qc", "ticket")
    git(root, "branch", "-f", "main", "HEAD~1")
    result = red_on_main(root, base=None)
    assert result.returncode == 0, result.stderr
    assert "1 red (holes), 0 green" in result.stdout
    assert "merge-base with main" in result.stdout


def test_branch_cut_from_another_branch_compares_against_where_it_was_created(tmp_path):
    root = repo(tmp_path, dependencies='"pytest"')
    git(root, "branch", "-f", "main", "HEAD~1")
    git(root, "switch", "-qc", "ticket")
    commit(
        root,
        {
            f"{TOOL}/tests/test_double.py": (
                f"{BASE_TESTS}\n\ndef test_guard_double_of_two():\n    assert double(2) == 4\n"
            )
        },
    )
    result = red_on_main(root, base=None)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "0 red (holes), 1 green" in result.stdout
    assert "the commit ticket was created at" in result.stdout


def test_guard_branch_that_merged_main_since_it_was_created_compares_against_main(tmp_path):
    root = repo(tmp_path, dependencies='"pytest"')
    git(root, "branch", "-f", "main", "HEAD")
    git(root, "switch", "-qc", "ticket", "HEAD~1")
    git(root, "merge", "-q", "--no-ff", "-m", "merge main", "main")
    result = red_on_main(root, base=None)
    assert result.returncode == 3, result.stdout + result.stderr
    assert "no test function is new or changed since merge-base with main" in result.stderr
