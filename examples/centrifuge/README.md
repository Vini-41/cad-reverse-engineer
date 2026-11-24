# Mini benchtop centrifuge

<img src="../../docs/images/centrifuge.webp" width="420" alt="A round printed centrifuge body, its lid off, with an amber six-tube rotor on the fan's hub">

A 3D-printed centrifuge built around an 80 mm computer fan, rebuilt from [its paper](https://doi.org/10.1016/j.ohx.2022.e00328) and [the authors' STEP files](https://doi.org/10.17632/sy2vrhj227.1). With [uv](https://docs.astral.sh/uv/) installed, run this from the root of a clone:

```bash
uvx --python '>=3.12,<3.15' cadrev==0.4.0 check examples/centrifuge
```

Expected status: `VERIFIED: 0 errors, 0 warnings, 27/27 checks pass`

After the first run's download, it takes about 30 seconds. Then, in `examples/centrifuge/build/`, open `assembly.step` for the CAD, `report.md` for the checks and `plan.md` for the assembly.

## What it shows

- **Released parts are compared whole.** The body, bottom plate and rotor are each held to the authors' STEP file, and the largest deviation is 0.6 µm.
- **Sources that disagree are recorded.** The paper gives the rotor 16 g, but the six-tube rotor built from its file weighs 13.15 g at the proposed density. The PCR-strip rotor's file matches the 16 g, so the mass stays a question for the author and no check compares it.
- **What the sources leave open is proposed.** 38 of the 133 parameters rest on proposed values, listed with the questions that would settle them.
- **The plan is held to the model.** It prints three parts, a fit coupon and the authors' fit tester, buys the rest and places all 12 instances. The machinist's review corrected the modelled fan's corners so its screws can be reached.

A fresh agent ran each of `noob`, `build-model` and `ask-machinist`, with these sources and no one to answer. A named reviewer then confirmed its seven figure readings against their crops in `figures/crops/`.

## Credits

Viktor Soma Poór, *A low-cost and open-source mini benchtop centrifuge for molecular biology labs*, HardwareX 12 (2022) e00328. The paper, its design files and the crops from Figs. 3, 8 and 10 are CC BY 4.0.
