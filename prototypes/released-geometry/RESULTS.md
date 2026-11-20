# PROTOTYPE #246: is one deviation analysis per released part enough?

Throwaway. This branch is the record; nothing here merges to main.

**Verdict: adopt.** This holds only if the comparison holds every part to `tolerance.length`, with no per-check `tol`. Of 23 seeded errors, the comparison caught all 23. Today's probes and shape checks caught 22. The strictness is what makes it catch what probes catch. Under it, the examples' released parts fail until their models match their files.

## Files

- `deviation.py`: the comparison, run over a project's shape checks.
- `seeds.py`: the 23 seeded errors.
- `tabulate.py`: the seed table, today's checks against the comparison.
- `minimax_frames.py`: for each cut-file region, the placement that minimises the largest deviation.
- `results/`: the JSON behind every number below.

Run them with `scripts/cadrev python <file> …`. Each file's docstring gives its arguments.

## The comparison

The part is built in its released file's frame. Here that frame is the rigid motion today's datum pairs fit on the unseeded model, held fixed for the seeded copies. It is compared whole with its body, with no alignment, at `tolerance.length`:

- **STEP:** the largest distance between sampled surfaces, both ways (`distance.py`, as the shape check does).
- **STL:** three tests on points both shapes hold exactly, so facet sag loosens none of them.
  1. Every mesh corner lies on the part.
  2. Every corner of the part where sharp edges meet lies on a mesh corner, and every sharp closed edge passes through at least three. Seams, smooth edges and tangent joins are left out: a tangent join's position is the parametrisation's, not the shape's.
  3. Every facet's three corners lie on one smooth patch of the part, meaning faces joined by tangent edges. Without this test, a hole left out of a plate is missed, because its wall facets' corners all lie on the plate's two faces.
- **Cut file:** the projected outline against the region's edges, both ways.

Two things were tried and dropped:

- **Allowing each facet its sag, estimated from the mesh.** The estimate breaks on fans, cones and coarse arcs, and on a flat face's curved outline, whose sag lies in the face's own plane.
- **ICP refinement of cut-file frames.** It turned the rotationally symmetric post rings 0.015° and shifted them 0.14 mm, which is why automatic alignment was rejected.

## Seeded errors

Today's suite catches a seed when its run files an error the unseeded example does not. compact-sspg's planet and sun already fail the comparison unseeded. On those two parts, a seed counts as caught when more points lie past tolerance than unseeded.

