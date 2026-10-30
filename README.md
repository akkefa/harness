# cordis-harness

A Python implementation of the [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness)
agent runtime, built on [deepseek-cordis](https://github.com/akkefa/deepseek-cordis).

PyPI distribution: `cordis-harness`. Python import: `harness`. Python 3.11+.

> **Status: pre-alpha.** Only the repository tooling exists. Nothing is usable yet.
> See [the plan](docs/PLAN.md) for what lands in each release.

## What it is

DeepSeek Harness is a TypeScript agent runtime in which every part (the model
adapter, the tool registry, the session log, the agent loop) is a Cordis plugin.
This package follows the same design in Python:

- one Python module per upstream package, mapped in [docs/upstream.json](docs/upstream.json)
- the same event names, tool schemas and JSONL session format (v4), so sessions are
  interchangeable with `dsh`
- agents composed from YAML bundles of plugin rows, loaded through the deepseek-cordis
  `Loader`

It is an independent implementation, not an official DeepSeek product. Upstream's own
Python SDK (`deepseek_harness`) drives the Node `dsh` binary over JSON-RPC; this
package runs the harness in-process in Python instead.

## Planned releases

| Release | Contents |
|---|---|
| 0.1 | Core runtime: session log and persistence, prompts, tools, agent loop, DeepSeek and OpenAI-compatible model adapters |
| 0.2 | Execution: local subprocess, filesystem and shell with sandboxing; Azure Container Apps sessions backend |
| 0.3 | Context and control: compaction, instructions, approvals, user questions, todo, plan mode |
| 0.4 | Reach: web search and fetch, MCP, skills, subagents |
| 0.5 | Product foundation: telemetry, settings, credentials, storage, presets, base bundle |

## Name clash

The unrelated PyPI package [`harness`](https://pypi.org/project/harness/) also installs a
top-level `harness` module. Don't install both in one environment.

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Apache-2.0. Upstream notices are in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
