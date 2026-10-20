"""scripts/ci-wait, run in a one-commit repo against a fake gh that reads GitHub's state from
JSON."""

import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "ci-wait"

FAKE_GH = r"""#!/usr/bin/env python3
import json, os, sys
state = json.load(open(os.environ["FAKE_GH_STATE"]))
args = sys.argv[1:]
if args[:2] == ["run", "list"]:
    sha = args[args.index("--commit") + 1]
    print(state["runs"].get(sha, {}).get("id", ""))
elif args[:2] == ["run", "watch"]:
    sys.exit(0 if state["conclusion"] == "success" else 1)
elif args[:2] == ["run", "view"]:
    print(state["conclusion"])
else:
    print(state["branch"])
"""


def setup(tmp_path: Path, runs: bool, conclusion: str = "success", branch: str = "") -> tuple:
    repo = tmp_path / "repo"
    repo.mkdir()
    git = ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run([*git, "init", "-q", "-b", "main"], check=True)
    subprocess.run([*git, "commit", "-q", "--allow-empty", "-m", "c"], check=True)
    sha = subprocess.run([*git, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    gh = tmp_path / "gh"
    gh.write_text(FAKE_GH)
    gh.chmod(0o755)
    state = tmp_path / "state.json"
    found = {sha: {"id": "77"}} if runs else {}
    state.write_text(json.dumps({"runs": found, "conclusion": conclusion, "branch": branch or sha}))
    env = {**os.environ, "GH": str(gh), "FAKE_GH_STATE": str(state), "CI_WAIT_SECONDS": "0"}
    return repo, sha, env


def run(repo: Path, env: dict, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], cwd=repo, env=env, capture_output=True, text=True
    )


def test_ci_wait_finds_the_run_by_the_full_sha_of_a_short_one(tmp_path):
    repo, sha, env = setup(tmp_path, runs=True)
    result = run(repo, env, sha[:7])
    assert result.returncode == 0, result.stderr
    assert result.stdout == f"CI success on {sha} (run 77)\n"


def test_ci_wait_exits_1_on_a_failed_run(tmp_path):
    repo, sha, env = setup(tmp_path, runs=True, conclusion="failure")
    result = run(repo, env)
    assert result.returncode == 1
    assert result.stdout == f"CI failure on {sha} (run 77)\n"


def test_ci_wait_names_the_rerun_when_the_pushed_commit_has_no_run(tmp_path):
    repo, _, env = setup(tmp_path, runs=False)
    result = run(repo, env)
    assert result.returncode == 1
    assert "push event was lost" in result.stderr
    assert "`gh workflow run test.yml --ref main`" in result.stderr


def test_ci_wait_says_to_push_when_github_is_at_another_commit(tmp_path):
    repo, sha, env = setup(tmp_path, runs=False, branch="0" * 40)
    result = run(repo, env)
    assert result.returncode == 1
    assert f"main on GitHub is at {'0' * 40}, not {sha}: push it first" in result.stderr


def test_ci_wait_help_prints_its_usage_and_asks_github_nothing(tmp_path):
    repo, _, env = setup(tmp_path, runs=True)
    for flag in ("-h", "--help"):
        result = run(repo, {**env, "GH": "false"}, flag)
        assert result.returncode == 0, result.stderr
        assert "scripts/ci-wait [commit, default HEAD]" in result.stdout


def test_ci_wait_exits_2_naming_an_argument_that_is_no_commit_before_asking_github(tmp_path):
    repo, _, env = setup(tmp_path, runs=True)
    for arg in ("--verbose", "nope"):
        result = run(repo, {**env, "GH": "false"}, arg)
        assert result.returncode == 2
        assert result.stderr == f"{arg} names no commit\n"
