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

## Release gate: runs 27 and 28

Issue #160's gate for v0.1.0: two fresh agents, each briefed with [brief.md](brief.md)'s Centrifuge entry word for word, with two lines changed so that each installed the skill as a stranger does, from the marketplace on GitHub at `46308e9` (main, after #157, #158, #159 and #177), not from a checkout:

| The brief's line | The gate's line |
|---|---|
| Use the skill at `<checkout>/plugin/skills/cad-reverse-engineer/SKILL.md`: read it and follow it, with its `references/`. | Use the cad-reverse-engineer skill, which this session has installed from its plugin marketplace as a stranger installs it (the install commands below): invoke it, read its SKILL.md and follow it, with its `references/`. |
| Read nothing else under that checkout: not `examples/` …, not the tool's source or tests, not `docs/`, not `.scratch/`. | Read nothing else of the plugin's install: not its `tool/` source, only SKILL.md and its `references/`. Read nothing of any checkout of the cad-reverse-engineer repository. |

Neither run's tool calls read outside its brief.

### Run 27: Claude Code

Claude Code 2.1.311, Claude (Opus 5.5), `claude -p` in auto mode with only project and local settings. Installed in the run directory with:

```
claude plugin marketplace add --scope local 'https://github.com/Vini-41/cad-reverse-engineer.git#main'
claude plugin install --scope local cad-reverse-engineer@cad-reverse-engineer
```

`claude plugin marketplace add` takes a branch or tag after `#`, not a commit, so it was given `main` and the clone was confirmed at `46308e9`. The session listed the skill as `cad-reverse-engineer:cad-reverse-engineer` and ran `cadrev` from the plugin's install. Project kept at `~/Documents/Projects/cadrev/dogfood/run-27`. 52 tool calls, about 30 minutes.

**End state:** VERIFIED PENDING REVIEW, not exact: 0 errors, 0 warnings, 93/93 checks pass. 102 params, resting on 84 source, 0 measured and 18 proposed (the fan, switch and DC-socket envelopes and seating, the screw head, `pla_density`, the boss web's `web_half`), with no physics values. Three readings await confirmation, crops in `figures/crops/`: `fig8-body-size.png` ("130.0 x 130.0 x 34.0 mm"), `fig8-arrows-size.png` ("78.3 x 80.4 x 0.2 mm") and `fig8-body-filament.png` ("121g · 40.63m").

**Rotor variant: the six-tube rotor for the 32.5 mm hub**, the paper's main configuration (Fig. 1), whose row states the hub, 7 blades, six tubes and 16 g. Its released body weighs 13.15 g at the proposed 1.24 g/cm³, 18% under the stated 16 g; the run set `tol_rel: 0.2` to pass it, and said that at that density the PCR-strip rotor weighs 16.0 g (run 10's choice). Fig. 8's 121 g body is a slicer estimate, kept as context.

**Released bodies.** All twelve STEP files registered, no STL. Shape-checked: body (0.0012 at `tol` 0.005), bottom plate (0.00035), rotor (0.0026 at 0.005). Skipped with a reason: the compatibility body and the three other rotors (variants), both fit testers, both arrow inlays (the engraving is built), both tube adapters (the rotor is unloaded).

**Probes.** 66: 40 of the body, 8 of the plate, 18 of the rotor. 65 each feed a source param checked by its own `c-*` check; the rotor's Ø32.5 bore probe is context, restating the quote. Every stated diameter (Ø32.5 hub, the DC socket's 5.5/2.1, M3, the 80 mm fan) has a check; the lid's 116 is not modelled, the lid being off. No conflicts recorded: the 36.6 mm PCR rotor's "32.5 mm hub" is read as a copy error in a variant not built.

