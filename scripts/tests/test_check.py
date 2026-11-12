"""scripts/check, copied into a small repo laid out like this one, with the scripts it runs and uv
stubbed: each stub records how it was called."""

import os
import re
import shutil
import signal
import subprocess
import time
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "check"
STUBS = ("check-doc-pointers", "committed-examples")


def stubbed(
    tmp_path: Path,
    uv_sync_code: int = 0,
    failing: dict[str, str] | None = None,
    bodies: dict[str, str] | None = None,
    uv_run: str = "exit 0",
) -> tuple[Path, Path, dict[str, str]]:
    """Copy the check beside its stubs: each stub in failing prints its text and exits 1, each in
    bodies runs its shell body instead, and uv runs uv_run for any command but sync. Returns the
    copied check, the file each stub logs its call to, and the environment to run it in."""
    root = tmp_path / "repo"
    (root / "plugin/skills/cad-reverse-engineer/tool").mkdir(parents=True)
    (root / "scripts").mkdir()
    shutil.copy(SCRIPT, root / "scripts/check")
    log = tmp_path / "calls"
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    stubs = {f"scripts/{name}": "exit 0" for name in STUBS}
    stubs |= {
        f"scripts/{name}": f"printf '{text}'; exit 1" for name, text in (failing or {}).items()
    }
    stubs |= {f"scripts/{name}": body for name, body in (bodies or {}).items()}
    stubs |= {"../bin/uv": f'[ "$1" = sync ] && exit {uv_sync_code}; {uv_run}'}
    for name, body in stubs.items():
        path = root / name
        path.write_text(f'#!/bin/sh\necho "{path.name} $*" >>"{log}"\n{body}\n')
        path.chmod(0o755)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    return root / "scripts/check", log, {**os.environ, "PATH": f"{bin_}:/usr/bin:/bin"}


def check(
    tmp_path: Path,
    uv_sync_code: int = 0,
    failing: dict[str, str] | None = None,
    bodies: dict[str, str] | None = None,
    args: list[str] | None = None,
    uv_run: str = "exit 0",
    env: dict[str, str] | None = None,
) -> tuple[subprocess.CompletedProcess[str], list]:
    """Run the check copied beside its stubs, as stubbed() sets them, with args and env."""
    script, log, base = stubbed(tmp_path, uv_sync_code, failing, bodies, uv_run)
    result = subprocess.run(
        ["bash", str(script), *(args or [])],
        capture_output=True,
        text=True,
        env={**base, **(env or {})},
    )
    return result, log.read_text().splitlines() if log.exists() else []


def test_the_test_extra_is_synced_before_any_step(tmp_path):
    _, calls = check(tmp_path)
    assert calls[0] == "uv sync --locked --extra test"


def test_a_failed_sync_stops_before_any_step(tmp_path):
    result, calls = check(tmp_path, uv_sync_code=1)
    assert result.returncode == 1
    assert calls == ["uv sync --locked --extra test"]
    assert "uv sync" in result.stdout + result.stderr


def test_a_failed_step_reprints_the_end_of_its_output_under_its_name(tmp_path):
    lines = "".join(f"line {i}\\n" for i in range(1, 31))
    result, _ = check(tmp_path, failing={"check-doc-pointers": lines})
    assert result.returncode == 1
    name = "failed: agent-facing docs point only at files that exist"
    block = result.stdout.split(name + "\n")[1].split("failed: ")[0].splitlines()
    rerun = (
        "  rerun alone: "
        "(cd plugin/skills/cad-reverse-engineer/tool && ../../../../scripts/check-doc-pointers)"
    )
    assert block == [rerun, *(f"  line {i}" for i in range(11, 31))]


def test_the_last_line_names_the_unstaged_edits_the_examples_were_checked_without(tmp_path):
    left_out = "echo 'not staged, so left out of the copy: examples/a/model.py' >&2; exit 0"
    result, _ = check(tmp_path, bodies={"committed-examples": left_out})
    assert result.stdout.splitlines()[-1] == (
        "examples checked at their staged text: 1 unstaged edit or untracked file left out"
    )


def test_the_last_line_is_the_summary_when_nothing_is_left_out(tmp_path):
    result, _ = check(tmp_path)
    assert "left out" not in result.stdout.splitlines()[-1]


def test_lint_runs_only_the_type_and_ruff_steps(tmp_path):
    result, calls = check(tmp_path, args=["--lint"])
    assert result.returncode == 0
    assert calls[0] == "uv sync --locked --extra test"
    assert sorted(calls[1:]) == [
        "uv run pyright -p ../../../../pyrightconfig.json",
        "uv run ruff check ../../../..",
        "uv run ruff format --check ../../../..",
    ]
    assert result.stdout.splitlines()[-1] == "all steps passed"


def untimed(out: str) -> list[str]:
    """The check's output lines, each step's header without the time it ends on."""
    return [re.sub(r"^(== .*) \(\d+ s\)$", r"\1", line) for line in out.splitlines()]


def test_each_steps_header_names_how_long_it_took(tmp_path):
    result, _ = check(tmp_path, bodies={"check-doc-pointers": "sleep 1; exit 0"})
    # A one-second sleep measures 1 or 2 in bash's whole seconds.
    assert re.search(
        r"^== agent-facing docs point only at files that exist \([12] s\)$", result.stdout, re.M
    )
    assert re.search(r"^== pyright \(\d+ s\)$", result.stdout, re.M)


def waits_for(mine: Path, other: Path) -> str:
    """A stub body that marks mine, then passes once other is marked, or fails after 5 s."""
    wait = f"for _ in $(seq 50); do [ -e '{other}' ] && exit 0; sleep 0.1; done"
    return f"touch '{mine}'; {wait}; exit 1"


