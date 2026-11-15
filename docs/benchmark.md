# Benchmark

Three frontier models each rebuilt three published devices from their documents alone: nine fresh agents, each given only the skill and the sources. Every run ended at VERIFIED PENDING REVIEW, the furthest an agent gets before a person confirms its figure readings, in 25 to 69 minutes of work.

| | Fable 5.2 | Opus 5.5 | Sol |
|---|---|---|---|
| [Centrifuge](../examples/centrifuge) | 118 checks, 50 min | 93 checks, 46 min | 121 checks, 25 min |
| [COMPAct gearbox](../examples/compact-sspg) | 128 checks, 53 min | 140 checks, 69 min | 334 checks, 55 min |
| [Cell stretcher](../examples/cell-stretcher) | 105 checks, 50 min | 99 checks, 51 min | 3,399 checks, 49 min |

Every check passed in every run.

## What the runs caught

**A stated mass that belongs to another rotor.** The centrifuge paper gives its rotor 16 g; the rotor built from the authors' files weighs 13.15 g. Fable 5.2 recorded the conflict and named its cause: the 16 g is the PCR-strip rotor's, whose released body weighs exactly that. Sol recorded the conflict and kept the 16 g out of the check, without naming the cause. Opus 5.5 widened the tolerance to ±20% and passed the check.

**Sheet dimensions: left as questions, or probed.** The cell stretcher is cut from acrylic sheets. At Fable's and Opus's commit no probe read a cut file, so both left about 100 sheet dimensions proposed under one gap, and said so, rather than present them as sourced. At Sol's, a probe reads a cut file's regions, and Sol probed every sheet dimension: 3,226 probes of the authors' files, against Fable's 22.

**Two shortcuts, both closed.** Sol's first runs, at Fable's and Opus's commit, twice reached the status by a route that verified nothing. Its gearbox parts were the authors' own meshes, so each shape check compared a file with itself. Its cell stretcher took 13,426 vertex coordinates off a render of the cut sheets and entered them as measured values. The tool now refuses each ([#195](https://github.com/Vini-41/cad-reverse-engineer/issues/195), [#196](https://github.com/Vini-41/cad-reverse-engineer/issues/196)), and Sol's runs above rebuilt every part from params.

## Method

- **Under test:** the skill and its CLI: for Fable 5.2 and Opus 5.5 at `b8ac5d2` (2026-11-11), in Claude Code; for Sol (`gpt-6.1-sol`) at `v0.1.0` (2026-11-15), in Codex. Each at `xhigh` effort with no subagents.
- **Brief:** one fixed prompt for every run, naming the device and its sources. The agent read nothing else in the repo, worked in an empty directory, and no one answered its questions.
- **Counts:** from checking a copy of each project again afterwards, not from the run's own report. Minutes are the time the agent worked.
- **One run per model per device:** a record of what each did, not a ranking.

To add a model, rerun the same briefs at the commit under test and check each project again from a copy without `build/`.
