"""The plugin as it ships from plugin/: what each channel's manifest names, its skills'
frontmatter and links, and the cadrev script that runs the tool."""

import json
import os
import re
import shutil
import subprocess

import pytest
import yaml
from conftest import REPO, SKILL, SKILLS

PLUGIN = REPO / "plugin"
# build-model ships the CLI and the file formats; ask-machinist uses them from beside it.
NAMES = ["ask-machinist", "build-model"]


def test_plugin_ships_only_what_its_channels_accept():
    listed = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "-co", "--exclude-standard", "plugin"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    shipped = [REPO / name for name in listed if (REPO / name).is_file()]
    assert len(shipped) > 20
    # Anthropic's plugin directory stops on any file over 5 MiB.
    assert [str(p) for p in shipped if p.stat().st_size > 5 * 2**20] == []
    stray = {"tests", "examples", "docs"}
    assert [str(p) for p in shipped if stray & set(p.relative_to(PLUGIN).parts)] == []
    assert (PLUGIN / "LICENSE").read_text() == (REPO / "LICENSE").read_text()
    assert len((PLUGIN / "README.md").read_text().split()) >= 40


def test_every_channel_installs_the_plugin_from_plugin_and_finds_its_skills():
    claude = json.loads((REPO / ".claude-plugin" / "marketplace.json").read_text())
    codex = json.loads((REPO / ".agents" / "plugins" / "marketplace.json").read_text())
    assert [p["source"] for p in claude["plugins"]] == ["./plugin"]
    assert [p["source"] for p in codex["plugins"]] == [{"source": "local", "path": "./plugin"}]
    paths = json.loads((REPO / "skills.sh.json").read_text())["paths"]
    assert [(REPO / p).resolve() for p in paths] == [SKILLS]
    assert sorted(d.name for d in SKILLS.iterdir() if (d / "SKILL.md").is_file()) == NAMES
    claude = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text())
    codex = json.loads((PLUGIN / ".codex-plugin" / "plugin.json").read_text())
    for key in ("name", "version", "description", "author", "license", "keywords"):
        assert codex[key] == claude[key], key
    interface = codex["interface"]
    assert interface["displayName"] and 0 < len(interface["shortDescription"]) <= 30
    for icon in (interface["composerIcon"], interface["logo"]):
        assert icon.startswith("./") and (PLUGIN / icon).is_file()
    # OpenAI's directory lists a plugin whose skill runs a local program as Desktop only.
    assert codex["requires_local_executor"] is True
    assert 0 < len(interface["capabilities"]) <= 20
    assert all(0 < len(label) <= 120 for label in interface["capabilities"])
    assert (PLUGIN / codex["skills"]).resolve() == SKILLS


@pytest.mark.parametrize("name", NAMES)
def test_skill_frontmatter_names_itself_its_license_and_what_it_needs(name):
    front = yaml.safe_load((SKILLS / name / "SKILL.md").read_text().split("---\n")[1])
    assert front["name"] == name and front["license"] == "MIT"
    assert 0 < len(front["description"]) <= 1024
    needs = front["compatibility"]
    assert len(needs) <= 500 and all(word in needs for word in ("uv", "3.12", "3.14", "network"))
    # The CLI ships in build-model alone, and the other skill says it is used from beside it.
    assert (SKILLS / name / "cadrev").is_file() == (name == SKILL.name)
    assert name == SKILL.name or "build-model skill installed beside it" in needs


