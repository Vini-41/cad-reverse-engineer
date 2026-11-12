# Dogfood run log: a fresh agent reconstructs the COMPAct 7.2:1 planetary gearbox

Spec #103; issue #116, and #159, which absorbs it from run 26. Each run is a fresh agent briefed with [brief.md](brief.md) word for word, under its COMPAct entry. It is given only the skill, the CC BY paper (Singh et al. 2025, arXiv:2510.07197) and the authors' released STL files for the 7.2:1 design (MIT, github.com/singhaman1750/COMPAct, `CADs/Actuator_STL_files/sspg_7.2`). The sources are kept outside the repo, at `~/Documents/Projects/cadrev/compact-sources`, until the project is committed. Each run's project is kept at `~/Documents/Projects/cadrev/dogfood/run-<n>`. Each trip it reported, or that its project showed, is listed with its fix.

## Runs 22–24

Codex (gpt-6.1-sol), skill and tool at `69e7112`, briefed as above. Logs kept at `~/Documents/Projects/cadrev/dogfood/codex-logs/run-<n>`. Each ended VERIFIED PENDING REVIEW with the train 25/65/155, module 0.5, 3 planets and the carrier turning 50° per sun turn, but none could become the example:

- Every final `cadrev check` took 320–457 s, over the 150 s CI rule: #127.
- The released gearbox casing STL was `[source-unreadable]`, its corners 7.6e-6 mm apart, so each run repaired it in its own way and checked the repair: #129.
- A diameter check on a trimmed cylindrical face failed with a NoneType error; runs 22 and 23 unwrapped `BasisSurface()` in their models: #130.

Also filed from these runs: #131 (interference on a placed Compound) and #136 (a diameter through three datums, for the odd-sided sun bore).

## Run 25

