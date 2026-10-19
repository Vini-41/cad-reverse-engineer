# Dogfood run log: a fresh agent reconstructs the full LegClaw

Spec #1, stories 56–57; issue #15 (runs 1–4). Spec #2, story 41; issue #37 (run 5). Each run is a fresh general-purpose subagent given only the path to `skills/cad-reverse-engineer/SKILL.md` (and its `references/`), the `uv run … cadrev` invocation, the CC-BY paper and supplement from `examples/legclaw-links/sources/`, a scratch project directory outside the repo (from #58 on, `~/Documents/AI-Tools/cadrev/Workspace/dogfood/run-<n>`, which survives a reboot; each run's section records it), and the goal "reconstruct the full LegClaw". It was told not to read `examples/`, the tool source, its tests or `docs/`. Each trip it reported, or that its project showed, is listed with the fix made before the next run. A trip of kind *environment* comes from the harness the run used, not from the skill: file it only once it reproduces in a default Claude Code session (#30 did not).

## Run 1

Skill and tool at `15e0dfa` (spec-1-integration with #13 and #14). 177 tool calls, about 31 minutes.

**End state:** VERIFIED PENDING REVIEW, not exact: 0 errors, 5 warnings, 38/38 checks pass. 72 params (37 source, 5 measured, 30 proposed). Two legs of 60 instances each: the thigh, servos, four-bar compression links, pedestal, base, bent linkages, foot frame with node shafts, X-linkages and springs, and four toes. It ended with six readings awaiting confirmation. Conflict K2 (420 g against 430 g) was still open. Four of the five warnings were false findings (trips 4 and 5).

| # | Trip | Kind | Fix |
|---|---|---|---|
| 1 | The interference check ended the run in a traceback (`AttributeError: 'ShapeList' object has no attribute 'volume'`) as soon as two instances really overlapped. The agent bisected the assembly by hand to find the pairs. | tool bug | The overlap volume sums a list of shapes. Test: `test_interference_between_overlapping_instances_fails_the_check_without_a_traceback`. |
| 2 | A `distance` between datums of two different parts was silently evaluated across the two unrelated part frames: it got 10 where 50 was meant. | tool hole | Such a check is now `[check-config]`, naming both datums. Tests: `test_distance_between_datums_of_two_parts_is_a_finding` and its guard. project-format.md says that checks read single parts, not instances, and what to do with a dimension that spans parts. |
| 3 | A part made of two disjoint boxes passed, although modeling.md says a part is one solid (`[part-invalid]`). | tool hole | A part of more than one solid is `[part-invalid]`. Tests: `test_part_of_two_disjoint_solids_is_invalid` and its guard. modeling.md says that separate bodies are separate parts. |
| 4 | A mass check's `density` and `add` params raised `[param-unused]` ("the model never reads it"), which step 5's done criterion forbids. | tool bug | Params a mass check reads count as read. Test: `test_params_only_a_mass_check_reads_are_not_unused`. |
| 5 | A source param used as a mass check's `add` (and its `density`) raised `[unchecked-source]`, which step 6 forbids. | tool bug | Params a mass check reads count as checked by it. Test: `test_source_param_a_mass_check_adds_is_checked_by_it`. |
| 6 | A `from`/`to` skip whose block ran onto the next page matched nothing and said nothing. Its quantities just stayed under `[coverage]`. A skip quote that matches nothing was silent too. | tool hole | A skip that matches no text on one page is the new error `[skip-not-found]`. Tests: `test_skip_that_matches_nothing_is_a_finding` and its guard. project-format.md says to split a block per page. |
| 7 | `cadrev check` left `__pycache__/` in the project, and the template `.gitignore` does not ignore it. | tool bug | model.py is imported without writing bytecode. Test: `test_verification_run_writes_nothing_into_the_project_outside_build`. |
| 8 | A `scope: not-modeled` item without `values` was `[evidence-values]`. The docs only said that context items may omit values. | doc | project-format.md says that a not-modeled item keeps its values. |
| 9 | The photo that the measured params scale off had no printed labels, but it still sat under "awaiting confirmation" with the reading "(no printed labels)". It was unclear what a reviewer confirms there. Figure labels about test rigs had no documented treatment either. | doc | project-format.md says what a measurement image's reading holds and what its reviewer confirms, and that figure labels not about the object need no evidence. SKILL.md step 3 scopes figure numbers to those about the object. |
| 10 | The agent made 45° as `degrees(atan2(p.claw_H, p.claw_H))` to get past `[model-literal]`. That is a constant built from params, which games the static lint. | doc; out-of-scope trigger | modeling.md says that a 45° chamfer or a count of 3 is a param, and names the `atan2(p.h, p.h)` move. The runtime-trace trigger fired, so it was filed as #23. |
| 11 | The leg-mass check went red at 142 g against 200 g. The agent raised two proposed params (hardware mass, resin density) until it passed at −20% with `tol_rel` at its 0.25 cap. It wrote down that it did so. | skill | SKILL.md step 6 says that a proposed param changed to turn a check green must say so in its rationale, since that check then confirms the choice rather than a source. |
| 12 | The foot's 70×56×22 sole envelope spans several parts. No check reads an assembly or a group of instances, so the agent invented proposed side rails to make the foot one part. | out-of-scope trigger | Filed as #22 (multi-object targets and subassemblies). project-format.md now says what to do meanwhile. |
| 13 | The shell sandbox of this harness refused commands with `$VAR`, heredocs or `source` as an argument. The agent wrote wrapper scripts. | environment | No change. This comes from the worktree isolation of the harness the run used, not from the skill. |
| 14 | Things it guessed: which Table S2 axis is which, part counts, attachment points, leg spacing, and that both overlays were perspective views. The datasheets for the servos and springs were not given. | inherent | No change. Each guess is a proposed param with a gap, or an interpretation, which is the design. |

## Run 2

Skill and tool with run 1's fixes. 107 tool calls, about 19 minutes.

**End state:** VERIFIED PENDING REVIEW, not exact: 0 errors, 2 warnings (both `[conflict-open]`: K2 on the mass, and K3 on which servo drives what), 40/40 checks pass. 72 params, resting on 42 source, 4 measured and 26 proposed. Both legs were built in full, with the toes' torsion springs. Seven readings were awaiting confirmation. It hit none of run 1's trips.

| # | Trip | Kind | Fix |
|---|---|---|---|
| 1 | A mass check's `counts` (`{xlink: 8, phalanx1: 4}`) were bare numbers with no basis, and no rule noticed. A wrong count can turn a red mass check green unseen. | tool hole | Each `counts` entry now names a param, so a count has a basis and shows in the report. A bare number is `[schema]`. Tests: `test_mass_check_counts_a_part_by_the_param_it_names`, `test_mass_check_count_given_as_a_bare_number_is_a_finding`. project-format.md documents it. |
| 2 | project-format.md's examples were LegClaw's own: the target sentence, `Bent Linkage 37×6.5×5`, the Fig. 2A 70×56×22 crop, and conflict K1 with its resolution. The agent's K1 resolution copied the example's. Every dogfood run on this paper was primed. | doc | The examples in project-format.md and modeling.md now describe a fictional two-finger gripper (Doe 2025). The SKILL.md skip list no longer says "airframe". |
| 3 | `cadrev figures` wrote the supplement's images as `.tiff`, which the Read tool cannot show. The agent converted them with `sips`. | tool | A figure in a format a viewer cannot show is written as PNG. Test: `test_figures_writes_an_image_a_viewer_cannot_show_as_png`. |
| 4 | `cadrev crop` takes full-resolution pixels, but Read shows large images downscaled. Three of the first six crops missed their labels. | skill | SKILL.md step 3 says to scale by the factor Read reports and to confirm that the whole label is inside the crop. |
| 5 | The interference row printed a pair at zero overlap ("0 leg2_xlink_1_1_-1 ∩ leg2_xlink_1_1_1"), which reads like a clash. | tool | A pair is named only where instances overlap. Test: `test_interference_check_with_no_overlap_names_no_pair`. |
| 6 | report.md printed two parameter counts: the headline by what each param rests on, and a "source: 38 · derived: 10 …" line by declared basis. Both are correct, but they read as contradicting each other. | tool | The second line is now labelled "Declared basis:". Test: `test_report_md_labels_the_declared_bases_apart_from_what_params_rest_on`. |
| 7 | The sweep never lists Table S1's unitless "BLCM 420 24.7", which is a mass of the object. The agent ledgered it by hand. | skill | SKILL.md step 3 says that the unitless cells of tables are the agent's to ledger, like the figure pass. |
| 8 | Derived params such as `toe_x = foot_L/2 - ph1_H/2` (toes flush with the foot ends) rest on source in the headline, yet each encodes a choice. | doc | project-format.md asks for an `interpretation` on derived params whose `expr` makes a placement choice. |
| 9 | modeling.md said unused params "raise `[param-unused]`" without saying that it is a warning. | doc | modeling.md now says "the warning", and that a param a mass check reads counts as read. |
| 10 | Battery cell counts ("2S", "3S") were swept as seconds, and "8G" as grams. | no change | The matcher reads lowercased text, so `S` cannot be told from `s`. One skip covers each, and the sweep is meant to err towards listing. |
| 11 | "six turns" and "Eight tension springs" are words, so they cannot be ledgered. Counts become proposed params whose rationale quotes the text. | no change | Words are not numbers by design (project-format.md). Run 2 trip 1 at least makes each count a visible param. |
| 12 | There is no angle check kind, so a source angle param would raise `[unchecked-source]` with no way to clear it. The agent moved the angle into context evidence. | filed | Not fixed in #15, and not one of the spec's deferred items. The code review filed it as #28. |
| 13 | Distance checks between datums are close to tautological, because the datums are computed from the same params as the solid and are not tied to it. | filed | This is the design in modeling.md ("compute them from the same params"). The code review filed it as #29, related to #23 (runtime trace), which would tie geometry to params. |
| 14 | The leg-mass check passed at −15% after the agent raised one proposed param (thigh wall 2.5 → 4 mm) and said so in its rationale. | works as revised | This is run 1 trip 11's rule being followed. |
| 15 | The shell sandbox refused `cadrev source …` (it read `source` as the builtin) and loops. The run had no assembly viewer, so the agent wrote one. | environment | No change. |

## Run 3

Skill and tool with run 2's fixes, commit `3e3b658`. 110 tool calls, about 19 minutes.

**End state:** VERIFIED PENDING REVIEW, not exact: 0 errors, 0 warnings, 38/38 checks pass. 60 params, resting on 38 source, 2 measured and 20 proposed. Two legs were built, each with its thigh, pedestal, compression and bent links, foot frame, X-links, springs, steering wheels and four toes. Five conflicts were recorded, each with a resolution. Eight readings were awaiting confirmation. It hit none of run 1's or run 2's tool trips. It followed the new rules: counts are params, tuned proposed params are named, the crop scale is applied and the label confirmed inside.

| # | Trip | Kind | Fix |
|---|---|---|---|
| 1 | The agent re-registered a source with `--license` and `--url`. `cadrev source` printed "refreshed", but it kept the old citation and wrote neither field, so the source stayed gitignored. The agent edited project.yaml and .gitignore by hand. | tool bug | Re-registering now refreshes `kind`, `citation`, `url` and `license` as well as `path` and `sha256`, and un-ignores the file under the new license. Test: `test_reregistering_a_source_takes_its_new_citation_url_and_license`. project-format.md documents it. |
| 2 | An unquoted comma in a flow mapping (`interpretation: disc diameter (L and W are both 18, read as …)`) split the value into a stray key. No finding was raised, and the report showed the truncated note. The committed example had the same bug: three skip reasons cut at a comma. | tool hole | An unknown key in an entry is `[schema]`, naming the key and suggesting quotes. Tests: `test_unknown_key_in_an_entry_is_a_finding_naming_it` and its guard. The example's three reasons are quoted. project-format.md says to quote values with commas. |
| 3 | The agent rewrote `3*w/2` as `w + w/2` and `/4` as `/2/2` to clear `[model-literal]`. | filed | These are relations to a param, which modeling.md allows. The question of whether the lint should see through them belongs to #23. |
| 4 | The paper states its counts in words ("Eight tension springs"), so all six count params are proposed, and that keeps the project from Exact. | filed | This is the same as run 2 trip 11. Words are not numbers by design; the code review filed the design decision as #27. |
| 5 | A measured param has no `gap` field, so G-leg-spacing appears with no params under it. | filed | This is minor. The code review filed it with run 4 trip 4 as #25. |
| 6 | Overlays offer only front, top and right views, with no rotation, so photos taken in another orientation cannot be overlaid. `crop --zoom` and throwaway measuring crops are not covered in the skill. | no change | Overlays add no pass or fail, and `--help` documents `--zoom`. |
| 7 | Battery cell counts, Jetson memory and video timestamps were swept as quantities. | no change | Same as run 2 trip 10. They are covered by skips. |
| 8 | The shell sandbox refused `source` as an argument. `init` file mtimes looked odd (template times are preserved). | environment | No change. |

## Run 4: the final run

Skill and tool with run 3's fixes, commit `854789e`. 102 tool calls, about 15 minutes.

**End state:** VERIFIED PENDING REVIEW, not exact: 0 errors, 0 warnings, 34/34 checks pass (30 bbox axes, 3 distances and 1 interference over 66 instances). 50 params, resting on 35 source, 1 measured and 14 proposed. Both legs were built, each with its thigh, compression four-bar, pedestal, bent linkages, paw, X-structure links and four toes. Every Table S2 row is checked, and so are the Fig. 2A paw envelope and the Fig. S1B node spans. Conflicts K1 (mass) and K2 (L14) both have resolutions.

**Readings awaiting confirmation**, each to be checked against its crop by a named reviewer:

| evidence | reading |
|---|---|
| fig2a-sole | "22mm; 56mm; 70mm" |
| figS1b-tension | "20mm; 46mm; 60mm" |
| fig2b-ph1 | no printed values; the measured phalanx pin inset is scaled on its 24 mm length |
| fig2a-beta | "(βmax =40°)" (not modeled) |
| fig2a-leg-mass | "m≈200g" (context) |
| fig2d-D | "Dmin = 20mm; Dmax = 50mm" (context) |

It hit no tool bug and none of the earlier trips.

| # | Trip | Kind | Fix |
|---|---|---|---|
| 1 | It was unclear whether context and not-modeled image items need confirmation. They do: they hold the status at PENDING REVIEW. | doc | project-format.md says that every image item awaits confirmation, whatever its scope. |
| 2 | The format's image example always shows `values`. The agent guessed that the image a measured param scales off may omit them. | doc | project-format.md says that such an image needs no `values`. |
| 3 | It made no mass check. With no stated density, a mass check would only confirm a tuned density, so it kept the 200 g as context. Step 6 says to check "`mass` where a mass is stated". | filed | This is a judgement the skill could make explicit. The code review filed it as #24. |
| 4 | A gap with no params left on it, and a gap id named only inside a conflict's text, are not flagged. | filed | This is minor. The code review filed it as #25. |
| 5 | Overlay PNGs are downscaled from source pixels, and the interference row does not say how many pairs it evaluated. | filed | This is report polish. The code review filed it as #26. |
| 6 | The skill asks for purchased-part datasheets, but the task allowed only the two sources. | inherent | Gap G-servos (ask: datasheet). |
| 7 | The shell sandbox again refused `source` as an argument, globs and compound heredocs. | environment | No change. |

## Out-of-scope triggers

From spec #1's Out of Scope:

- **Multi-object targets and subassemblies:** fired (run 1, the foot envelope over several parts). Filed as #22.
- **Runtime parameter trace:** fired (run 1, `atan2(p.claw_H, p.claw_H)` for 45°; run 3, `w + w/2`). Filed as #23.
- **OCR of text inside figures:** did not fire. Every run ledgered the figure-only labels (Fig. 2A, Fig. S1B, Fig. 2D) through the step 3 figure pass.
- **`cadrev fetch`:** did not fire. Both sources are CC-BY and committed.
- **A `standard` basis:** did not fire. The proposed values are clearances, layouts and pin sizes, and the purchased parts are datasheet gaps, not catalogue stock sizes.
- **Publishing:** not a dogfood trigger.

## Run 5: spec #2's rules

Spec #2, issue #37. Skill and tool at `308d9ee` (spec-2-integration with #32–#36). Same brief as runs 1–4.

**End state:** VERIFIED PENDING REVIEW, not exact: 0 errors, 0 warnings, 35/35 checks pass (27 Table S2 bbox axes, 3 Fig. S1B pin pitches, one of them over instances, the Fig. 2A sole envelope over instances on 3 axes, 1 mass check and 1 interference check over all pairs). 63 params, resting on 40 source (33 declared source, 7 derived), 1 measured (`ph_margin`, scaled off Fig. 2B) and 22 proposed (clearances and frame sizes, two pose angles, the density, the servo body, and the six counts). One leg was built, 13 parts in 44 instances: thigh, tendon and hip servos, steering wheels, compression rhombus, pedestal, bent linkages (straight), end and middle foot frames, eight X-linkages and four toes. Conflicts K1 (430 g against 420 g), K2 (L14) and K3 (which servo variant drives what) each have a resolution. Eight readings were awaiting confirmation. It hit no tool trip of runs 1–4.

| # | Trip | Kind | Fix |
|---|---|---|---|
| 1 | `cadrev text` prints "two dual-" and "axis servos" on two lines. The matcher re-joins such a break as "dualaxis", so the P12-servos quote copied across it as printed ("dual- axis") was `[quote-not-found]`. "intertoe" matched only with the hyphen deleted by hand. The agent split the quote into two context items. | tool bug | A quote is matched against the line-break hyphen read both ways (split word and compound), and a quote copied across the break as printed ("dual- axis", "inter- toe") matches too; the coverage sweep counts its quantities as covered. Test: `test_quote_copied_across_a_hyphenated_line_break_matches`. |
| 2 | Unquoted commas in interpretations gave 8 `[schema]` errors in params.yaml and 1 in skips, although project-format.md warns about it. | doc | Run 3 trip 2's rule caught each one. project-format.md now says to quote every free-text value (`interpretation`, `rationale`, `reason`) in a `{…}` entry, and its examples do. |
| 3 | The paper states its counts in words ("four linkages", "Eight tension springs"), so all six counts are proposed, and the mass check rests on proposed for counts the paper gives. | filed | #27. |
| 4 | The skill asks for purchased-part datasheets, but the brief allowed only the two sources. The servo bodies are proposed boxes with a datasheet gap; their stated 63 g enters the mass check through `add`. | inherent | Gap G-servo-env (close by: datasheet). |
| 5 | Checks that are partly circular. Each Table S2 bbox checks a box built from the same three numbers. `env-sole` passes because `fr_mx` is derived as (70 − 60)/2. The pin pitches derived from envelopes (`cl_pitch = cl_L - cl_H`, pins at the centres of the rounded ends) rest on source, and the choice shows only in the interpretation. | inherent; filed | A bbox confirms that the transcription reached the geometry, which is the design. A derived param that makes a placement choice resting on source is filed as #40. |
| 6 | `foot_px / 4` was `[model-literal]`, so the agent added the derived param `xl_x`. `3 * rz / 2` was `[model-literal]` for the 3, and the agent rewrote it as `rz + rz / 2`, which it flagged as edging toward gaming the rule. | works as designed; filed | The first is the rule followed. The second is a number's spelling, not a constant built from params, so `[model-constant]` does not see it; filed as #39. |
| 7 | Every image item awaits review, the context ones too: the servo part-number crops and the Dmin, βmax and mass labels add five readings that drive no geometry. | no change | project-format.md says so (run 4 trip 1); a reading a reviewer has not seen should not count as confirmed. |
| 8 | Crops landed short even after the 1.03 scale factor Read reported; three labels took 2–4 re-crops each. | works as revised | Run 2 trip 4's rule: the agent confirmed each whole label inside its crop. |
| 9 | The overlay PNG is 1599 px wide where the source figure is 2051 px, which threw off the agent's first calibration by about 40 px. | filed | #26. |
| 10 | The interference check over all pairs ran in about 2.5 s. The agent set the clearance to −1 in a copy and got 644 mm³ between the hip servo and the thigh. | works | The check reads the whole assembly. |
| 11 | Guesses: one leg rather than the landing gear, the Fig. S1B wireframe as pin-centre lines inside the Fig. 2A envelope, the X-linkage planes, Dmin and Dmax as context, the bent-link angle the geometry forces (about 10°), and the 1.15 g/cm³ density. | inherent | Each is a proposed param with a gap, or an interpretation. |
| 12 | (Implementers of #33.) `[model-constant]` judged only the largest param expression, so `p.y * atan2(p.h, p.h)` got through because it changes with `p.y`. | tool hole | Each part of a param expression that changes is judged too, and the outermost constant part is reported. Test: `test_model_constant_inside_a_relation_that_varies_is_a_finding`. modeling.md names the case. Run 5's project still ends VERIFIED PENDING REVIEW under it. |
| 13 | (Implementers of #32 and #33.) `scripts/red-on-main -k <rule>` names a new rule's row of `test_guard_change_raises_its_rule` a red guard and exits 1, so each ticket that adds a rule trips it. | filed | #41, related to #38. |

### Spec #2's issues

- **#22 (envelopes and spacings over several parts):** gone. `env-sole` is a bbox over the 11 foot instances (both end frames, the middle frame and the eight X-linkages, toes excluded), and `foot-pitch-x` is a distance over `[frame_l, frame_r]`. It needed `along: x`, since `frame_l` is turned 180° about Z. No part was invented to make the foot one part.
- **#23 (constants built from params):** behaves as decided. `[model-constant]` never fired, and model.py holds no constant built from params: the angles it computes (`atan2(rise, half_span)` for the bent links) change with their params. The literal-spelling move of trip 6 is #39. The sub-expression hole of trip 12 is fixed.
- **#24 (mass check on a proposed density):** behaves as decided. `leg-mass` shows "rests on proposed: density, n_cl, n_bl, n_lk, n_frame, n_toe, n_wheel". It passed at 202.7 g against 200 g on the first run, with nothing tuned.
- **#28 (stated angles):** behaves as decided, as context. No source states an angle of the one static configuration. The 0–40° toe range, βmax = 40°, the 180° hip flip and the 385° servo rotation are ranges or motions, kept as context as project-format.md says. The 45° spring preset is not modelled. The rhombus half-angle and the X-linkage angle are proposed, with gaps. No angle check was needed.
- **#29 (datums tied to the solid):** gone. Every datum sits on a pin bore's axis at mid-thickness, or on the steering wheel disc's axis. `[datum-off-solid]` never fired, so the pin-pitch checks measure the bores.

### Spec #2's Out-of-scope triggers

- **Named or nested subassemblies:** did not fire. Two checks name instances, and their lists neither repeat nor nest.
- **Ranges of motion:** did not fire. The stated ranges stayed context, and nothing asked for a range to be checked.
- **Datums found from named features:** did not fire. No datum passed `[datum-off-solid]` on the wrong face; the readings still await a human review.
- **Whole-model runtime trace:** did not fire. No number got past `[model-constant]` through a build123d call or a loop variable. `rz + rz / 2` is a spelling (#39), and `p.y * atan2(p.h, p.h)` was a hole in the perturbation, now closed.
- **Counting checks by what they rest on, and angles between two datum directions:** did not come up.
