# Mini benchtop centrifuge

The mini benchtop centrifuge from Soma Poór, *A low-cost and open-source mini benchtop centrifuge for molecular biology labs*, HardwareX 12 (2022) e00328. [doi:10.1016/j.ohx.2022.e00328](https://doi.org/10.1016/j.ohx.2022.e00328). CC BY 4.0. Its STEP and STL files are on Mendeley Data, [doi:10.17632/sy2vrhj227.1](https://doi.org/10.17632/sy2vrhj227.1), also CC BY 4.0.

A fresh agent reconstructed it from the skill and these sources alone. It is a static project of six parts: the body, the bottom plate, the PCR-strip rotor for the 32.5 mm fan hub, the 80 mm fan as a frame and hub, and the four M3 screws. It shows released geometry as a source:

- Twelve STEP files registered as `kind: geometry`. The STL beside each is not registered, since it holds the same body.
- 74 probes of the body, the plate and the rotor: 73 feed a param, and one restates the quoted 32.5 mm hub. A `diameter` probe reads a bore, and a `distance` probe reads a pitch or a cut-out's corner.
- Three shape checks, comparing the built body, plate and rotor with their released bodies.
- Ten bodies skipped with a reason: the variants not built (the compatibility body and three rotors), the two fit testers, the arrow inlay and the tube adapters.
- A mass check on the rotor, 16.02 g against the stated 16 g, resting on a proposed PLA density.
- One figure reading, Fig. 8's Cura object list, held as a hashed crop.

Expected status: `VERIFIED: 0 errors, 0 warnings, 88/88 checks pass`

The Fig. 8 reading was checked against `figures/crops/fig8-body-dims.png` by a named reviewer, recorded as `confirmed_by` on `fig8-body-dims` in `evidence.yaml`.

`gen_ledger.py` writes `evidence.yaml`, `params.yaml`, `checks.yaml` and `gaps.yaml`, reading `skips.json`; edit it and rerun it (`python3 gen_ledger.py`) rather than editing those files.

## Sources

The paper and the twelve STEP files are committed, so a fresh clone needs no download.

The crop `figures/crops/fig8-body-dims.png` is reproduced from Fig. 8 of the article under CC BY 4.0, credit Soma Poór 2022.
