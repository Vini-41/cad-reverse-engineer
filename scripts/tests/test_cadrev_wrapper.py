"""The cadrev script the skill ships, and the repo's scripts/cadrev, run from another directory as
an agent's shell runs them."""

import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def run(script: Path, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([str(script), "--help"], cwd=cwd, capture_output=True, text=True)


def test_the_skills_cadrev_runs_the_tool_from_any_directory(tmp_path):
    result = run(REPO / "plugin/skills/cad-reverse-engineer/cadrev", tmp_path)
    assert result.returncode == 0, result.stderr
    assert "usage: cadrev" in result.stdout


def test_guard_the_repos_cadrev_runs_the_tool_from_any_directory(tmp_path):
    result = run(REPO / "scripts/cadrev", tmp_path)
    assert result.returncode == 0, result.stderr
    assert "usage: cadrev" in result.stdout


def test_the_skills_cadrev_runs_only_the_locked_versions(tmp_path):
    skill = tmp_path / "cad-reverse-engineer"
    source = REPO / "plugin/skills/cad-reverse-engineer"
    ignored = shutil.ignore_patterns(".venv", "__pycache__", "*.egg-info")
    shutil.copytree(source, skill, ignore=ignored)
    pyproject = skill / "tool" / "pyproject.toml"
    text = pyproject.read_text()
    assert '    "pyyaml>=6",\n' in text
    pyproject.write_text(text.replace('    "pyyaml>=6",\n', '    "pyyaml>=6",\n    "six",\n'))
    result = run(skill / "cadrev", tmp_path)
    assert result.returncode != 0
    assert "lockfile" in result.stderr
