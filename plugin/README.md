# cad-reverse-engineer

A skill that rebuilds a part, gripper or mechanism from a paper, patent, supplement or datasheet as a parametric build123d model, with STEP and MuJoCo exports. Every number the sources state is recorded as a verbatim quote or a hashed figure crop, every parameter the model uses declares its basis, and every stated value is checked against the built geometry. `build/report.md` says what is verified and which values the reconstruction proposed.

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

Then ask the agent something like *"reverse-engineer the gripper in this paper as CAD"*. It asks whether you want the complete model or known first: only the parts the sources settle, built and checked, before anything is proposed.

Built for Fable 5.2 and [benchmarked](https://github.com/Vini-41/cad-reverse-engineer/blob/main/docs/benchmark.md) across Anthropic's and OpenAI's frontier models.

## Requirements

The skill's `cadrev` CLI runs locally on your machine and needs [uv](https://docs.astral.sh/uv/) and Python 3.10 to 3.13, which uv can install. Its first run downloads build123d, OCC and MuJoCo from PyPI (about a minute), at the versions pinned in `skills/cad-reverse-engineer/tool/uv.lock`. Under Codex, allow network access as above.

Source, examples and documentation: https://github.com/Vini-41/cad-reverse-engineer. MIT license.
