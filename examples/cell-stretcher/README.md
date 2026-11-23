# Uniaxial cell stretcher

<img src="../../docs/images/cell-stretcher.webp" width="520" alt="A motion stage of laser-cut plates: two stepper motors turn two amber lead screws that move a grey carriage over six wells; the mould parts lie beside it">

A six-well stretching stage of laser-cut acrylic, from Kah et al., *A low-cost uniaxial cell stretcher for six parallel wells*, HardwareX 9 (2021) e00162. [doi:10.1016/j.ohx.2020.e00162](https://doi.org/10.1016/j.ohx.2020.e00162). CC BY 4.0. Its laser-cut SVG sheets and STL files are on Mendeley Data, [doi:10.17632/mgkbmytx63.1](https://doi.org/10.17632/mgkbmytx63.1), also CC BY 4.0.

```
scripts/cadrev check examples/cell-stretcher
```

Expected status: `VERIFIED: 0 errors, 4 warnings, 106/106 checks pass`

It takes about 50 seconds. Then open `build/assembly.step` in a CAD program and read `build/report.md`. The mechanism is in `build/model.mjcf`, for MuJoCo.

## What it shows

A lead-screw stage whose sources hold shapes but few dimensions, taken through `noob` and `build-model` by a fresh agent for each, given the skills and these sources alone. No one was there to answer, so the run chose for itself: millimetres, acrylic cut from 6 mm and 3 mm sheet with printed clamps and mould frame, built as designed, and the complete model. The electronics and controller unit are left out. Review then replaced the run's check on the second screw, whose angle wrapped past a wrong lead, with one on the carriage's travel.

- **The lead screws are checked in motion.** Two stepper motors each turn their own screw, and both move one carriage. One turn of either moves the carriage the stated "8 mm per revolution". The carriage also reaches the 25 mm of Table 2's largest tested amplitude.
- **The cut sheets are sources.** All 54 regions of `Acryl6MM.svg` and 21 of `Acryl3MM.svg` (twelve mould parts, a template and eight rings) are compared, outline to outline, with the plates the model builds. The rest of the 3 mm sheet, the controller housing's plates, is skipped with a reason.
- **The printed parts are compared with their meshes.** The clamp and the mould frame are built where `Clamp.stl` and `MoldFrame.stl` hold them, and both lie within 0.000001 mm.
- **The tolerance was widened for the sheets.** The authors' drawing is not perfectly regular: a mounting's lobe stands about 0.003 mm off the centre of its hole. The model takes the design values, so the run set the project's length tolerance to 0.005 mm, from the default 0.001. The largest difference is 0.0035 mm. At 0.001, 29 of the 77 shape checks fail and every other check still passes.
- **What the sources leave open is proposed.** The paper's supplement and the printer kit's datasheets are not among the sources, so the run sizes the rods, screws, bearings, nuts, shaft couplings, motors and other bought parts, and proposes each material's density. These are 50 proposed parameters of the 309, and 59 rest on proposed values, those 50 among them.
- **Two conflicts are recorded.** The paper's 21.5 mm clamp baseline does not fit the released clamp on hooks 25 mm apart, and its stated 47 × 42 × 11 cm envelope is not the 452 × 404 × 95 mm the sheets and profiles build. Each is kept as context with its reason.
- **What nothing holds is named.** Two warnings: the mould and the two stacks of stretch-holding frames stand beside the unit. Two more: the template and rings cut on the 3 mm sheet are built and compared, but no source says what they are for, so no instance places them and no parameter names their two gaps.

No figure reading is needed, so no reviewer confirms one.

## Sources

The paper, both SVG sheets and both STL are committed, so a fresh clone needs no download.
