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
    "committed-examples",
    "rule-coverage",
)


def check(
    tmp_path: Path, uv_sync_code: int = 0, failing: dict[str, str] | None = None
) -> tuple[subprocess.CompletedProcess[str], list]:
    """Run the copied check; each stub in failing prints its text and exits 1."""
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
    stubs |= {"../bin/uv": f'[ "$1" = sync ] && exit {uv_sync_code}; exit 0'}
    for name, body in stubs.items():
        path = root / name
        path.write_text(f'#!/bin/sh\necho "{path.name} $*" >>"{log}"\n{body}\n')
        path.chmod(0o755)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    env = {**os.environ, "PATH": f"{bin_}:/usr/bin:/bin"}
    result = subprocess.run(
        ["bash", str(root / "scripts/check")], capture_output=True, text=True, env=env
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
    assert block == [f"  line {i}" for i in range(11, 31)]
