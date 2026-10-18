"""scripts/check-doc-pointers, run as CI runs it, on a small repo laid out like this one."""

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "check-doc-pointers"


def repo(tmp_path: Path, docs: dict[str, str]) -> Path:
    for name in ("skills/cad-reverse-engineer/references/project-format.md", "GLOSSARY.md"):
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
        {"skills/cad-reverse-engineer/SKILL.md": "intro\nsee [format](references/gone.md)\n"},
    )
    result = check(root)
    assert result.returncode == 1
    assert "skills/cad-reverse-engineer/SKILL.md:2: references/gone.md" in result.stdout


def test_broken_backticked_path_in_agent_docs_fails(tmp_path):
    root = repo(
        tmp_path, {"docs/agents/domain.md": "Read `skills/cad-reverse-engineer/GONE.md`.\n"}
    )
    result = check(root)
    assert result.returncode == 1
    assert "docs/agents/domain.md:1: skills/cad-reverse-engineer/GONE.md" in result.stdout


def test_guard_pointers_that_name_files_or_no_repo_path_pass(tmp_path):
    skill = (
        "See [format](references/project-format.md#units), [uv](https://docs.astral.sh/uv/),"
        " [below](#steps) and `references/project-format.md`.\n"
        "Writes `build/report.md` and `build/parts/<name>.step`; `1/50` scale.\n"
    )
    agents = (
        "Read `.scratch/handoff.md`, `GLOSSARY.md`, `skills/cad-reverse-engineer/references/`"
        " and `Vini-41/cad-reverse-engineer`; load `/writing-for-agents`.\n"
    )
    root = repo(tmp_path, {"skills/cad-reverse-engineer/SKILL.md": skill, "AGENTS.md": agents})
    result = check(root)
    assert (result.returncode, result.stdout) == (0, "")