| Seed | What | Today: what failed | Comparison: what failed |
| --- | --- | --- | --- |
| C1 | bore 2% off (centrifuge body, STEP) | probe `chk-B-bore`, `body-shape`, `datum-off-solid` | 1.26 |
| C2 | plate's screw holes moved 0.5 out | probe `chk-B-boss-pcd`, `body-shape`, `plate-shape` | 0.472 |
| C3 | a plate hole missing | `plate-shape`, `clear` | 0.5 |
| C4 | a Ø3 hole added in the deck | `body-shape`, `model-literal` | 3.5 |
| C5 | body turned 180° onto its other fan hole | **nothing: VERIFIED** | 6.39 |
| C6 | body Ø + 0.005 | `body-shape`, `body-envelope` L and W | 0.0025 |
| K1 | planet bore 2% off (STL) | probe `p-P-bore`, `planet-shape` | corners 0.1 |
| K1b | retainer bore 2% off (STL) | probe `p-R-id`, `retainer-shape` | 0.705 |
| K2 | retainer's holes moved 0.5 out | probe `p-R-hR`, `retainer-shape` | 0.5 |
| K3 | a retainer hole missing | `retainer-shape` | 24 facets on no one patch |
| K4 | a retainer hole added | `retainer-shape` | 2 closed edges through no corner |
| K5 | sun turned one tooth | probe `p-S-pcd` only | corners 2.0 |
| K6 | retainer OD + 0.01 (its rim's facets sag 0.13) | probe `p-R-od`, `retainer-shape` | 0.005 |
| K6b | planet counterbore + 0.01 | probe `p-P-cb` only | corners 0.005 |
| Z1 | clamp post hole 2% off (STL) | `clamp-hole` (probe), `shape-clamp` | 0.03 |
| Z2 | a clamp hole moved 0.5 | `clamp-pitch` (probe), `shape-clamp` | 0.5 |
| Z3 | a clamp hole missing | `shape-clamp` | 56 facets on no one patch |
| Z4 | a hole added in the clamp's plate | `shape-clamp`, `model-literal` | a closed edge through no corner |
| Z6 | clamp post hole + 0.01 | `clamp-hole` (probe), `shape-clamp` | 0.005 |
| Y1 | mould base's post holes 2% off (cut file) | `straw-diameter` | 0.030 |
| Y2 | a mould-base corner hole moved 0.5 | 6 shape checks, `datum-off-solid` | 0.5 |
| Y3 | a mould-base corner hole missing | 6 shape checks | 6.17 |
| Y4 | a hole added at the mould base's centre | 6 shape checks, `model-literal` | 15.2 |

Deviations are in mm. K5 and K6b were caught today by a probe alone: the shape check's loosened `tol` (0.1 and 0.08) passes both. With a `tol` as loose as today's STL ones (0.03 to 0.5), the comparison would miss K6, K6b, Z6 and C6 as well. So adopting it means no `tol`.

## The examples as they stand

| Example | Released parts | Pass strictly, as modelled | In the file's frame? | What it costs |
| --- | --- | --- | --- | --- |
| centrifuge | 3 STEP | 3 of 3 (≤ 1.4e-6) | Yes. The body as built; the plate and rotor sit 34 and 40.288 mm down the axis, where the assembly puts them. | None: each part is built where the assembly places it, and its placement becomes identity. |
| compact-sspg | 6 STL | 1 of 6 (the retainer) | No. Each file's origin is its bbox corner: shifts of (16.5, 16.5, 0) to (51.4, 56.15, 0), the carriers 0.21 and 0.278 up, the planet turned 177.23° (half a tooth off 180°), the retainer 90° about x. | One placement per part, read off the file. The parts that fail differ from their files: the gears' flanks are 5-point polygons (the planet's, sun's and ring's own corners lie 0.27, 0.11 and 0.26 from any mesh corner), a casing circle is 0.047 off, the secondary carrier 0.42, the carrier 0.08. |
| cell-stretcher | 2 STL and 75 cut-file regions (23 parts) | STL: 2 of 2. Regions: 26 of 75 in the pairs' frame, 34 of 75 at the best placement. | The STLs, yes. The cut parts, no: a part cut several times (the mount plate 12 times) needs a frame per region, and 9 regions are turned 180°. | One sheet placement per region (75), read to better than 0.001: datums typed to 0.01 leave a frame about 0.001 off. 41 regions differ at any placement, by 0.0012 to 0.81 (`end_motor_in` 0.81, the frames 0.10, `end_motor_out` 0.038, `motor_base` 0.012, …). Today's `tol` of 0.05 to 1.2 accepts them. |

None of these differences is on a probed value: the strict comparison finds what probes never read.

Adopting it would remove 198 probes (74, 107 and 17), 588 datums on released bodies (92, 198 and 248, the derived ones among them), 265 alignment pairs (15, 18 and 232) and every shape check's `tol`.

## Run time

Each figure is in seconds, run one after another on one machine.

| | Today: whole check | Today: shape checks | Today: datums on released bodies | Comparison |
| --- | --- | --- | --- | --- |
| centrifuge | 18.5 | 11.7 | 0.1 | 11.9 |
| compact-sspg | 104.8 | 46.8 | 6.2 | 72.9 (the casing 63) |
| cell-stretcher | 24.1 | 9.4 | 2.4 | 4.7 |

Evaluating the probes takes under 0.1 s. The comparison is as fast or faster everywhere but compact-sspg's casing. There test 3 makes 171k naive OCC point-to-face calls (54 s), which `distance.py`'s numpy bounds would serve as they serve the shape check. Without test 3, compact-sspg's comparison took 15 s.

## For the follow-up, if adopted

For a released part, the agent would write:

- the part, built in its body's frame (a cut part with one sheet placement per region), its params citing the body;
- one check, `{kind: shape, part, body}`, with no pairs and no `tol`;
- no probes, and no datums on released bodies.

Not shown here: whether compact-sspg's gears, built as true involutes, pass at 0.001. The prototype shows only that polygons do not.