def test_every_relative_link_in_the_skills_names_a_file_and_a_heading_in_it():
    def headings(doc) -> set[str]:
        """Each heading of a Markdown file as the anchor a link names it by."""
        found = re.findall(r"^#+ (.*)$", doc.read_text(), re.M)
        return {re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-") for heading in found}

    docs = [SKILLS / name / "SKILL.md" for name in NAMES]
    docs += sorted((SKILL / "references").glob("*.md"))
    links = [
        (doc, target) for doc in docs for target in re.findall(r"\]\(([^)\s]+)\)", doc.read_text())
    ]
    relative = [(doc, t) for doc, t in links if not re.match(r"[a-z][a-z0-9+.-]*:", t)]
    assert len(relative) > 10
    for doc, target in relative:
        path, _, anchor = target.partition("#")
        file = (doc.parent / path).resolve() if path else doc
        where = f"{doc.parent.name}/{doc.name}"
        assert file.is_file(), f"{where} links to {target}, which is no file"
        # A skill reaches another only as it is installed: beside it, under the same directory.
        assert SKILLS in file.parents, f"{where} links to {target}, outside the skills"
        assert not anchor or anchor in headings(file), f"{where} links to {target}: no heading"


def test_cadrev_script_runs_the_tool_from_any_directory_at_the_locked_versions_only(tmp_path):
    def run(script, *args):
        command = [str(script), *(args or ["--help"])]
        return subprocess.run(command, cwd=tmp_path, capture_output=True, text=True)

    result = run(SKILL / "cadrev")
    assert result.returncode == 0 and "usage: cadrev" in result.stdout, result.stderr
    # `cadrev python` is the Python the CLI runs on, for a script of the agent's own.
    result = run(SKILL / "cadrev", "python", "-c", "import build123d, cadrev; print('own')")
    assert result.returncode == 0 and result.stdout == "own\n", result.stderr
    # A copy whose pyproject.toml asks for more than its lock holds is refused, not re-resolved.
    skill = tmp_path / SKILL.name
    shutil.copytree(SKILL, skill, ignore=shutil.ignore_patterns(".venv", "__pycache__"))
    pyproject = skill / "tool" / "pyproject.toml"
    text = pyproject.read_text()
    assert '    "pyyaml>=6",\n' in text
    pyproject.write_text(text.replace('    "pyyaml>=6",\n', '    "pyyaml>=6",\n    "six",\n'))
    result = run(skill / "cadrev")
    assert result.returncode != 0 and "lockfile" in result.stderr


SEEN = ("UV_CACHE_DIR", "UV_PYTHON_INSTALL_DIR", "UV_PROJECT_ENVIRONMENT", "XDG_CACHE_HOME")
SEEN += ("MPLCONFIGDIR",)


def launch(tmp_path, writable: bool) -> dict[str, str]:
    """Run a copy of the script with HOME and the plugin's tool/ writable or not; the cache
    variables and arguments a stand-in uv receives."""
    skill, home, tmp, bin = (tmp_path / d for d in ("skill", "home", "tmp", "bin"))
    for d in (skill / "tool", home, tmp, bin):
        d.mkdir(parents=True)
    shutil.copy(SKILL / "cadrev", skill / "cadrev")
    echo = "".join(f'echo "{v}=${{{v}-}}"\n' for v in SEEN)
    (bin / "uv").write_text(f'#!/bin/sh\n{echo}echo "args=$*"\n')
    (bin / "uv").chmod(0o755)
    locked = [] if writable else [skill / "tool", home]
    for d in locked:
        d.chmod(0o555)
    env = {"PATH": f"{bin}:/usr/bin:/bin", "HOME": str(home), "TMPDIR": f"{tmp}/"}
    try:
        command = [str(skill / "cadrev"), "check", "my project"]
        out = subprocess.run(command, env=env, capture_output=True, text=True, check=True).stdout
    finally:
        for d in locked:
            d.chmod(0o755)
    return dict(line.split("=", 1) for line in out.splitlines())


def test_cadrev_script_moves_its_caches_to_tmpdir_only_where_a_sandbox_blocks_them(tmp_path):
    # A sandbox such as Codex's lets cadrev write its workspace and TMPDIR, not HOME or the
    # installed plugin's tool/.venv. chmod stands in for it, so this cannot run as root.
    seen = launch(tmp_path / "open", writable=True)
    assert {v: seen[v] for v in SEEN} == dict.fromkeys(SEEN, "")
    seen = launch(tmp_path / "shut", writable=False)
    tmp = tmp_path / "shut" / "tmp" / f"cadrev-{os.getuid()}"
    assert seen["UV_PROJECT_ENVIRONMENT"].startswith(f"{tmp}/venv-")
    assert {v: seen[v] for v in SEEN if v != "UV_PROJECT_ENVIRONMENT"} == {
        "UV_CACHE_DIR": f"{tmp}/cache/uv",
        "UV_PYTHON_INSTALL_DIR": f"{tmp}/python",
        "XDG_CACHE_HOME": f"{tmp}/cache",
        "MPLCONFIGDIR": f"{tmp}/matplotlib",
    }
    assert seen["args"].endswith("cadrev check my project")
