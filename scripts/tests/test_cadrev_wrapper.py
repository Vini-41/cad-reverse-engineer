"""The cadrev script the skill ships, and the repo's scripts/cadrev, run from another directory as
an agent's shell runs them."""

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def run(script: Path, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([str(script), "--help"], cwd=cwd, capture_output=True, text=True)


def test_the_skills_cadrev_runs_the_tool_from_any_directory(tmp_path):
    result = run(REPO / "skills/cad-reverse-engineer/cadrev", tmp_path)
    assert result.returncode == 0, result.stderr
    assert "usage: cadrev" in result.stdout


def test_guard_the_repos_cadrev_runs_the_tool_from_any_directory(tmp_path):
    result = run(REPO / "scripts/cadrev", tmp_path)
    assert result.returncode == 0, result.stderr
    assert "usage: cadrev" in result.stdout
