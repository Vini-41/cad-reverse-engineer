# Benchmark

How close does a rebuilt part come to the real one when the agent never sees the real one?

Three published devices come with the authors' own CAD. We withheld it. Four frontier models each rebuilt the devices from the paper alone, twelve fresh agents in all, and afterwards every rebuilt part was laid over the authors' file and the gap between the two surfaces taken, in millimetres.

![Four rebuilt parts coloured by their distance from the authors' files: the centrifuge body and rotor almost entirely within 0.25 mm, the gearbox casing within 0.5 mm on its ring and up to 2 mm on its flange, and the stretcher clamp about 1 mm off throughout](images/benchmark-deviation.webp)

<sub>Fable 5.2's parts, each coloured by its distance from the authors' file.</sub>

## Results

Each cell is the typical distance from the authors' surface, then the distance 95% of the surface lies within.

**[Centrifuge](../examples/centrifuge)**, whose paper prints a section of its parts on a 1 mm grid:

| | Fable 5.2 | Opus 5.5 | Sol | Neon |
|---|---|---|---|---|
| Body, Ø130 mm | 0.01 · 0.09 mm | 0.01 · 0.09 mm | 0.02 · 3.48 mm | 0.01 · 3.11 mm |
| Bottom plate | 0.03 · 0.05 mm | 0.00 · 0.01 mm | 0.02 · 0.04 mm | 0.47 · 0.55 mm |
| Rotor | 0.07 · 0.42 mm | 0.09 · 0.20 mm | 0.43 · 1.69 mm | 0.08 · 0.26 mm |

**[COMPAct gearbox](../examples/compact-sspg)**, whose paper states its gears and shows the rest in one small section:

| | Fable 5.2 | Opus 5.5 | Sol | Neon |
|---|---|---|---|---|
| Sun gear | 0.18 · 0.77 mm | 0.21 · 1.08 mm | 0.04 · 1.11 mm | 0.06 · 1.02 mm |
| Planet gear | 0.03 · 1.10 mm | 0.02 · 0.83 mm | 0.03 · 1.10 mm | 0.03 · 0.66 mm |
| Casing with the ring gear | 0.24 · 1.77 mm | 0.20 · 2.18 mm | 0.36 · 3.65 mm | 0.21 · 2.87 mm |
| Carrier | 0.18 · 2.41 mm | 0.54 · 2.63 mm | 0.52 · 11.99 mm | 0.62 · 10.59 mm |

**[Cell stretcher](../examples/cell-stretcher)**, whose paper draws the mould and never shows a clamp:

| | Fable 5.2 | Opus 5.5 | Sol | Neon |
|---|---|---|---|---|
| Mould frame, 50 mm square | 0.00 · 0.03 mm | 0.00 · 0.03 mm | 0.00 · 0.76 mm | 0.00 · 0.05 mm |
| Clamp, 33 mm long | 0.91 · 2.30 mm | 0.97 · 2.48 mm | 0.83 · 2.35 mm | 1.12 · 1.95 mm |

Every run ended at VERIFIED PENDING REVIEW, the furthest an agent gets before a person confirms its figure readings, with every check passing, in 11 to 53 minutes of work.

## What decides the distance

**What the paper prints.** Where a paper gives a scaled drawing, the rebuilt part lands within a few hundredths of a millimetre: the centrifuge body and the mould frame. Where it gives numbers for one feature, that feature is right and the rest is not: every model cut the gearbox's 25, 65 and 155 teeth at module 0.5 as stated, and proposed the bearing seats, flanges and screw circles around them.

**The report says which is which.** The clamp is about a millimetre off in every run, and no run presented it as known. No figure shows one, so its width, depth and thickness are marked proposed, beside the question that would settle them. The status says every number is accounted for. The report says how many of them the paper settled: 10 to 34 of each run's 64 to 142 parameters rest on a quote, and the others on a figure or a proposal.

## What the runs caught

**A scale bar 30% too long.** Scaled by its own 1 cm bar, the stretcher's Figure 1C draws the mould 31 mm wide with posts 19 mm apart, and the text states 25 mm. All four models recorded the conflict. Fable 5.2, Opus 5.5 and Neon scaled the figure from the stated spacing instead, and their mould frames match the authors' file.

**A section of the wrong rotor.** The centrifuge's section shows a rotor whose socket scales to 36.6 mm, and the rotor asked for fits a 32.5 mm hub. Fable 5.2, Opus 5.5 and Neon recorded the conflict and built the stated 32.5 mm.

**A stated mass the rotor does not have.** The paper gives the rotor 16 g, and the authors' own six-tube rotor weighs 13.1 g in solid PLA. Fable 5.2 and Opus 5.5 built rotors of 13.2 and 13.1 g, recorded the conflict and compared nothing with the 16 g. Neon's 13.0 g rotor and Sol's 15.1 g one each passed a mass check, at tolerances of 22% and 15%.

## Method

- **Under test:** the three skills and `cadrev` at 0.3.0. Fable 5.2 and Opus 5.5 ran in Claude Code, Sol (`gpt-6.2-sol`) in Codex and Neon (`gemini-4-neon`) in Antigravity, each at its `xhigh` setting with no subagents.
- **Brief:** one fixed prompt for every run, naming the device, its paper and the parts to be compared. It said the authors' files exist and are withheld. No one answered a question, so each agent gave the answers the skills prescribe for that case and built the complete model.
- **Held out:** the paper was the only file in the agent's source folder. Afterwards each run's transcript was searched for web requests and for reads outside its own project, the skills and the paper. None had any; one listed the other runs' folder names and opened none.
- **Distance:** each rebuilt part is moved onto the authors' file as a rigid body, with no scaling, and both surfaces are sampled 60,000 times. A sample's distance is to the nearest point of the other surface. A part rebuilt from the authors' own file scores 0.00 mm this way. The gearbox carrier was released in two versions, and each run is compared with the closer.
- **Neon's two differences:** Gemini refuses two of the centrifuge paper's figures as 0.3.0 writes them, grayscale JPEGs that Claude and Codex read, so Neon ran 0.3.0 with [that one fix](https://github.com/Vini-41/cad-reverse-engineer/pull/294). Its brief also told it to view figures as `cadrev figures` writes them, since Gemini's filter blocked the whole PDF.
- **Not compared:** the stretcher's laser-cut plates, the purchased parts, and the RP2040 package, whose datasheet has no released CAD to hold out.
- **One run per model per device:** a record of what each did, not a ranking.
