# CAD reverse-engineering

Rebuilding a published object, from a single part up to a mechanism like the LegClaw, from its sources (including geometry its authors released) as parametric CAD, optionally with a kinematic model that exports to MuJoCo. Every number is traced to a quoted source or named as a reconstruction choice, and every stated value, motion included, is checked against the built model. The result can be modified and simulated kinematically. It does not cover the reconstructor's own measurements of a physical object, behavioural simulation, fabrication-ready tolerances, or whole robots (ADR-0007).

## Evidence

**Source**:
A registered, hash-pinned document that states things about the object: a paper, supplement, datasheet, video or drawing.
_Avoid_: reference, input

**Figure**:
An image in a source: a plot, photo, drawing or video frame. Figure crops and overlays are taken from it.
_Avoid_: source figure, source image, source pixel

**Ledger**:
The record of every statement the sources make about the object, each a verbatim quote or a hashed figure crop.
_Avoid_: evidence list, extraction

**Reading**:
The label text of a figure crop, transcribed exactly as printed; it counts fully only once a named human has confirmed it.
_Avoid_: quote (for image evidence)

**Conflict**:
Two ledger entries that disagree about the same feature; open until it carries a resolution.

**Stated quantity**:
A number a source prints with a unit, as an `a×b×c` product or as a thread size; each one is ledgered or skipped.
_Avoid_: dimension (for anything that is not a size of the object's geometry), dimension candidate

**Skip**:
A stated quantity set aside with a reason because it is not about the object, such as a test load or a result.
_Avoid_: exclusion, ignore

## Parameters

**Basis**:
The declared origin of a parameter's value: `source`, `derived`, `measured` or `proposed`. A parameter with basis `source` *traces to a source*.

**Rests on**:
The basis a parameter's value ultimately depends on: its own; proposed for a derived parameter that names a gap, since its computation is itself a reconstruction choice; or for any other derived parameter the weakest among the parameters it is computed from, proposed being weaker than measured and measured weaker than source. A check rests on the weakest among the parameters it reads, or on source when it reads none; a mass check that weighs a part in several instances with no stated count rests on proposed, since how many there are is then the model's choice.
_Avoid_: traces to (for a derived parameter), effective basis

**Measured**:
The basis of a value scaled off an image or video frame against a known reference. Never used for evaluating the built model.

**Proposed**:
The basis of a value the reconstruction chooses because no source states it.
_Avoid_: assumed, guessed

**Gap**:
A question that, once answered, would replace a proposed or measured value, or the choice a derived parameter's computation makes, with a stated one.

**Physics value**:
A parameter only the simulation reads, such as a joint's damping or friction, a spring's stiffness or rest, or a tendon's elasticity; it has a basis like any other but shapes no geometry.
_Avoid_: simulation parameter, tuning value

**Spring rest**:
The joint value at which a joint's spring exerts no torque, or no force on a slide, measured from the assembly as built like a pose. A spring preloaded against a stop rests outside its joint's range.
_Avoid_: preset, preload, springref

## Verification

**Instance**:
One placement of a part in the assembly; a check over several instances reads them where the assembly places them.
_Avoid_: copy, occurrence

**Datum**:
A named point on a part's solid that distance and angle checks read: on the axis of a cylindrical face (a pin, a hole, a pivot) or on a face.
_Avoid_: reference point, marker

**Joint**:
How one instance moves relative to another: revolute (turning about an axis through two datums of the moving one), slide (sliding along such an axis) or fixed (moving with the other as one body). A revolute joint or slide is either actuated (an input) or passive (moved by the rest of the mechanism).
_Avoid_: pivot (for the joint itself; a pivot is its datum), prismatic, weld, DOF

**Gear**:
A coupling of two joints of one type, so one moves a stated ratio times as far as the other: meshed gears or a belt.
_Avoid_: transmission, mimic joint

**Cable**:
An inextensible cord laid through datums on several instances, whose length the posed assembly gives; one wound on a wheel joint drives the joints it closes, each moving in proportion to the wheel's turn toward its closed pose. Unlike a tendon, a cable does not stretch.
_Avoid_: tendon (for an inextensible cord)

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
One comparison between the built geometry and a ledger value: an envelope, a distance or an angle between datums, a mass or an interference.
_Avoid_: test, assertion

**Tolerance**:
How far the value a check evaluates may stray from its ledger value and still pass; one other than the default is shown beside its check. An interference check compares with no ledger value, so its overlap limit is not a tolerance, though one other than the default is shown beside its check too.
_Avoid_: margin, allowance

**Coverage sweep**:
The pass over every text source that lists each stated quantity no ledger quote or skip covers.
_Avoid_: coverage check, scan

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
