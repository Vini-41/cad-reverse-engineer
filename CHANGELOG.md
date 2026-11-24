# Changelog

The highlights of each version. Its release has the full notes.

## [v0.4.1](https://github.com/Vini-41/cad-reverse-engineer/releases/tag/v0.4.1)

- **A raised number stays raised.** `cadrev text` writes a superscript as one: `10⁻⁵` and `cm²`, not `105` and `cm2`. This covers PDF, HTML and DOCX sources. `2.1 × 10⁵ MPa` reads as one quantity, 210 000 MPa. A raised run after a unit is that unit's power, and anywhere else it is a footnote marker and no number.
- **A symbol font reads as printed.** In Elsevier papers, `cadrev text` now reads µ, β, °, ~, −, ©, ® and bullets as the page shows them. A concentration such as `20 µM` is no longer read as a length.

**Upgrading:** a `[quote-not-found]` on a quote that passed before means it copied a flattened superscript or a misread symbol. Quote the page as `cadrev text` now prints it, with superscripts or carets (`10^-5`).

## [v0.4.0](https://github.com/Vini-41/cad-reverse-engineer/releases/tag/v0.4.0)

- **The model states each hole's fit.** `threads` holds a hole or shank that carries the thread, and the new `clears` holds a hole its screw passes through. cadrev no longer guesses the fit from the diameter. The drawing, the plan's screw warning and a `count` check read the fit stated, and a count counts each screw once.
- **A ledger number is the number the page prints.** `cadrev text` reads a symbol font's µ and ×, prints an inch mark as ″, and keeps two table cells apart. A quote that copied one of these misreadings is refused.
- **A check that raises is a finding.** It files `[check-unevaluated]` with the check's name, and the report says NOT VERIFIED. A full run that dies leaves no earlier report behind.
- **`--no-build` no longer warns `[unchecked-source]`** about params a shape check covers. The full run still names a param no check compares.

**Upgrading:** move each clearance hole from `threads` to `clears`. One wider than the thread's major diameter fails with `[model-thread]` until it is moved. One at the major diameter still passes as tapped, so find those by hand. A hole the screw cuts its own thread in is neither, so leave it undeclared. A `[quote-not-found]` on a quote that passed before means it copied a misreading: quote the page as `cadrev text` now prints it.

## [v0.3.1](https://github.com/Vini-41/cad-reverse-engineer/releases/tag/v0.3.1)

- **Figures reach every model.** `cadrev figures` writes a grayscale or CMYK JPEG as PNG, because some models refuse those JPEGs.
- **A proposed or derived param takes no `from`.** Its citation counted a stated value as used even when the param contradicted it. This is now a `[param-from]` error.

**Upgrading:** a project with such a param fails until its `from` is removed. If the param replaces a stated value, set that value aside with `scope: not-modeled` and a reason.

## [v0.3.0](https://github.com/Vini-41/cad-reverse-engineer/releases/tag/v0.3.0)

See what a document settles before anything is built, then build and plan the object in three skills.

- **`noob` comes first.** It reads the documents, shows what they state and leave open, and asks what only you can answer.
- **`build-model` replaces `known-first` and `complete-model`.** It builds the settled parts first, and stops there under known first.
- **The CLI is a package.** One `uvx` line runs it with no clone, and the plugin holds no code.
- **Stated ranges are checked as ranges,** as a datasheet prints its MIN and MAX.
- **A released part is proven by one shape check,** compared whole with the authors' file.
- **The kinematic model claims nothing about behaviour.** It carries no spring, damper or friction.
- **A datasheet example:** the RP2040's QFN-56 package.

**Upgrading:** 0.3.0 refuses a format-1 project, and nothing migrates it. [The release notes](https://github.com/Vini-41/cad-reverse-engineer/releases/tag/v0.3.0) show how to keep running it on 0.2.0 or carry it forward by hand.

## [v0.2.0](https://github.com/Vini-41/cad-reverse-engineer/releases/tag/v0.2.0)

A model you can make, shaped by a mechanical engineer's review.

- **Three skills in place of one:** `known-first`, `complete-model` and `ask-machinist`.
- **Three questions before anything is proposed:** metric or US, the material, and design or function.
- **Threads and screws come from the standard tables,** in lengths you can buy.
- **A plan held to the model,** with a view of each assembly step.
- **A drawing of each part,** dimensioned by its checks.
- **A part left in mid-air is flagged,** and is an error once the project has a plan.

## [v0.1.0](https://github.com/Vini-41/cad-reverse-engineer/releases/tag/v0.1.0)

The first release: a skill and its CLI, `cadrev`, with three worked examples.