def test_steps_run_at_once(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    pyright = f'[ "$2" = pyright ] || exit 0; {waits_for(b, a)}'
    result, _ = check(tmp_path, bodies={"check-doc-pointers": waits_for(a, b)}, uv_run=pyright)
    assert result.returncode == 0, result.stdout


def test_guard_output_and_failures_follow_the_steps_order_whatever_finishes_first(tmp_path):
    slow_pyright = '[ "$2" = pyright ] && { sleep 1; echo types; exit 1; }; exit 0'
    bodies = {"check-doc-pointers": "echo pointers; exit 1"}
    result, _ = check(tmp_path, bodies=bodies, uv_run=slow_pyright)
    lines = untimed(result.stdout)
    pointers = "agent-facing docs point only at files that exist"
    assert lines[lines.index("== pyright") + 1] == "types"
    assert lines[lines.index(f"== {pointers}") + 1] == "pointers"
    assert lines.index("== pyright") < lines.index(f"== {pointers}")
    assert [line for line in lines if line.startswith("failed: ")] == [
        "failed: pyright",
        f"failed: {pointers}",
    ]


@pytest.mark.parametrize("sig", [signal.SIGINT, signal.SIGTERM], ids=["SIGINT", "SIGTERM"])
def test_an_interrupted_check_stops_every_step_it_started(tmp_path, sig):
    started, finished = tmp_path / "started", tmp_path / "finished"
    body = f"touch '{started}'; sleep 2; touch '{finished}'"
    script, _, env = stubbed(tmp_path, bodies={"check-doc-pointers": body})
    child = subprocess.Popen(
        ["bash", str(script)], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    deadline = time.monotonic() + 10
    while not started.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    child.send_signal(sig)
    assert child.wait(timeout=10) != 0
    time.sleep(3)
    assert not finished.exists()


def test_an_unknown_argument_runs_no_step(tmp_path):
    result, calls = check(tmp_path, args=["--fast"])
    assert result.returncode == 2
    assert calls == []
    assert "usage: scripts/check [--lint]" in result.stderr


def test_every_example_the_copy_holds_is_checked_for_its_documented_status(tmp_path):
    copy = tmp_path / "copy" / "examples"
    for name in ("alpha", "beta"):
        (copy / name).mkdir(parents=True)
        (copy / name / "project.yaml").write_text("format: 1\n")
    (copy / "notes").mkdir()  # not a project, so no example
    result, _ = check(tmp_path, bodies={"committed-examples": f"echo '{copy}'; exit 0"})
    steps = [line for line in untimed(result.stdout) if line.startswith("== examples/")]
    assert steps == [
        "== examples/alpha reaches its documented status",
        "== examples/beta reaches its documented status",
    ]


def test_guard_examples_the_copy_cannot_be_made_of_fail_and_none_is_checked(tmp_path):
    result, calls = check(tmp_path, failing={"committed-examples": "no index\\n"})
    assert result.returncode == 1
    failed = (
        "failed: the examples copy as a clone holds them\n  rerun alone: scripts/committed-examples"
    )
    assert failed in result.stdout
    assert not any("cadrev check" in call for call in calls)


def examples_copy(tmp_path: Path) -> dict[str, str]:
    """A committed-examples stub whose copy holds alpha and beta."""
    copy = tmp_path / "copy" / "examples"
    for name in ("alpha", "beta"):
        (copy / name).mkdir(parents=True)
        (copy / name / "project.yaml").write_text("format: 1\n")
        (copy / name / "README.md").write_text("Expected status: `VERIFIED`\n")
    return {"committed-examples": f"echo '{copy}'; exit 0"}


# A cadrev check that takes two seconds and prints the status every example's README expects.
SLOW_CHECK = '[ "$2" = cadrev ] && { sleep 2; echo "VERIFIED. Report: build/report.md"; }; exit 0'


def test_a_failed_step_that_runs_a_function_names_the_command_that_reruns_it(tmp_path):
    # uv's stub prints no status, so each example fails.
    result, _ = check(tmp_path, bodies=examples_copy(tmp_path))
    assert result.returncode == 1
    name = "failed: examples/alpha reaches its documented status"
    rerun = "  rerun alone: scripts/cadrev check examples/alpha"
    assert result.stdout.split(name + "\n")[1].splitlines()[0] == rerun


def test_an_example_slower_than_the_budget_fails(tmp_path):
    result, _ = check(
        tmp_path,
        bodies=examples_copy(tmp_path),
        uv_run=SLOW_CHECK,
        env={"EXAMPLE_SECONDS": "1"},
    )
    assert result.returncode == 1
    assert "failed: examples/alpha reaches its documented status" in result.stdout
    # A two-second sleep measures 2 or 3 in bash's whole seconds.
    assert re.search(r"examples/alpha took [23] s, over the 1 s an example may take", result.stdout)


def test_guard_an_example_within_the_budget_passes(tmp_path):
    result, _ = check(
        tmp_path,
        bodies=examples_copy(tmp_path),
        uv_run=SLOW_CHECK,
        env={"EXAMPLE_SECONDS": "60"},
    )
    assert result.returncode == 0


def test_an_edit_to_the_script_while_it_runs_takes_effect_only_on_the_next_run(tmp_path):
    # A step empties scripts/check partway through; the run still reaches its summary.
    emptied = ': > "$(dirname "$0")/check"; exit 0'
    result, _ = check(tmp_path, bodies={"check-doc-pointers": emptied})
    assert result.stdout.splitlines()[-1] == "all steps passed"
