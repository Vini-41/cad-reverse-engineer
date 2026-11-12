# cad-reverse-engineer

A skill and CLI that has a coding agent rebuild published hardware as CAD anyone can audit, number by number, against the paper. Built for Fable 5.2 and [benchmarked](docs/benchmark.md) across Anthropic's and OpenAI's frontier models, it runs in Claude Code, Codex and any agent that reads skills.

Papers rarely ship CAD. They give an envelope table in the supplement, a few labelled dimensions in a figure, a kinematic length in the methods, and part numbers for the servos. A reconstruction built from that mixes stated values with guesses, and once the STEP file exists, nobody can tell which number is which.

This project keeps that boundary visible and machine-checked:

1. **Ledger.** Every number a source states about the object is recorded as a verbatim quote, located in a SHA-256-pinned copy of the source. Numbers printed only inside figures are recorded as hashed image crops with a human-confirmed reading.
2. **Parameters.** The model can only get numbers from `params.yaml`, and each parameter declares its basis: `source`, `derived`, `measured` or `proposed`. The model file is linted so that it contains no dimension literals.
3. **Checks.** Published values become geometry checks (envelopes, pin pitches, masses, interference), evaluated on the built solids and compared with the ledger, never with the parameters.
4. **Coverage.** A sweep lists every stated quantity in the sources. Each one is either ledgered or skipped with a reason.
5. **Report.** `build/report.md` states what is verified, which parameters rest on proposed values, which conflicts between sources are still open, and which questions to send the authors.

```
$ cadrev check examples/legclaw-links
wrote build/parts/compression_linkage.step
...
VERIFIED: 0 errors, 2 warnings, 10/10 checks pass. Report: build/report.md
```

```
**VERIFIED**: 0 errors, 2 warnings. 10/10 geometry checks pass.
Of 15 parameters, 9 rest on sources, 0 on measured values and 6 on proposed values.
```

Here VERIFIED means that every number is accounted for and the geometry realises every checked source value. Anything the sources leave open stays listed as proposed, so the report never claims more than the evidence supports. A number read off a figure crop holds the status at VERIFIED PENDING REVIEW until a named reviewer confirms that reading; the example's Fig. 2A label has been confirmed.

## Two ways to build

The agent asks which you want before it starts:

- **The complete model.** Every part is built. Each value the sources leave open is proposed, beside the question that would settle it.
- **Known first.** Only the parts the sources settle completely are built and checked. The rest wait, each with its question, until you build on the model yourself or have the agent propose the rest.

## Install

### As a Claude Code plugin

```
/plugin marketplace add Vini-41/cad-reverse-engineer
/plugin install cad-reverse-engineer@cad-reverse-engineer
```

Then ask Claude something like *"reverse-engineer the gripper in this paper as CAD"*, or invoke `/cad-reverse-engineer`. The skill guides the agent through nine steps: scope, sources, ledger, released geometry, parameters, model, checks, joints and hand-over. Each step ends on a criterion the CLI can confirm.

### As a Codex plugin

```
codex plugin marketplace add Vini-41/cad-reverse-engineer
codex plugin add cad-reverse-engineer@cad-reverse-engineer
```

Codex's default sandbox blocks network access, which the CLI needs to download its dependencies. Allow it in `~/.codex/config.toml`:

```toml
[sandbox_workspace_write]
network_access = true
```

### As a skill for any agent

```
npx skills add Vini-41/cad-reverse-engineer
```

### Requirements

The plugin ships from [`plugin/`](plugin): the skill, its CLI's source and lockfile, and nothing else of this repo. The CLI runs locally and needs [uv](https://docs.astral.sh/uv/), with Python 3.10 to 3.13. Its first run downloads build123d, OCC and MuJoCo from PyPI (about a minute), at the versions in the lockfile. Under Codex, allow network access as [its install](#as-a-codex-plugin) says.

### As a standalone CLI

The CLI requires [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/Vini-41/cad-reverse-engineer
alias cadrev="$PWD/cad-reverse-engineer/plugin/skills/cad-reverse-engineer/cadrev"
cadrev init my-project
cadrev source my-project paper.pdf --id paper --kind paper --citation "Doe et al. 2026"
cadrev text my-project paper --page 4      # the exact text quotes are matched against
cadrev figures my-project paper            # extract embedded figures
cadrev crop my-project figures/paper/p004_01.jpg 850 160 1240 385 --name fig2a --zoom 2
cadrev coverage my-project                 # stated quantities not yet ledgered or skipped
cadrev check my-project                    # everything; writes build/
```

Outputs:

- `build/parts/*.step`: one STEP file per part.
- `build/assembly.step`: the assembly, with labelled instances.
- `build/overlays/*.png`: model edges drawn over figures.
- `build/report.md` and `build/report.json`: the verification report.

## Examples

[`examples/legclaw-links`](examples/legclaw-links) reconstructs three linkages of the leg-claw in Cheng et al., *Bioinspired Adaptive Leg-Claw Enables Robust Perching and Grasping for UAVs*, Advanced Science 2026 ([doi:10.1002/advs.202523518](https://doi.org/10.1002/advs.202523518)). Both sources are CC BY 4.0 and committed with it, so `cadrev check examples/legclaw-links` runs from a fresh clone; `scripts/check` runs it before every merge.

The example covers each kind of evidence: Table S2 envelopes from the DOCX supplement, quotes from the PDF methods, a figure-label crop from Fig. 2A, two recorded source conflicts, and proposed pin pitches with the author questions that would settle them.

[`examples/legclaw`](examples/legclaw) is the full LegClaw from the same sources, both legs and their mounts with their motion, exported as `build/model.mjcf`. A fresh agent built it from the skill alone; it reads the sources from `examples/legclaw-links/sources/`, and `scripts/check` runs it too.

[`examples/centrifuge`](examples/centrifuge) is the mini benchtop centrifuge of Soma Poór 2022, a static project checked against the authors' released STEP files; [`examples/cell-stretcher`](examples/cell-stretcher) the uniaxial cell stretcher of Kah et al. 2021, two lead screws driving one carriage, checked against the authors' laser-cut SVG sheets and STL; and [`examples/compact-sspg`](examples/compact-sspg) the COMPAct 7.2:1 planetary gearbox of Singh et al. 2025, its train checked from its tooth counts and against the authors' STL. Fresh agents built all three from the skill alone; `scripts/check` runs them too.

## Files

```
.claude-plugin/          the Claude Code marketplace
.agents/plugins/         the Codex marketplace
skills.sh.json           where npx skills finds the skill
plugin/                  the plugin, as it installs
  .claude-plugin/        its Claude Code manifest
  .codex-plugin/         its Codex manifest
plugin/skills/cad-reverse-engineer/
  SKILL.md               the workflow the agent follows
  references/            project file formats; the model contract
  tool/                  the cadrev Python package (build123d, pypdf, PyYAML, matplotlib)
tests/                   the cadrev tests
examples/                worked reconstructions
```

## Development

```bash
cd plugin/skills/cad-reverse-engineer/tool
uv sync --locked -p 3.12 --extra test
uv run pytest -q ../../../../tests
```

`scripts/check` is the repo's only CI, run locally before every merge. It sets this clone's `core.hooksPath` to `.githooks`, whose pre-commit hook ruff-formats staged Python.

## License

The code is under the MIT license. Each example's sources and figure crops keep the license and credit its README names: CC BY 4.0 for the articles and their files, MIT for COMPAct's STL.
