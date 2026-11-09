# Dogfood run log: a fresh agent reconstructs the COMPAct 7.2:1 planetary gearbox

Spec #103; issue #116. Each run is a fresh agent briefed with [brief.md](brief.md) word for word, under its COMPAct entry. It is given only the skill, the CC BY paper (Singh et al. 2025, arXiv:2510.07197) and the authors' released STL files for the 7.2:1 design (MIT, github.com/singhaman1750/COMPAct, `CADs/Actuator_STL_files/sspg_7.2`). The sources are kept outside the repo, at `~/Documents/Projects/cadrev/compact-sources`, until the project is committed. Each run's project is kept at `~/Documents/Projects/cadrev/dogfood/run-<n>`. Each trip it reported, or that its project showed, is listed with its fix.

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

**Released bodies.** All eight STLs registered, each one valid solid. Shape-checked: planet (0.062 at `tol` 0.07), sun (0.399 at 0.45), updated carrier (0.427 at 0.85), secondary carrier (0.639 at 0.80), bearing retainer (0.143 at 0.2), and the gearbox casing holding the ring (0.706 at 1.5). Skipped: the earlier carrier, superseded by the updated one, and the motor casing, outside the target.

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
