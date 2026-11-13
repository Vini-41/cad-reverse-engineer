# LegClaw

The full bioinspired leg-claw mechanism (BLCM) from Cheng et al., *Bioinspired Adaptive Leg-Claw Enables Robust Perching and Grasping for UAVs*, Advanced Science 2026, e23518. [doi:10.1002/advs.202523518](https://doi.org/10.1002/advs.202523518). CC BY 4.0.

Both legs and their connecting-plate mounts, with their motion: the knee four-bars, the foot's compression rhombus and X-linkages, the toes, the leg-flip and tendon servos, and the tendons that close the claws and spread the toes. A fresh agent built it from the skill alone; it is committed as that run left it, with the figure readings confirmed and the sources pointed at `examples/legclaw-links/sources/`, and with its tendons since added as cables, the toe segments reshaped to carry them.

- Every Table S2 row and the Fig. 2A sole envelope of each foot are checked on the built geometry, and L14 = 37 mm as the bent linkage's overall tip-to-tip length (conflict K3); Fig. S1B's cell pitches are context, not checked (conflict K2). The leg width D is checked at both ends: Dmin = 20 mm as a distance between the knee pins as built, Dmax = 50 mm as the end of the slide's one-ended range.
- The leg's and the landing gear's masses are checked within 10%: only the servos' 63 g is stated, the printed parts rest on a proposed density and proposed part counts, and the stated masses are round figures (200 g, about 430 g).
- Every stated range of motion (leg width D 20–50 mm, the 180° hip flip, the claw servo's 385° of rotation, the toes' 0–40°) is a `range` check, and swept interference checks, at 19 poses each, find no overlap across the slide, the flip and each servo wheel's turn; the toe-motion wheel's sweep is the toe range's, since it spreads all four toes together.
- Per leg, two claw cables on the claw servo's wheel each run down one toe of a same-side pair, across and up the other, and close its six flexion joints to a proposed −38°: 38.02 mm of shortening, checked against the stated "approximately 38 mm" within the 5% cap. The segments hinge on their outer edges with tapered ends and carry the cable in bores along their inner walls, as Fig. 2B draws them. Two toe-motion cables on the other wheel spread β to 40° over a proposed 180° turn. The claw sweep leaves out the opposite side's toes, which meet as the claws close around a branch. The passive tendon is not built: its only statement is an inequality.
- `build/model.mjcf` loads in MuJoCo with all 24 loops closed: 84 joints, 2 gears, 16 tension springs as tendons, 8 cables.
- Conflicts K1 (420 or 430 g), K2 (Fig. S1B against the 31 mm linkages) and K3 (L14 as pitch or overall length) are resolved in `evidence.yaml`; `gaps.yaml` holds the questions for the authors and datasheets that would replace the 63 proposed params.

Expected status: `VERIFIED: 0 errors, 0 warnings, 73/73 checks pass`

The five figure readings (`fig2d-width`, `fig2a-beta`, `fig2a-sole`, `fig2a-mass`, `figS1-tension`) were checked against their crops in `figures/crops/` by a named reviewer, recorded as `confirmed_by` in `evidence.yaml`.

`checks.yaml` is written by `gen_checks.py` (`../../scripts/cadrev python gen_checks.py`, from this directory), which repeats the checks per leg, toe and servo: edit the script, not the file.

Instances are named `<leg>_<part>`, and toes `<leg>_toe_<side><row>_<segment>`: leg `a` or `b`; side `L` or `R`, the two halves of one foot, whose toes close toward each other; row `f` or `b`; segment `j` (the β joint block), `p1`, `p2` or `c` (the claw).

## Sources

`project.yaml` registers the two sources at `../legclaw-links/sources/`, the copies `examples/legclaw-links` commits, so they are committed once.

The crops in `figures/crops/` and the page image `figures/paper/p004_01.jpg` (which `overlays.yaml` draws the model over) are reproduced from the article and its supplement under CC BY 4.0, credit Cheng et al. 2026.
