# cad-reverse-engineer

Three skills that turn a paper, patent or datasheet into parametric CAD, with every dimension traced to where it came from. Give your coding agent the documents a device was published in, and it builds:

- **CAD you can open and change**: a STEP file per part and one for the assembly, from a parametric build123d model whose every dimension is a named value in `params.yaml`.
- **A mechanism that moves**: joints, gear ratios and lead screws exported to MuJoCo, with stated motion checked on the model.
- **A drawing of each part**: three views and an isometric one, dimensioned with the checked values, with screw threads named from the ISO metric or Unified table.
- **A report of where each dimension came from**: quoted from a document, read off a file the authors released, or proposed because nothing states it, beside the question that would settle it.
- **A plan to make it**: how each part is made, what to buy and the assembly sequence, which `cadrev check` holds to the model.

## The skills

- **`noob`** comes first, for every object. It tells you what the documents state and leave open and what cadrev does not cover, has you confirm what it read off the figures, and asks metric or US, the material, whether to follow the design or the function, and known first or the complete model.
- **`build-model`** starts from that project and builds the parts the documents settle first. For the complete model it then proposes what they leave open from standard sizes: a thread from the table, a screw in a length you can buy. Under **known first** it stops at the settled parts, with what waits listed as questions.
- **`ask-machinist`** reviews the model as the person who has to make it, part by part, and writes the plan.

*"Reverse-engineer the gripper in this paper"* starts with `noob`, and *"with nothing guessed"* chooses known first. Say "build now" and `noob` answers its questions from the documents. `noob` and `build-model` each end by naming the line to run next: clear the context and run it, and the project's files carry everything across.

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

Any agent that reads skills: `npx skills add Vini-41/cad-reverse-engineer --skill '*'`. Install all three, since `noob` and `ask-machinist` read the file formats that `build-model` holds.

Built for Fable 5.2, and [benchmarked](https://github.com/Vini-41/cad-reverse-engineer/blob/main/docs/benchmark.md) across Anthropic's and OpenAI's frontier models on the flow before 0.3.0.

## The CLI

The skills run the `cadrev` CLI on your machine. It needs [uv](https://docs.astral.sh/uv/), which can install the Python 3.12 to 3.14 it runs on. To run it yourself, with no clone:

```bash
uvx --python '>=3.12,<3.15' cadrev==0.3.0 check my-project
```

Its first run downloads the package, build123d, OCC and MuJoCo from PyPI (about a minute), each at an exact version. Under Codex, allow network access as above.

Four worked examples you can run, and the rest of the documentation: https://github.com/Vini-41/cad-reverse-engineer. MIT license.
