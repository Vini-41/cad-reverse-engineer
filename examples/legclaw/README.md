# LegClaw

The full bioinspired leg-claw mechanism (BLCM) from Cheng et al., *Bioinspired Adaptive Leg-Claw Enables Robust Perching and Grasping for UAVs*, Advanced Science 2026, e23518. [doi:10.1002/advs.202523518](https://doi.org/10.1002/advs.202523518). CC BY 4.0.

Both legs and their connecting-plate mounts, with their motion: the knee four-bars, the foot's compression rhombus and X-linkages, the toes, the leg-flip and tendon servos. A fresh agent built it from the skill alone, in dogfood run 8 (`docs/dogfood/legclaw-run-log.md`); it is committed as that run left it, with the figure readings confirmed and the sources pointed at `examples/legclaw-links/sources/`.

- Every Table S2 row and the Fig. 2A sole envelope of each foot are checked on the built geometry, and L14 = 37 mm as the bent linkage's overall tip-to-tip length (conflict K3); Fig. S1B's cell pitches are context, not checked (conflict K2). The leg width D is checked at both ends: Dmin = 20 mm as a distance between the knee pins as built, Dmax = 50 mm as the end of the slide's one-ended range, a departure from two-ended ranges recorded on spec #51.
- The leg's and the landing gear's masses are checked within 10%: only the servos' 63 g is stated, the printed parts rest on a proposed density and proposed part counts, and the stated masses are round figures (200 g, about 430 g).
- Every stated range of motion (leg width D 20–50 mm, the 180° hip flip, 385° of servo rotation, the toes' 0–40°) is a `range` check, and swept interference checks, at 19 poses each, find no overlap across the slide, the flip, each servo wheel's turn and the toe range.
- `build/model.mjcf` loads in MuJoCo with all 24 loops closed: 84 joints, 2 gears, 16 tension springs as tendons.
- Conflicts K1 (420 or 430 g), K2 (Fig. S1B against the 31 mm linkages) and K3 (L14 as pitch or overall length) are resolved in `evidence.yaml`; `gaps.yaml` holds the questions for the authors and datasheets that would replace the 59 proposed params.

Expected status: `VERIFIED: 0 errors, 0 warnings, 79/79 checks pass`

The five figure readings (`fig2d-width`, `fig2a-beta`, `fig2a-sole`, `fig2a-mass`, `figS1-tension`) were checked against their crops in `figures/crops/` by a named reviewer, recorded as `confirmed_by` in `evidence.yaml`. Without those fields the status would be VERIFIED PENDING REVIEW.

`scripts/check`, which CI runs on every push, copies the examples as a clone holds them, runs `cadrev check` on this directory and fails if it prints anything else; the run takes under two minutes. A change that moves the status updates this line.

`checks.yaml` is written by `gen_checks.py` (`python gen_checks.py`), which repeats the checks per leg, toe and servo: edit the script, not the file.

## Sources

`project.yaml` registers the two sources at `../legclaw-links/sources/`, the copies `examples/legclaw-links` commits, so they are committed once. `cadrev check .` compares each file with the SHA-256 hash in `project.yaml`, so a `[source-hash]` finding means a source file was changed.

The crops in `figures/crops/` and the page image `figures/paper/p004_01.jpg` (which `overlays.yaml` draws the model over) are reproduced from the article and its supplement under CC BY 4.0, credit Cheng et al. 2026.
