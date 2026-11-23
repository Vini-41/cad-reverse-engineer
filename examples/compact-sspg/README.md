# COMPAct 7.2:1 planetary gearbox

<img src="../../docs/images/compact-sspg.webp" width="420" alt="A planetary gearbox with an amber sun gear and three blue planet gears inside a grey casing">

The gearbox of a robot actuator, rebuilt from [its paper](https://arxiv.org/abs/2510.07197) and [the authors' STL meshes](https://github.com/singhaman1750/COMPAct). The secondary carrier is hidden in the image to show the gears. With [uv](https://docs.astral.sh/uv/) installed, run this from the root of a clone:

```bash
uvx --python '>=3.12,<3.15' cadrev==0.3.0 check examples/compact-sspg
```

Expected status: `VERIFIED: 0 errors, 1 warning, 17/17 checks pass`

After the first run's download, it takes about 75 seconds. Then, in `examples/compact-sspg/build/`, open `assembly.step` for the CAD, `report.md` for the checks and `model.mjcf` for MuJoCo.

## What it shows

- **The gears come from the paper's numbers.** Table I's `[25, 65, 155, 0.5, 3]` gives the tooth counts, module and number of planets, and each pitch diameter is checked as module × teeth.
- **The ratio is checked in motion.** One sun turn moves the carrier 50°, as the stated 7.2:1 requires.
- **Each printed part is compared whole** with the authors' mesh: the sun, planet, both carriers, the casing with its ring, and the bearing retainer.
- **Two limits were loosened, and the report says so.** Two corners of the carrier's mesh lie 0.0036 mm inside its Ø13 bore, so the length tolerance is 0.004 mm, not the default 0.001. The released teeth have no backlash, so their flanks may overlap by 0.00001 mm³.
- **A conflict is recorded.** The carrier's screw holes stand 23.5 mm from the axis and the secondary carrier's 24.25 mm. Each part follows its mesh, and the project's one warning is the open question of which is right.
- **What the sources leave open is proposed.** 30 of the 171 parameters rest on proposed values: the bearings, screws, part placements, tooth flank detail and the PLA's density.

A fresh agent ran each of `noob` and `build-model`, with these sources and no one to answer. A named reviewer then confirmed its three figure readings against their crops in `figures/crops/`.

## Credits

Singh, Kapa, Joshi and Kolathaya, *COMPAct: Computational Optimization and Automated Modular design of Planetary Actuators*, arXiv:2510.07197v2 (2025), CC BY 4.0, as are the crops from Figs. 4, 7 and 9. The STL files are from `CADs/Actuator_STL_files/sspg_7.2` in the authors' repository, under the MIT license in `sources/LICENSE-COMPAct.txt`.
