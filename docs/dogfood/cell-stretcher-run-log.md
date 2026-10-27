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
