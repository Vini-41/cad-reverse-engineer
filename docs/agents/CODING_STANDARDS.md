# Coding standards

What `/code-review` holds a diff to beyond its own baseline. `scripts/check` holds the mechanical rules.

- **A rule earns its place.** cadrev is a verifier. A rule joins it where VERIFIED would otherwise claim something false; a mistake a general mechanism already reports (the schema, a `Fault` at the entry's boundary) gets no rule, branch or doc line of its own.
- **A finding, never a traceback.** Whatever reads project input or user code raises `Fault`, and the boundary that reads the entry files it as a finding that says what is wrong and where.
- **A rule is stated once.** The reference docs give the formats and what they mean; the finding says what broke. A change to a format updates the one reference that owns it, in the same change.
- **One status authority.** The status is decided in `report.status`; everything else that prints or writes it reads that result.
- **Tests drive the CLI.** They assert on rules, statuses and report.json, not on wording, so the tool's modules stay free to change. Every rule the tool can file has a test that trips it.
- **A valid project keeps its verdict.** A change that is not meant to change behaviour leaves every example's report.json as it was.
