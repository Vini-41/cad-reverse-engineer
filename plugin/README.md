# cad-reverse-engineer

Three skills that turn a paper, patent or datasheet into parametric CAD, with every dimension traced to where it came from. Give your coding agent the documents a device was published in, and it builds:

- **CAD you can open and change**: a STEP file per part and one for the assembly, from a parametric build123d model whose every dimension is a named value in `params.yaml`.
- **A mechanism that moves**: joints, gear ratios and lead screws exported to MuJoCo, with stated motion checked on the model.
- **A drawing of each part**: three views and an isometric one, dimensioned with the checked values, with screw threads named from the ISO metric or Unified table.
- **A report of where each dimension came from**: quoted from a document, probed from a file the authors released, or proposed because nothing states it, beside the question that would settle it.
- **A plan to make it**: how each part is made, what to buy and the assembly sequence, held to the model.

## The skills

- **`known-first`** builds only what the documents settle, and lists what they leave open as questions. Nothing is guessed.
- **`complete-model`** builds the whole object. It asks metric or US, the material, and whether to follow the design or the function, then proposes what the documents leave open from standard sizes: a thread from the table, a screw in a length you can buy.
- **`ask-machinist`** reviews the model as the person who has to make it, part by part, and writes the plan.

Name the skill you want, or ask for the CAD: *"reverse-engineer the gripper in this paper"* gets you the complete model. Say "build now" and it answers its questions from the documents.

## Install

Claude Code:

```
/plugin marketplace add Vini-41/cad-reverse-engineer
/plugin install cad-reverse-engineer@cad-reverse-engineer
```

Codex:

```
codex plugin marketplace add Vini-41/cad-reverse-engineer
codex plugin add cad-reverse-engineer@cad-reverse-engineer
```

Codex's default sandbox blocks network access, which the CLI needs to download its dependencies. Allow it in `~/.codex/config.toml`:

```toml
[sandbox_workspace_write]
network_access = true
```

Any agent that reads skills: `npx skills add Vini-41/cad-reverse-engineer --skill '*'`. Install all three, since `complete-model` and `ask-machinist` use the CLI that `known-first` holds.

Built for Fable 5.2 and [benchmarked](https://github.com/Vini-41/cad-reverse-engineer/blob/main/docs/benchmark.md) across Anthropic's and OpenAI's frontier models.

## Requirements

The skills' `cadrev` CLI runs locally on your machine and needs [uv](https://docs.astral.sh/uv/) and Python 3.12 to 3.14, which uv can install. Its first run downloads build123d, OCC and MuJoCo from PyPI (about a minute), at the versions pinned in `skills/known-first/tool/uv.lock`. Under Codex, allow network access as above.

Three worked examples you can run, and the rest of the documentation: https://github.com/Vini-41/cad-reverse-engineer. MIT license.
