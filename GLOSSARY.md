# CAD reverse-engineering

Rebuilding a published object, from a single part up to a mechanism, from its sources (including geometry its authors released) as parametric CAD, optionally with a kinematic model that exports to MuJoCo. Every number is traced to a quoted source or named as a reconstruction choice, and every stated value, motion included, is checked against the built model. The result can be modified, simulated kinematically and, with its plan, made. It does not cover the reconstructor's own measurements of a physical object, behavioural simulation, tolerance analysis, or whole robots (ADR-0007, ADR-0021).

## Evidence

**Source**:
A registered, hash-pinned document that states things about the object: a paper, supplement, datasheet, video or drawing, or geometry its authors released (a STEP, STL or cut file), which states shape rather than text.
_Avoid_: reference, input

**Figure**:
An image in a source: a plot, photo, drawing or video frame. Figure crops and overlays are taken from it.
_Avoid_: source figure, source image, source pixel

**Ledger**:
The record of every statement the sources make about the object, each a verbatim quote, a hashed figure crop or a probe.
_Avoid_: evidence list, extraction

**Reading**:
The label text of a figure crop, transcribed exactly as printed; it counts fully only once a named human has confirmed it.
_Avoid_: quote (for image evidence)

**Probe**:
A ledger entry taken from a body in released geometry: its envelope, a distance or angle between datums on it, or a diameter, which cadrev evaluates from the file and compares with the design value the entry records. Unlike a reading, it needs no human confirmation.
_Avoid_: geometry reading, measurement (for a value taken from released geometry)

**Conflict**:
Two ledger entries that disagree about the same feature; open until it carries a resolution.

