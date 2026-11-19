# A plan's instances are held, and each step has a view

A plan is held to one more thing: every instance is held. An instance is held where it touches another, or sits within the plan's `clearance` of one, the length param of the loosest fit; a group of instances that hold only each other floats as one. `cadrev check` files what floats as `[plan-held]`, naming it and its gap, so a model with a plan is one object. A part made beside the object, a fit coupon or a jig, is a part no instance places.

The plan is also written as `build/plan.md`, a guide of its own, in place of a section of the report (ADR-0021): what is made, what is bought, and each step that places an instance over `build/steps/<n>.png`, the isometric view of the instances it places, in black and named by part, on what the steps before it placed, in grey, taking in the part each goes onto. A step that places nothing has no view. The report links to it.

This came from a mechanical engineer's review of a mechanism rebuilt to be printed: the assembly had parts floating in it, and the assembly guide wanted illustrations. The model was VERIFIED with a plan. Its fit coupon was an instance 42 mm from the mechanism, because a made part had to be placed to be counted, and its sixteen extension springs were tubes that touched nothing, their hooks left out. The same shows in other objects: a jig placed beside a mould, fan blades off their hub, a power supply beside its device.

We rejected holding every complete model to it. The three examples follow released geometry and legitimately leave out what holds some parts: bearings, a membrane between two clamps, a second unit beside the first. A plan is where a model claims to be put together, so that is where floating is false.

We rejected counting a joint as holding. The springs each had a fixed joint to the part they hovered beside: a joint says how an instance moves, and is declared across any gap.

We rejected a fixed limit. Across the runs, fits leave gaps from 0.1 to 0.5 mm and the springs floated at 0.3 mm, so only the project's own fit separates the two; naming its param keeps the number in params.yaml, with its basis and its gap.

We rejected asking each step to place its instances onto what is already there: a subassembly starts on the bench, held by nothing yet. Only the finished assembly is held to being one object.

We rejected a setting for a more detailed guide. The views are drawn from the model and the steps, so they cost the user nothing and are always written. We rejected exploded views and arrows: nothing tells cadrev the direction a part goes in from (ADR-0021 rejects sweeping it into place), and a view that guessed would mislead.

Whether two solids touch is OCC's exact distance, computed only between the faces that a proximity test on their meshes names; a group left apart is confirmed between whole solids, so a mesh never decides that an instance floats.
