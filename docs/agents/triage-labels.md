# Triage Labels

Labels use the canonical role names: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix` for state, and `bug`, `enhancement` for category.

An issue a spec absorbs keeps its category and drops its state label: the spec holds `ready-for-agent` for it, and a comment on the issue names the spec. It stays open until its part of the spec lands.

A `ready-for-agent` brief whose criteria lean on a project setting with a default (`model_literals`, `tolerance`) states the behaviour under a non-default value too, and its triage prototype runs the tool tests, so a criterion that breaks an existing test surfaces in triage rather than as a spec departure.
