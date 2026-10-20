# Triage Labels

Labels use the canonical role names: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix` for state, and `bug`, `enhancement` for category.

An issue a spec absorbs keeps its category and drops its state label: the spec holds `ready-for-agent` for it, and a comment on the issue names the spec. It stays open until its part of the spec lands.

A `ready-for-agent` brief whose criteria lean on a project setting with a default (`model_literals`, `tolerance`) states the behaviour under a non-default value too, and its triage prototype runs `scripts/check`, so a criterion that breaks an existing test or an example's documented status surfaces in triage, named in the brief, rather than as a spec departure. A `ready-for-human` brief's recommended option for a model change is built on that prototype and run through `scripts/check` too, and the brief names each check it breaks.

A brief gated on a future condition ("build only when a real source needs it") is `ready-for-human` until the condition holds; it moves to `ready-for-agent` with a comment naming what met it.
