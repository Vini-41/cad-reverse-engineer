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
runs = {r["id"]: r for rs in state["runs"].values() for r in rs}
if args[:2] == ["run", "list"]:
    sha = args[args.index("--commit") + 1]
    for r in state["runs"].get(sha, []):
        print(f'{r["id"]}\t{r["event"]}')
elif args[:2] == ["run", "watch"]:
    sys.exit(0 if runs[args[2]]["conclusion"] == "success" else 1)
elif args[:2] == ["run", "view"] and "--log-failed" in args:
    print(runs[args[2]].get("log", ""))
elif args[:2] == ["run", "view"]:
    print(runs[args[2]]["conclusion"])
else:
    print(state["branch"])
"""


def setup(
    tmp_path: Path,
    runs: bool,
    conclusion: str = "success",
    branch: str = "",
    log: str = "",
    more: tuple = (),
) -> tuple:
    """A repo whose commit has, when runs is set, a push run 77 ending in conclusion, then each
    run of more, an (id, event, conclusion) triple."""
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
    listed = [{"id": "77", "event": "push", "conclusion": conclusion, "log": log}]
    listed += [{"id": i, "event": e, "conclusion": c, "log": log} for i, e, c in more]
    found = {sha: listed} if runs else {}
    state.write_text(json.dumps({"runs": found, "branch": branch or sha}))
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
    assert result.stdout == f"CI success on {sha} (push run 77)\n"


def test_ci_wait_exits_1_on_a_failed_run(tmp_path):
    repo, sha, env = setup(tmp_path, runs=True, conclusion="failure")
    result = run(repo, env)
    assert result.returncode == 1
    assert result.stdout == f"CI failure on {sha} (push run 77)\n"


# gh run view --log-failed: each line is job, step and a timestamped message, tab-separated.
# scripts/check echoes a failed step's output, so pytest's lines come twice.
FAILED_LOG = """\
test (3.12)\tRun ../../../scripts/check\t2026-10-22T01:39:31.6Z wrote build/model.mjcf
test (3.12)\tRun ../../../scripts/check\t2026-10-22T01:39:32.3Z failed: tool tests
test (3.12)\tRun ../../../scripts/check\t2026-10-22T01:39:32.3Z   E   ValueError: too many values
test (3.12)\tRun ../../../scripts/check\t2026-10-22T01:39:32.3Z   FAILED tests/test_x.py::test_a
test (3.12)\tRun ../../../scripts/check\t2026-10-22T01:39:32.3Z   1 failed, 971 passed in 106.02s
test (3.12)\tRun ../../../scripts/check\t2026-10-22T01:39:32.4Z   1 failed, 971 passed in 106.02s
test (3.10)\tRun ../../../scripts/check\t2026-10-22T01:39:40.1Z failed: pyright
"""


def test_ci_wait_watches_every_run_on_the_commit_and_fails_if_any_fails(tmp_path):
    # A PR's head commit has a push run and a pull_request run, which compare against different
    # bases, so one can pass while the other fails.
    repo, sha, env = setup(tmp_path, runs=True, more=(("78", "pull_request", "failure"),))
    result = run(repo, env)
    assert result.returncode == 1
    assert result.stdout == (
        f"CI success on {sha} (push run 77)\nCI failure on {sha} (pull_request run 78)\n"
    )


def test_guard_ci_wait_passes_when_every_run_on_the_commit_succeeds(tmp_path):
    repo, sha, env = setup(tmp_path, runs=True, more=(("78", "pull_request", "success"),))
    result = run(repo, env)
    assert result.returncode == 0, result.stderr
    assert result.stdout.count("CI success") == 2


def test_ci_wait_on_a_failed_run_prints_what_failed_in_each_job(tmp_path):
    repo, sha, env = setup(tmp_path, runs=True, conclusion="failure", log=FAILED_LOG)
    result = run(repo, env)
    assert result.returncode == 1
    assert result.stdout == (
        f"CI failure on {sha} (push run 77)\n"
        "test (3.12): failed: tool tests\n"
        "test (3.12): FAILED tests/test_x.py::test_a\n"
        "test (3.12): 1 failed, 971 passed in 106.02s\n"
        "test (3.10): failed: pyright\n"
    )


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
