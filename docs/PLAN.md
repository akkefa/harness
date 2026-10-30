# Harness package: implementation plan

Status: **draft for review, revision 2**. No code has been written yet.
Date: 2026-10-30.

Revision 2 makes the upstream TypeScript DeepSeek Harness the source of truth.
Revision 1 (a port of the PepGPT Python harness) is replaced.

## Goal

A Python implementation of [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness)
that any team can install from PyPI and build agents on. It follows upstream's
architecture, package boundaries, event vocabulary and session file format, and
runs on [deepseek-cordis](https://github.com/akkefa/deepseek-cordis), the Python
port of upstream's Cordis plugin runtime.

A second goal shapes many decisions: PepGPT must be able to replace its in-tree
`harness/` with this package later without a rewrite. See
[PepGPT replacement](#pepgpt-replacement) and
[pepgpt-migration.md](pepgpt-migration.md).

## Decisions

| Topic | Decision |
|---|---|
| Source of truth | Upstream DeepSeek Harness TypeScript, pinned per milestone. PepGPT's Python harness is used only as a head start where its code already matches current upstream behaviour. |
| Session file | Upstream JSONL **format v4**, the same event names, fields and file layout. Sessions are interchangeable with `dsh`. |
| Composition | Upstream-style config rows. Bundles are YAML row lists loaded through the deepseek-cordis `Loader`, plus a Python API that builds the same rows. |
| Model adapters | Port upstream's DeepSeek adapter (`[deepseek]`) and add a generic OpenAI-compatible adapter (`[openai]`). |
| Execution backends | Port upstream's local subprocess, filesystem and shell with its sandbox policy. Add PepGPT's Azure Container Apps sessions backend as `[azure]`. |
| Distribution name | `cordis-harness` on PyPI. `harness` and `deepseek-harness` are taken by unrelated projects. |
| Import name | `import harness`. Upstream's own Python SDK uses `deepseek_harness`; it drives the Node `dsh` binary over JSON-RPC and is a different thing. |
| Python | `>=3.11`, same as deepseek-cordis. CI runs 3.11, 3.12, 3.13. |
| License | Apache-2.0 (already in the repo). MIT notices for DeepSeek Harness and Cordis in `THIRD_PARTY_NOTICES.md`. |
| Tooling | Copied from PyCordis: hatchling, uv, ruff, mypy, pytest, GitHub Actions CI, tag-triggered PyPI release. |

## Sources and locations

| What | Path or URL | Pinned at |
|---|---|---|
| **This package (target)** | `/Users/iali/workplace/projects/personal/harness` · <https://github.com/akkefa/harness> | `main` @ `397471b` (uv scaffold only) |
| **Upstream DeepSeek Harness (source of truth)** | `/Users/iali/workplace/projects/personal/deepseek-harness` · <https://github.com/deepseek-ai/deepseek-harness> | `master` @ `ce7073d` (2026-10-30) |
| Upstream architecture docs | `deepseek-harness/docs/architecture.md`, `docs/capability-seams.md`, `docs/subsystems/*.md` | same |
| Upstream session format | `deepseek-harness/docs/session-format-status.md`, `docs/persistence-schema.json`, `docs/persistence-changes/finalized/v4.json` | format v4 |
| Upstream bundles | `deepseek-harness/packages/bundle/sdk-minimal/cordis.patch.yml`, `packages/bundle/base/cordis.patch.yml` | same |
| deepseek-cordis (plugin runtime) | `/Users/iali/workplace/projects/personal/PyCordis` · <https://github.com/akkefa/deepseek-cordis> · <https://pypi.org/project/deepseek-cordis/> | repo `0.1.2` @ `f804a26`, audited against Harness `f3803c9` and vendored Cordis 4.0.6-alpha.1; PyPI latest `0.1.1` |
| PepGPT Python harness (head start, migration target) | `/Users/iali/workplace/projects/pep/pepgpt-llm-orchestrator/harness/` | `dev` @ `0cffd1ff`, ported from upstream `21638c5` (2026-09-27) |
| PepGPT code that uses the harness | `/Users/iali/workplace/projects/pep/pepgpt-llm-orchestrator/app/harness_agent/`, `m365/`, `onereach_profile/` | same |
| pepgpt-cordis (what PepGPT uses today) | `/Users/iali/workplace/projects/pep/pepgpt-cordis` | `0.1.3`. Same API as deepseek-cordis; only logging and namespace differ. |
| Unrelated earlier experiment | `/Users/iali/workplace/projects/personal/py-harness` (LangChain and Deep Agents) | not used |

## Upstream at a glance

Facts this plan is built on, from upstream `ce7073d`:

- Everything is a Cordis plugin, including the model adapter, tool registry,
  session log and agent loop. Registrations are effects that unwind when their
  plugin unloads.
- A **capability seam** has three roles: Service Definition (interface), Service
  Provider (implementation), Consumer (usually a model-facing tool). Plugins depend
  on definitions, never on concrete providers.
- A running agent is a plugin tree composed from **bundles** (ordered config rows)
  and **profiles**. `dsh-sdk-minimal` is a complete standalone tree;
  `dsh-base` is the shared product foundation.
- Three event domains: durable **session events** (`turn/*`, `step/*`,
  `user/message`, `assistant/message`, `tool/*` …), live **agent events**
  (`agent/pre-step`, `agent/request`, `agent/assistant-stream` …) and
  **capability events** (`tools/pre-execute`, `fs/*`, `telemetry/*`). Waterfalls
  call `next()`; serial events do not.
- **Model-visible means logged.** Every model request can be rebuilt from the
  session log. `deriveMessages()` projects model history from it.
- JSONL persistence uses immutable, version-named generation files, a single-writer
  lease and valid-prefix recovery. The current writer format is v4.
- Size of the in-scope upstream source, excluding tests: core spine about 12k lines,
  `llm` group about 10k, `session` group about 9k, and execution, compaction, web,
  skill, subagent, MCP and interaction together about 45k. About a third of the
  `subagent` group (ACP, Claude Code, Codex and DSH SDK providers) is out of scope.

## Scope

### In scope, by milestone

Each upstream package becomes one Python module directory named after it
(`@deepseek-ai/dsh-session-persistence-jsonl` → `harness.session.persistence_jsonl`).

| Milestone | Upstream packages |
|---|---|
| **0.1 Core runtime** | `core/scope`, `core/session`, `core/system-prompt`, `core/tools`, `core/tool-executor-native`, `core/agent`, `core/agent-loop`, `core/agent-default-model`, `core/agent-tool-presentation`; `llm/llm`, `llm/llm-retry`, `llm/token-meter`, `llm/llm-deepseek` (+ `deepseek-llm-api-extensions`, `session-log-deepseek` as needed); new OpenAI-compatible adapter; `session/session-format`, `session/session-persistence`, `session/session-persistence-jsonl`, `session/session-projection`, `session/session-checkpoint-policy`, `session/session-title` (fallback only); bundle loader and a `minimal` bundle |
| **0.2 Execution** | `subprocess/subprocess`, `subprocess-local`; `sandbox/sandbox`, `sandbox-local` (bwrap on Linux, Seatbelt on macOS), `sandbox-policy`; `fs/fs`, `fs-local`, `fs-sandbox`, `fs-observation-policy`, `tool-fs`, `tool-fs-search`; `shell/shell`, `shell-env`, `bash-local`, `bash-sandbox`, `tool-bash`; `session/working-directory`, `tool-working-directory`; `attachment/attachment`, `attachment-local`; `spill/spill`, `spill-local`, `spill-policy`; `guard/timeout-policy`; Azure sessions backend (from PepGPT) |
| **0.3 Context and control** | `compaction/compaction`, `compaction-basic`, `compaction-tool-result-pruner`, `compaction-image-offload`, `command-compact`; `context/agent-instructions`, `time-context`; `interaction/commands`, `user-approval`, `user-questions`, `tool-ask-user`, `permission-presets`; `todo`; `plan/plan-mode`; `guard/repeat-tool-reminder`; `session/session-title-llm` |
| **0.4 Reach** | `web/web`, `tool-web`, `web-fetch-http`, `web-search-deepseek`, `web-deepseek-api`, `web-search-exa`, `web-search-perplexity`; `mcp/mcp-client` (official `mcp` Python SDK), `mcp-resources`; `skill/skill`, `skill-filesystem`, `tool-skill`; `subagent/subagent`, `subagent-spawn-in-process`, `subagent-fork-in-process`, `subagent-in-process-driver`, `tool-subagent`, `tool-subagent-control` |
| **0.5 Product foundation** | `telemetry/otel`, `session/session-telemetry-otel`; `settings`; `credentials` (env and `.env` provider); `storage` (JSON backend); `preset/agent-preset`, `agent-preset-registry`; a Python `base` bundle |

### Out of scope

Not planned. Each can be reconsidered later.

- GUI and servers: `host`, `client`, web server, desktop app, `api` gateway, `typert`.
- Node-specific runtimes: `ptc-runtime`, `workflow`, `tool-executor-ptc`, HMR,
  plugin manager, `extensions`.
- Other environments: `ssh`, `terminal`/PTY (persistent shell), `lsp`,
  `browser-use`, `computer-use`, PowerShell and Windows ACL sandbox, Landlock
  (needs upstream's native addon).
- Product features: `goal`, `schedule`, `jobs`, `feedback`, `deliverables`,
  `session-query`, agent teams, DeepSeek account login.
- Upstream's own SDK and ACP servers (`sdk`, `acp`). A JSON-RPC server compatible
  with upstream's Python SDK is a possible later addition.
- Reading session formats v0–v3. v4 only; older files are refused with a clear
  error until the migration chain is ported.

## Target layout

```
harness/                              repo root
  src/harness/
    __init__.py  py.typed
    core/
      scope/  session/  system_prompt/  tools/  tool_executor_native/
      agent/  agent_loop/  agent_default_model/  agent_tool_presentation/
    llm/                              the llm seam itself (packages/llm/llm)
      retry/  token_meter/  deepseek/  deepseek_api_key/  openai/
    session/
      format/  persistence/  persistence_jsonl/  projection/
      checkpoint_policy/  title/  log_deepseek/  working_directory/
    subprocess/  sandbox/  fs/  shell/  attachment/  spill/  guard/
    azure_sessions/                   paired fs + subprocess providers (like upstream ssh/)
    compaction/  context/  interaction/  todo/  plan/
    web/  mcp/  skill/  subagent/
    telemetry/  settings/  credentials/  storage/  preset/
    bundle/
      loader.py                       YAML rows -> deepseek-cordis Loader
      minimal.yml  base.yml
    testing/                          scripted adapter + contract suites (public)
  tests/
    <mirrors src>/                    ported upstream specs
    upstream_assets/                  pinned copies of persistence-schema.json, v4.json, fixtures
    boundary/                         import and dependency rules
  docs/
    PLAN.md  pepgpt-migration.md  upstream.md  compatibility-cases.json
    <one page per capability>
  examples/  scripts/
  THIRD_PARTY_NOTICES.md  CHANGELOG.md  CONTRIBUTING.md  README.md
```

The exact naming rule is in [upstream.md](upstream.md#module-names): a group's own
package (its Service Definition) is the group module itself, so `fs/fs` is
`harness.fs` and `fs/fs-local` is `harness.fs.local`.

Each module directory exposes Cordis plugin metadata (`name`, `inject`,
`Config`) and an `apply(ctx, config)` or a `Service` subclass, so a YAML row can
reference it as `harness.fs.tool_fs`. Each module's docstring names the upstream
package and commit it follows.

## Python translation rules

| Upstream TypeScript | Python |
|---|---|
| `ctx.systemPrompt`, `ctx.agentLoop`, … | the same services in snake_case: `ctx.system_prompt`, `ctx.agent_loop` |
| `@deepseek-ai/cordis` Context, Service, effects, events | `deepseek_cordis` equivalents |
| schemastery config schemas | Pydantic models, validated through the deepseek-cordis `ConfigValidator` |
| `AbortSignal` | asyncio cancellation plus an explicit cancellation-cause object where upstream records a cause |
| async iterables and streams | `AsyncIterator` |
| declaration merging for `SessionEventMap` | an explicit event-codec registry; unknown durable events fail closed |
| `cordis.yml` rows and patches | YAML rows of `id`, `name` (Python reference), `config`, `disabled`; patches replace a row by `id` or insert rows |
| `fetch` | `httpx` (only in the extras that need HTTP) |
| zstd JSONL | the optional `[zstd]` extra (`zstandard`) |

Names of events, session event types, tool names and tool schemas are copied
exactly, because sessions and model-visible output must match upstream.

## Dependencies

| Group | Packages |
|---|---|
| core | `deepseek-cordis>=0.1.1,<0.2`, `pydantic>=2.7,<3`, `pyyaml>=6` |

Each extra is added to `pyproject.toml` in the phase that adds the module needing it,
and registered in `tests/boundary/test_import_boundaries.py`.

| Group | Packages |
|---|---|
| `[deepseek]`, `[openai]` | `httpx>=0.27` |
| `[web]` | `httpx>=0.27`, HTML extraction library chosen in Phase 10 |
| `[mcp]` | `mcp>=1.10` |
| `[azure]` | `httpx>=0.27` |
| `[otel]` | `opentelemetry-api`, `opentelemetry-sdk` |
| `[zstd]` | `zstandard` |
| `[all]` | everything above |

## How upstream fidelity is kept

1. **One pin per milestone.** `docs/upstream.md` records the upstream commit and
   maps every upstream package in scope to its Python module.
2. **Source-indexed tests.** Each ported upstream test case carries
   `@pytest.mark.upstream("packages/core/session/tests/surface.spec.ts::<case name>")`
   and is listed in `docs/compatibility-cases.json`, the pattern PyCordis already
   uses. Intentional differences are recorded there with a reason.
3. **Format conformance.** Sessions written by Python are checked against a pinned
   copy of upstream's `persistence-schema.json`. That file is a normalized type
   inventory with per-type digests, not a ready-made JSON Schema, so Phase 2 adds a
   small validator that reads it. Session files written by `dsh` at
   the pinned commit are committed as fixtures and must open, project and replay in
   Python. Python-written files must open in `dsh`.
4. **Change tracking.** `scripts/upstream_changes.py` lists upstream commits since the
   pin that touch any mapped package. It is run at the start of every milestone and
   the result goes in `docs/upstream-audit-<date>.md`, as PyCordis does.
5. **Cordis first.** If a harness package needs a Cordis behaviour deepseek-cordis
   lacks, the fix lands and is released in deepseek-cordis before the harness uses it.

## PepGPT replacement

Built in from the start so the later switch is mostly wiring, not rewriting.

1. **PepGPT plugs into seams.** Everything product-specific in PepGPT becomes a
   provider or listener on a public seam: a Postgres `SessionPersistence` backend,
   Bedrock, Gemini and LangChain model adapters, a Bing search provider, Arize
   telemetry listeners, the agent UI and SSE layer over `ctx.agents` and
   `session/event`. Nothing PepGPT-specific goes into this package.
2. **Contract suites.** `harness.testing` ships reusable test suites for every seam
   PepGPT implements: session persistence backend, LLM adapter, filesystem and
   subprocess providers, search and fetch providers. PepGPT runs them against its
   own providers.
3. **Azure sessions backend in the package.** PepGPT's remote execution moves here
   as `[azure]`, shaped like upstream's paired `ssh` providers.
4. **Migration inventory.** [pepgpt-migration.md](pepgpt-migration.md) lists all 129
   symbols PepGPT imports from `harness` today, with their upstream counterpart and
   the milestone that provides it. Every phase updates the rows it covers.
5. **PepGPT-only features stay in PepGPT.** Memory, auto-skills, the Python code
   interpreter, durable tool calls, hand-off tools and the canary have no upstream
   counterpart. PepGPT keeps them as its own plugins on the public seams. Any of them
   can move into a `harness.contrib` module later if another team needs it.
6. **Session data.** PepGPT's stored sessions use its own event vocabulary. The
   migration doc maps each PepGPT event type to its v4 equivalent so PepGPT can write
   a one-time converter.
7. **Cordis.** PepGPT replaces `pepgpt-cordis` with `deepseek-cordis`; the API is the same.

## Phases

Every phase ends with `ruff check`, `mypy src` and `pytest` green, the
compatibility catalog and migration inventory updated, and one commit on the
working branch `port/v0.1`. Nothing is pushed, tagged or published without the
owner's go-ahead.

### Phase 0 — Repo and upstream tooling

- Replace the uv scaffold: `pyproject.toml` (hatchling, `cordis-harness`,
  `>=3.11`, extras), remove the `harness:main` script, add `py.typed`.
- Copy and adapt from PyCordis: CI and release workflows, distribution and
  installation check scripts, ruff/mypy/pytest config, the compatibility-case
  catalog format.
- `docs/upstream.md` with the pin and the full package → module map.
- `scripts/upstream_changes.py`.
- Copy pinned upstream assets into `tests/upstream_assets/`.
- Boundary tests: no imports of PepGPT, LangChain or other non-declared
  dependencies; `import harness` works with only the core dependencies.
- `THIRD_PARTY_NOTICES.md`, `CHANGELOG.md`, `CONTRIBUTING.md`, README skeleton,
  `docs/pepgpt-migration.md`.

**Exit:** `uv build`, `twine check` and an empty test suite pass locally.

### Phase 1 — Cordis alignment

- List every Cordis API the in-scope upstream packages use (`inject`, `provide`,
  services, effects, waterfall/serial/parallel events, scope labels, isolate
  realms, the timer plugin, loader rows and patches).
- Check each against deepseek-cordis and write the gaps down.
- Close gaps in deepseek-cordis and release it. Upstream is planning a Cordis rc.11
  upgrade; the audit notes which gaps depend on it.

**Exit:** a gap list with each item closed or scheduled; the harness pins the
deepseek-cordis version that covers 0.1.

### Phase 2 — Scope and session log

- Port `core/scope` and `core/session`: v4 event types, the append-only log,
  sequence ranges, active surface, `derive_messages`, plugin message projections,
  request header and context events, repair, fork and seed.
- Port `session/session-format` (v4 codec, filenames, canonical JSON).
- Port the session spec files (about 20) as source-indexed tests.
- Also needed, and ported here: the `llm/llm` message and call-config vocabulary and the
  `util/values` JSON helpers the session log uses (`docs/upstream.json` maps both).
- Rule found here for every later service: upstream Cordis hands a service method the
  caller's context; deepseek-cordis doesn't, so services resolve the caller as explicit
  `ctx=`, else `current_context()`, else themselves (`SessionStore.caller`).

**Exit:** v4 events round-trip through the codec, conform to the pinned
`persistence-schema.json` inventory (which, at `ce7073d`, already differs from the
finalized v4 baseline in 8 event types and adds 3), and `derive_messages` matches
upstream test cases.

### Phase 3 — Session persistence

- Port `session/session-persistence` (handle, lease, `create`/`open`/`stat`/`list`/`export`)
  and `session/session-persistence-jsonl` (generations, exclusive publication,
  valid-prefix recovery, two-process lease). zstd behind `[zstd]`.
- Port `session-projection`, `session-checkpoint-policy`, and `session-title`
  (fallback titles only).
- Generate v4 session fixtures with `dsh` at the pin (needs Node 24 and a local
  upstream build; done once and committed).
- Add `harness.testing.persistence_contract` for third-party backends.

**Exit:** Python opens, projects and replays `dsh`-written fixtures; a Python-written
session opens in `dsh`; the contract suite passes for memory and JSONL stores.

### Phase 4 — Model seam

- Port `llm/llm` (message and stream vocabulary, adapter seam, `ctx.llm`),
  `llm-retry` and `token-meter`.
- Add `harness.testing.ScriptedAdapter` and `harness.testing.llm_adapter_contract`.

**Exit:** the scripted adapter passes the adapter contract; retry and token metering
pass their ported specs.

### Phase 5 — Agent spine and bundles

- Port `core/system-prompt`, `core/tools`, `core/tool-executor-native`,
  `core/agent`, `core/agent-loop`, `core/agent-default-model` and
  `core/agent-tool-presentation`.
- Bundle loader: YAML rows → deepseek-cordis `Loader`, row patches by `id`, and a
  Python builder that produces the same rows. Ship `bundle/minimal.yml`.
- Port the agent-loop specs (about 27 files), tools specs and system-prompt specs.
- Example: `examples/minimal_agent.py` with the scripted adapter.

**Exit:** a scripted agent runs no-tool, single-tool, recursive-tool, cancelled and
failed-step turns, and the session log matches upstream's sequence for each.

### Phase 6 — Model adapters → release 0.1.0

- Port `llm/llm-deepseek` (with the DeepSeek wire extensions and
  `session-log-deepseek` where they affect the log) as `[deepseek]`.
- New `llm/llm_openai` as `[openai]`: Chat Completions streaming, tool calls, usage,
  finish reasons, context-overflow mapping, custom base URL and headers, Azure
  OpenAI mode.
- Both pass `llm_adapter_contract` using recorded HTTP responses; no live calls in CI.
- README quick start, `docs/` pages for the core, and the 0.1.0 changelog.

**Exit:** both adapters pass the contract; the examples run by hand against real
endpoints. Release 0.1.0 to TestPyPI, then PyPI, **after owner approval**.

### Phase 7 — Execution world

- Port the subprocess, sandbox (bwrap and Seatbelt), sandbox-policy, filesystem,
  shell, working-directory, attachment (`read_image`), spill and timeout-policy
  packages listed under 0.2.
- Add contract suites for filesystem and subprocess providers.
- Sandbox tests run in CI on Linux (bwrap) and macOS (Seatbelt).

**Exit:** `bundle/minimal.yml` reaches parity with upstream `sdk-minimal`, apart
from the persistent PTY shell.

### Phase 8 — Azure sessions backend → release 0.2.0

- Port PepGPT's Azure Container Apps sessions code as paired filesystem and
  subprocess providers, following upstream's `ssh` group shape.
- Run the filesystem and subprocess contract suites against it with mocked HTTP.

**Exit:** the same `tool_fs` and `tool_bash` work unchanged on local and Azure
backends. Release 0.2.0 after approval.

### Phase 9 — Context and control → release 0.3.0

- Port the compaction, context, interaction, todo, plan-mode, repeat-tool-reminder
  and session-title-llm packages listed under 0.3.

**Exit:** compaction replaces older history in the model view without deleting log
events, and a replay rebuilds the compacted request. Approval and user questions
work through the interaction seam. Release 0.3.0 after approval.

### Phase 10 — Web, MCP, skills, subagents → release 0.4.0

- Port the web, MCP, skill and subagent packages listed under 0.4. The MCP client
  wraps the official `mcp` SDK.
- Keep upstream's fetch safety rules (SSRF, redirects, content types, size limits).
  Check them against PepGPT's `SafeHttpFetchProvider` tests and add any missing cases.

**Exit:** web, MCP, skill and subagent specs pass; a subagent uses the same runtime
and persistence as its parent. Release 0.4.0 after approval.

### Phase 11 — Product foundation → release 0.5.0

- Port telemetry (`otel`, `session-telemetry-otel`), settings, credentials,
  storage and presets.
- Ship `bundle/base.yml`: upstream `dsh-base` minus the out-of-scope rows.

**Exit:** `bundle/base.yml` boots with every in-scope row. Release 0.5.0 after approval.

### Phase 12 — PepGPT readiness

- Finish `docs/pepgpt-migration.md`: every one of the 129 symbols has a target, and
  every PepGPT event type has a v4 mapping.
- Example host: `examples/fastapi_sse_server.py` serving an agent over SSE through
  `ctx.agents` and `session/event` (FastAPI only in the example).
- Optional, only with approval and in the PepGPT repo: a trial migration branch that
  runs PepGPT's harness tests against this package.

**Exit:** the migration guide is complete, and either the trial branch passes or its
gaps are written down as issues.

### Ongoing — upstream sync

At the start of each milestone, run `scripts/upstream_changes.py`, write the audit,
move the pin, and port the changes that are approved.

## Test plan

- **Upstream specs:** port the spec cases of each in-scope package, marked with
  their upstream source. Cases that depend on Node-only behaviour are recorded as
  intentional differences rather than silently dropped.
- **Format conformance:** schema validation plus two-way `dsh` fixtures (Phase 3).
- **Contract suites:** shipped in `harness.testing` and run here against every
  in-package provider.
- **Boundary:** dependency and import rules; a core-only install job in CI.
- **Platforms:** Linux and macOS in CI on 3.11–3.13. Windows runs the core suites
  only; the sandboxed shell is not supported there.
- No test makes a network call. Live adapter tests read keys from the environment
  and skip without them.

## Risks and open items

- **Size.** About 75k lines of upstream TypeScript are in scope. Expect 40–50k lines
  of Python. The milestone cuts give a usable 0.1 early.
- **Upstream moves fast.** 4745 commits landed between 2026-09-27 and 2026-10-30.
  Pins per milestone and the change script keep this bounded; upstream APIs are
  still pre-stable.
- **Cordis rc.11.** Upstream is planning a Cordis upgrade that changes config access,
  loader and HMR. deepseek-cordis must follow it, and Phase 1 records the exposure.
- **Exact v4 files.** Byte-level compatibility depends on matching upstream's JSON
  canonicalization (key order, escaping, number formatting). Phase 2 writes a
  canonical encoder and the two-way fixtures prove it.
- **Fixtures need a Node build.** Generating `dsh` fixtures needs Node ≥ 24.9 and a
  pnpm build of the upstream checkout. It is a one-off per pin, not a CI step.
- **Native sandbox features.** Landlock and Windows ACL use upstream's native addon
  and are out of scope. Linux uses bwrap, macOS uses Seatbelt.
- **`import harness` clash.** The unrelated PyPI `harness` package installs the same
  top-level module. The last cheap time to rename is before 0.1.0.
- **deepseek-cordis 0.1.2 is not on PyPI** (PyPI has 0.1.1). Phase 1 decides the
  floor and publishes a release if needed.
- **PepGPT migration cost.** PepGPT will rewrite its model adapters against the new
  seam and convert stored sessions to v4. The contract suites and migration guide
  reduce this but don't remove it.
- **PepGPT code reuse.** Reusing PepGPT code as a head start relies on the owner's
  earlier confirmation that it is cleared for publication.

## Working rules

- One working branch, `port/v0.1`, with one commit per phase.
- Each phase keeps the suite green. Any behaviour that differs from upstream gets a
  test and an entry in `docs/compatibility-cases.json`.
- No push, pull request, tag or publish without the owner's go-ahead.
- No secrets in the repo or CI files. PyPI uses trusted publishing.
