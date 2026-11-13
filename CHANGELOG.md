# Changelog

## v0.1.0

The first release of `cad-reverse-engineer`, a skill and CLI (`cadrev`) for rebuilding a published object, from a single part up to a mechanism, as a parametric build123d model that anyone can audit, number by number, against its sources.

### What it does

- **Ledger.** Every number a source states about the object is a verbatim quote located in a SHA-256-pinned copy of the source (PDF, DOCX, SVG cut sheet, released STEP or STL). A number printed only inside a figure is a hashed crop with a reading a named reviewer confirms.
- **Parameters.** The model takes its numbers only from `params.yaml`, each with a basis: `source`, `derived`, `measured` or `proposed`. `model.py` is linted to hold no dimension literals.
- **Checks.** Stated values become checks on the built solids (envelopes, diameters, distances, masses, interference, shape against a released body), compared with the ledger, never with the parameters. A mechanism names its joints, loops and gears; its stated motion is checked on the posed model, which exports to MuJoCo as `build/model.mjcf`.
- **Coverage.** A sweep lists every stated quantity in the sources; each one is ledgered or skipped with a reason.
- **Report.** `cadrev check` writes one STEP per part, the assembly, figure overlays and `build/report.md`: one status (VERIFIED, VERIFIED PENDING REVIEW, or a failing one), what rests on proposed values, open conflicts, and the questions to send the authors.

The skill takes the agent through nine stages (scope, sources, ledger, released geometry, parameters, model, checks, motion, hand-over), each ending on a criterion `cadrev` confirms. At the start the agent asks which build the user wants: the complete model, every value the sources leave open proposed beside the question that would settle it; or **known first**, only the parts the sources settle, built and checked, with the rest waiting until the user builds on it or has the agent propose them.

It is built for Fable 5.2 and [benchmarked](docs/benchmark.md) across Anthropic's and OpenAI's frontier models.

### Examples

One small example shows each kind of evidence, and four full reconstructions were each built by a fresh agent from the skill and the sources alone. `scripts/check` holds every one to the status its README states.

- `examples/legclaw-links`: three linkages of the LegClaw (Cheng et al., Advanced Science 2026), with Table S2 envelopes from the DOCX supplement, methods quotes, a figure-label crop, two source conflicts and proposed pin pitches.
- `examples/legclaw`: the full LegClaw, both legs and their mounts with their motion and tendons, exported to MuJoCo.
- `examples/centrifuge`: the mini benchtop centrifuge (Soma Poór, HardwareX 2022), a static project checked against the authors' released STEP files.
- `examples/cell-stretcher`: the uniaxial cell stretcher (Kah et al., HardwareX 2021), two lead screws driving one carriage, checked against laser-cut SVG sheets and STL.
- `examples/compact-sspg`: the COMPAct 7.2:1 single-stage planetary gearbox (Singh et al., arXiv 2025), its train checked by tooth counts and the output's posed turn.

### Install

- Claude Code: `/plugin marketplace add Vini-41/cad-reverse-engineer`, then `/plugin install cad-reverse-engineer@cad-reverse-engineer`.
- Codex: `codex plugin marketplace add Vini-41/cad-reverse-engineer`, then `codex plugin add cad-reverse-engineer@cad-reverse-engineer`.
- Any agent: `npx skills add Vini-41/cad-reverse-engineer`.

### Requirements

The CLI runs locally through [uv](https://docs.astral.sh/uv/) on Python 3.12 to 3.14. Its first run downloads build123d, OCC and MuJoCo from PyPI (about a minute) at the versions in the shipped lockfile, so it needs network access then. Under Codex, allow it with `network_access = true` under `[sandbox_workspace_write]` in `~/.codex/config.toml`; `cadrev` moves any cache the sandbox will not let it write under `TMPDIR`.
