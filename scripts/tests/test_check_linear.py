"""scripts/check-linear, run in a small repo whose branch holds or lacks a merge commit."""

import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "check-linear"


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def repo(tmp_path: Path, merged: bool) -> Path:
    """main with one commit, and a branch with two commits, joined by a merge where merged."""
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "commit", "-q", "--allow-empty", "-m", "base")
    git(root, "checkout", "-q", "-b", "side")
    git(root, "commit", "-q", "--allow-empty", "-m", "side work")
    git(root, "checkout", "-q", "-b", "feature", "main")
    git(root, "commit", "-q", "--allow-empty", "-m", "feature work")
    if merged:
        git(root, "merge", "-q", "--no-ff", "-m", "Merge branch 'side' into feature", "side")
    return root


def check(root: Path, **env: str) -> subprocess.CompletedProcess[str]:
    clean = {k: v for k, v in os.environ.items() if k not in ("BASE", "HEAD_SHA")}
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=root,
        env={**clean, **env},
        capture_output=True,
        text=True,
    )


def test_a_merge_commit_since_main_is_named_and_fails(tmp_path):
    root = repo(tmp_path, merged=True)
    result = check(root)
    assert result.returncode == 1
    merge = git(root, "rev-parse", "--short", "HEAD")
    assert f"{merge} Merge branch 'side' into feature" in result.stdout
    assert "gh pr merge --rebase" in result.stdout


def test_guard_a_linear_branch_passes(tmp_path):
    root = repo(tmp_path, merged=False)
    result = check(root)
    assert result.returncode == 0, result.stdout
    assert result.stdout == ""


def test_head_sha_names_the_commit_checked_in_place_of_head(tmp_path):
    # A pull_request run checks out GitHub's own merge of the PR into its base; HEAD_SHA names the
    # PR's head, so that merge isn't counted.
    root = repo(tmp_path, merged=True)
    merged = git(root, "rev-parse", "HEAD")
    git(root, "checkout", "-q", "main")
    git(root, "merge", "-q", "--no-ff", "-m", "Merge pull request", "feature")
    base = git(root, "rev-parse", "HEAD^1")
    assert check(root, BASE=base, HEAD_SHA=merged).returncode == 1
    git(root, "checkout", "-q", "-b", "linear", "feature~1")
    linear = git(root, "rev-parse", "HEAD")
    git(root, "checkout", "-q", "main")
    assert check(root, BASE=base, HEAD_SHA=linear).returncode == 0


def test_guard_a_base_of_the_null_commit_compares_nothing_and_passes(tmp_path):
    root = repo(tmp_path, merged=True)
    result = check(root, BASE="0" * 40)
    assert result.returncode == 0
    assert "nothing to compare" in result.stderr
