"""scripts/check-doc-pointers, run as CI runs it, on a small repo laid out like this one."""

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "check-doc-pointers"
SKILL = "plugin/skills/cad-reverse-engineer"


def repo(tmp_path: Path, docs: dict[str, str]) -> Path:
    for name in (f"{SKILL}/references/project-format.md", "GLOSSARY.md"):
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text("# exists\n")
    for name, text in docs.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(text)
    return tmp_path


def check(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), str(root)], capture_output=True, text=True)


def test_broken_markdown_link_in_skill_fails(tmp_path):
    root = repo(
        tmp_path,
        {f"{SKILL}/SKILL.md": "intro\nsee [format](references/gone.md)\n"},
    )
    result = check(root)
    assert result.returncode == 1
    assert f"{SKILL}/SKILL.md:2: references/gone.md" in result.stdout


def test_broken_backticked_path_in_agent_docs_fails(tmp_path):
    root = repo(tmp_path, {"docs/agents/workflow.md": f"Read `{SKILL}/GONE.md`.\n"})
    result = check(root)
    assert result.returncode == 1
    assert f"docs/agents/workflow.md:1: {SKILL}/GONE.md" in result.stdout


def test_guard_pointers_that_name_files_or_no_repo_path_pass(tmp_path):
    skill = (
        "See [format](references/project-format.md#units), [uv](https://docs.astral.sh/uv/),"
        " [below](#steps) and `references/project-format.md`.\n"
        "Writes `build/report.md` and `build/parts/<name>.step`; `1/50` scale.\n"
    )
    agents = (
        f"Read `.scratch/handoff.md`, `GLOSSARY.md`, `{SKILL}/references/`"
        " and `Vini-41/cad-reverse-engineer`; load `/writing-for-agents`.\n"
    )
    root = repo(tmp_path, {f"{SKILL}/SKILL.md": skill, "AGENTS.md": agents})
    result = check(root)
    assert (result.returncode, result.stdout) == (0, "")
