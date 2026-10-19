"""scripts/file-tickets, run against a fake gh that keeps GitHub's state in a JSON file."""

import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "file-tickets"

FAKE_GH = r"""#!/usr/bin/env python3
import json, os, re, sys
path = os.environ["FAKE_GH_STATE"]
state = json.load(open(path))
args = sys.argv[1:]
def save():
    json.dump(state, open(path, "w"))
def flag(name):
    return args[args.index(name) + 1]
if args[:2] == ["issue", "create"]:
    number = state["next"]
    state["next"] += 1
    labels = [args[i + 1] for i, a in enumerate(args) if a == "--label"]
    state["issues"][str(number)] = {"title": flag("--title"), "body": flag("--body"),
                                    "labels": labels, "blocked_by": [], "subs": []}
    save()
    print(f"https://github.com/o/r/issues/{number}")
    sys.exit(0)
path_arg = next(a for a in args[1:] if a.startswith("repos/"))
m = re.fullmatch(r"repos/\{owner\}/\{repo\}/issues/(\d+)(/[^?]*)?(\?.*)?", path_arg)
number, rest = m[1], m[2] or ""
if "POST" in args:
    value = int(next(a for a in args if a.startswith(("sub_issue_id=", "issue_id="))).split("=")[1])
    if rest == "/sub_issues":
        state["issues"].setdefault(number, {"subs": []})["subs"].append(value // 1000)
    elif str(value // 1000) not in os.environ.get("FAKE_GH_DROP_BLOCKER", "").split():
        state["issues"][number]["blocked_by"].append(value // 1000)
    save()
elif rest == "":
    print(json.dumps({"id": int(number) * 1000, "number": int(number)}))
elif rest == "/sub_issues":
    print(json.dumps([{"number": n} for n in state["issues"][number]["subs"]]))
else:
    print(json.dumps([{"number": n} for n in state["issues"][number]["blocked_by"]]))
"""


def setup(tmp_path: Path, tickets: dict[str, str]) -> tuple[Path, dict[str, str]]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    gh = tmp_path / "gh"
    gh.write_text(FAKE_GH)
    gh.chmod(0o755)
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"next": 10, "issues": {"9": {"subs": []}}}))
    folder = tmp_path / "tickets"
    folder.mkdir()
    for name, text in tickets.items():
        (folder / name).write_text(text)
    return folder, {**os.environ, "GH": str(gh), "FAKE_GH_STATE": str(state)}


def run(folder: Path, env: dict[str, str], *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "9", str(folder), *extra],
        capture_output=True,
        text=True,
        env=env,
    )


def issues(env: dict[str, str]) -> dict[str, dict]:
    return json.loads(Path(env["FAKE_GH_STATE"]).read_text())["issues"]


TICKETS = {
    "t1.md": "# Tracer\n\nBuild it. Evidence T1-foot stays as written.\n\n## Blocked by\n\nNone.\n",
    "t2.md": "# Mass\n\nReplaces T1's placeholder.\n\n## Blocked by\n\n- Blocked by T1\n",
    "t3.md": "# Skill\n\nAfter T1 and T2.\n\n## Blocked by\n\n- Blocked by T1\n- Blocked by T2\n",
}


def test_files_tickets_in_order_with_numbers_sub_issues_and_blockers(tmp_path):
    folder, env = setup(tmp_path, TICKETS)
    result = run(folder, env, "--label", "enhancement", "--label", "ready-for-agent")
    assert result.returncode == 0, result.stderr
    filed = issues(env)
    assert [filed[n]["title"] for n in ("10", "11", "12")] == ["Tracer", "Mass", "Skill"]
    assert "Evidence T1-foot stays as written" in filed["10"]["body"]
    assert "Replaces #10's placeholder" in filed["11"]["body"]
    assert "- Blocked by #10\n- Blocked by #11" in filed["12"]["body"]
    assert filed["11"]["blocked_by"] == [10] and sorted(filed["12"]["blocked_by"]) == [10, 11]
    assert filed["10"]["blocked_by"] == []
    assert filed["9"]["subs"] == [10, 11, 12]
    assert filed["10"]["labels"] == ["enhancement", "ready-for-agent"]
    assert "T3 -> #12 Skill" in result.stdout


def test_a_ticket_naming_a_later_ticket_files_nothing(tmp_path):
    folder, env = setup(tmp_path, {**TICKETS, "t1.md": "# Tracer\n\nBefore T2.\n"})
    result = run(folder, env)
    assert result.returncode == 2
    assert "t1.md names T2" in result.stderr
    assert list(issues(env)) == ["9"]


def test_a_blocker_that_is_not_a_ticket_files_nothing(tmp_path):
    folder, env = setup(tmp_path, {**TICKETS, "t2.md": "# Mass\n\n- Blocked by T7\n"})
    result = run(folder, env)
    assert result.returncode == 2
    assert "t2.md names T7, which is not a ticket" in result.stderr
    assert list(issues(env)) == ["9"]


def test_a_missing_title_or_a_gap_in_numbering_files_nothing(tmp_path):
    folder, env = setup(tmp_path, {"t1.md": "Tracer\n\nbody\n"})
    assert "first line must be '# <title>'" in run(folder, env).stderr
    folder, env = setup(tmp_path / "gap", {"t1.md": "# A\n", "t3.md": "# C\n"})
    result = run(folder, env)
    assert result.returncode == 2 and "no gap" in result.stderr
    assert list(issues(env)) == ["9"]


def test_a_blocker_github_did_not_keep_fails_the_read_back(tmp_path):
    folder, env = setup(tmp_path, TICKETS)
    result = run(folder, {**env, "FAKE_GH_DROP_BLOCKER": "11"})
    assert result.returncode == 1
    assert "#12 (T3) is blocked by [10], expected [10, 11]" in result.stderr


def test_dry_run_prints_the_plan_and_files_nothing(tmp_path):
    folder, env = setup(tmp_path, TICKETS)
    result = run(folder, env, "--dry-run")
    assert result.returncode == 0
    assert "T3: Skill (blocked by T1, T2)" in result.stdout
    assert list(issues(env)) == ["9"]
