# Dogfood run log: a fresh agent reconstructs the uniaxial cell stretcher

Spec #103; issue #115. Each run is a fresh general-purpose subagent briefed with [brief.md](brief.md) word for word, under its Cell stretcher entry. It is given only the skill, the CC BY paper (Kah et al. 2021, HardwareX e00162) and the authors' released laser-cut SVG sheets and STL files (Mendeley Data, doi:10.17632/mgkbmytx63.1: `Acryl3MM.svg`, `Acryl6MM.svg`, `Clamp.stl`, `MoldFrame.stl`; the PDF copies of the sheets are not given). The sources are kept outside the repo, at `~/Documents/Projects/cadrev/cell-stretcher-sources`, until the project is committed. Each run's project is kept at `~/Documents/Projects/cadrev/dogfood/run-<n>`. Each trip it reported, or that its project showed, is listed with its fix.

## Run 11

Skill and tool at `97e4f67` (main, after #114). Project kept at `~/Documents/Projects/cadrev/dogfood/run-11`. 69 tool calls, about 43 minutes. Its goal read "reconstruct the uniaxial cell stretcher's stretcher unit with its lead-screw motion"; from run 12 on, the goal also names the clamps and the mould, so that both STL are compared.

**End state:** VERIFIED PENDING REVIEW, not exact: 0 errors, 0 warnings, 32/32 checks pass. 85 params, resting on 3 source (`t`, `lead`, `stroke`), 2 measured and 80 proposed, with no physics values. The run narrowed its target to the drive: the two lead screws and their motor frames, the guide rods, the far end piece, the motor-end rod plate and the carriage. It left out the stationary bar, its substrate mountings, the limit switch, the clamps and the substrates. Ten readings await confirmation: nine scale bars that calibrate nothing but one overlay, and `fig2f-panel`, the source of the two measured params.

**Drive.** Each screw has its own motor: "realized by two spindle-driven linear actuators … operated by two linear stepper motors" (p. 3). Motor L turns screw L (actuated), which drives the carriage slide through lead gear `drive_l`; the carriage drives screw R (passive) through `drive_r`, since a joint takes one gear's drive. Both gears read `lead` = 8 mm from "lead screws of 8 mm per revolution" (p. 11), checked by `travel-left` and `travel-right`, posed `distance` checks with `from`. `build/model.mjcf` loads, with 2 hinges, 1 slide and 13 fixed joints.

**Stroke.** A `range` check on the carriage slide, from the param `stroke` = 25 mm, Table 2's "0.5 Hz 25 mm", its interpretation saying the rail travel isn't stated.

**Released geometry.** All four files are registered. Of `Acryl6MM.svg`'s 54 regions, 22 are shape-checked and 32 skipped, as parts the narrowed target leaves out; `Acryl3MM.svg` is skipped whole by one `within` rectangle (the controller housing and mould bases). `Clamp.stl` and `MoldFrame.stl` are skipped, so neither STL is shape-checked, which #115 asks for. No probes: a cut file cannot be probed and both STL are skipped.

| # | Trip | Kind | Fix |
|---|---|---|---|
| 1 | Every plate dimension read from `Acryl6MM.svg` (64 params) is proposed under one gap, since a probe of a cut file is `[evidence-anchor]`, though 22 shape checks confirm them. | filed | #122. |
| 2 | A pose of one screw turn can be neither a bare number (`[schema]`) nor a derived constant (`[param-constant]`), so `one_turn` = 360 is proposed, under a gap asking nothing of the object, and the travel checks rest on proposed. | filed | #121. |
| 3 | `expect: "E-vmax.v * 60 / E-rpm.rpm"` failed, expected 1.3333 against 8: cadrev reads 1000 rpm as 6000 °/s, which project-format.md didn't say. | doc | project-format.md's `expect` section: an expect reads each ledger value in the project's units, a rate per second. |
| 4 | Quoting "the pitch of the Anet A8 lead screws of 8 mm per revolution" gave `[unit-ambiguous] E-lead.lead is printed as 8 with no unit and 8 mm`: the 8 of "A8". The run trimmed the quote. | no change | The finding names the fix, "quote only the part that states it". A number after letters is not left out of the reader, since `M3` is the same shape and states a size. |
| 5 | Every `cadrev check` took 70–95 s. | tool | Reading the two sheets took 66 s, computing each contour's area again in every pair. Each area is now computed once, and a pair whose bboxes cannot nest is ruled out first: the full check on run 11 takes 16.5 s, with its report.json unchanged. |
| 6 | Nine scale bars were ledgered as image evidence though only one calibrates anything, and all ten readings hold the project at PENDING REVIEW. | skill | SKILL.md step 3: a scale bar is ledgered only where an overlay or a measured param calibrates from it. |
| 7 | A sheet nesting the whole unit's plates means building 54 regions or narrowing the target; the run narrowed it to the drive, which the skill didn't guide. | skill | SKILL.md step 1: a target narrows by version and configuration and keeps every part; a sheet's regions of another unit are skipped. |
| 8 | The tool's `stroke` kind reads a cable only, so the slide's travel is a `range` check. | no change | SKILL.md step 8 already confirms a stated range with a `range` check; the brief's "stroke check" named the value, not the kind. |

## Run 12

Skill and tool at `a3a699c` (main, after run 11's fixes). Project kept at `~/Documents/Projects/cadrev/dogfood/run-12`. 87 tool calls, about 47 minutes.

**End state:** VERIFIED, not exact: 0 errors, 1 warning (`[param-gap]` on `one_turn`), 118/118 checks pass. 171 params, resting on 32 source, 0 measured and 139 proposed, with no physics values. No figure reading was needed, so none awaits confirmation. The target is the stretcher unit (aluminium frame, two lead-screw actuators, carriage, stationary bar, substrate mountings with the clamps, the stretch-holding frames) and the PDMS casting mould, at zero stretch with the clamps fitted; the electronics and controller unit is left out. It became `examples/cell-stretcher`.

**Drive.** Each screw has its own motor: "Uniaxial stretch is realized by two spindle-driven linear actuators … operated by two linear stepper motors" (p. 3), "connected at the moving ends by a mobile bar, or carriage". Motor L (actuated) turns screw L, whose lead gear `lead_l` drives the carriage slide (passive); the carriage drives motor R through lead gear `lead_r`. Both leads are source params from E-lead, "lead screws of 8 mm per revolution" (p. 11). `travel-per-turn-l` and `travel-per-turn-r` are posed `distance` checks with `from`, one turn of each motor: the first against E-lead, the second against `expect: "E-vmax.v * 360 / E-rpm.rpm"` (7.9998). `build/model.mjcf` loads, with 2 hinges, 1 slide and 21 fixed joints, and the two gears as joint equalities.

**Stroke.** `carriage-range`, a `range` check on the carriage slide, rests on Table 2's "0.5 Hz 25 mm" through `stretch_max`. A `stroke` check models a substrate as a cable between its two posts, lengthening 5 mm over the narrow frames' "0–5 mm".

**Released geometry.** All four files are registered. Every region of `Acryl6MM.svg` (54) is shape-checked against 19 parts; the mould's regions of `Acryl3MM.svg` are shape-checked (6 bases, 6 platforms, a jig, 8 post rings), and the controller housing's are skipped by two `within` rectangles. `Clamp.stl` and `MoldFrame.stl` are shape-checked, at `tol` 0.03 and 0.005 for the facets' sag, and 14 probes of them feed the clamp's and the frame's params. One conflict, K-env: the stated 47 × 42 × 11 cm envelope against the 48.5 × 40.4 × 9.5 cm built, resolved as counting cables and motor boxes no source places.

| # | Trip | Kind | Fix |
|---|---|---|---|
| 1 | A quote copied as "Dashed line represents … 25 mm" was found, but the 25 mm in it stayed `[coverage]`: the text reads "Dashed li ne", so the quote matched only ignoring whitespace, and coverage credited only exact matches. The run dropped the first two words. | tool bug | Coverage finds a quote's span as the quote check does, ignoring whitespace where no exact match is found. Test: `test_quote_matched_across_a_word_the_text_breaks_with_a_space_covers_its_quantity`. |
| 2 | Every plate dimension of the cut files is proposed, 139 params in all. | filed | #122, as run 11's trip 1. |
| 3 | `one_turn` = 360 is proposed, and with no gap raises `[param-gap]`; the lead checks rest on proposed. | filed | #121, as run 11's trip 2. |
| 4 | project-format.md says a pose holds every other actuated joint as built, yet motor R moved through its gear. | no change | The same paragraph says a gear moves its other joint "whatever that joint's drive". |
| 5 | A shape check's datum pairs must fit within `tolerance.length` even where it sets `tol`; `frame_wide` failed at 0.0013 on asymmetric slots, and the run moved its anchors. | doc | project-format.md's `shape` entry: a pair farther apart than `tolerance.length`, whatever the check's `tol`, fails. |
| 6 | A clockwise `Polygon` extruded the wrong way, leaving `[part-invalid] motor_gusset: is 6 solids`. | no change | The run's own slip, caught by `[part-invalid]`. |
| 7 | A datum at an obround slot's centre is `[datum-off-solid]`, on no cylinder's axis. | no change | The rule held as documented; the run used face points. |
| 8 | The run renamed its part `clamp` to `stretch_clamp` in case it clashed with the body `clamp` in datum names. | no change | Not reproduced: the run renamed before trying. |
| 9 | A full `cadrev check` takes about 3 minutes, 160 s of it the shape check against `MoldFrame.stl`'s 18,308 triangles. | filed | #123. Until it is fixed, the example's README says `Checked: nightly`: `scripts/check` leaves it out and `scripts/check --nightly`, which `.github/workflows/nightly.yml` runs, checks it. |
| 10 | The run wrote the whole model at once, though it took the clamp through as the tracer part, 10/10 green, before adding the rest. | no change | A process slip the report shows. |

**The example.** The run's project was copied without `build/` or its extracted figures. Two edits, recorded here, each one #115 asks for:

- `carriage-range` and `stretch_max` say the rail travel itself is not stated.
- `travel-per-turn-r` compares the right screw's travel with "8 mm per revolution" (E-lead), as `travel-per-turn-l` does; the run's comparison with the lead worked out from the top speed and motor speed is kept as a third check, `travel-speed-r`. The status moves to 119/119.

The project's name is `cell-stretcher`.

**CI.** About three minutes, so the example is checked nightly; `examples/legclaw-links` and `examples/centrifuge` stay on every push.

## Runs 35–37: the model benchmark

Fable 5.2 (run 35), Opus 5.5 (run 36) and Sol (run 37). Skill and tool at `b8ac5d2` (main after #184), each at `xhigh` effort, briefed as above plus the two lines [the benchmark's method](../benchmark.md#method) names. Projects kept at `~/Documents/Projects/cadrev/dogfood/run-<n>`. Each ended VERIFIED PENDING REVIEW, and a re-check from a copy agreed. Their counts, audit and trips are in [docs/benchmark.md](../benchmark.md), where the trips are grouped into tickets for approval.
