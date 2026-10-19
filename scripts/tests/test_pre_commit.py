""".githooks/pre-commit, run as git runs it, from the top of a small repo with staged files."""

import subprocess
from pathlib import Path

HOOK = Path(__file__).resolve().parents[2] / ".githooks" / "pre-commit"
UGLY = "x=1\n"


def git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t", *args],
        check=True,
        capture_output=True,
    )


def staged(root: Path, name: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), "show", f":{name}"], capture_output=True, text=True, check=True
    ).stdout


def repo(tmp_path: Path, files: dict[str, str]) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)
    git(root, "add", ".")
    return root


def hook(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([str(HOOK)], cwd=root, capture_output=True, text=True)


def test_staged_python_is_formatted_and_restaged(tmp_path):
    root = repo(tmp_path, {"a.py": UGLY, "scripts/tool": UGLY})
    result = hook(root)
    assert result.returncode == 0
    assert staged(root, "a.py") == staged(root, "scripts/tool") == "x = 1\n"


def test_unformatted_file_with_unstaged_changes_stops_the_commit_naming_it(tmp_path):
    root = repo(tmp_path, {"a.py": UGLY})
    (root / "a.py").write_text(UGLY + "y=2\n")
    result = hook(root)
    assert result.returncode == 1 and "a.py" in result.stderr
    assert staged(root, "a.py") == UGLY


def test_guard_formatted_or_non_python_files_pass_untouched(tmp_path):
    root = repo(tmp_path, {"a.py": "x = 1\n", "notes.md": UGLY})
    result = hook(root)
    assert result.returncode == 0 and result.stdout == ""
    assert staged(root, "notes.md") == UGLY
