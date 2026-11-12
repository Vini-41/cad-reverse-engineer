# Uniaxial cell stretcher

The six-well uniaxial cell stretcher from Kah et al., *A low-cost uniaxial cell stretcher for six parallel wells*, HardwareX 9 (2021) e00162. [doi:10.1016/j.ohx.2020.e00162](https://doi.org/10.1016/j.ohx.2020.e00162). CC BY 4.0. Its laser-cut SVG sheets and STL files are on Mendeley Data, [doi:10.17632/mgkbmytx63.1](https://doi.org/10.17632/mgkbmytx63.1), also CC BY 4.0.

A fresh agent reconstructed it from the skill and these sources alone. It is the stretcher unit, with its 3D-printed clamps, and the mould its PDMS substrates are cast in; the electronics and controller unit is left out. It shows a lead screw and cut files as sources:

- Two stepper motors, each turning its own lead screw, both moving one carriage on a slide: two `lead` gears, each reading the stated "8 mm per revolution", exported to `build/model.mjcf` as joint equalities.
- Posed `distance` checks with `from`, the carriage's travel per turn of each screw, against the stated lead; a third compares the right screw's with the lead `expect` works out from the stated top speed and motor speed.
- A `range` check on the carriage, 25 mm, Table 2's largest tested amplitude; the rail travel itself is not stated.
- Two cut files registered as `kind: geometry`: every region of `Acryl6MM.svg` (54) and the mould's regions of `Acryl3MM.svg` are shape-checked against the built plates, and the controller housing's regions are skipped by two rectangles.
- Both STL, `Clamp.stl` and `MoldFrame.stl`, shape-checked against the built clamp and mould frame, whose dimensions are probed.

Expected status: `VERIFIED: 0 errors, 0 warnings, 119/119 checks pass`

No figure reading is needed, so no reviewer confirms one.

`cadrev check` on this directory takes under a minute: the shape check against `MoldFrame.stl`'s 18,000 triangles computes in OCC the distance of only the sample points near the largest (#123). `scripts/check` checks it and fails if it prints anything else. A change that moves the status updates the line above.

`gen_cutfile.py` writes `evidence.yaml` and `checks.yaml` from the hand-written `evidence.src.yaml` and `checks.src.yaml`, adding a shape check and its sheet datums for each cut-file region a part reproduces; edit the `.src.yaml` files and rerun it (`uv run --project ../../plugin/skills/cad-reverse-engineer/tool python -I gen_cutfile.py`) rather than editing those two files.

## Sources

The paper, both SVG sheets and both STL are committed, so a fresh clone needs no download. `cadrev check .` compares each with the SHA-256 hash in `project.yaml`, so a `[source-hash]` finding means a source file was changed.
