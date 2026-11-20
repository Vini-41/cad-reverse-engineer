# Uniaxial cell stretcher

<img src="../../docs/images/cell-stretcher.webp" width="520" alt="A motion stage of laser-cut plates: two stepper motors turn two amber lead screws that move a grey carriage over six wells; the mould parts lie beside it">

A six-well stretching stage of laser-cut acrylic, from Kah et al., *A low-cost uniaxial cell stretcher for six parallel wells*, HardwareX 9 (2021) e00162. [doi:10.1016/j.ohx.2020.e00162](https://doi.org/10.1016/j.ohx.2020.e00162). CC BY 4.0. Its laser-cut SVG sheets and STL files are on Mendeley Data, [doi:10.17632/mgkbmytx63.1](https://doi.org/10.17632/mgkbmytx63.1), also CC BY 4.0.

```
scripts/cadrev check examples/cell-stretcher
```

Expected status: `NOT VERIFIED: 41 errors, 86 warnings, 62/103 checks pass`

It takes under a minute. Then open `build/assembly.step` in a CAD program and read `build/report.md`. The mechanism is in `build/model.mjcf`, for MuJoCo.

## What it shows

A lead-screw stage whose sources hold shapes but few dimensions. A fresh agent reconstructed it from the skill and these sources alone: the stretcher unit with its 3D-printed clamps, and the mould its PDMS substrates are cast in. The electronics and controller unit is left out.

- **The lead screws are checked in motion.** Two stepper motors each turn their own screw, and both move one carriage. One turn of either moves it the stated "8 mm per revolution", and a third check works the same lead out from the stated top speed and motor speed. The carriage's range is 25 mm, Table 2's largest tested amplitude.
- **Cut sheets are sources.** Every region of `Acryl6MM.svg` (54) and the mould's regions of `Acryl3MM.svg` is compared, outline to outline, with the plate the model builds, where model.py places it on the sheet: once for each region it is cut from. The controller housing's regions are skipped with a reason.
- **Proposed values are named, then held to the shape.** The paper prints no plate dimensions, so 138 of the 320 parameters are proposed, under ten gaps for the authors and the datasheets. The plates built from them still have to match the cut sheets within 0.001 mm, and 41 of the 75 regions do not: they differ by 0.0019 to 1.16 mm (`end_motor_in` 1.16, the stretch-holding frames 0.10, `end_motor_out` 0.038, `motor_base` 0.024, …). Those regions' places on the sheet stay unchecked until their shape checks pass: 82 of the warnings.
- **What nothing holds is named.** Four more warnings: the mould and its platform jig stand beside the stretcher, as do the two stacks of stretch-holding frames; each clamp stands 3.5 mm off its mounting, the substrate between them not built; and the carriage 1.5 mm off its lead screws, their nuts not built.
- **The printed parts are compared with their meshes.** The clamp and the mould frame are built where `Clamp.stl` and `MoldFrame.stl` hold them, their dimensions cite those bodies, and both pass their shape checks at 0.001 mm.

No figure reading is needed, so no reviewer confirms one.

## Sources

The paper, both SVG sheets and both STL are committed, so a fresh clone needs no download.
