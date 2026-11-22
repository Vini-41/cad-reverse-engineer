# Mini benchtop centrifuge

A 3D-printed centrifuge built around an 80 mm computer fan, from Viktor Soma Poór, *A low-cost and open-source mini benchtop centrifuge for molecular biology labs*, HardwareX 12 (2022) e00328. [doi:10.1016/j.ohx.2022.e00328](https://doi.org/10.1016/j.ohx.2022.e00328). Its STEP and STL files are on Mendeley Data, [doi:10.17632/sy2vrhj227.1](https://doi.org/10.17632/sy2vrhj227.1).

```
scripts/cadrev check examples/centrifuge
```

Expected status: `VERIFIED PENDING REVIEW: 0 errors, 0 warnings, 27/27 checks pass`

It takes about 25 seconds. Then open `build/assembly.step` in a CAD program, and read `build/report.md` and the plan, `build/plan.md`.

## What it shows

A static assembly with a plan, taken through `noob`, `build-model` and `ask-machinist` by a fresh agent for each, given the skills and these sources alone. No one was there to answer, so the run chose for itself: millimetres, PLA printed by FDM, built as designed, the complete model, and the six-tube rotor for the 32.5 mm fan hub.

- **Released bodies are compared whole.** The body, bottom plate and rotor are each held to the authors' STEP file, surface to surface, and the largest deviation is 0.6 µm.
- **What is not built says why.** Ten released bodies are skipped with a reason: the variants not chosen, two fit testers, the arrow inlay and the tube adapters.
- **What the sources leave open is proposed.** The bought parts' unstated sizes, the printed fit and the PLA's density make 30 proposed parameters of the 133, each under a gap that names what would settle it. 38 rest on them.
- **Sources that disagree are recorded.** The paper gives the rotor 16 g, but the six-tube rotor built from its file weighs 13.15 g at the proposed density, and the PCR-strip rotor's file matches the 16 g. No check compares that mass, and the conflict says why.
- **The plan is held to the model.** It prints three parts, a fit coupon and the authors' fit tester, buys the rest, and places all 12 instances in 8 of its 11 steps. The machinist's review opened the fan's corners so its screws can be reached, and left two concerns on the authors' geometry: the Ø3.2 post holes are wider than an M3 thread, so the coupon tries them, and the 1 mm plate is too thin to countersink, so the screw heads stand proud of it, within the height of its 3 mm feet.

The run earns no warnings. Its status stays PENDING REVIEW until a named person confirms the seven figure readings against their crops in `figures/crops/`, recorded as `confirmed_by` in `evidence.yaml`.

## Sources

The paper and the twelve STEP files are committed, so a fresh clone needs no download. The STL the authors publish beside each STEP file holds the same body and is not registered.

The paper is CC BY 4.0. Mendeley Data lists the design files as CC BY 4.0, and the paper's own table lists them as CC BY-SA 4.0. The crops are reproduced from Figs. 3, 8 and 10 of the article, credit Viktor Soma Poór 2022.
