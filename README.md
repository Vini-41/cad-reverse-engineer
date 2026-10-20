# cad-reverse-engineer

A Claude Code skill and CLI for rebuilding published hardware as CAD that anyone can audit, number by number, against the paper.

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

## Install

### As a Claude Code plugin

```
/plugin marketplace add Vini-41/cad-reverse-engineer
/plugin install cad-reverse-engineer@cad-reverse-engineer
```

Then ask Claude something like *"reverse-engineer the gripper in this paper as CAD"*, or invoke `/cad-reverse-engineer`. The skill guides Claude through seven steps: scope, sources, ledger, parameters, model, checks and hand-over. Each step ends on a criterion the CLI can confirm.

### As a standalone CLI

The CLI requires [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/Vini-41/cad-reverse-engineer
alias cadrev="$PWD/cad-reverse-engineer/skills/cad-reverse-engineer/cadrev"
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

[`examples/legclaw-links`](examples/legclaw-links) reconstructs three linkages of the leg-claw in Cheng et al., *Bioinspired Adaptive Leg-Claw Enables Robust Perching and Grasping for UAVs*, Advanced Science 2026 ([doi:10.1002/advs.202523518](https://doi.org/10.1002/advs.202523518)). Both sources are CC BY 4.0 and committed with it, so `cadrev check examples/legclaw-links` runs from a fresh clone; CI runs it on every push.

The example covers each kind of evidence: Table S2 envelopes from the DOCX supplement, quotes from the PDF methods, a figure-label crop from Fig. 2A, two recorded source conflicts, and proposed pin pitches with the author questions that would settle them.

[`examples/legclaw`](examples/legclaw) is the full LegClaw from the same sources, both legs and their mounts with their motion, exported as `build/model.mjcf`. A fresh agent built it from the skill alone; it reads the sources from `examples/legclaw-links/sources/`, and CI runs it on every push too.

## Files

```
.claude-plugin/          plugin and marketplace manifests
skills/cad-reverse-engineer/
  SKILL.md               the workflow Claude follows
  references/            project file formats; the model contract
  tool/                  the cadrev Python package (build123d, pypdf, PyYAML, matplotlib)
examples/                worked reconstructions
```

## Development

```bash
cd skills/cad-reverse-engineer/tool
uv sync --locked -p 3.12 --extra test
uv run pytest -q
```

`scripts/check` runs every CI step locally, and sets this clone's `core.hooksPath` to `.githooks`, whose pre-commit hook ruff-formats staged Python.

## License

The code is under the MIT license. The example's sources and figure crop come from the CC BY 4.0 article cited above and keep that license and attribution.
