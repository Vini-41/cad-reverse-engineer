"""Every example project reaches the status its README states."""

import re
import shutil

import pytest
from conftest import REPO, cadrev

EXAMPLES = sorted(project.parent.name for project in (REPO / "examples").glob("*/project.yaml"))


@pytest.mark.slow
@pytest.mark.parametrize("name", EXAMPLES)
def test_example_reaches_the_status_its_readme_states(tmp_path, name):
    # The whole tree, since an example may read a neighbour's sources (legclaw reads
    # legclaw-links'), and none of its build output: the run writes its own.
    examples = tmp_path / "examples"
    ignored = shutil.ignore_patterns("build", "__pycache__")
    shutil.copytree(REPO / "examples", examples, ignore=ignored)
    stated = re.search(
        r"^Expected status: `(.+)`$", (examples / name / "README.md").read_text(), re.M
    )
    assert stated, f"examples/{name}/README.md states no expected status"
    code, out = cadrev("check", examples / name)
    last = out.strip().splitlines()[-1]
    assert last.startswith(f"{stated[1]}. "), last
    assert code == (0 if stated[1].startswith("VERIFIED") else 1)
