# Uniaxial cell stretcher

<img src="../../docs/images/cell-stretcher.webp" width="520" alt="A motion stage of laser-cut plates: two stepper motors turn two amber lead screws that move a grey carriage over six wells; the mould parts lie beside it">

A six-well stretching stage of laser-cut acrylic, rebuilt from [its paper](https://doi.org/10.1016/j.ohx.2020.e00162) and [the authors' cut sheets and meshes](https://doi.org/10.17632/mgkbmytx63.1). With [uv](https://docs.astral.sh/uv/) installed, run this from the root of a clone:

```bash
uvx --python '>=3.12,<3.15' cadrev==0.3.0 check examples/cell-stretcher
```

Expected status: `VERIFIED: 0 errors, 4 warnings, 106/106 checks pass`

After the first run's download, it takes about 50 seconds. Then, in `examples/cell-stretcher/build/`, open `assembly.step` for the CAD, `report.md` for the checks and `model.mjcf` for MuJoCo.

## What it shows

- **The lead screws are checked in motion.** One turn of either screw moves the carriage the stated 8 mm.
- **The cut sheets supply the plate outlines,** which the paper does not dimension. The 75 cut regions the model builds are compared with the authors' SVG outlines, and the printed clamp and mould frame with their meshes.
- **The tolerance was widened, and the report says so.** The authors' drawing is slightly irregular, so the length tolerance is 0.005 mm, not the default 0.001. At 0.001, 29 of the 77 shape checks fail.
- **Two conflicts are recorded.** The paper's 21.5 mm clamp baseline does not fit the released clamp, and its 47 × 42 × 11 cm envelope is not the 452 × 404 × 95 mm the sheets and profiles build.
- **What the sources leave open is proposed.** 59 of the 309 parameters rest on proposed values, mostly the bought parts' sizes.
- **Its four warnings are real.** The mould and two stacks of frames stand beside the unit, and no source says what the template and rings on the 3 mm sheet are for.

A fresh agent ran each of `noob` and `build-model`, with these sources and no one to answer. Review found that the second screw's angle check could pass a wrong lead, so it now checks the carriage's travel.

## Credits

Kah et al., *A low-cost uniaxial cell stretcher for six parallel wells*, HardwareX 9 (2021) e00162, CC BY 4.0. The SVG sheets and STL files are on Mendeley Data, also CC BY 4.0.
