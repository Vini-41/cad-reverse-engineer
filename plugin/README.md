# cad-reverse-engineer

A skill that turns a paper, patent or datasheet into parametric CAD, with every dimension traced to where it came from. Give your coding agent the documents a device was published in, and it builds:

- **CAD you can open and change**: a STEP file per part and one for the assembly, from a parametric build123d model whose every dimension is a named value in `params.yaml`.
- **A mechanism that moves**: joints, gear ratios and lead screws exported to MuJoCo, with stated motion checked on the model.
- **A drawing of each part**: three views and an isometric one, dimensioned with the checked values, with screw threads named from the ISO metric or Unified table.
- **A report of where each dimension came from**: quoted from a document, probed from a file the authors released, or proposed because nothing states it, beside the question that would settle it.

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

Any agent that reads skills: `npx skills add Vini-41/cad-reverse-engineer`.

Then give the agent your documents and ask for the CAD: *"reverse-engineer the gripper in this paper"*. Before it builds, it asks what it cannot assume: metric or US, and whether you want the complete model or known first, only the parts the sources settle, built and checked, before anything is proposed. Say "build now" and it answers those from the sources.

Built for Fable 5.2 and [benchmarked](https://github.com/Vini-41/cad-reverse-engineer/blob/main/docs/benchmark.md) across Anthropic's and OpenAI's frontier models.

## Requirements

The skill's `cadrev` CLI runs locally on your machine and needs [uv](https://docs.astral.sh/uv/) and Python 3.12 to 3.14, which uv can install. Its first run downloads build123d, OCC and MuJoCo from PyPI (about a minute), at the versions pinned in `skills/cad-reverse-engineer/tool/uv.lock`. Under Codex, allow network access as above.

Three worked examples you can run, and the rest of the documentation: https://github.com/Vini-41/cad-reverse-engineer. MIT license.