| # | Trip | Kind | Fix |
|---|---|---|---|
| 1 | `cadrev init .` failed with ". is not empty": the directory held only the `.claude/` the local-scope install wrote. The run initialised in its scratchpad and copied the files in. | ticket C | *unconfirmed* beyond the run: whether `init` should accept a directory holding only dot-directories an agent harness writes. A user-scope install writes none. |
| 2 | The coverage sweep listed Table 2's `13x13x10`, whose unit (cm) is printed only in the column heading, so it reads as 13 mm. The run ledgered it as context with no values. | ticket C | Run 10 trip 2 did the same by hand, and run 28 trip 7 again: a table cell's unit given in its heading is not read. |
| 3 | A probe restating a figure reading (`P-body-env` and `F-body-size`, both 130/34) raised no finding, where a probe restating a quote is context. The run kept both in scope. | ticket C | *unconfirmed*: whether a probe that restates a figure reading should be context, as one restating a quote is. |
| 4 | Each of the 65 probe-fed params needed its own check repeating the probe on the model; `gen_ledger.py` generated them. | duplicate | Run 26 trip 8, its ticket B. |
| 5 | Probes recorded at 3 decimals failed the shape checks by 0.0012 and 0.0026; the run set `tol: 0.005` on the body and rotor. | duplicate | #119 (v0.2), as run 10 trip 5. |
| 6 | Fig. 8's labels were unreadable at native size; the run re-cropped with `--zoom 4`, which `cadrev crop --help` gives and SKILL.md does not. | ticket C | SKILL.md step 3's crop instruction does not say a small label is cropped with `--zoom`. |
| 7 | The run modelled every part before its first build, not following the tracer-part order. | no change | The run's own departure from SKILL.md, which no rule can see. |
| 8 | (From the project.) The six-tube rotor's mass check passes 13.15 g against the stated 16 g only at `tol_rel: 0.2`, under the 0.25 cap. The 16 g matches the PCR-strip rotor at the same density (run 10). Run 28 did the same. | ticket D | *unconfirmed*: which rotor the paper's "rotor (16 g)" weighs; the skill does not say that a mass check failing by more than the density's spread points at the variant, not the tolerance. |

### Run 28: Codex

Codex CLI 0.167.0, its default model (gpt-6.1-sol), `codex exec` with a fresh `CODEX_HOME` holding only the login, so no other plugin or setting was loaded. Installed with:

```
codex plugin marketplace add Vini-41/cad-reverse-engineer --ref 46308e992a0edfbd67718584b5416d7ac8624cf5
codex plugin add cad-reverse-engineer@cad-reverse-engineer
```

Run as `codex exec --sandbox workspace-write -c sandbox_workspace_write.network_access=true --add-dir ~/.cache/uv -C <run dir>`: the README's "allow network for that first run" was not enough (trip 0). The fresh `CODEX_HOME` lay under `/private/tmp`, which the sandbox lets a command write, so the plugin's own `tool/.venv` could be created there; a stranger's `~/.codex` is not writable from the sandbox, which this run therefore did not test. Project kept at `~/Documents/Projects/cadrev/dogfood/run-28`. 70 commands, about 25 minutes.

**End state:** VERIFIED PENDING REVIEW, not exact: 0 errors, 0 warnings, 154/154 checks pass. 200 params, resting on 179 source, 0 measured and 21 proposed, with no physics values. Four readings await confirmation, crops in `figures/crops/`: `body-slicer.png` ("130.0 x 130.0 x 34.0 mm"), `arrows-slicer.png` ("78.3 x 80.4 x 0.2 mm"), `body-slicer-mass.png` ("15 hours 20 minutes; 121g · 40.63m") and `arrows-slicer-mass.png` ("1 minute; 0g · 0.02m").

**Rotor variant: the six-tube rotor for the 32.5 mm hub**, the paper's main configuration, chosen to compare with the stated 16 g. Its mass check reads 13.147 g against 16 g at `tol_rel: 0.2`, as run 27's; the body's full-solid 121.26 g passes against the slicer's 121 g at 5%, both at the proposed 1.24 g/cm³.

