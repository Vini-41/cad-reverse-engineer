"""scripts/batch, run from a copy in a clone of a bare origin, against a fake gh that reads and
writes GitHub's state as JSON, a fake claude that commits what a test tells it to, and a fake
ci-wait."""

import importlib.machinery
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
BRIEF = SCRIPTS.parent / "docs" / "agents" / "batch-ticket.md"


def load_batch():
    loader = importlib.machinery.SourceFileLoader("batch", str(SCRIPTS / "batch"))
    spec = importlib.util.spec_from_loader("batch", loader)
    assert spec
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


FAKE_GH = r"""#!/usr/bin/env python3
import json, os, subprocess, sys
path = os.environ["FAKE_GH_STATE"]
state = json.load(open(path))
args = sys.argv[1:]
state["calls"].append(args)
issues = {str(i["number"]): i for i in state["issues"]}
code = 0
if args[:2] == ["issue", "list"]:
    print(json.dumps(state["issues"]))
elif args[:2] == ["issue", "view"]:
    print(json.dumps(issues[args[2]]))
elif args[0] == "api":
    number = args[1].rsplit("/", 1)[1]
    print(issues[number].get("blocked_by", 0))
elif args[:2] == ["pr", "view"]:
    code = 1
elif args[:2] == ["pr", "create"]:
    branch = args[args.index("--head") + 1]
    state["prs"].append(branch)
    print(f"https://github.com/o/r/pull/{len(state['prs'])}")
elif args[:2] == ["pr", "merge"]:
    branch = state["prs"][int(args[2]) - 1]
    subprocess.run(["git", "push", "-q", "origin", f"origin/{branch}:refs/heads/main"], check=True)
    subprocess.run(["git", "fetch", "-q", "origin"], check=True)
json.dump(state, open(path, "w"))
sys.exit(code)
"""

# Reads the ticket number from the task, then does what FAKE_CLAUDE says for it: commit a file, and
# write the result file the brief names.
FAKE_CLAUDE = r"""#!/usr/bin/env python3
import json, os, re, subprocess, sys
prompt = sys.argv[sys.argv.index("-p") + 1]
number = re.search(r"Issue #(\d+)", prompt).group(1)
result = re.search(r"`([^`]+\.result\.md)`", prompt).group(1)
plan = json.load(open(os.environ["FAKE_CLAUDE"]))[number]
if plan.get("file"):
    open(plan["file"], "w").write(number)
    subprocess.run(["git", "add", plan["file"]], check=True)
    subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", f"ticket {number}"], check=True)
open(result, "w").write(plan["result"])
"""

FAKE_CI = """#!/bin/sh
if [ -n "$FAKE_CI_RED" ]; then echo "CI failure on $1"; exit 1; fi
echo "CI success on $1"
"""


def setup(tmp_path: Path, issues: list[dict], agents: dict) -> tuple[Path, dict, Path]:
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    repo = tmp_path / "repo"
    subprocess.run(["git", "clone", "-q", str(origin), str(repo)], check=True)
    (repo / "scripts").mkdir()
    shutil.copy(SCRIPTS / "batch", repo / "scripts" / "batch")
    (repo / "docs" / "agents").mkdir(parents=True)
    shutil.copy(BRIEF, repo / "docs" / "agents" / "batch-ticket.md")
    (repo / ".gitignore").write_text(".scratch/\n.claude/\n")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "base"], check=True)
    subprocess.run(["git", "-C", str(repo), "push", "-q", "origin", "main"], check=True)
    for name, text in (("gh", FAKE_GH), ("claude", FAKE_CLAUDE), ("ci-wait", FAKE_CI)):
        (tmp_path / name).write_text(text)
        (tmp_path / name).chmod(0o755)
    state = tmp_path / "gh.json"
    state.write_text(json.dumps({"issues": issues, "calls": [], "prs": []}))
    (tmp_path / "claude.json").write_text(json.dumps(agents))
    env = {
        **os.environ,
        "GH": str(tmp_path / "gh"),
        "CLAUDE": str(tmp_path / "claude"),
        "CI_WAIT": str(tmp_path / "ci-wait"),
        "FAKE_GH_STATE": str(state),
        "FAKE_CLAUDE": str(tmp_path / "claude.json"),
        "CADREV_PROJECTS": str(tmp_path / "no-projects"),
        "BATCH_NOTIFY": "0",
    }
    return repo, env, state


def issue(number: int, touches: str | None = None, labels: tuple = ("ready-for-agent",)) -> dict:
    body = f"Touches: {touches}\n\nThe brief." if touches else "The brief."
    return {
        "number": number,
        "title": f"Ticket {number}",
        "body": body,
        "labels": [{"name": n} for n in labels],
    }


def batch(repo: Path, env: dict, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(repo / "scripts" / "batch"), *args],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
    )


