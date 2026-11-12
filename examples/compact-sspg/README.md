# COMPAct SSPG 7.2:1 gearbox

The single-stage planetary gearbox of the 7.2:1 SSPG actuator from Singh, Kapa, Joshi and Kolathaya, *COMPAct: Computational Optimization and Automated Modular design of Planetary Actuators*, arXiv:2510.07197v2 (2025). [arXiv:2510.07197](https://arxiv.org/abs/2510.07197). CC BY 4.0. Its STL files are in the authors' repository, [github.com/singhaman1750/COMPAct](https://github.com/singhaman1750/COMPAct), `CADs/Actuator_STL_files/sspg_7.2`, under the MIT licence.

A fresh agent reconstructed it from the skill and these sources alone. It is the gearbox as built: the sun, three planets, the primary carrier with its secondary carrier, the gearbox casing with the ring cut inside it, and the output-bearing retainer. The motor and the purchased bearings and bolts are left out. It shows a planetary train, counts and worked ledger values:

- Table I's design vector `[25, 65, 155, 0.5, 3]`: sun 25, planet 65 and ring 155 teeth, module 0.5, 3 planets, each a count.
- The ring fixed, the sun the input and the carrier the output, quoting the paper. The train is a chain of gears: sun → carrier at `z_sun / (z_sun + z_ring)`, and carrier → each planet at `-z_ring / z_planet`, exported to `build/model.mjcf` as joint equalities.
- A posed `angle` check, `carrier-turn`: one sun turn moves the carrier 50°, against `expect: 360 / R1.ratio` from the stated 7.2:1.
- A `count` check of the 3 planets, and each pitch diameter (sun 12.5, planet 32.5, ring 77.5) as a `distance` across opposite flanks with `expect: module * z`. The planets' 22.5 mm centre distance is checked from the sun and from the ring.
- An `interference` check, `mesh-clear`, at `max_volume: 0.001` rather than the default `tolerance.length`³: the polyline involutes mesh at zero backlash and overlap by up to 0.00078 mm³ (`planet_2 ∩ casing_1`).
- All eight STL registered as `kind: geometry`, with 107 probes. Six are shape-checked against the built parts, the casing with its ring among them. The earlier carrier, superseded by the updated one, and the motor casing, outside the target, are skipped with that reason.

Expected status: `VERIFIED: 0 errors, 1 warnings, 123/123 checks pass`

The warning is `[param-gap]` on `one_turn`, the sun turn `carrier-turn` is posed at, which no source states (#121).

The Fig. 4(a) reading, `R1-fig4`'s "(a) SSPG (MN8014, 7.2:1)", was checked against `figures/crops/fig4a-label.png` by a named reviewer, recorded as `confirmed_by` on it in `ledger_paper.yaml`, which `ledger.py` carries into `evidence.yaml`. It restates R1, the quoted 7.2:1 that `carrier-turn` compares with, so it is context. Without that field the status would be VERIFIED PENDING REVIEW.

A full `cadrev check` of this directory takes about 2 minutes on a laptop, about half of it the casing's shape check. `scripts/check` checks it and fails if it prints anything else. A change that moves the status updates the line above.

`ledger.py` writes `evidence.yaml` from the hand-written `ledger_paper.yaml` (the paper's quotes and the figure reading) and the probes and datums it reads from the STL; `checks_gen.py` writes `checks.yaml`. Edit those and rerun them (`uv run --project ../../plugin/skills/cad-reverse-engineer/tool python -I ledger.py` and `python3 checks_gen.py`) rather than editing the two files they write.

## Sources

The paper and the eight STL are committed, so a fresh clone needs no download. `cadrev check .` compares each with the SHA-256 hash in `project.yaml`, so a `[source-hash]` finding means a source file was changed. `sources/LICENSE-COMPAct.txt` is the MIT licence the STL ship under.

The crop `figures/crops/fig4a-label.png` is reproduced from Fig. 4 of the article under CC BY 4.0, credit Singh et al. 2025.
