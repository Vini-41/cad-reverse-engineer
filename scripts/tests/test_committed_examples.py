"""scripts/committed-examples, run as scripts/check runs it, on a small repo with examples."""

import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "committed-examples"


def git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t", *args],
        check=True,
        capture_output=True,
    )


def repo(tmp_path: Path) -> Path:
    """A repo with one committed example file, ex/model.py, and an ignored build/."""
    root = tmp_path / "repo"
    (root / "examples" / "ex").mkdir(parents=True)
    git(root, "init", "-q")
    (root / ".gitignore").write_text("build/\n")
    (root / "examples" / "ex" / "model.py").write_text("committed\n")
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "init")
    return root


def copy(root: Path) -> Path:
    result = subprocess.run([str(SCRIPT)], cwd=root, capture_output=True, text=True, check=True)
    return Path(result.stdout.strip())


def test_copy_holds_what_a_commit_would_staged_files_at_their_staged_text(tmp_path):
    root = repo(tmp_path)
    ex = root / "examples" / "ex"
    (ex / "new.yaml").write_text("staged\n")
    git(root, "add", "examples/ex/new.yaml")
    (ex / "new.yaml").write_text("staged, then edited\n")
    (ex / "model.py").write_text("edited, unstaged\n")
    (ex / "stray.yaml").write_text("untracked\n")
    examples = copy(root)
    files = sorted(str(p.relative_to(examples)) for p in examples.rglob("*") if p.is_file())
    assert files == ["ex/model.py", "ex/new.yaml"]
    assert (examples / "ex" / "model.py").read_text() == "committed\n"
    assert (examples / "ex" / "new.yaml").read_text() == "staged\n"


def test_guard_ignored_files_stay_out_of_the_copy(tmp_path):
    root = repo(tmp_path)
    (root / "examples" / "ex" / "build").mkdir()
    (root / "examples" / "ex" / "build" / "report.md").write_text("ignored\n")
    examples = copy(root)
    assert not (examples / "ex" / "build").exists()
    assert (examples / "ex" / "model.py").is_file()


def stderr(root: Path) -> str:
    return subprocess.run(
        [str(SCRIPT)], cwd=root, capture_output=True, text=True, check=True
    ).stderr


def test_each_edit_left_out_of_the_copy_is_named_on_stderr(tmp_path):
    root = repo(tmp_path)
    (root / "examples" / "ex" / "model.py").write_text("edited, unstaged\n")
    (root / "examples" / "ex" / "stray.yaml").write_text("untracked\n")
    assert stderr(root).splitlines() == [
        "not staged, so left out of the copy: examples/ex/model.py",
        "not staged, so left out of the copy: examples/ex/stray.yaml",
    ]


def test_guard_a_fully_staged_tree_copies_without_a_word(tmp_path):
    root = repo(tmp_path)
    (root / "examples" / "ex" / "model.py").write_text("edited, staged\n")
    git(root, "add", "examples")
    assert stderr(root) == ""
