# A pose may be a number fixed by definition

A check's `pose` or `from` may give a joint value as a number, read in the joint's unit: `{screw: 360}` in degrees is one turn. It says where the check is read, as a sweep's `steps` says how finely, so it adds nothing to what the check rests on and keeps no project from being exact. "8 mm per revolution" fixes the turn by definition, and no source has a number to ledger for it. A pose a source does state ("turned 30° on") names its ledger value, as before.

We rejected ledgering "per turn" as a value (`{turn: 360}`) and a derived param that is a constant of the units (`expr: "360"`): both would put a definition into the ledger or the params, where every value is a claim about the object. A proposed `one_turn`, what projects used before (#121), made every per-turn check rest on proposed and raised `[param-gap]` for a gap no one could answer.
