"""The plugin as it ships from plugin/: what each channel's manifest names, its skills'
frontmatter, links and pinned CLI, and how the package starts in a sandbox."""

import json
import os
import re
import shutil
import subprocess
import sys
import tomllib

import pytest
import yaml
from conftest import REPO, SKILL, SKILLS

PLUGIN = REPO / "plugin"
PACKAGE = tomllib.loads((REPO / "pyproject.toml").read_text())["project"]
PIN = re.compile(r"cadrev==([0-9][\w.]*)")
# Named by its range: uvx otherwise takes the first Python it finds, which may be newer than any
# the package's pinned wheels are built for.
UVX = f"uvx --python '{PACKAGE['requires-python']}' cadrev=={PACKAGE['version']}"
OWN = f"cadrev-{os.getuid()}"
# build-model holds the file formats, which the other two read from beside it.
NAMES = ["ask-machinist", "build-model", "noob"]


def test_plugin_ships_only_what_its_channels_accept():
    listed = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "-co", "--exclude-standard", "plugin"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    shipped = [REPO / name for name in listed if (REPO / name).is_file()]
    assert len(shipped) > 5
    # Anthropic's plugin directory stops on any file over 5 MiB, and from an unverified publisher
    # on code or package configuration: the plugin is Markdown, manifests, its icon and license.
    assert [str(p) for p in shipped if p.stat().st_size > 5 * 2**20] == []
    kept = [
        p for p in shipped if p.suffix in (".md", ".png") or p.name in ("plugin.json", "LICENSE")
    ]
    assert sorted(map(str, set(shipped) - set(kept))) == []
    assert [str(p) for p in shipped if p.read_bytes().startswith(b"#!")] == []
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
    assert claude["version"] == PACKAGE["version"]
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


@pytest.mark.parametrize("name", NAMES)
def test_each_skill_runs_the_cli_itself_at_the_package_version(name):
    assert f"{UVX} --help" in (SKILLS / name / "SKILL.md").read_text()


@pytest.mark.parametrize("name", NAMES)
def test_each_skills_sandbox_line_gives_uv_directories_of_this_users(tmp_path, name):
    lines = (SKILLS / name / "SKILL.md").read_text().splitlines()
    line = next(text for text in lines if "UV_CACHE_DIR=" in text)
    bin, tmp = tmp_path / "bin", tmp_path / "tmp"
    for d in (bin, tmp):
        d.mkdir()
    uv = ("UV_CACHE_DIR", "UV_PYTHON_INSTALL_DIR", "UV_TOOL_DIR")
    echo = "".join(f'echo "{v}=${{{v}-}}"\n' for v in uv)
    (bin / "uvx").write_text(f'#!/bin/sh\n{echo}echo "args=$*"\n')
    (bin / "uvx").chmod(0o755)
    env = {"PATH": f"{bin}:/usr/bin:/bin", "HOME": str(tmp_path / "shut"), "TMPDIR": str(tmp)}
    out = subprocess.run(["sh", "-c", line], env=env, capture_output=True, text=True, check=True)
    assert dict(entry.split("=", 1) for entry in out.stdout.splitlines()) == {
        "UV_CACHE_DIR": f"{tmp / OWN}/uv",
        "UV_PYTHON_INSTALL_DIR": f"{tmp / OWN}/python",
        "UV_TOOL_DIR": f"{tmp / OWN}/tools",
        "args": f"--python {PACKAGE['requires-python']} cadrev=={PACKAGE['version']} --help",
    }


def test_every_pin_the_plugin_prints_is_the_package_version():
    docs = [*PLUGIN.rglob("*.md"), REPO / "README.md"]
    pins = [pin for doc in docs for pin in PIN.findall(doc.read_text())]
    assert len(pins) >= len(NAMES) and set(pins) == {PACKAGE["version"]}


def test_package_pins_every_runtime_package_at_the_version_the_lock_holds():
    # uvx reads no lockfile, so the package's own requirements are what reach a user.
    command = "uv export --frozen --no-dev --no-hashes --no-emit-project --format requirements-txt"
    out = subprocess.run(command.split(), cwd=REPO, capture_output=True, text=True, check=True)
    locked = {line for line in out.stdout.splitlines() if line and line[0] not in "# "}
    assert len(locked) > 10 and set(PACKAGE["dependencies"]) == locked


