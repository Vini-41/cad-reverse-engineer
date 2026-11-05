"""scripts/check-cli-imports, run as CI runs it, on a small repo laid out like this one."""

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "check-cli-imports"
TESTS = "skills/cad-reverse-engineer/tool/tests"


def check(tmp_path: Path, text: str) -> subprocess.CompletedProcess[str]:
    (tmp_path / TESTS).mkdir(parents=True)
    (tmp_path / TESTS / "test_cadrev.py").write_text(text)
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(tmp_path)], capture_output=True, text=True
    )


def test_test_importing_a_cadrev_module_but_the_cli_fails(tmp_path):
    result = check(tmp_path, "from cadrev import cli, sources\nimport cadrev.units\n")
    assert result.returncode == 1
    assert result.stdout.splitlines() == [
        f"{TESTS}/test_cadrev.py:1: imports cadrev.sources; tests import only cadrev.cli",
        f"{TESTS}/test_cadrev.py:2: imports cadrev.units; tests import only cadrev.cli",
    ]


def test_guard_tests_importing_only_the_cli_pass(tmp_path):
    # Its near misses: a package whose name begins with cadrev, and another package.
    text = "from cadrev import cli\nimport cadrevolt\nfrom build123d import Box\n"
    result = check(tmp_path, text)
    assert result.returncode == 0
    assert result.stdout == ""
