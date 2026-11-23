# Changelog

The highlights of each version. Its release has the full notes.

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
