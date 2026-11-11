# LegClaw linkages

Three linkages of the bioinspired leg-claw mechanism (BLCM) from Cheng et al., *Bioinspired Adaptive Leg-Claw Enables Robust Perching and Grasping for UAVs*, Advanced Science 2026, e23518. [doi:10.1002/advs.202523518](https://doi.org/10.1002/advs.202523518). CC BY 4.0.

The example is deliberately small. It models the compression, bent and plain linkages and keeps the rest of Table S2 in the ledger as `not-modeled`. It shows each kind of evidence:

- Table S2 envelopes quoted from the DOCX supplement and checked as bounding boxes.
- Methods text from the PDF (springs, tendons, L14, mechanism mass).
- A Fig. 2A label that exists only in pixels, held as a hashed crop.
- Conflicts K1 (is L14 the bent-linkage length?) and K2 (420 g or 430 g?).
- Proposed pin pitches, each tied to a question for the authors.

Expected status: `VERIFIED: 0 errors, 2 warnings, 10/10 checks pass`

The Fig. 2A reading was checked against `figures/crops/fig2a-foot-sole.png` by a named reviewer, recorded as `confirmed_by` on `fig2a-foot-sole` in `evidence.yaml`. Without that field the status would be VERIFIED PENDING REVIEW.

`scripts/check` runs `cadrev check` on this directory and fails if it prints anything else. A change that moves the status updates this line.

## Sources

Both sources are CC BY 4.0, so they are committed and a fresh clone needs no download:

```
sources/Cheng2026_LegClaw.pdf                  the article PDF
sources/Cheng2026_LegClaw_supplementary.docx   Supporting Information (advs74831-sup-0001-suppmat.docx)
```

`cadrev check .` compares each file with the SHA-256 hash in `project.yaml`, so a `[source-hash]` finding means a source file was changed.

The crop `figures/crops/fig2a-foot-sole.png` is reproduced from Fig. 2A of the article under CC BY 4.0, credit Cheng et al. 2026.
