"""scripts/check, copied into a small repo laid out like this one, with the scripts it runs and uv
stubbed: each stub records how it was called."""

import os
import shutil
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "check"
STUBS = (
    "red-on-main",
    "check-doc-pointers",
    "check-glossary-words",
    "check-kind-branches",
    "check-linear",
    "committed-examples",
    "rule-coverage",
)


def check(
    tmp_path: Path,
    uv_sync_code: int = 0,
    failing: dict[str, str] | None = None,
    bodies: dict[str, str] | None = None,
    args: list[str] | None = None,
) -> tuple[subprocess.CompletedProcess[str], list]:
    """Run the copied check; each stub in failing prints its text and exits 1, and each in bodies
    runs its shell body instead."""
    root = tmp_path / "repo"
    (root / "skills/cad-reverse-engineer/tool").mkdir(parents=True)
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
    stubs |= {"../bin/uv": f'[ "$1" = sync ] && exit {uv_sync_code}; exit 0'}
    for name, body in stubs.items():
        path = root / name
        path.write_text(f'#!/bin/sh\necho "{path.name} $*" >>"{log}"\n{body}\n')
        path.chmod(0o755)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    env = {**os.environ, "PATH": f"{bin_}:/usr/bin:/bin"}
    result = subprocess.run(
        ["bash", str(root / "scripts/check"), *(args or [])],
        capture_output=True,
        text=True,
        env=env,
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
    result, _ = check(tmp_path, failing={"check-glossary-words": lines})
    assert result.returncode == 1
    name = "failed: the skill and tool source use none of GLOSSARY.md's avoided words"
    block = result.stdout.split(name + "\n")[1].split("failed: ")[0].splitlines()
    rerun = (
        "  rerun alone: "
        "(cd skills/cad-reverse-engineer/tool && ../../../scripts/check-glossary-words)"
    )
    assert block == [rerun, *(f"  line {i}" for i in range(11, 31))]


def test_a_failed_step_that_runs_a_function_names_the_script_that_reruns_it(tmp_path):
    result, _ = check(tmp_path, failing={"red-on-main": "misnamed\\n"})
    assert result.returncode == 1
    name = "failed: red-on-main: new tests are red holes or green guards"
    assert (
        result.stdout.split(name + "\n")[1].splitlines()[0] == "  rerun alone: scripts/red-on-main"
    )


def test_the_last_line_names_the_unstaged_edits_the_examples_were_checked_without(tmp_path):
    left_out = "echo 'not staged, so left out of the copy: examples/a/model.py' >&2; exit 0"
    result, _ = check(tmp_path, bodies={"committed-examples": left_out})
    assert result.stdout.splitlines()[-1] == (
        "examples checked at their staged text: 1 unstaged edit or untracked file left out"
    )


def test_the_last_line_is_the_summary_when_nothing_is_left_out(tmp_path):
    result, _ = check(tmp_path)
    assert "left out" not in result.stdout.splitlines()[-1]


def test_the_end_repeats_red_on_mains_count_past_the_examples_output(tmp_path):
    counted = "echo '10 red (holes), 1 green'; exit 0"
    result, _ = check(tmp_path, bodies={"red-on-main": counted})
    assert result.stdout.splitlines()[-1] == "red-on-main: 10 red (holes), 1 green"


def test_guard_the_end_names_no_count_where_red_on_main_printed_none(tmp_path):
    result, _ = check(tmp_path)
    assert not result.stdout.splitlines()[-1].startswith("red-on-main:")


def test_lint_runs_only_the_type_and_ruff_steps(tmp_path):
    result, calls = check(tmp_path, args=["--lint"])
    assert result.returncode == 0
    assert calls == [
        "uv sync --locked --extra test",
        "uv run pyright",
        "uv run ruff check ../../..",
        "uv run ruff format --check ../../..",
    ]
    assert result.stdout.splitlines()[-1] == "all steps passed"


def test_an_unknown_argument_runs_no_step(tmp_path):
    result, calls = check(tmp_path, args=["--fast"])
    assert result.returncode == 2
    assert calls == []
    assert "usage: scripts/check [--lint | --nightly]" in result.stderr


def test_every_example_the_copy_holds_is_checked_for_its_documented_status(tmp_path):
    copy = tmp_path / "copy" / "examples"
    for name in ("alpha", "beta"):
        (copy / name).mkdir(parents=True)
        (copy / name / "project.yaml").write_text("format: 1\n")
    (copy / "notes").mkdir()  # not a project, so no example
    result, _ = check(tmp_path, bodies={"committed-examples": f"echo '{copy}'; exit 0"})
    steps = [line for line in result.stdout.splitlines() if line.startswith("== examples/")]
    assert steps == [
        "== examples/alpha reaches its documented status",
        "== examples/beta reaches its documented status",
    ]


def examples_copy(tmp_path: Path, nightly: tuple[str, ...]) -> dict[str, str]:
    """A committed-examples stub whose copy holds alpha and beta, those named in nightly marked
    `Checked: nightly` in their README."""
    copy = tmp_path / "copy" / "examples"
    for name in ("alpha", "beta"):
        (copy / name).mkdir(parents=True)
        (copy / name / "project.yaml").write_text("format: 1\n")
        marker = "Checked: nightly\n" if name in nightly else ""
        (copy / name / "README.md").write_text(f"Expected status: `VERIFIED`\n{marker}")
    return {"committed-examples": f"echo '{copy}'; exit 0"}


def test_an_example_its_readme_marks_nightly_is_left_to_the_nightly_check(tmp_path):
    result, _ = check(tmp_path, bodies=examples_copy(tmp_path, nightly=("beta",)))
    steps = [line for line in result.stdout.splitlines() if line.startswith("== examples/")]
    assert steps == ["== examples/alpha reaches its documented status"]
    assert "examples/beta: checked nightly (scripts/check --nightly), not here" in result.stdout


def test_nightly_checks_only_the_examples_marked_nightly(tmp_path):
    result, calls = check(
        tmp_path, bodies=examples_copy(tmp_path, nightly=("beta",)), args=["--nightly"]
    )
    steps = [line for line in result.stdout.splitlines() if line.startswith("== ")]
    assert steps == ["== examples/beta reaches its documented status"]
    copy = tmp_path / "copy" / "examples"
    assert calls == [
        "uv sync --locked --extra test",
        "committed-examples ",
        f"uv run cadrev check {copy}/beta",
    ]
