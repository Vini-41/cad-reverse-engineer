---
name: ask-machinist
description: Review a reconstructed CAD project as the machinist who has to make it, and write its plan, how each part is made, what is bought and the assembly sequence, which cadrev holds to the model. Use when asked whether a design can be made, how to fabricate or assemble it, or for its bill of materials, on a known-first or complete-model project.
license: MIT
compatibility: Uses the CLI of the known-first skill installed beside it, which runs locally through uv on Python 3.12-3.14 and needs network access on its first run.
---

# Ask the machinist

A design costs little to change until someone has to make it. Put the project's model in front of the person who will: say part by part whether it can be made, change what cannot, and write the **plan**: how each part is made, what is bought, and the steps that put the object together. `cadrev check` holds the plan to the model.

This skill works on a project of the [known-first](../known-first/SKILL.md) or the complete-model skill. Its CLI is known-first's, installed beside it ([Tool](../known-first/SKILL.md#tool)), and so are its file formats.

## 1. The model

Run `cadrev check <dir>`, read `build/report.md`, and view `build/isometric.png` and every part's drawing in `build/drawings/`. The machinist needs two things:

- **A model that stands**: the status VERIFIED or VERIFIED PENDING REVIEW. A plan of a model that fails its checks is a plan of the wrong object, so the skill that built it finishes it first.
- **The material**: what the parts are made of and how (`PLA, FDM printed`; `6061 aluminium, milled`), `material` in [project.yaml](../known-first/references/project-format.md#projectyaml). Where it gives none, ask the user. Where no one answers, take the one the sources state for the object, and say so at the hand-over.

Done when the model stands and project.yaml holds the material.

## 2. Review

Take every part in turn as the person who has to make it from that material, and give it a thumbs up or a thumbs down. Measure before judging: a wall's thickness, a hole's depth and a tool's reach come from a script of your own on the built parts (`cadrev python`). Look for what makes a shop send a part back:

- **What the process cannot form**: a wall thinner than it holds, an overhang or an undercut it cannot reach, an inside corner sharper than its cutter, a hole deeper than its drill.
- **What is off the chart**: a hole no standard drill makes, a thread or a screw length no catalogue holds, a radius or a stock size that has to be ordered specially.
- **What is tighter than its job**: a fit, a tolerance or a finish finer than the part's function needs.
- **What costs more than it should**: a part cut from a block for one slim feature, where a plain block and a bought pin do the same job; a part made that a catalogue sells; two parts where one would do.
- **What a hand cannot assemble**: a screw no driver reaches, a part closed in before the one that goes inside it.
- **What nothing holds**: a pin free to slide out of its hole, a cord's end with no anchor, a part that rests where nothing keeps it.

A thumbs down names the feature, the reason, and the change that would turn it.

Done when every part has its verdict.

## 3. Changes

Give the user the review, the thumbs-down parts first, and make the changes they accept. Each change is a proposal: make it as the complete-model skill's [Proposing](../complete-model/SKILL.md#proposing) says, its `rationale` naming the reason, and run `cadrev check` back to the status it had. Where the project follows the design, a value the sources state stays as stated: report what makes it hard to make, and leave it.

Where no one answers, make the changes that touch proposed values alone, and report the rest at the hand-over.

Done when every thumbs down is turned, declined or reported.

## 4. Plan

Write [plan.yaml](../known-first/references/project-format.md#planyaml):

- **`general_tolerance`**, one line for the whole object: the loosest that works.
- **`make`**, for each part that is made: its operations in the order the shop does them. The stock, or the print's orientation and supports. Each cut with its tool where the tool is on the chart: the drill, the tap, the reamer. Each feature that needs tighter than the general tolerance, with the reason. The finish, and the edges broken.
- **`buy`**, for each part that is bought: what is ordered, by its standard or catalogue designation. For each screw, its head and material; cadrev prints its thread and length. And anything else the steps use: an adhesive, a wire.
- **`steps`**, the assembly sequence a person follows. Each step places instances onto what is already there, from a direction a hand and a tool can reach, drives its screws (`with`), and says how in its `note`: the tool, what to align, how tight, and what to check before the next step. What goes inside goes in first.
- **What floats is an error under a plan.** Build what holds it, move it onto what does, or name the loosest fit as project.yaml's [`clearance`](../known-first/references/project-format.md#projectyaml).
- **A fit that asks for a test is tried before the parts are made.** Where a fit param's gap is `ask: test`, the plan says how: a coupon, a part of its own that no instance places, holding that fit around the proposed size, and a step that tries the real pin, screw or bearing in it.

Done when `cadrev check` reports nothing about the plan and ends on the status it had, and each step's view in `build/steps/` shows what its note says.

## 5. Hand over

Show the user `build/plan.md`, the guide with each step under its view. Then: each thumbs down and what became of it, each gap that asks for a test before the parts are made, and each answer you gave in the user's place.
