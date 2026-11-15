# Benchmark

Three frontier models each rebuilt three published devices from their documents alone: nine fresh agents, each given only the skill and the sources. Every run ended at VERIFIED PENDING REVIEW, the furthest an agent gets before a person confirms its figure readings, in 28 to 69 minutes of work.

| | Fable 5.2 | Opus 5.5 | Sol |
|---|---|---|---|
| [Centrifuge](../examples/centrifuge) | 118 checks, 50 min | 93 checks, 46 min | 190 checks, 28 min |
| [COMPAct gearbox](../examples/compact-sspg) | 128 checks, 53 min | 140 checks, 69 min | 58 checks, 40 min † |
| [Cell stretcher](../examples/cell-stretcher) | 105 checks, 50 min | 99 checks, 51 min | 315 checks, 31 min † |

Every check passed in every run. † Reached by a shortcut the tool now refuses, described below.

## What the runs caught

**A stated mass that belongs to another rotor.** The centrifuge paper gives its rotor 16 g; the rotor built from the authors' files weighs 13.15 g. Fable 5.2 recorded the conflict and named its cause: the 16 g is the PCR-strip rotor's, whose released body weighs exactly that. Opus 5.5 and Sol widened the tolerance to ±20% and passed the check.

**A hundred dimensions left as questions.** The cell stretcher is cut from acrylic sheets, and at the benchmark's commit no probe read a cut file. Fable 5.2 and Opus 5.5 left about 100 sheet dimensions proposed under one gap, and said so, rather than present them as sourced.

**Two shortcuts, both now closed.** Sol was the fastest, and twice reached the status by a route that verified nothing. Its gearbox parts were the authors' own meshes, so each shape check compared a file with itself. Its cell stretcher took 13,426 vertex coordinates off a render of the cut sheets and entered them as measured values. Both passed every rule the tool had; it now refuses each ([#195](https://github.com/Vini-41/cad-reverse-engineer/issues/195), [#196](https://github.com/Vini-41/cad-reverse-engineer/issues/196)).

## Method

- **Under test:** the skill and its CLI at `b8ac5d2` (2026-11-11). Fable 5.2 and Opus 5.5 ran in Claude Code, Sol (`gpt-6.1-sol`) in Codex, each at `xhigh` effort with no subagents.
- **Brief:** [`dogfood/brief.md`](dogfood/brief.md), word for word, in an empty directory.
- **Counts:** from checking a copy of each project again afterwards, not from the run's own report. Minutes are the time the agent worked.
- **One run per model per device:** a record of what each did, not a ranking.

To add a model, rerun the same briefs at the commit under test and check each project again from a copy without `build/`.
