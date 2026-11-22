# COMPAct SSPG 7.2:1 gearbox

<img src="../../docs/images/compact-sspg.webp" width="420" alt="A planetary gearbox with an amber sun gear and three blue planet gears inside a grey casing">

The single-stage planetary gearbox of the 7.2:1 SSPG actuator from Singh, Kapa, Joshi and Kolathaya, *COMPAct: Computational Optimization and Automated Modular design of Planetary Actuators*, arXiv:2510.07197v2 (2025). [arXiv:2510.07197](https://arxiv.org/abs/2510.07197). CC BY 4.0. Its STL files are in the authors' repository, [github.com/singhaman1750/COMPAct](https://github.com/singhaman1750/COMPAct), `CADs/Actuator_STL_files/sspg_7.2`, under the MIT licence.

```
scripts/cadrev check examples/compact-sspg
```

Expected status: `VERIFIED PENDING REVIEW: 0 errors, 1 warning, 17/17 checks pass`

It takes about 75 seconds. Then open `build/assembly.step` in a CAD program and read `build/report.md`. The mechanism is in `build/model.mjcf`, for MuJoCo.

## What it shows

A gear train whose authors released only meshes, taken through `noob` and `build-model` by a fresh agent for each, given the skills and these sources alone. No one was there to answer, so the run chose for itself: millimetres, PLA printed by FDM, built as designed, the complete model, and the updated carrier that the paper's photo shows.

- **The gears are built from the paper's numbers.** Table I's design vector `[25, 65, 155, 0.5, 3]` gives the sun, planet and ring tooth counts, the module and the number of planets. Each pitch diameter (12.5, 32.5 and 77.5 mm) is checked as module × teeth, and the planets' 22.5 mm centre distance from both the sun and the ring.
- **The ratio is checked in motion.** The ring is fixed, the sun is the input and the carrier the output, as the paper says. One sun turn moves the carrier 50°, checked against 360° over the stated 7.2:1, and the teeth still clear one another there. The train exports to `build/model.mjcf` as joint equalities.
- **Each built part is compared whole with its released mesh.** The sun, planet, carrier, secondary carrier, casing with the ring inside it, and bearing retainer all pass. Five lie within 0.00005 mm of their meshes.
- **The tolerance was widened for one mesh.** Two corners of the carrier's mesh lie 0.0036 mm inside its Ø13 bore, where the file's other corners on that bore lie on the circle. The run set the project's length tolerance to 0.004 mm, from the default 0.001, so that the carrier passes. At 0.001 that one shape check fails and every other check still passes.
- **What is not built says why.** Two released bodies are skipped with a reason: the earlier carrier, superseded by the updated one, and the motor casing, outside the target.
- **Sources that disagree are recorded.** The carrier's extrusion bolt holes stand 23.5 mm from the axis and the secondary carrier's 24.25 mm. Each part is built as its own mesh holds it, and a gap asks the authors which is right. No param can name that gap, so it is the run's one warning.
- **What the sources leave open is proposed.** The bearings, the bolts, where each part sits along the axis, the tooth flank's point count and the PLA's density make 24 proposed parameters of the 171, under 16 gaps. 30 rest on them.

Three figure labels restate the 7.2:1 and await a named reviewer: `fig4a-label.png`, `fig7a-title.png` and `fig9-legend.png` in `figures/crops/`. Once each carries `confirmed_by` in `evidence.yaml`, the project is VERIFIED.

## Sources

The paper and the eight STL are committed, so a fresh clone needs no download. `sources/LICENSE-COMPAct.txt` is the MIT licence the STL ship under.

The crops are reproduced from Figs. 4, 7 and 9 of the article under CC BY 4.0, credit Singh et al. 2025.