Claude (Opus 5.5), skill and tool at `4c9d95c` (main, after #127, #129 and #130). Project kept at `~/Documents/Projects/cadrev/dogfood/run-25`. 121 tool calls, about 72 minutes.

**End state:** VERIFIED PENDING REVIEW, not exact: 0 errors, 1 warning, 106/106 checks pass. 141 params, resting on 128 source, 0 measured and 13 proposed (the involute's addendum, dedendum and pressure angle, two fillets, the carrier's tip clearance, the sun's and ring's tooth phases, three axial seats, `one_turn` and the PLA density). One reading awaits confirmation: `R1-fig4`, "(a) SSPG (MN8014, 7.2:1)", crop `figures/crops/fig4a-ratio.png`. The released casing STL read unrepaired.

**Train.** Table I's `[25,65,155,0.5,3]` (`T1`), the ring fixed, the sun input and the carrier output, quoting "the ring gear fixed, the sun gear driven by the motor, and the carrier providing the output". `carrier-turn` reads 50° against `360 / R1.ratio`; `planet-turn` reads −119.2°. `planet-count` checks 3. The pitch diameters 12.5, 32.5 and 77.5 and the 22.5 mm centre distance are `distance` checks across opposite flanks at the pitch radius, each with `expect` from `T1` (trip 3).

**Released bodies.** All eight STL registered, each one valid solid. Shape-checked: planet (0.062 at `tol` 0.07), sun (0.399 at 0.45), updated carrier (0.427 at 0.85), secondary carrier (0.639 at 0.80), bearing retainer (0.143 at 0.2), and the gearbox casing holding the ring (0.706 at 1.5). Skipped: the earlier carrier, superseded by the updated one, and the motor casing, outside the target.

**Time.** The final check took 787 s; rerun from a copy, 800 s. The casing's shape check takes 739 s of it: OCC computes 284 175 point distances against the built casing's 1701 faces, its involute ring faces having no bound. The other five shape checks take 26 s together.

| # | Trip | Kind | Fix |
|---|---|---|---|
| 1 | The coverage sweep read symbols as quantities: the design vector's `m1`, `m2`, Eq. 12's spaced `m 2N r2` as 2 N, and "60:1 in unit increments" as 1 inch. Skipped with reasons. | filed | #141; the modules share #135's cause. |
| 2 | No probe kind reads an angle about an axis off the body, so the sun's and ring's tooth phases against their holes were proposed, as were two fillet radii. | filed | #143. Two `along` distance probes and a derived `asin` would have given the phase on source, unchecked. |
| 3 | A toothed gear has no pitch cylinder for a `diameter` check, as project-format.md's planetary example (`kind: diameter, at: sun.pitch`) uses; the run used `distance` checks across opposite flanks. | filed | #142. The flank `distance` works for even tooth counts too, against the run's note. |
| 4 | The posed checks rest on `one_turn` (360), which can only be proposed, so the project cannot be exact; with no gap it raises `[param-gap]`. | duplicate | #121, commented with the `[param-gap]`, planetary and exactness cases. |
| 5 | Counts of holes, notches and pockets have no probe; the run derived each from a chord probe through `asin`, and added 6 to `model_literals` for the hex pockets. | filed | #144. |
| 6 | A circle with an odd number of facets has no opposite corners, so its diameter was probed as a span of two radii, two with a `tol`. | duplicate | #136, commented. The 42.0022 hole chord is the file's 24.25·√3, which the run recorded as 42: no bug. |
| 7 | `[model-arithmetic]` read `(a/2 + b/2)/2` as a 0.25 factor. | no change | The net factor is 0.25, the hidden factor the rule catches, as `p.L / 2 / 2` in modeling.md. |
| 8 | The casing's shape check takes 739 s (above): its two cones, torus and 25 cut cylinders get no bound, so OCC computes 85 585 STL points, none raising the worst. | filed | #140. |

## Run 26

Claude (Opus 5.5), skill and tool at `1b5b9e9` (main, after #155, #156 and #167). Project kept at `~/Documents/Projects/cadrev/dogfood/run-26`. 110 tool calls, about 48 minutes.

**End state:** VERIFIED PENDING REVIEW, not exact: 0 errors, 1 warning (`[param-gap]` on `one_turn`), 123/123 checks pass. 147 params, resting on 131 source, 0 measured and 15 proposed (the involute's pressure angle, addendum and dedendum, three fillets, the secondary carrier's boss radius, `one_turn`; the three gears' phases and three axial placements, each derived naming a gap; and the extrusions' clearance radius, derived from the addendum), with one proposed physics value, `print_density`. One reading awaits confirmation: `R1-fig4`, "(a) SSPG (MN8014, 7.2:1)", crop `figures/crops/fig4a-label.png`. It became `examples/compact-sspg`, where Vini Rezanejad confirmed that reading, so the example is VERIFIED.

**Train.** Table I's "Stage-1:[25,65,155,0.5,3]" (`T1`), quoting "has the ring gear fixed, the sun gear driven by the motor, and the carrier providing the output": the ring is cut in the casing, the root; the sun is actuated; the carrier is passive. Gears sun → carrier at `25/180` and carrier → each planet at `-155/65`. `carrier-turn` reads 50° against `360 / R1.ratio`. `planets` counts 3. The pitch diameters 12.5, 32.5 and 77.5 are `distance` checks across opposite flanks with `expect: module * z`, as #142 now has the skill say; the 22.5 mm centre distance is checked from the sun (`sun-planet`) and from the ring (`ring-planet`). `build/model.mjcf` loaded: 5 revolute joints, the secondary carrier fixed on the carrier, 4 gears.

**Released bodies.** All eight STL registered, with 107 probes, each feeding a param of the same name checked by its own `p-<probe>` check. Shape-checked: planet (0.062 at `tol` 0.08), sun (0.075 at 0.1), updated carrier (0.105 at 0.2), secondary carrier (0.455 at 0.5, its boss built as a cone), gearbox casing holding the ring (0.185 at 0.3) and bearing retainer (0.143 at 0.2). Skipped: the earlier carrier, superseded by the updated one, and the motor casing, outside the target. No conflicts.

**Time.** The run's final check took 126.5 s. On the example, on the same laptop with other batch agents running (load average about 2.8), it took 146 s cold and 127 s warm: the probes and static rules 25 s, the build 19 s, the checks 81 s, the casing's shape check 64 s of them. Run 25's casing check took 739 s before #156 and #167.

**Slip corrected in the example.** `cadrev source` un-ignored only the CC BY paper, since its licence pattern does not include MIT, so the eight STL would not have been committed. The example's `.gitignore` un-ignores each, and `sources/LICENSE-COMPAct.txt` carries the MIT notice.

| # | Trip | Kind | Fix |
|---|---|---|---|
| 1 | An odd-sided STL circle has no corners opposite each other, so SKILL.md step 4's diameter instruction failed on six circles ("sun.bore: no opposite pair on r=2.5 at 0 (13 corners)"). The run probed radial differences against a concentric circle's corner, leaving chains of derived params. | duplicate | #136, with #149 and #151 in spec #5 (v0.2). |
| 2 | Pattern counts (6 hex pockets, 18 lobes, 4 flange holes) have no probe, and `[model-literal]` forbids the literal 6. The run derived each from an angle probe as `360 / (180 - a)`. | duplicate | #144, with #148 in spec #5 (v0.2). |
| 3 | A gear's clocking about an empty axis cannot be probed; the run proposed the ring's phase, then derived each gear's from the involute's base point on 0°, through gap G-clock. | duplicate | #143, with #150 in spec #5 (v0.2). |
| 4 | The `one_turn` pose can only be proposed, giving `[param-gap]` and putting `carrier-turn` on proposed. | duplicate | #121 (v0.2), as run 25's trip 4. |
| 5 | `physics: true` on the mass model's density is accepted, so `print_density` is counted as a proposed physics value and leaves Exact; the skill names only joint and tendon slots as physics values. | ticket B | *unconfirmed*: whether a density only the MJCF's inertias read is a physics value. |
| 6 | The interference check's default limit, `tolerance.length`³, failed zero-backlash polyline involutes that overlap 0.00078 mm³ (`planet_2 ∩ casing_1`); the run set `max_volume: 0.001` on `mesh-clear`, which the report lists. | ticket B | *unconfirmed*: whether the skill should say how to set the limit for meshing gears. |
| 7 | `[model-arithmetic]` read `slot_l / 2` as multiplying `cas_b0` by 0.25, tracking factors through local names; the run used `Rectangle(align=MIN)`. | no change | The hidden factor the rule catches, as run 25's trip 7. |
| 8 | Every probe-fed param needs its own check (`[unchecked-source]`): 107 checks restating probes, which the run generated with `checks_gen.py`. | ticket B | *unconfirmed*: the skill does not say a probe-fed param is checked by restating its probe on model datums, nor that it can be generated. |
| 9 | The run renamed its parts (`sun_gear`, `planet_gear`) in advance so datum names would not collide with geometry source ids (`planet.tip0`). | ticket B | *unconfirmed*: the run did not test whether the tool catches the clash. |
| 10 | The skill gives no `cadrev crop` box syntax; `--box` failed with "unrecognized arguments: --box". It takes LEFT TOP RIGHT BOTTOM positionally. | ticket A | SKILL.md step 3 says the box is in pixels of the extracted file but not how it is passed. |
| 11 | (From the project.) `cadrev source` did not un-ignore the MIT-licensed STL (above). | duplicate | #102 (v0.2) drops the licence field and commits every source. |

**Tickets for approval.** The trips group into these, for the user to approve in one pass ([workflow.md](../agents/workflow.md)); trips 1–4 and 11 are already filed:

- **A. The skill gives `cadrev crop`'s box as it is passed** (trip 10). Blocks v0.1: a stranger following SKILL.md step 3 runs a command that fails.
- **B. The skill says how a released geometry's probes are checked, what a physics value is, and how to limit a meshing gear's interference** (trips 5, 6, 8, 9). v0.2: each cost the run a workaround, none a wrong result; each needs a repro before filing, since none was confirmed beyond the run.
- **Spec #5 (#147) and #121, #102**: trips 1–4 and 11, already v0.2.
- **The example's time.** 126 s in `scripts/check` (127 s warm standalone) against the 2-minute goal; the casing's shape check is 64 s of it. #140 (v0.1, absorbed by #156, then #167) closes on this time: the owner judged about 2 minutes to meet the goal, with no follow-up on the casing's shape check.

## Runs 32–34: the model benchmark

Fable 5.2 (run 32), Opus 5.5 (run 33) and Sol (run 34). Skill and tool at `b8ac5d2` (main after #184), each at `xhigh` effort, briefed as above plus the two lines [the benchmark's method](../benchmark.md#method) names. Projects kept at `~/Documents/Projects/cadrev/dogfood/run-<n>`. Each ended VERIFIED PENDING REVIEW, and a re-check from a copy agreed. Their counts, audit and trips are in [docs/benchmark.md](../benchmark.md), where the trips are grouped into tickets for approval.