**Released bodies.** All twelve STEP files registered, no STL. Shape-checked: body, bottom plate and rotor, at `tol` 0.0012 and 0.007 where the files' edges are coarser than the default. Skipped with a reason: both arrow inlays (monochrome build), the compatibility body and the three other rotors (variants), both fit testers (tools), both tube adapters (unloaded).

**Probes and diameters.** 134 recorded values, each feeding params listed in the run's `build/audit.md` and `build/probe-inventory.csv`, which also give each stated or probed diameter's check. **Conflicts**, each resolved: the 36.6 mm PCR rotor's "32.5" as a copy error; the 121 g slicer screenshot at 100% infill against the instructions' 10% body infill.

| # | Trip | Kind | Fix |
|---|---|---|---|
| 0 | (Before the run.) Under Codex's `workspace-write` sandbox with network allowed, as the README says, `cadrev --help` fails: `Could not acquire lock … Operation not permitted (os error 1) at path "/Users/…/.cache/uv/.tmpHoRnYG"`. Run as `codex sandbox -c 'sandbox_mode="workspace-write"' -c 'sandbox_workspace_write.network_access=true' <plugin>/skills/cad-reverse-engineer/cadrev --help`. The run was given `--add-dir ~/.cache/uv`. | ticket A | The README and the Codex manifest say only to allow network; uv also writes its cache and the plugin's `tool/.venv`, outside the workspace. |
| 1 | `cadrev check` could not write Matplotlib's and fontconfig's caches; the run set `MPLCONFIGDIR` and `XDG_CACHE_HOME` to temporary directories in `run_check.sh`. | ticket A | The same sandbox: a stranger's run needs these writable or redirected. |
| 2 | `ps` was refused by the sandbox. | no change | The sandbox; the run used its own logs. |
| 3 | Its own inspection scripts hit `NameError`, `Vertex.to_tuple`, `No module named yaml` and a missing `sqrt` import. | no change | The run's scripting, fixed as it went. |
| 4 | `[datum-off-solid]` and `[model-arithmetic]` (√2 and quarter factors) on first builds; the run moved datums onto faces and the factors into derived params. | no change | The rules working as SKILL.md says. |
| 5 | A revolve gave a null shape and a zero-volume rotor until the run used the profile's edges; a seventh tab's fuse cut the rotor's volume from 11683.8 to 47.9 mm³, found with its own `debug_build.py`, until it cut the gaps from a continuous ring. | ticket C | *unconfirmed*: whether a part whose volume collapses in its build should be a finding; the run's shape check would have failed on it. |
| 6 | The released files' edge precision exceeded `tolerance.length`; the run set shape `tol` 0.0012 and 0.007. | duplicate | #119, as run 27 trip 5. |
| 7 | Table 2's centimetre columns: unit only in the heading. The run ledgered them with ×10 expressions. | ticket C | As run 27 trip 2. |
| 8 | (From the project.) The six-tube rotor's mass check at `tol_rel: 0.2`. | ticket D | As run 27 trip 8. |

**Tickets for approval.** The two runs' trips group into these, for the user to approve in one pass ([workflow.md](../agents/workflow.md)):

- **A. Under Codex's sandbox, the README and the Codex manifest say what `cadrev` must write** (run 28 trips 0 and 1): uv's cache, the plugin's `tool/.venv`, Matplotlib's and fontconfig's caches, or a `--add-dir` for each. Blocks a stranger on Codex, so v0.1, before the tag. It changes protected paths (README, the plugin manifests), so its PR waits for the user.
- **B. Run 26's ticket B** absorbs run 27 trip 4.
- **C. The skill and the sweep, from the gate runs** (run 27 trips 1, 2, 3, 6; run 28 trips 5, 7): a table cell's unit in its heading, `--zoom` in SKILL.md's crop step, a probe restating a figure reading, `init` beside a harness's dot-directory, a build whose volume collapses. v0.2: each cost a workaround, none a wrong result; trips 1, 3 and 5 need a repro before filing.
- **D. A stated mass is checked on the variant it weighs** (run 27 trip 8, run 28 trip 8): both runs passed a 16 g against 13.15 g by widening `tol_rel` to 0.2, where run 10 found the 16 g on the PCR-strip rotor. v0.2, after a repro: the status is right by its own rules, but the check holds less than it reads.
- #119 holds run 27 trip 5 and run 28 trip 6.

