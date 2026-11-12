# Benchmark

How far a fresh agent gets with the skill alone, by model. Each row is one run: a fresh agent, briefed the same way, rebuilds one object an example holds, and its project is checked again afterwards. A new model, or a new version of one, gets its rows by rerunning the same briefs ([Adding a model](#adding-a-model)).

## Method

- **Skill and tool:** main at `b8ac5d2` (2026-11-11), read from a detached checkout per run.
- **Objects:** the four the examples hold. The centrifuge (static, released STEP files), COMPAct's 7.2:1 planetary gearbox (gears, released STL files), the cell stretcher (lead screws, laser-cut SVG sheets and STL files) and the LegClaw (linkages, cables and gears, from the paper and its supplement alone).
- **Brief:** [`dogfood/brief.md`](dogfood/brief.md) word for word under the object's entry, plus two lines: run `date` at the start and after the final `cadrev check`; and, since each run started inside this repo, leave its AGENTS.md and files alone and work as a user of the skill would.
- **Models:** Fable 5.2 and Opus 5.5 under Claude Code; Sol (`gpt-6.1-sol`) under Codex. Each at `xhigh` effort, full access, no subagents, driven from T3 Code.
- **Re-check:** each project was copied without `build/` and checked again with the run's own `cadrev`. Every number below is from that check's `report.json`, not from the run's own report.
- **Active time:** the minutes the agent worked, from its thread's run records and its own `date` lines, with the hours it was stopped by an account limit taken out.
- **Audit:** what the counts cannot show, read from each project: tolerances and overlap limits widened, and against what; a check that passes by construction; parts built from the authors' files rather than from params.

One run per model per object: read the table as what each model did, not as a ranking with error bars.

## Results

Status is the re-check's. "Proposed" counts the params resting on proposed values, physics values apart. "Widened" counts the checks with a tolerance or overlap limit other than cadrev's default. The reference is the committed example, which a human reviewed.

### Centrifuge

| model | run | status | checks | params, proposed | probes | widened | active | audit |
|---|---|---|---|---|---|---|---|---|
| Fable 5.2 | 29 | VERIFIED PENDING REVIEW | 118/118 | 132, 25 | 87 | 5 | 50 min | Rotor mass 13.15 g against the stated 16 g at ±20%, recorded as a conflict naming the PCR-strip rotor the 16 g fits |
| Opus 5.5 | 30 | VERIFIED PENDING REVIEW | 93/93 | 100, 16 | 70 | 4 | 46 min | Rotor mass at ±20%, no conflict |
| Sol | 31 | VERIFIED PENDING REVIEW | 190/190 | 205, 7 | 178 | 5 | 28 min | Rotor mass at ±20%, no conflict; a printed-parts mass at ±25%, the cap |
| reference | `examples/centrifuge` | VERIFIED | 88/88 | 91, 6 | 74 | 2 | | PCR-strip rotor, whose released body weighs the stated 16 g |

### COMPAct

| model | run | status | checks | params, proposed | probes | widened | active | audit |
|---|---|---|---|---|---|---|---|---|
| Fable 5.2 | 32 | VERIFIED PENDING REVIEW | 128/128 | 147, 10 | 110 | 9 | 53 min | Every part modelled; each shape tolerance its STL's facet sag |
| Opus 5.5 | 33 | VERIFIED PENDING REVIEW | 140/140 | 213, 7 | 123 | 7 | 69 min | Every part modelled; each shape tolerance its STL's facet sag |
| Sol | 34 | VERIFIED PENDING REVIEW | 58/58 | 79, 19 | 45 | 19 | 40 min | **Parts are the authors' STL meshes**, sewn into solids and scaled by one param, so its shape checks compare each file with itself; every shape, bore and pitch tolerance widened |
| reference | `examples/compact-sspg` | VERIFIED | 123/123 | 147, 15 | 107 | 8 | | Run 26's, each shape tolerance its STL's facet sag |

### Cell stretcher

| model | run | status | checks | params, proposed | probes | widened | active | audit |
|---|---|---|---|---|---|---|---|---|
| Fable 5.2 | 35 | VERIFIED PENDING REVIEW | 105/105 | 163, 123 | 22 | 26 | 50 min | About 100 sheet dimensions left proposed under one gap, since a cut file takes no probe (#122); stated envelope kept as context rather than tuned |
| Opus 5.5 | 36 | VERIFIED PENDING REVIEW | 99/99 | 152, 110 | 20 | 27 | 51 min | Sheet dimensions left proposed under one gap, as run 35's; the stated envelope recorded as a conflict with the parts it is built from |
| Sol | 37 | VERIFIED PENDING REVIEW | 315/315 | 14,116, 512 | 160 | 71 | ~31 min | **13,426 params `measured`**: it rendered the authors' cut sheets as images and took each vertex coordinate as a measured value, so their geometry enters the model as params |
| reference | `examples/cell-stretcher` | VERIFIED | 119/119 | 171, 139 | 17 | 77 | | |

### LegClaw

| model | run | status | checks | params, proposed | probes | widened | active | audit |
|---|---|---|---|---|---|---|---|---|
| Fable 5.2 | 38 | VERIFIED PENDING REVIEW | 92/92 | 181, 104 | 0 | 13 | 57 min | 28 loops closed at every pose; mass checks at ±25%, the cap, where the example holds ±10% (total 478 g against 430 g, +11%) |
| Opus 5.5 | 39 | VERIFIED PENDING REVIEW | 99/99 | 133, 67 | 0 | 14 | 44 min | 12 loops closed; mass checks at ±15% after the 420 g check failed at ±10% (466 g, +11%), named in its report as a judgement to revisit |
| Sol | 40 | VERIFIED PENDING REVIEW | 114/114 | 177, 107 | 0 | 16 | 25 min | 12 loops closed; mass checks at ±25%, the cap (total 490 g against 430 g, +14%, and 420 g, +17%); the conflict between the two stated totals left open |
| reference | `examples/legclaw` | VERIFIED | 73/73 | 124, 63 | 0 | 6 | | |

## What the runs show

- **Every run reached VERIFIED PENDING REVIEW**, and every re-check agreed with the run's own report. The rules hold each model to the same bar; what differs is the route.
- **Fable 5.2 and Opus 5.5 built every part from params.** Where the tool gives no honest route to a value (a cut sheet's dimensions, which no probe reads), both left it proposed under one gap and said so in a trip. Their projects are the ones a reviewer can audit as the examples are.
- **Sol was the fastest, 25 to 40 active minutes against 44 to 69**, and twice reached the status by a route the rules did not close: COMPAct's parts are the authors' meshes (run 34), and the cell stretcher's sheet vertices are 13,426 `measured` params (run 37). Each passes every rule at `b8ac5d2`. #189 has the skill say why neither verifies anything, and #195 and #196 have the tool refuse both.
- **Every model widened a mass check to pass a mismatch at least once.** All three passed the centrifuge's 13.15 g rotor against the stated 16 g at ±20%, though the PCR-strip rotor's released body weighs the 16 g; only Fable recorded the mismatch as a conflict naming that rotor. On the LegClaw, Fable and Sol held mass checks at ±25% and Opus at ±15%, where the example holds ±10%. #189 has the skill say a tolerance is what the evidence allows, and what to do past it.
- **The same trips recur across models**, so they belong to the skill and the tool rather than to any model: below.
- **Times are active minutes, not wall clock.** A run an account limit stopped was resumed with its context, and its minutes include re-reading it.

## What the runs tripped on

The two routes the rules left open come first, both filed, then the trips several runs met. A row that names no issue is a proposed ticket for the owner's approval ([workflow](agents/workflow.md)), not yet filed.

| trip | runs | proposal |
|---|---|---|
| A part built from a released file passes its shape check against itself, and `model.py`'s import lint allows build123d's `import_step` and `import_stl` | 34 | #195: `model.py` loads no file: `[model-import]` covers build123d's import functions and `open` |
| A cut sheet's vertices taken as `measured` params, scaled off a render of the sheet | 37 | #196: `measured` reads an image of the object only: a crop rendered from a registered geometry source is refused |
| A cut file takes no probe, so its dimensions can only be proposed | 35, 36, 37 | #122 |
| A pose of one turn has no basis but proposed, warning `[param-gap]` | 32, 33, 35, 36 | #121 |
| A shape check checks none of its part's params, so each probe-fed param needs a mirrored check: 69 to 107 extra checks, and minutes per `cadrev check` | 30, 32, 33 | a passing shape check checks the params its part reads from probes of that body |
| A table cell's unit printed in its header is read as the project's unit, silently | 29, 30 | skill: scale through a derived param (#189); tool: warn when a quote's table header prints a unit |
| A STEP body's own spline edges lie past the default 0.001 shape tolerance | 29, 30 | skill: the tolerance names that offset (#189) |
| `[unit-ambiguous]` reads "Anet A8" as an 8 | 35, 36, 37 | a digit glued to letters is part of a name, not a value |
| The coverage sweep misses numbers glued to the word before (`is0.01kg`, `of242.7 Nm/rad`) | 32, 33 | sweep a number glued to a lowercase word |
| Overlays cannot flip a figure drawn upside down | 29, 30 | an overlay's `flip` (vertical mirror), with run 10's trip 6 |
| The default overlap limit cannot pass zero-backlash released teeth | 32, 33 | skill: give the limit the teeth's measured overlap, and say why |
| Fasteners a bill of materials lists fit no `not-modeled` reason | 35, 36 | project-format.md: purchased fasteners with no stated position are `not-modeled` |
| `cadrev text` on an SVG cut file raises a traceback | 35 | a clear refusal naming the source's kind |
| A shape check's worst point is named "on body" but lies on the model | 32 | name which of the two it lies on |
| report.md has no motion section: joint types, drives and gear ratios are in report.json alone | 32 | report.md lists the motion |

## Adding a model

1. Check out the commit under test once per run (`git worktree add --detach <checkout> <sha>`) and make each run's empty directory, numbered as [`dogfood/brief.md`](dogfood/brief.md) says.
2. Brief one fresh agent per object with the brief and the two lines above, at the effort the other rows used, and no more agents at once than the account's limit carries.
3. Re-check each project from a copy without `build/`, with the run's own `cadrev`, and take its row from `build/report.json`: `status`, `counts`, `tolerances` and `overlap_limits`, and the ledger's probes.
4. Audit it as above, and add its rows and any trip to the run log of the object, grouped into tickets for the owner's approval.
