# LegClaw linkages

Three linkages of the bioinspired leg-claw mechanism (BLCM) from Cheng et al., *Bioinspired Adaptive Leg-Claw Enables Robust Perching and Grasping for UAVs*, Advanced Science 2026, e23518. [doi:10.1002/advs.202523518](https://doi.org/10.1002/advs.202523518). CC BY 4.0.

The example is deliberately small. It models the compression, bent and plain linkages and keeps the rest of Table S2 in the ledger as `not-modeled`. It shows each kind of evidence:

- Table S2 envelopes quoted from the DOCX supplement and checked as bounding boxes.
- Methods text from the PDF (springs, tendons, L14, mechanism mass).
- A Fig. 2A label that exists only in pixels, held as a hashed crop.
- Conflicts K1 (is L14 the bent-linkage length?) and K2 (420 g or 430 g?).
- Proposed pin pitches, each tied to a question for the authors.

## Sources

The source files are not committed. Download them from the article page and place them here:

```
sources/Cheng2026_LegClaw.pdf                  the article PDF
sources/Cheng2026_LegClaw_supplementary.docx   Supporting Information (advs74831-sup-0001-suppmat.docx)
```

`cadrev check .` compares each file with the SHA-256 hash in `project.yaml`. A different download of the same article can produce a different file. If the check reports `[source-hash]`, re-register your copy with `cadrev source` and check whether any quote moved.

The crop `figures/crops/fig2a-foot-sole.png` is reproduced from Fig. 2A of the article under CC BY 4.0, credit Cheng et al. 2026.
