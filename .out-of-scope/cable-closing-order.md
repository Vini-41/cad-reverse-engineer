# A cable's stated order of closing

cadrev does not model the order or law in which a cable closes its joints. A cable wound on a wheel moves each joint it closes in proportion to the wheel's turn, from as built to that joint's closed pose (ADR-0009), so every joint it closes is the same fraction of the way there at every pose.

## Why this is out of scope

A stated order of closing, such as a finger's joints bending proximal first through spring preload, is behaviour: it comes from the springs, preloads and contact the cable pulls against. Modelling it would mean either

- letting MuJoCo find where the joints come to rest against their springs, which ADR-0007 and ADR-0009 keep out: a failed check could not say whether the reconstruction or the solver's springs and contacts were wrong, and the posed model cadrev checks would no longer be the one MuJoCo runs; or
- a per-joint onset or ratio law with no stated closed pose, which ADR-0009 rejected: a closed angle is the question a source could answer, a bare ratio or onset is not.

Where no source prints a closing angle, a sequence law would add parameters no source states, and a check could confirm only the order, not the geometry. The closed values stay proposed with a gap, and their `interpretation` says the stated order is not represented, as modeling.md directs.

## Prior requests

- #86: "A cable closes its joints in a stated order"
