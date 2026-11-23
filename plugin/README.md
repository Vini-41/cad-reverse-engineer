# cad-reverse-engineer

Turn a paper, patent or datasheet into parametric CAD, with every dimension traced to where it came from.

Give your coding agent the documents a device was published in. It rebuilds the object, checks the geometry against what they state, and shows you every dimension it had to propose. You get:

- **CAD you can change.** Every dimension is a named parameter in `params.yaml`, rebuilt into a STEP file for each part and the assembly.
- **A drawing of each part.** Three views and an isometric one, with checked dimensions at their as-built values.
- **A mechanism that moves.** When the model has joints, it exports to the MuJoCo simulator as a kinematic model, with its gear ratios and lead screws.
- **A report you can audit.** Each dimension is traced to a quote, a figure or a released file, or marked as proposed, with the questions that would settle what is open.
- **A plan to make it.** How each part is made, what to buy and how it goes together.

## Use it

Give your agent the documents and ask:

```
Reverse-engineer the gripper in this paper
```

1. **`noob` reads the documents.** It shows what they state and what they leave open, has you confirm what it read off the figures, and asks four things: metric or US, the material, whether to keep the design as shown or only its function, and whether to build only what the documents settle.
2. **`build-model` builds and checks the CAD,** proposing what the documents leave open unless you chose to build only what they settle.
3. **`ask-machinist` reviews the design you accept** as the person who has to make it, then writes the plan.

`noob` and `build-model` each end by naming the line to run next. Start a fresh session and run it: the project's files carry everything across.

## Install

The skills run the `cadrev` CLI, which needs [uv](https://docs.astral.sh/uv/).

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

The CLI downloads its dependencies, so allow network access in `~/.codex/config.toml`:

```toml
[sandbox_workspace_write]
network_access = true
```

Any agent that reads skills:

```
npx skills add Vini-41/cad-reverse-engineer --skill '*'
```

To run the CLI yourself:

```bash
uvx --python '>=3.12,<3.15' cadrev==0.3.1 check my-project
```

Built for Fable 5.2, and [benchmarked](https://github.com/Vini-41/cad-reverse-engineer/blob/main/docs/benchmark.md) across Anthropic's, OpenAI's and Google's frontier models. See [four worked examples](https://github.com/Vini-41/cad-reverse-engineer#readme). MIT license.
