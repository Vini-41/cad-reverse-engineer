# COMPAct SSPG 7.2:1 gearbox

<img src="../../docs/images/compact-sspg.webp" width="420" alt="A planetary gearbox with an amber sun gear and three blue planet gears inside a grey casing">

The single-stage planetary gearbox of the 7.2:1 SSPG actuator from Singh, Kapa, Joshi and Kolathaya, *COMPAct: Computational Optimization and Automated Modular design of Planetary Actuators*, arXiv:2510.07197v2 (2025). [arXiv:2510.07197](https://arxiv.org/abs/2510.07197). CC BY 4.0. Its STL files are in the authors' repository, [github.com/singhaman1750/COMPAct](https://github.com/singhaman1750/COMPAct), `CADs/Actuator_STL_files/sspg_7.2`, under the MIT licence.

```
scripts/cadrev check examples/compact-sspg
```

Expected status: `VERIFIED: 0 errors, 0 warnings, 123/123 checks pass`

It takes a little over a minute. Then open `build/assembly.step` in a CAD program and read `build/report.md`. The mechanism is in `build/model.mjcf`, for MuJoCo.

## What it shows

A gear train whose authors released only meshes. A fresh agent reconstructed it from the skill and these sources alone: the sun, three planets, the primary and secondary carriers, the casing with the ring cut inside it, and the output-bearing retainer. The motor and the purchased bearings and bolts are left out.

- **The gears are built from the paper's numbers.** Table I's design vector `[25, 65, 155, 0.5, 3]` gives the sun, planet and ring tooth counts, the module and the number of planets. Each pitch diameter (12.5, 32.5 and 77.5 mm) is checked as module × teeth, and the planets' 22.5 mm centre distance from both the sun and the ring.
- **The ratio is checked in motion.** The ring is fixed, the sun is the input and the carrier the output, as the paper says. One sun turn moves the carrier 50°, checked against 360° over the stated 7.2:1. The train exports to `build/model.mjcf` as joint equalities.
- **Each built part is compared with the released mesh.** Six shape checks hold the parts to their STL bodies, each within the mesh's own facet error, and 107 probes read the dimensions the paper does not print.
- **The teeth are checked for interference.** The involutes mesh at zero backlash, so the overlap limit is raised to a sliver, 0.001 mm³, and the report lists that limit as non-default.
- **What is not built says why.** Two released bodies are skipped with a reason: the earlier carrier, superseded by the updated one, and the motor casing, outside the target.
- **What the sources leave open is a question.** 14 of 146 parameters are proposed, under six gaps: the tooth form, the fillet radii, how the parts locate axially.

One reading comes from a figure: Fig. 4(a)'s label "(a) SSPG (MN8014, 7.2:1)", held as the hashed crop `figures/crops/fig4a-label.png`. A named reviewer checked it against the crop, recorded as `confirmed_by` in `ledger_paper.yaml`, which `ledger.py` carries into `evidence.yaml`. It restates the quoted 7.2:1, so it is context.

`ledger.py` writes `evidence.yaml` from the hand-written `ledger_paper.yaml` (the paper's quotes and the figure reading) and the probes and datums it reads from the STL; `checks_gen.py` writes `checks.yaml`. Edit those and rerun them (`../../scripts/cadrev python -I ledger.py` and `python3 checks_gen.py`) rather than editing the two files they write.

## Sources

The paper and the eight STL are committed, so a fresh clone needs no download. `sources/LICENSE-COMPAct.txt` is the MIT licence the STL ship under.

The crop is reproduced from Fig. 4 of the article under CC BY 4.0, credit Singh et al. 2025.
