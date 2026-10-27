# Dogfood run log: a fresh agent reconstructs the mini benchtop centrifuge

Spec #103; issue #114. Each run is a fresh general-purpose subagent briefed with [brief.md](brief.md) word for word, under its Centrifuge entry. It is given only the skill, the CC BY paper (Soma Poór 2022, HardwareX e00328) and the authors' released STEP and STL files (Mendeley Data, doi:10.17632/sy2vrhj227.1). The sources are kept outside the repo, at `~/Documents/Projects/cadrev/centrifuge-sources`, until the project is committed. Each run's project is kept at `~/Documents/Projects/cadrev/dogfood/run-<n>`. Each trip it reported, or that its project showed, is listed with its fix.

## Run 10

Skill and tool at `a0d632e` (main, after spec #103's #104–#113). Project kept at `~/Documents/Projects/cadrev/dogfood/run-10`. 62 tool calls, about 34 minutes.

**End state:** VERIFIED PENDING REVIEW, not exact: 0 errors, 0 warnings, 88/88 checks pass. 91 params, resting on 85 source, 0 measured and 6 proposed (`fan_t`, `fan_bore_d`, `fan_rot`, `fan_top_y`, `rotor_seat_y`, `pla_density`), with no physics values. It is a static model of six parts: body, bottom plate, rotor, fan frame, fan hub and four M3 screws. The bottom plate was the tracer part, 9/9 green with its shape check before any other part was built. One reading awaits confirmation: `fig8-body-dims`, "130.0 x 130.0 x 34.0 mm", crop `figures/crops/fig8-body-dims.png`. It became `examples/centrifuge`, where Vini Rezanejad confirmed that reading, so the example is VERIFIED.

**Rotor variant: the PCR-strip rotor for the 32.5 mm hub.** Its released body weighs 16.02 g at a proposed PLA density of 1.24 g/cm³, which matches the stated "rotor (16 g)". The six-tube rotor would weigh 13.1 g. Its faces are all planes, cylinders and cones, so it can be rebuilt exactly. Its own table row states the 32.5 mm hub. The 36.6 mm PCR rotor's row also says "32.5 mm hub", which the run recorded as conflict K1, resolved as a copy error in the row of a variant not built.

**Released bodies.** All twelve STEP files are registered as `kind: geometry`. No STL is, since each ships beside its STEP. The body, plate and rotor are shape-checked (0.0011 mm at `tol` 0.002, 5.6e-7 mm and 1.3e-6 mm). The run skipped ten bodies with a reason:

- variants not built: the compatibility body and the six-tube, 36.6 mm and 36.6 mm PCR rotors;
- the two fit testers;
- the two arrow bodies, the optional inlay (the body's arrow recess is built);
- the 0.5 ml and 0.2 ml tube adapters, which belong to the six-tube rotor.

The fan and screws are purchased parts with no released body. The STEP files' "Steel" material name is not ledgered, nor is any density from it. The rotor's mass check rests on the proposed PLA density.

**Probes.** 74 in all: 43 of the body, 7 of the plate, 23 of the rotor, and `R-hub-bore` (32.5) as context restating the quote. Each in scope feeds a param, checked by a `chk-<id>` check. Every stated or probed diameter has a diameter, bbox or distance check: the 32.5 mm hub, the M3 screws, the 130 mm body and the 80 mm fan among the stated ones.

**Conflicts**, each resolved: K1 above; K2, a 12.5 mm switch against its 13 mm cut-out; K3, a 9 mm lid switch against its 12 mm slot. K2 and K3 each compare a purchased part with the clearance cut for it.

| # | Trip | Kind | Fix |
|---|---|---|---|
| 1 | The coverage sweep read the price-table cell "500 n.a." as 500 newtons. The run skipped it with a from/to skip. | tool bug | A unit spelling that begins a dotted abbreviation is no unit. `NOT_SWEPT` row `n.a.`, with the near miss `rated at 500 N.` in `STILL_SWEPT`. |
| 2 | A product written with an asterisk (`19*12.5 mm`, `6*9 mm`, `13*13*10`) was swept as its last factor only, or not at all where unitless. The run ledgered Table 2's `13*13*10` (cm, unit in the row header) as context by hand. | tool hole | An asterisk between digits joins a product as `x` and `×` do. `SWEPT` rows `19*12.5 mm` and `13*13*10`. The fix swept one more quantity in the example, the rocker switch's `(0.7500*0.500)` in inches, now skipped as restating `P3-main-switch`. |
| 3 | `cadrev check` printed `[model-build] model.build failed: AssertionError: ` with no line. The run found the empty boolean with its own harness. | tool | A failed build names the model.py line it failed on, unless the failure names a param. Test: `test_model_failing_with_no_message_names_the_model_py_line_it_failed_on`. |
| 4 | report.md's Evidence table showed each probe as `figure None: "None" (unconfirmed)`, which reads as if it awaited review. | tool bug | A probe shows as `probe <kind>` with where it reads. Test: `test_report_md_shows_a_probe_in_the_evidence_table_as_a_probe_awaiting_no_reviewer`. |
| 5 | `body-shape` evaluated to 0.001111 at the DC hole rim, just over `tolerance.length`, though the run says the hole matches the file. It set `tol: 0.002`. | filed | #119. |
| 6 | Fig. 5's sections are drawn upside down, and overlays have no vertical flip, so the run made no overlay. | no change | Overlays add no pass or fail; the LegClaw's run 3 trip 6 is the same. |
| 7 | No probe kind reads the design value of a rotated cut-out or web plane, so the run probed raw corner coordinates (`50.25184`). | filed | #120. |
| 8 | SKILL.md step 6 says to build every part the parts tables list, but the target is lid-off, so the purchased lid is `not-modeled`. | doc | project-format.md's `not-modeled` covers a part the `target`'s configuration leaves out (a lid taken off). |
| 9 | (From the project.) `target` named the six-tube rotor, written at step 1 before the run chose the PCR-strip rotor. | skill | project-format.md: where the authors released several variants, `target` names the one built; SKILL.md step 1: a variant chosen later is written into the target. The example's target is corrected. |
| 10 | (From the project.) The STEP files were registered as CC-BY-SA-4.0; the dataset is CC BY 4.0. | no change | The licence field is going (#102). The example's licences are corrected. |
| 11 | (From the project, at review.) The compatibility body's and the arrows' skip reasons named a variant and an optional inlay, without saying that neither is part of the device. | example | Their reasons in the example say so. |

**CI.** `cadrev check` on the example takes about 17 s, so `examples/centrifuge` runs on every push beside `examples/legclaw-links`, and no nightly job is needed.
