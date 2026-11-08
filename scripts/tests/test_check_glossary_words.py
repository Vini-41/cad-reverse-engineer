"""scripts/check-glossary-words, run as CI runs it, on a small repo laid out like this one."""

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "check-glossary-words"
SKILL = "plugin/skills/cad-reverse-engineer"
GLOSSARY = """# Glossary

**Datum**:
A named point on a part's solid.
_Avoid_: reference point, weld

**Tolerance**:
How far a value may stray.
_Avoid_: margin, allowance

**Reading**:
The label text of a figure crop.
_Avoid_: quote (for image evidence)

**Source**:
A registered document.
_Avoid_: reference, input
"""


def repo(tmp_path: Path, files: dict[str, str]) -> Path:
    for name, text in {"GLOSSARY.md": GLOSSARY, **files}.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(text)
    return tmp_path


def check(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), str(root)], capture_output=True, text=True)


def test_avoided_words_in_the_skill_its_references_and_the_tool_source_are_named(tmp_path):
    root = repo(
        tmp_path,
        {
            f"{SKILL}/SKILL.md": "intro\nWeld the pin; a weld-free clamp.\n",
            f"{SKILL}/references/format.md": "Each check has a margin.\n",
            f"{SKILL}/tool/src/cadrev/report.py": '"""Margins are shown."""\n# a reference point\n',
        },
    )
    result = check(root)
    assert result.returncode == 1
    assert result.stdout.splitlines() == [
        f'{SKILL}/SKILL.md:2: "Weld": say Datum',
        f'{SKILL}/SKILL.md:2: "weld": say Datum',
        f'{SKILL}/references/format.md:1: "margin": say Tolerance',
        f'{SKILL}/tool/src/cadrev/report.py:1: "Margins": say Tolerance',
        f'{SKILL}/tool/src/cadrev/report.py:2: "reference point": say Datum',
    ]


def test_guard_qualified_common_or_partial_words_and_other_files_pass(tmp_path):
    root = repo(
        tmp_path,
        {
            f"{SKILL}/SKILL.md": "Copy the quote; the input joint turns; welding.\n",
            "tests/test_report.py": "# a margin\n",
            "examples/legclaw/evidence.yaml": "quote: a 2 mm margin\n",
            "docs/notes.md": "an allowance\n",
        },
    )
    result = check(root)
    assert (result.returncode, result.stdout) == (0, "")


def test_avoided_word_written_as_a_quoted_name_passes_while_its_prose_use_is_named(tmp_path):
    root = repo(
        tmp_path,
        {
            f"{SKILL}/references/format.md": "MuJoCo's `margin` attribute holds the margin.\n",
            f"{SKILL}/tool/src/cadrev/motion.py": 'attrs = {"margin": 1}  # a margin\n',
        },
    )
    result = check(root)
    assert result.returncode == 1
    assert result.stdout.splitlines() == [
        f'{SKILL}/references/format.md:1: "margin": say Tolerance',
        f'{SKILL}/tool/src/cadrev/motion.py:1: "margin": say Tolerance',
    ]
