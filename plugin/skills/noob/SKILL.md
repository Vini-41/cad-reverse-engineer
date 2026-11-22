---
name: noob
description: The first step for every object, before anything is built. Any request to reverse-engineer or rebuild a part, gripper or mechanism as CAD from its paper, patent, supplement or datasheet starts here. It reads the sources, has the user confirm the figure readings and answer the foundational questions, and leaves the project build-model starts from.
license: MIT
compatibility: Uses the CLI of the build-model skill installed beside it, which runs locally through uv on Python 3.12-3.14 and needs network access on its first run.
---

# Read the sources

Find out what an object's documents settle while changing course still costs nothing. This skill reads them into a project, tells the user where that leaves them, takes their answers, and hands the project to the [build-model](../build-model/SKILL.md) skill, which starts from it in a fresh context with its whole context free for modelling.

The project's files carry everything across: the target and the answers in `project.yaml`, the registered sources, the **ledger** (`evidence.yaml`) of every number the sources state, each a verbatim quote or a hashed figure crop, the **gaps** (`gaps.yaml`), what they leave open as questions, and the **brief**, the user's own words.

## Tool

The CLI is the `cadrev` script of the build-model skill installed beside this one, and needs [`uv`](https://docs.astral.sh/uv/). Run it by its full path on every call, since shell functions and aliases do not carry between calls:

```bash
<the directory holding this SKILL.md>/../build-model/cadrev --help
```

`cadrev` below stands for that path. The first run installs build123d and MuJoCo (about a minute).

- `cadrev check <dir> --no-build` runs every rule that needs no model, in seconds. Each finding names its rule in brackets and says what is wrong and where.
- Read [`project-format.md`](../build-model/references/project-format.md) before writing project YAML. It gives the formats; the findings give the rules as you meet them.
- `cadrev python <script>` runs a script of your own on the CLI's Python, with build123d, numpy and matplotlib.

## The work

Take the stages in order: each builds on what the ones before settled.

### 1. Scope

**The target** is the object, its version and its configuration. Papers often show earlier iterations beside the reported one; the target names the one the ledger describes. A target narrows the object, not its parts: a file holding many parts is that many parts to build. Look through the sources far enough to name it.

Where the sources show several versions and the request names none, ask which, with where the project directory goes. Where the user said to build now, or no one answers, choose the version and name it at the hand-over.

Run `cadrev init <dir>` and write `target` in [project.yaml](../build-model/references/project-format.md#projectyaml).

Done when project.yaml names the target.

### 2. Sources

Register with `cadrev source` the paper, its supplement (where the tables usually are), any video or drawing, and the datasheet of every purchased part the paper names. Geometry the authors released is `--kind geometry`: a STEP, an STL, or a laser-cut SVG sheet.

Done when every document the reconstruction will cite is registered.

### 3. Ledger

Read every page with `cadrev text <dir> <source>`, and view every image `cadrev figures <dir> <source>` writes: each page of a PDF whole, which shows its vector drawings and tables as printed, and each image embedded in it at full resolution. Ledger each statement about the object:

- Copy each quote from `cadrev text` output, the text the matcher sees.
- A number printed only inside a figure is image evidence. Crop its label with `cadrev crop <dir> <image> LEFT TOP RIGHT BOTTOM --name <name>`, which prints the `image` and `image_sha256` the item takes. The box is in pixels of the file you crop, whose size `cadrev figures` prints, so scale it from the size you viewed the image at. View the crop, and write the `reading` exactly as printed. A scale bar is evidence only where a measured param is scaled against it.
- The coverage sweep lists numbers printed with a unit. A count printed without one (a table cell, `3 planets`) and a ratio (`7.2:1`) are yours to find: ledger each one the object's geometry or motion depends on.
- Stated ranges of motion are ledgered too; the build reads them. A stated spring, damper or friction is [`not-modeled`](../build-model/references/project-format.md#evidence-the-ledger).
- A value stated in several places is ledgered at each, one in scope and the rest restatements. A disagreement between sources is a conflict. A stated quantity about something else (a test object, a load, a rig, a result) is skipped with a reason.

Done when every figure has been viewed and its labels ledgered, and the only `[coverage]` findings of `cadrev check <dir> --no-build` name released bodies, which stage 4 takes. `[evidence-unused]` and `[gap-unused]` stand until the build uses each value and gap.

### 4. Released geometry

Geometry the authors released settles values no text states, and one shape check holds the part to all of them at once. A project with none goes to stage 5.

- **Read each body** with a script of your own, `read_bodies.py` in the project directory, run by `cadrev python`. It loads a STEP or STL with build123d, or a cut file's contours in the sheet's frame, and prints each value the part needs (a hole spacing, a bore, an envelope, a thickness) as its design value, `32.5` and not the file's `32.4999`, and the frame the file holds the body in: where its origin and axes lie, since the part is built there. The build reads the bodies through this script.
- **An STL body** holds only flat triangles, whose corners lie on the true surface and whose faces cut inside a curve: read an arc by its corners, a bore's diameter as the circle through three corners on its rim.
- **Each body** is compared or skipped: a [`shape` check](../build-model/references/project-format.md#checksyaml) naming the part the build will make in the body's frame, or a skip with a reason for a body that is not part of the target (a fit tester, a variant it leaves out, a part of another device). A part cut from several regions of a cut file takes a shape check per region.

Done when `cadrev check <dir> --no-build` reports no `[coverage]` finding, and `read_bodies.py` prints every value the model will use from a body.

### 5. Parts

List every part the sources' parts tables name and every part their figures show, and sort them:

- A part is **settled** when the sources settle its every dimension: quoted, worked out from quotes, read off a released body or measured.
- A part **waits** where they leave one open. Give it a gap in [gaps.yaml](../build-model/references/project-format.md#gapsyaml) whose question names the part and the dimension ("What diameter are the finger link's pins?").
- A settled part whose place they leave open stays settled, and takes a gap asking where it sits.

Done when every part is settled or named by a gap.

### 6. Tell the user, and ask

Send one message, and end your turn on it:

1. **What the sources state**, part by part: each part, what they give for it, and whether it is settled or waits.
2. **What they leave open**, as the gaps' questions, grouped by part. Invite an answer to any the user can give now: a datasheet they hold, hardware they own, a dimension they can measure.
3. **What cadrev does not cover**, which stays theirs: electronics and wiring, loads and strength, behaviour, and tolerance analysis.
4. **The three foundational questions, then known first or the complete model**, each with the answer the sources point to:
   - **Metric or US**: the project's length unit, `mm` or `in`. Every proposed value is in it, and every proposed thread and screw length comes from its table, ISO metric or Unified.
   - **The material**: what the parts are made of and how (`PLA, FDM printed`; `6061 aluminium, milled`), or none yet. It decides what a proposed wall, clearance and fit can be.
   - **Design or function**: whether the object is built as its sources show it, or to do what it does. Design keeps every part and feature as shown. Function replaces a feature that is hard to make in the material with one that does the same job.
   - **Known first or the complete model**, with the count of parts each would build. Known first builds the settled parts and lists what waits, with nothing guessed. The complete model builds every part, proposing each value the sources leave open.
5. **Every figure crop beside its reading**, in one batch, each shown as an image where the interface can show one and otherwise by its path. Ask the user to confirm or correct them, and for the name to record.

Where the user said to build now, or no one answers, answer each question from the sources and go on to stage 7: the unit is the system they print their dimensions in, the material the one they state for the object, or none, and the object follows its design. It is known first where the request names it or asks for nothing guessed, and otherwise the complete model.

Done when the user has replied, or each question has its answer from the sources.

### 7. Record the answers

- **project.yaml.** Write `units`, `follows` (`design` or `function`), `material` unless the answer is none yet, and `known_first: true` for known first.
- **The readings.** A reading is confirmed by a person who looked, so `confirmed_by` takes the user's name only on their word in this conversation, for the readings their word covers. Correct a reading they correct, with its values, and confirm it the same way. Every other reading stays unconfirmed.
- **The brief.** Save the user's words about the object, the request and each answer as they wrote them, to `<dir>/sources/brief.md`, and register it: `cadrev source <dir> <dir>/sources/brief.md --id brief --kind brief --citation "The user's brief"`. It holds their words alone, so an answer given in their place stays out of it. Ledger what it states like any source. A value that answers a gap closes it: remove the gap, and the part is settled once no gap asks for one of its dimensions. Where it overrides a document, record the [conflict](../build-model/references/project-format.md#conflicts).

Done when the brief is registered and `cadrev check <dir> --no-build` reports no `[coverage]` finding.

### 8. Hand over

Give the user the project's path, the counts of settled and waiting parts, any reading still unconfirmed, and each answer you gave in their place. End on the next step, with the project's absolute path:

> Clear the context, then run: `Use the build-model skill on <dir>`

Where the user said to build now, or no one answers, carry on with [build-model](../build-model/SKILL.md) in this context.