**Stated quantity**:
A number a source prints with a unit, as an `a×b×c` product, as a diameter callout (`Ø 32.5`, a length) or as a thread size (`M3`, `1/4-20`); each one is ledgered or skipped.
_Avoid_: dimension (for anything that is not a size of the object's geometry), dimension candidate

**Count**:
A whole number a source states of how many there are: a gear's teeth, a train's planets, a spring's turns. It is ledgered like any number and read as a pure number, not as a length; it is a stated quantity only when printed with a count unit (turns, teeth). A count per leg or per joint is checked through an expect: one stated count times another.
_Avoid_: unitless quantity, integer (for a count)

**Skip**:
A stated quantity, or a body in released geometry, set aside with a reason because it is not about the object, such as a test load, a result or a fit tester.
_Avoid_: exclusion, ignore

## Parameters

**Basis**:
The declared origin of a parameter's value: `source`, `derived`, `measured` or `proposed`. A parameter with basis `source` *traces to a source*.

**Rests on**:
The basis a value ultimately depends on. A parameter rests on its own basis; a derived one on the weakest among the parameters it is computed from, proposed being weaker than measured and measured weaker than source, or on proposed where its computation is itself a reconstruction choice. A check rests on the weakest among the parameters its Reads names, or on source when it names none.
_Avoid_: traces to (for a derived parameter), effective basis

**Measured**:
The basis of a value scaled off an image or video frame against a known reference. Never used for evaluating the built model.

**Proposed**:
The basis of a value the reconstruction chooses because no source states it.
_Avoid_: assumed, guessed

**Gap**:
A question that, once answered, would replace a proposed or measured value, or the choice a derived parameter's computation makes, with a stated one. In a known-first project, a gap no parameter names is what a waiting part asks.

**Physics value**:
A parameter only the simulation reads, such as a joint's damping or friction, a spring's stiffness or rest, or a tendon's elasticity; it has a basis like any other but shapes no geometry.
_Avoid_: simulation parameter, tuning value

**Spring rest**:
The joint value at which a joint's spring exerts no torque, or no force on a slide, measured from the assembly as built like a pose. A spring preloaded against a stop rests outside its joint's range.
_Avoid_: preset, preload, springref

**Thread**:
A standard screw thread, named by its designation in the ISO metric table or the Unified one (`M3`, `M8x1`, `1/4-20`). A thread param holds one, stated by a source or proposed from the project's table, and the table gives its diameter, pitch, tap drill and clearance hole. The model declares it on the plain hole or shank made for it and never cuts it: what a CAD program calls a cosmetic thread.
_Avoid_: screw size (for a designation), thread size (for a diameter typed beside a pitch), modelled thread

**Screw**:
A thread and a length, bought and never made: a thread param that names its length. A proposed screw's length is a standard length of its thread's table, and the model is fitted to the screw.
_Avoid_: fastener (for a screw alone), bolt

## Verification

**Instance**:
One placement of a part in the assembly; a check over several instances reads them where the assembly places them.
_Avoid_: copy, occurrence

**Datum**:
A named point on a part's solid that distance and angle checks read: on the axis of a cylindrical face (a pin, a hole, a pivot) or on a face. A released body's datum may instead be derived from datums on it, and so lie off its solid: the circle through three, read at its centre, or the midpoint of two.
_Avoid_: reference point, marker

**Joint**:
How one instance moves relative to another: revolute (turning about an axis through two datums of the moving one), slide (sliding along such an axis) or fixed (moving with the other as one body). A revolute joint or slide is either actuated (an input) or passive (moved by the rest of the mechanism).
_Avoid_: pivot (for the joint itself; a pivot is its datum), prismatic, weld, DOF

**Gear**:
A coupling of two joints, so one moves in step with the other: of one type at a stated ratio (meshed gears, a belt), or a revolute joint and a slide at a stated lead (a lead screw, a rack and pinion). A planetary train with one member fixed is a chain of gears: sun to carrier, and carrier to each planet.
_Avoid_: transmission, mimic joint, screw joint

**Lead**:
How far a gear's slide moves per full turn of its revolute joint, a length; negative where the slide moves toward its axis's first datum as the revolute joint turns positive. A rack and pinion's is its pitch circumference.
_Avoid_: pitch (for a lead; a screw with several starts has a lead several times its thread pitch), ratio (for a lead)

**Cable**:
An inextensible cord laid through datums on several instances, whose length the posed assembly gives; one wound on a wheel joint drives the joints it closes, each moving in proportion to the wheel's turn toward its closed pose. Unlike a tendon, a cable does not stretch.
_Avoid_: tendon (for an inextensible cord)

**Wheel**:
The joint a cable is wound on and driven by: any joint that moves, actuated or passive, revolute or slide, whose one-ended range is its full turn (a slide's, its stroke). A servo's horn is one; so is a slide whose stroke pulls a cord. Each joint a cable closes is closed by that one cable alone.
_Avoid_: spool (for the joint itself)

**Closed pose**:
The value of each joint a cable closes when its wheel has made its full turn; where no source states it, it is proposed, and a stated order of closing (one joint before another) is then not represented.
_Avoid_: grasp pose, final pose

**Loop**:
A pair of datums on two instances that must coincide, closing a ring of joints such as a four-bar.
_Avoid_: closure constraint, cut joint

**Pose**:
A configuration of the assembly given by joint values measured from the assembly as built; a check evaluated at one is posed.
_Avoid_: state, configuration (for the values themselves)

**Check**:
One comparison between the built geometry and a ledger value, or a value worked out from ledger values alone (an expect, such as module × teeth): an envelope, a distance or an angle between datums, a diameter, a mass, a count of instances or of threaded holes, an interference, or a whole part against its released body (a shape check).
_Avoid_: test, assertion

**Reads**:
What a check's evaluation read: the params the check names (its pose, its sweep's steps, a mass check's density), the params the model gives it (its joint's range ends, the ratio or lead of each gear and the turn and closed values of each cable a pose moves a joint through) and the parts it weighs. What the check rests on is judged from them.
_Avoid_: dependencies, inputs (of a check)

**Claim**:
What a check compares with in place of a ledger value, where a source states a direction but prints no number: a stroke check's `shortens` or `lengthens`, passing only when the change between its two poses exceeds the length tolerance. The statement it cites is a quote with no values.
_Avoid_: assertion, inequality check

**Checked param**:
A param some check reads (see Reads), directly or through a param derived from it, or whose ledger value some check compares. A source param that is not one is unchecked.
_Avoid_: covered (by a check), confirmed (by a check)

**Tolerance**:
How far the value a check evaluates may stray from its ledger value and still pass. It is the model's: how far a made part may stray is its plan's to say. An interference check compares with no ledger value, so its overlap limit is not a tolerance.
_Avoid_: margin, allowance

**Coverage sweep**:
The pass over every text source that lists each stated quantity no ledger quote or skip covers, and over every geometry source that lists each body no shape check or skip covers.
_Avoid_: coverage check, scan

**Shape check**:
A check that aligns a built part with its released body through pairs of datums and compares the largest distance between their surfaces with a length tolerance. It checks the shape as a whole, not the params that build it.
_Avoid_: mesh comparison, ICP check

**Drawing**:
A part's sheet, written by every verification run: its front, top and right views and an isometric one, dimensioned by the checks that read that part alone, each dimension the value as built. An envelope no check compares is a reference dimension. The assembly has an isometric view and no drawing.
_Avoid_: render, sketch, blueprint

**Verification run**:
One execution of `cadrev check`: lint, build, every check, and the report.
_Avoid_: check (for the whole run)

**Evaluate**:
What a check does to the built solids to get the value it compares with the ledger.
_Avoid_: measure

**VERIFIED**:
The status of a project in which every number is accounted for and every check passes, even if some parameters are proposed.

**VERIFIED PENDING REVIEW**:
The status of a project that would be VERIFIED except that some readings await human confirmation.

**PARTIAL**:
The status of a verification run that skipped the build or the coverage sweep, and so makes no claim.

**Exact**:
VERIFIED with no parameter resting on a proposed value, physics values and a sweep's resolution (how many poses it evaluates) aside: exactness is judged over what the sources state about geometry and kinematics.
_Avoid_: verified (for this stronger state)

## Workflow

**Tracer part**:
The first part taken through modelling, checks and the report before any other part is modelled.

**Tracer loop**:
The first closed loop of a mechanism taken through its joints, the MJCF export and a posed check before any other joint is declared.

**Known first**:
A project that builds only its settled parts, those whose every dimension the sources settle (quoted, worked out from quotes, probed or measured), and lists what waits. No parameter rests on a proposed value, physics values and a sweep's resolution aside. The user then builds on it, or has the reconstruction propose the rest as the complete model.
_Avoid_: draft model, sources-only model

**Waiting**:
Of a part in a known-first project: not settled, since it needs a value the sources leave open, and so not built. Of a stated value: one no parameter uses and no check compares, as a waiting part's are.
_Avoid_: pending (for a value; PENDING REVIEW is a status), deferred

**Complete model**:
A project that builds every part: what the sources settle as known first does, and each value they leave open proposed, to be made, beside the gap that would close it.
_Avoid_: full model, final model

**Foundational question**:
A question whose answer shapes every value a complete model proposes, so it is settled before anything is proposed: metric or US, the material, and design or function. The user answers them, or the reconstruction does from the sources and says so.
_Avoid_: assumption (for an answer given in the user's place), clarifying question

**Material**:
What the object's made parts are made of and how (PLA, FDM printed), or none yet. It decides what a proposed wall, clearance and fit can be.
_Avoid_: process (for the answer as a whole)

**Design or function**:
What a complete model follows where the object is hard to make as its sources show it: the design, built as shown, or the function, where a proposed feature that does the same job replaces the one shown.
_Avoid_: fidelity, mode

## Making

**Plan**:
How the object is made and put together, written once its design is accepted: how each part is made or what is bought for it, and the steps that assemble its instances. It is held to the model: every part an instance places is made or bought, every instance is placed by one step, and an instance that floats is an error.
_Avoid_: instructions, bill of materials (for the plan as a whole)

**Step**:
One act of the plan's assembly sequence: the instances it places, the screws it drives, and how. Its view shows what it places on what the steps before it placed.
_Avoid_: operation (an operation makes a part; a step assembles)

**Held**:
Of an instance: touching another instance, which two do within the length tolerance, or within the clearance of one. One that is not held floats, and so does a group of instances that hold only each other: a warning, and an error under a plan. A known-first project with no plan is not held to it.
_Avoid_: mated, constrained, attached

**Clearance**:
The largest gap the model leaves between two parts that hold each other, the loosest fit: a length param project.yaml names.
_Avoid_: tolerance (for a fit's gap), play
