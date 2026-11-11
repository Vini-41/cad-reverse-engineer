""".githooks/commit-msg, run as git runs it, on a message file."""

import subprocess
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[2] / ".githooks" / "commit-msg"


def hook(tmp_path: Path, message: str) -> subprocess.CompletedProcess[str]:
    path = tmp_path / "COMMIT_EDITMSG"
    path.write_text(message, encoding="utf8")
    return subprocess.run([str(HOOK), str(path)], capture_output=True, text=True)


def test_a_subject_past_72_characters_stops_the_commit_naming_its_length(tmp_path):
    result = hook(tmp_path, "a" * 73 + "\n\nThe body.\n")
    assert result.returncode == 1 and "73 characters" in result.stderr


@pytest.mark.parametrize(
    "message",
    [
        "a" * 72 + "\n\n" + "b" * 200 + "\n",
        "# Please enter the commit message\n\n" + "a" * 72 + "\n# " + "c" * 100 + "\n",
        "é" * 72 + "\n",
        'Revert "' + "a" * 72 + '"\n',
        "fixup! " + "a" * 72 + "\n",
    ],
    ids=["at-72", "comments-skipped", "characters-not-bytes", "revert", "fixup"],
)
def test_guard_a_subject_of_72_characters_or_one_git_writes_passes(tmp_path, message):
    assert hook(tmp_path, message).returncode == 0
