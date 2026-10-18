# Dogfood run log: a fresh agent reconstructs the full LegClaw

Spec #1, stories 56–57; issue #15. Each run is a fresh general-purpose subagent given only the path to `skills/cad-reverse-engineer/SKILL.md` (and its `references/`), the `uv run … cadrev` invocation, the CC-BY paper and supplement from `examples/legclaw-links/sources/`, a scratch project directory outside the repo, and the goal "reconstruct the full LegClaw". It was told not to read `examples/`, the tool source, its tests or `docs/`. Each trip it reported, or that its project showed, is listed with the fix made before the next run.

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
| 12 | There is no angle check kind, so a source angle param would raise `[unchecked-source]` with no way to clear it. The agent moved the angle into context evidence. | open | Not fixed in #15, and not one of the spec's deferred items. It is left for `/code-review` to decide. |
| 13 | Distance checks between datums are close to tautological, because the datums are computed from the same params as the solid and are not tied to it. | open | This is the design in modeling.md ("compute them from the same params"). It is related to #23 (runtime trace), which would tie geometry to params. |
| 14 | The leg-mass check passed at −15% after the agent raised one proposed param (thigh wall 2.5 → 4 mm) and said so in its rationale. | works as revised | This is run 1 trip 11's rule being followed. |
| 15 | The shell sandbox refused `cadrev source …` (it read `source` as the builtin) and loops. The run had no assembly viewer, so the agent wrote one. | environment | No change. |

## Run 3

Skill and tool with run 2's fixes, commit `3e3b658`. 110 tool calls, about 19 minutes.

**End state:** VERIFIED PENDING REVIEW, not exact: 0 errors, 0 warnings, 38/38 checks pass. 60 params, resting on 38 source, 2 measured and 20 proposed. Two legs were built, each with its thigh, pedestal, compression and bent links, foot frame, X-links, springs, steering wheels and four toes. Five conflicts were recorded, each with a resolution. Eight readings were awaiting confirmation. It hit none of run 1's or run 2's tool trips. It followed the new rules: counts are params, tuned proposed params are named, the crop scale is applied and the label confirmed inside.

| # | Trip | Kind | Fix |
|---|---|---|---|
| 1 | The agent re-registered a source with `--license` and `--url`. `cadrev source` printed "refreshed", but it kept the old citation and wrote neither field, so the source stayed gitignored. The agent edited project.yaml and .gitignore by hand. | tool bug | Re-registering now refreshes `kind`, `citation`, `url` and `license` as well as `path` and `sha256`, and un-ignores the file under the new license. Test: `test_reregistering_a_source_takes_its_new_citation_url_and_license`. project-format.md documents it. |
| 2 | An unquoted comma in a flow mapping (`interpretation: disc diameter (L and W are both 18, read as …)`) split the value into a stray key. No finding was raised, and the report showed the truncated note. The committed example had the same bug: three skip reasons cut at a comma. | tool hole | An unknown key in an entry is `[schema]`, naming the key and suggesting quotes. Tests: `test_unknown_key_in_an_entry_is_a_finding_naming_it` and its guard. The example's three reasons are quoted. project-format.md says to quote values with commas. |
| 3 | The agent rewrote `3*w/2` as `w + w/2` and `/4` as `/2/2` to clear `[model-literal]`. | open | These are relations to a param, which modeling.md allows. The question of whether the lint should see through them belongs to #23. |
| 4 | The paper states its counts in words ("Eight tension springs"), so all six count params are proposed, and that keeps the project from Exact. | open | This is the same as run 2 trip 11. Words are not numbers by design, and a change there is a design decision left for `/code-review`. |
| 5 | A measured param has no `gap` field, so G-leg-spacing appears with no params under it. | open | This is minor. It is left for `/code-review`. |
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
| 3 | It made no mass check. With no stated density, a mass check would only confirm a tuned density, so it kept the 200 g as context. Step 6 says to check "`mass` where a mass is stated". | open | This is a judgement the skill could make explicit. It is left for `/code-review`. |
| 4 | A gap with no params left on it, and a gap id named only inside a conflict's text, are not flagged. | open | This is minor. It is left for `/code-review`. |
| 5 | Overlay PNGs are downscaled from source pixels, and the interference row does not say how many pairs it evaluated. | open | This is report polish. It is left for `/code-review`. |
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