**Status against the example's.** Both runs end where run 10 did before review: VERIFIED PENDING REVIEW, 0 errors, 0 warnings, each with Fig. 8's "130.0 x 130.0 x 34.0 mm" among its readings. `examples/centrifuge`'s VERIFIED comes from a named reviewer confirming that reading, which a run cannot do.

**The gate is not yet passed on Codex.** Run 28 reached its status only with `--add-dir ~/.cache/uv`, which the README does not give, and with a `CODEX_HOME` the sandbox can write, which a stranger's `~/.codex` is not. Codex's gate stays open until ticket A lands and a rerun from the marketplace follows only what the README then says.

## Runs 29–31: the model benchmark

Fable 5.2 (run 29), Opus 5.5 (run 30) and Sol (run 31). Skill and tool at `b8ac5d2` (main after #184), each at `xhigh` effort, briefed as above plus the two lines [the benchmark's method](../benchmark.md#method) names. Projects kept at `~/Documents/Projects/cadrev/dogfood/run-<n>`. Each ended VERIFIED PENDING REVIEW, and a re-check from a copy agreed. Their counts, audit and trips are in [docs/benchmark.md](../benchmark.md), where the trips are grouped into tickets for approval.

### Run 41: Codex, the gate rerun

Codex CLI 0.167.1, its default model (gpt-6.1-sol), at main `7b56024`, after #182, #191 and #194. A fresh `CODEX_HOME` under `$HOME`, which the sandbox cannot write, as a stranger's `~/.codex` is, holding only the login and the one entry the README gives:

```toml
[sandbox_workspace_write]
network_access = true
```

Installed with `codex plugin marketplace add Vini-41/cad-reverse-engineer --ref 7b56024faa81ef04be741b7a4f90574372196620` and `codex plugin add cad-reverse-engineer@cad-reverse-engineer`, run as `codex exec --skip-git-repo-check --sandbox workspace-write -C <run dir>`, with no `--add-dir`. Brief: the centrifuge entry, installing as above and building the complete model. Project kept at `~/Documents/Projects/cadrev/dogfood/run-41`, log at `codex-logs/run-41`. 39 commands, 17 minutes.

**End state:** VERIFIED PENDING REVIEW, not exact: 0 errors, 0 warnings, 210/210 checks pass, and a re-check from a copy with the installed plugin's `cadrev` agreed. 325 params, resting on 281 source, 0 measured and 44 proposed. The six-tube 32.5 mm rotor; its mass, 13.15 g against the stated 16 g, failed at a tolerance the density's spread allows, so the run kept the 16 g as context under conflict K-mass, naming the PCR-strip rotor's 16.02 g, rather than widen it, as #194's step 7 says. Three readings await confirmation.

**The gate passes on Codex:** the README's install and its one config entry were enough.

| # | Trip | Kind | Fix |
|---|---|---|---|
| 1 | Helper scripts run as `uv run --project <skill>/tool python <script>`, as SKILL.md step 4 says, failed on uv's cache and the plugin's `.venv`: that route skips the launcher's redirects to `TMPDIR`. The run redirected them by hand. | skill | not filed: run helper scripts through the launcher, or have it export its redirects. |
| 2 | Step 3's header-unit guidance checks a scaled cell through `expect`, which a `bbox` check does not take. The run used distance checks between exterior datums. | skill | not filed: step 3 names the distance check for an envelope. |
| 3 | No count probe, so seven tabs stay proposed (#144). | filed | #144. |
