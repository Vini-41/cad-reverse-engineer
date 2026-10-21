# Triage Labels

Labels use the canonical role names: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix` for state, and `bug`, `enhancement` for category.

An issue a spec absorbs keeps its category and drops its state label: the spec holds `ready-for-agent` for it, and a comment on the issue names the spec. It stays open until its part of the spec lands.

A `ready-for-agent` brief whose criteria lean on a project setting with a default (`model_literals`, `tolerance`) states the behaviour under a non-default value too, and its triage prototype runs `scripts/check`, so a criterion that breaks an existing test or an example's documented status surfaces in triage, named in the brief, rather than as a spec departure. A `ready-for-human` brief's recommended option for a model change is built on that prototype and run through `scripts/check` too, and the brief names each check it breaks.

A `ready-for-agent` brief calls a test a guard only when the behaviour it shows already holds on main; one the fix changes is a test, so `scripts/red-on-main` finds it red.

A `ready-for-agent` refactor brief names each path its guards (`scripts/same-reports`, the tests) do not reach, such as a check a finding stops partway, and says whether it is held fixed or may change, so a difference there is decided in the brief rather than found as a departure.

A `ready-for-agent` brief that changes a rule names, as an acceptance criterion, the line of the reference doc that owns the rule, so the implementer edits it in the same pass as the code.

A brief gated on a future condition ("build only when a real source needs it") is `ready-for-human` until the condition holds; it moves to `ready-for-agent` with a comment naming what met it.
