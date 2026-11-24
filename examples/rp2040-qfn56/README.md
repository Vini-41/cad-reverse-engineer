# RP2040 QFN-56 package

<img src="../../docs/images/rp2040-qfn56.webp" width="620" alt="A square black chip package seen from above with its pin 1 dot, and from below with 56 amber leads around a notched amber centre pad">

The 7×7 mm package of the RP2040 microcontroller, rebuilt from [its datasheet](https://datasheets.raspberrypi.com/rp2040/rp2040-datasheet.pdf). With [uv](https://docs.astral.sh/uv/) installed, run this from the root of a clone:

```bash
uvx --python '>=3.12,<3.15' cadrev==0.4.1 check examples/rp2040-qfn56
```

Expected status: `VERIFIED: 0 errors, 0 warnings, 138/138 checks pass`

After the first run's download, it takes about 5 seconds. Then, in `examples/rp2040-qfn56/build/`, open `assembly.step` for the CAD and `report.md` for the checks.

## What it shows

- **It is built in its footprint's frame.** The origin is the centre of Figure 168's land pattern and Z = 0 is the board's surface, so the STEP drops into an ECAD library with no transform.
- **Each stated range is compared as a range.** A, A1, A2, b, D2, E2, L and R are held to the MIN, the MAX or both that Figure 167's table prints.
- **A value with no nominal says so.** A1 has only a MIN and a MAX, and R only a MIN, so the values the model builds them at rest on proposed values.
- **A conflict is recorded.** Table 633 places the pin 1 dot at X 0.5, Y 6, and Figure 169 draws it near (0.6, 6.4). The model follows the table, and an open question asks which point of the dot the table locates.
- **What the sources leave open is proposed.** Of 34 parameters, 24 rest on the datasheet, 3 on values scaled off its drawing and 7 on proposed values. The tie-bar ends, the logo and text marking, and the plating are not built.

A fresh agent ran each of `noob` and `build-model`, with the datasheet and no one to answer. Review then tied R's check to the axis of the lead's rounded end, so a lead with no round there is refused. A named reviewer confirmed its 27 figure readings against their crops in `figures/crops/`.

## Credits

Raspberry Pi Ltd, [*RP2040 Datasheet*](https://datasheets.raspberrypi.com/rp2040/rp2040-datasheet.pdf), build 4c5ccacb2c2f of 19 November 2026, committed unmodified. The datasheet and the crops from its Figures 3, 167, 168, 169 and 171 are © Raspberry Pi Ltd, under [CC BY-ND 4.0](https://creativecommons.org/licenses/by-nd/4.0/).
