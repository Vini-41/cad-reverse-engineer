"""The plugin as it ships from plugin/: what each channel's manifest names exists, and what the
plugin directory holds stays within what the channels accept."""

import json
import re
import subprocess
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
PLUGIN = REPO / "plugin"
SKILL = PLUGIN / "skills" / "cad-reverse-engineer"


def shipped() -> list[Path]:
    """Every file under plugin/ a clone holds: tracked, or new and not ignored."""
    listed = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "-co", "--exclude-standard", "plugin"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    return [REPO / name for name in listed if (REPO / name).is_file()]


def test_no_file_the_plugin_ships_is_over_5_mib():
    # Anthropic's plugin directory stops on any file over 5 MiB.
    big = [str(p.relative_to(REPO)) for p in shipped() if p.stat().st_size > 5 * 2**20]
    assert big == []


def test_the_plugin_ships_no_tests_examples_or_docs():
    stray = [
        str(p.relative_to(REPO))
        for p in shipped()
        if {"tests", "examples", "docs"} & set(p.relative_to(PLUGIN).parts)
    ]
    assert stray == []


def test_every_marketplace_installs_the_plugin_from_plugin_dir():
    claude = json.loads((REPO / ".claude-plugin" / "marketplace.json").read_text())
    codex = json.loads((REPO / ".agents" / "plugins" / "marketplace.json").read_text())
    assert [p["source"] for p in claude["plugins"]] == ["./plugin"]
    assert [p["source"] for p in codex["plugins"]] == [{"source": "local", "path": "./plugin"}]


def test_the_codex_manifest_matches_claudes_and_names_an_icon_it_ships():
    claude = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text())
    codex = json.loads((PLUGIN / ".codex-plugin" / "plugin.json").read_text())
    for key in ("name", "version", "description", "author", "license", "keywords"):
        assert codex[key] == claude[key], key
    interface = codex["interface"]
    assert interface["displayName"]
    assert 0 < len(interface["shortDescription"]) <= 30
    for icon in (interface["composerIcon"], interface["logo"]):
        assert icon.startswith("./") and (PLUGIN / icon).is_file()
    assert (PLUGIN / codex["skills"] / "cad-reverse-engineer" / "SKILL.md").is_file()


def test_skills_sh_finds_the_skill_under_a_path_it_names():
    paths = json.loads((REPO / "skills.sh.json").read_text())["paths"]
    assert [REPO / p / "cad-reverse-engineer" / "SKILL.md" for p in paths] == [SKILL / "SKILL.md"]


def test_the_plugin_carries_its_readme_and_the_repos_license():
    assert len((PLUGIN / "README.md").read_text().split()) >= 40
    assert (PLUGIN / "LICENSE").read_text() == (REPO / "LICENSE").read_text()


def test_skill_frontmatter_names_its_license_and_what_it_needs():
    text = (SKILL / "SKILL.md").read_text()
    front = yaml.safe_load(text.split("---\n")[1])
    assert front["license"] == "MIT"
    needs = front["compatibility"]
    assert len(needs) <= 500
    assert all(word in needs for word in ("uv", "3.10", "3.13", "network"))


def test_both_readmes_say_the_cli_runs_locally_and_downloads_on_first_run():
    for readme in (REPO / "README.md", PLUGIN / "README.md"):
        text = re.sub(r"\s+", " ", readme.read_text())
        for said in (
            "runs locally",
            "uv",
            "build123d, OCC and MuJoCo from PyPI",
            "Codex's default sandbox",
        ):
            assert said in text, f"{readme.relative_to(REPO)} does not say {said!r}"
