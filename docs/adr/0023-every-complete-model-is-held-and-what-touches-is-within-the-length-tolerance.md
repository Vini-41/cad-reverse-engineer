# Every complete model is held, and what touches is within the length tolerance

Every project's instances are held, a known-first project with no plan aside: an instance that floats is a `[held]` warning, and an error under a plan. The clearance is the model's, so project.yaml names it, not plan.yaml. Two solids touch where they lie within `tolerance.length` of each other. This amends ADR-0022, which held only a plan's instances, kept the clearance in the plan and let nothing but OCC's distance say what touches.

ADR-0022 rejected holding every complete model because the examples legitimately leave out what holds some parts. That left a complete model with no plan free to pass with a part in mid-air, and two past runs did: a mechanism's springs, and a fan's blades off their hub. A warning says so without failing the model whose target leaves out a bearing: the status stands, the report names what floats, and the skill hands it over. A plan still makes it an error, since a plan says the object is put together. A known-first project builds only what the sources settle, so what holds a part may wait, until it has a plan.

A rule that runs without a plan needs its clearance without one. The clearance was always a fact of the model, the largest gap it leaves between two parts that hold each other, so it sits in project.yaml beside the tolerance.

The gearbox example's sun stands 0.00024 mm from its planets: two gears built in mesh, each flank a curve fitted to its involute. That gap is how closely the model realises a contact, which is what `tolerance.length` already states of every other length, and what an interference check already allows of an overlap. A plan on a zero-backlash train would otherwise have to name a clearance it does not have.

We rejected an error for every complete model. The three examples would fail on what their targets leave out: a fan's motor, a gearbox's bearings, a membrane between two clamps, a mould beside its stretcher. So would any project of two objects.

We rejected a way to say what holds a floating instance, a reason beside it as a skip has. ADR-0022 rejected counting a joint as holding for the same cause: the declaration is written across any gap. The warning is the statement, and it stays in the report until the part is held.

We rejected a fixed limit for touching. ADR-0022's 1e-6 followed a review's objection that a loose tolerance would widen the clearance. A tolerance loose enough to hide a floating part is capped at 5% of every value the checks compare, and is printed in the report as the model's own precision.

A `count` check also takes an `expect`. A source states a count per leg or per joint, which no instance count equals, and such a param could only stand unchecked: six of one run's thirteen warnings.