def test_batch_plans_waves_of_disjoint_tickets_and_runs_one_without_touches_alone(tmp_path):
    issues = [
        issue(1, "src/a/"),
        issue(2, "docs/"),
        issue(3, "src/a/x.py"),
        issue(4),
        issue(5, "tests/"),
        issue(6, "lib/", labels=("ready-for-agent", "needs-info")),
    ]
    issues.append({**issue(7, "other/"), "blocked_by": 1})
    repo, env, _ = setup(tmp_path, issues, {})
    result = batch(repo, env, "--dry-run")
    assert result.returncode == 0, result.stderr
    assert result.stdout == (
        "wave 1: #1 Ticket 1, #2 Ticket 2\n"
        "wave 2: #3 Ticket 3\n"
        "wave 3: #4 Ticket 4\n"
        "wave 4: #5 Ticket 5\n"
    )


def test_batch_caps_a_wave_at_max(tmp_path):
    issues = [issue(1, "a/"), issue(2, "b/"), issue(3, "c/")]
    repo, env, _ = setup(tmp_path, issues, {})
    result = batch(repo, env, "--dry-run", "--max", "2")
    assert result.stdout == "wave 1: #1 Ticket 1, #2 Ticket 2\nwave 2: #3 Ticket 3\n"


@pytest.mark.parametrize(
    "path, held",
    [
        ("skills/cad-reverse-engineer/SKILL.md", True),
        ("plugin/skills/cad-reverse-engineer/references/modeling.md", True),
        ("README.md", True),
        ("examples/centrifuge/README.md", True),
        (".claude-plugin/plugin.json", True),
        (".github/workflows/test.yml", True),
        ("docs/agents/batch-ticket.md", True),
        ("scripts/check", True),
        ("skills/cad-reverse-engineer/tool/src/cadrev/shape.py", False),
        ("scripts/check-linear", False),
        ("docs/dogfood/brief.md", False),
        ("references.py", False),
    ],
)
def test_a_change_waits_for_the_user_only_on_a_protected_path(path, held):
    assert load_batch().protected(path) is held


def test_batch_merges_a_green_ticket_and_holds_one_that_changes_the_readme(tmp_path):
    agents = {
        "1": {"file": "a.py", "result": "done\nAdds a.py."},
        "2": {
            "file": "README.md",
            "result": "done\nRewrites the README.\n\nDepartures:\nNone big.",
        },
    }
    repo, env, state = setup(tmp_path, [issue(1, "a.py"), issue(2, "README.md")], agents)
    result = batch(repo, env)
    assert result.returncode == 0, result.stdout + result.stderr
    main = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "origin/main"], capture_output=True, text=True
    ).stdout.strip()
    calls = json.loads(state.read_text())["calls"]
    assert ["pr", "merge", "1", "--rebase", "--delete-branch"] in calls
    assert ["issue", "close", "1", "--comment", f"Landed in {main}; CI green on {main}."] in calls
    assert not any(c[:3] == ["pr", "merge", "2"] for c in calls)
    assert "#1 Ticket 1: PR #1" in result.stdout
    assert "#2 Ticket 2: PR #2 changes README.md" in result.stdout
    created = next(c for c in calls if c[:2] == ["pr", "create"])
    assert created[created.index("--body") + 1].startswith("Part of #1\n\nAdds a.py.")


def test_batch_puts_an_agent_question_on_its_issue_and_opens_no_pr(tmp_path):
    agents = {"1": {"result": "needs-info\nWhich unit does the sweep read?"}}
    repo, env, state = setup(tmp_path, [issue(1, "a.py")], agents)
    result = batch(repo, env)
    assert result.returncode == 0, result.stdout + result.stderr
    calls = json.loads(state.read_text())["calls"]
    comment = next(c for c in calls if c[:2] == ["issue", "comment"])
    assert "Which unit does the sweep read?" in comment[-1]
    assert [
        "issue",
        "edit",
        "1",
        "--add-label",
        "needs-info",
        "--remove-label",
        "ready-for-agent",
    ] in calls
    assert not any(c[:2] == ["pr", "create"] for c in calls)
    assert "## Needs info\n\n- #1 Ticket 1: Which unit does the sweep read?" in result.stdout


def test_batch_asks_when_ci_stays_red_after_one_fix_and_leaves_the_pr_open(tmp_path):
    agents = {"1": {"file": "a.py", "result": "done\nAdds a.py."}}
    repo, env, state = setup(tmp_path, [issue(1, "a.py")], agents)
    result = batch(repo, {**env, "FAKE_CI_RED": "1"})
    assert result.returncode == 0, result.stdout + result.stderr
    calls = json.loads(state.read_text())["calls"]
    assert any(c[:2] == ["pr", "create"] for c in calls)
    assert not any(c[:2] == ["pr", "merge"] for c in calls)
    logs = sorted(p.name for p in (repo / ".scratch" / "batches").glob("*/*.log"))
    assert logs == ["1.ci-fix.log", "1.implement.log"]
    assert "#1 Ticket 1: CI stays red on PR #1 after one fix" in result.stdout
