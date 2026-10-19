"""scripts/red-on-main, run on a small git repo laid out like this one, with a fix in its last commit."""

import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "red-on-main"
TOOL = "skills/cad-reverse-engineer/tool"
BASE_TESTS = (
    "from double import double\n\n\ndef test_double_of_zero():\n    assert double(0) == 0\n"
)


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


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
    git(root, "init", "-q")
    git(root, "add", ".")
    git(root, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "base")
    write(
        root,
        {
            f"{TOOL}/src/double.py": "def double(x):\n    return 2 * x\n",
            f"{TOOL}/tests/test_double.py": (
                f"{BASE_TESTS}\n\ndef test_double_doubles():\n    assert double(2) == 4\n"
            ),
        },
    )
    git(root, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "fix")
    return root


def red_on_main(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=root,
        env={**os.environ, "BASE": "HEAD~1"},
        capture_output=True,
        text=True,
    )


def test_pytest_that_cannot_run_fails(tmp_path):
    result = red_on_main(repo(tmp_path, dependencies=""))
    assert result.returncode != 0
    assert "pytest" in result.stderr


def test_pytest_that_selects_no_test_fails(tmp_path):
    result = red_on_main(repo(tmp_path, dependencies='"pytest"'), "-k", "no_such_test")
    assert result.returncode != 0
    assert "pytest" in result.stderr


def test_guard_hole_test_counts_red(tmp_path):
    result = red_on_main(repo(tmp_path, dependencies='"pytest"'))
    assert result.returncode == 0, result.stderr
    assert "1 red (holes), 0 green" in result.stdout


def test_guard_collect_only_passes(tmp_path):
    result = red_on_main(repo(tmp_path, dependencies='"pytest"'), "--co", "-q")
    assert result.returncode == 0, result.stderr