def test_repo_script_runs_the_working_tree_from_any_directory_at_the_locked_versions(tmp_path):
    def run(script, *args):
        command = [str(script), *(args or ["--help"])]
        return subprocess.run(command, cwd=tmp_path, capture_output=True, text=True)

    script = REPO / "scripts" / "cadrev"
    result = run(script)
    assert result.returncode == 0 and "usage: cadrev" in result.stdout, result.stderr
    # `cadrev python` is the Python the CLI runs on, for a script of the agent's own.
    code = "import build123d, cadrev; print(cadrev.__file__)"
    result = run(script, "python", "-c", code)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(REPO / "src" / "cadrev" / "__init__.py")
    # A copy whose pyproject.toml asks for more than its lock holds is refused, not re-resolved.
    copy = tmp_path / "copy"
    (copy / "scripts").mkdir(parents=True)
    shutil.copy(script, copy / "scripts" / "cadrev")
    shutil.copy(REPO / "uv.lock", copy / "uv.lock")
    text = (REPO / "pyproject.toml").read_text()
    assert "dependencies = [\n" in text
    grown = text.replace("dependencies = [\n", 'dependencies = [\n    "tomli-w",\n', 1)
    (copy / "pyproject.toml").write_text(grown)
    result = run(copy / "scripts" / "cadrev")
    assert result.returncode != 0 and "lockfile" in result.stderr


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


CACHES = ("XDG_CACHE_HOME", "MPLCONFIGDIR")
PROBE = f"""
import json, os
seen = {{v: os.environ.get(v, "") for v in {CACHES!r}}}  # before Matplotlib sets its own fallback
import matplotlib
print(json.dumps(seen | {{"plots": matplotlib.get_cachedir()}}))
"""


def start_cli(root, writable: bool, plant=None) -> dict[str, str]:
    """Start the CLI with HOME writable or not, and read the caches a script of the user's gets."""
    home, tmp = root / "home", root / "tmp"
    for d in (home, tmp):
        d.mkdir(parents=True)
    if plant:
        plant(tmp / OWN)
    start = "import sys; from cadrev import cli; cli.main(sys.argv[1:])"
    command = [sys.executable, "-c", start, "python", "-c", PROBE]
    env = {"PATH": "/usr/bin:/bin", "HOME": str(home), "TMPDIR": f"{tmp}/"}
    if not writable:
        home.chmod(0o555)
    try:
        run = subprocess.run(command, env=env, capture_output=True, text=True)
    finally:
        home.chmod(0o755)
    assert run.returncode == 0, run.stderr
    return json.loads(run.stdout.strip().splitlines()[-1])


def test_cli_moves_its_caches_to_tmpdir_only_where_a_sandbox_blocks_them(tmp_path):
    # A sandbox such as Codex's lets cadrev write its workspace and TMPDIR, not HOME. chmod stands
    # in for it, so this cannot run as root.
    seen = start_cli(tmp_path / "open", writable=True)
    assert {v: seen[v] for v in CACHES} == dict.fromkeys(CACHES, "")
    assert not (tmp_path / "open" / "tmp" / OWN).exists()
    seen = start_cli(tmp_path / "shut", writable=False)
    moved = tmp_path / "shut" / "tmp" / OWN
    assert seen == {
        "XDG_CACHE_HOME": f"{moved}/cache",
        "MPLCONFIGDIR": f"{moved}/matplotlib",
        "plots": f"{moved}/matplotlib",
    }


def test_cli_keeps_its_caches_out_of_a_tmpdir_entry_it_does_not_own(tmp_path):
    # TMPDIR may be the shared /tmp, where another user can plant the name first.
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    seen = start_cli(tmp_path / "shut", writable=False, plant=lambda p: p.symlink_to(elsewhere))
    assert {v: seen[v] for v in CACHES} == dict.fromkeys(CACHES, "")
    assert list(elsewhere.iterdir()) == []


def test_cli_still_starts_where_a_cache_directory_cannot_be_made(tmp_path):
    def plant(own):
        own.mkdir(mode=0o700)
        (own / "cache").write_text("a file where the directory would go")

    seen = start_cli(tmp_path / "shut", writable=False, plant=plant)
    assert seen["XDG_CACHE_HOME"] == ""
    assert seen["MPLCONFIGDIR"] == str(tmp_path / "shut" / "tmp" / OWN / "matplotlib")
