---
name: complete-model
description: Reverse-engineer one published object, from a single part up to a mechanism, as complete parametric CAD (build123d, STEP, MuJoCo). What its documents state is quoted and checked on the built model, and what they leave open is proposed to be made, from standard sizes for the user's units and material. Use when asked to rebuild or reverse-engineer a part, gripper or mechanism from a paper, patent, supplement or datasheet as CAD, or to complete a known-first project.
license: MIT
compatibility: Uses the CLI of the known-first skill installed beside it, which runs locally through uv on Python 3.12-3.14 and needs network access on its first run.
---

# Complete model

The whole object as CAD: every part built, what the sources settle held to them, and each value they leave open **proposed**, beside the **gap** whose answer would replace it. A proposed value is chosen to be made: a standard size, in the user's units, for the user's material.

This skill carries on [known-first](../known-first/SKILL.md), installed beside it. Read that skill first: its CLI, its file formats and its nine stages are this skill's too, with one difference. Nothing waits: where known first leaves a part waiting, propose what it needs and build it.

## Foundational questions

Three answers shape every value proposed, so they come before anything is proposed. Ask the user those the request leaves open, in one message. Where they said to build now, or there is no one to ask, answer each from the sources and name those answers at the hand-over.

- **Metric or US**: the project's length unit, `mm` or `in`. Every proposed value is in it, and every proposed thread and screw length comes from its table, ISO metric or Unified. Answered from the sources, it is the system they print their dimensions in.
- **The material**: what the parts are made of and how (`PLA, FDM printed`; `6061 aluminium, milled`), or none yet. It decides what a proposed wall, clearance and fit can be; with none, propose the shape alone. Answered from the sources, it is the one they state for the object.
- **Design or function**: whether the object is built as its sources show it, or to do what it does. Design keeps every part and feature as shown. Function replaces a feature that is hard to make in the material with one that does the same job. Answered without the user, design.

Write them in [project.yaml](../known-first/references/project-format.md#projectyaml): `units`, `material` and `follows`.

## The work

Take known-first's stages for the whole object. They differ here:

- **1. Scope** writes the three answers beside the target and leaves `known_first` out. A known-first project is carried on by removing it, and goes to stage 5.
- **5. Params** gives every part its params. A dimension takes the strongest basis available, and `proposed` where no source settles it, as [Proposing](#proposing) says.
- **6. Model** builds and places every part the sources' parts tables list, the settled ones first.
- **7. Checks** keeps a stated total mass's check where a density or a count it reads is proposed. Hold that value at its rationale rather than tuning it until the check passes: the report then shows the check rests on a proposed value, and the gap is what closes it. A proposed param changed to turn any check green names that check in its `rationale`, since the check then confirms the choice rather than a source.
- **8. Motion** proposes a range, a ratio or a pose no source states, with its gap, and declares the motion that needs it.
- **9. Hand over** is [below](#hand-over).

## Proposing

A proposed param takes a `rationale` and names a gap in gaps.yaml, phrased as the question that would settle it. Propose as the person who has to make the object would choose:

- **Standard before invented.** A proposed value is one a chart, a catalogue or a stock list holds, in the project's units: a stock thickness, a standard drill for a plain hole, a standard cutter's radius in an inside corner, a standard chamfer on an outside edge. Its `rationale` names the standard or the stock.
- **Bought before made.** What a catalogue sells is bought: a screw, a nut, a pin, a bearing, a spring, a switch. Its `rationale` names it as it is ordered, and the model holds it as its envelope.
- **A screw is a [thread param](../known-first/references/project-format.md#threads) with a length**: its thread from the project's table and its length a standard one, both held by `cadrev check`. Fit the model to the screw: derive a boss's height and a hole's depth from the screw's length, and size each hole from its thread.
- **One before two.** One screw size serves the object, and one stock thickness, until something stated calls for a second, and the `rationale` says what. A part stays one piece wherever the material lets it be made as one.
- **As shown before as invented.** What a figure shows is built as it shows it. A part keeps its figure's outline and proportions, scaled by the one size proposed for it, and its features: a slotted wheel stays one wheel, with slots.
- **Loose before tight.** A fit between two parts takes a clearance param, proposed for the material as the loosest its function allows. One param serves every fit of its kind, and its gap is `ask: test`. A wall is one the process forms and the part survives.
- **Asked before guessed.** A snap fit, a press fit and a living hinge work by properties of the material that no source gives. Under design, build the form as shown, its gap `ask: test`. Under function, join the parts with screws.

Under **function**, a feature that is hard to make in the material is replaced by one that does the same job more loosely, and the project says so. The `rationale` of what replaces it names the feature and the reason, and a stated value the replacement leaves unbuilt is ledgered `scope: not-modeled`, its `reason` naming what replaced it.

## Hand over

Report as known first does, in place of what waits: each foundational question you answered in the user's place, the params resting on proposed values, and each feature built other than the sources show it, with what it replaces. Call the project exact only where the report prints **Exact**.

Then offer the next step. Once the user accepts the design, the [ask-machinist](../ask-machinist/SKILL.md) skill reviews it as the person who has to make it, and writes its fabrication and assembly plan. Where the request already asks for that plan, carry on with it once the status is VERIFIED or VERIFIED PENDING REVIEW.
