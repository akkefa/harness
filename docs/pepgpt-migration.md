# PepGPT migration inventory

Status: **seeded 2026-10-30**. Every phase updates the rows it covers.

This lists every symbol PepGPT imports from its in-tree `harness` package today
(129 symbols, from `app/`, `m365/` and `onereach_profile/` at PepGPT `dev` @
`0cffd1ff`), and where each one lands when PepGPT switches to this package.

Targets marked *proposed* follow the upstream package that owns the concept. They
are confirmed, with exact names, in the phase that ports that package.

## Status values

- **package**: provided by this package. The target column gives the module.
- **pepgpt-plugin**: stays in PepGPT as its own plugin on a public seam.
- **pepgpt-app**: stays in PepGPT's application code. It is not a harness concern.
- **dropped**: replaced by upstream behaviour; PepGPT changes its call site.

## Kernel

| PepGPT import | Status | Target (proposed) | Milestone |
|---|---|---|---|
| `harness.kernel.KernelContext` | package | `deepseek_cordis.Context` | 0.1 |
| `harness.kernel.PluginManager` | package | `deepseek_cordis.loader.Loader` + `harness.bundle` | 0.1 |
| `harness.kernel.Scope` | package | `harness.core.scope` | 0.1 |
| `harness.kernel.EffectHandle` | package | `deepseek_cordis.Effect` | 0.1 |
| `harness.kernel.runtime.KernelRuntime` | package | `harness.bundle` boot API | 0.1 |

## Session and persistence

| PepGPT import | Status | Target (proposed) | Milestone |
|---|---|---|---|
| `harness.core.session.Session` | package | `harness.core.session` | 0.1 |
| `harness.core.session.SessionEvent` | package | `harness.core.session` (v4 event types) | 0.1 |
| `harness.core.session.CoreEventType` | package | `harness.core.session` event type names | 0.1 |
| `harness.core.session.ModelMessage` | package | `harness.llm.llm` message vocabulary | 0.1 |
| `harness.core.session.thaw_json` | package | `harness.session.format` JSON helpers | 0.1 |
| `harness.persistence.SessionStore` | package | `harness.session.persistence` (`SessionPersistence`) | 0.1 |
| `harness.persistence.MemorySessionStore` | package | in-memory store in `harness.core.session` | 0.1 |
| `harness.persistence.DatabaseSessionStore` | pepgpt-plugin | PepGPT Postgres `SessionPersistence` backend (`harness.session.persistence`), checked with `harness.testing.run_persistence_contract` and `run_live_write_path_contract` | 0.1 |

## System prompt and tools

| PepGPT import | Status | Target (proposed) | Milestone |
|---|---|---|---|
| `harness.core.system_prompt.SystemPromptRegistry` | package | `harness.core.system_prompt` (`ctx.system_prompt`) | 0.1 |
| `harness.core.system_prompt.PromptSection` | package | `harness.core.system_prompt` | 0.1 |
| `harness.core.system_prompt.PromptRenderContext` | package | `harness.core.system_prompt` assembly context | 0.1 |
| `harness.core.tools.ToolDefinition` | package | `harness.core.tools` | 0.1 |
| `harness.core.tools.ToolExecutionContext` | package | `harness.core.tools` | 0.1 |
| `harness.core.tools.ToolExecutionMode` | package | `harness.core.tools` | 0.1 |
| `harness.core.tools.ToolExecutionResult` | package | `harness.core.tools` | 0.1 |
| `harness.core.tools.ToolExecutor` | package | `harness.core.tool_executor_native` | 0.1 |
| `harness.core.tools.ToolRegistry` | package | `harness.core.tools` (`ctx.tools`) | 0.1 |
| `harness.core.tools.visibility.restrict_tool_visibility` | package | `harness.core.agent_tool_presentation` | 0.1 |

## Agent and loop

| PepGPT import | Status | Target (proposed) | Milestone |
|---|---|---|---|
| `harness.core.agent.AgentConfig` | package | `harness.core.agent` | 0.1 |
| `harness.core.agent.AgentConstruction` | package | `harness.core.agent` (`ctx.agents.create`) | 0.1 |
| `harness.core.agent.AgentRegistry` | package | `harness.core.agent` (`ctx.agents`) | 0.1 |
| `harness.core.agent.AgentTurnRunner` | package | `harness.core.agent` | 0.1 |
| `harness.core.agent.MissingParentAgentError` | package | `harness.core.agent` | 0.1 |
| `harness.core.agent.RuntimeAgent` | package | `harness.core.agent` (`Agent`) | 0.1 |
| `harness.core.agent.UserInput` | package | `harness.core.agent` | 0.1 |
| `harness.core.agent.api.UserInput` | package | `harness.core.agent` | 0.1 |
| `harness.core.agent_loop.RecursiveToolAgentLoop` | package | `harness.core.agent_loop` (`AgentLoop`) | 0.1 |
| `harness.core.agent_loop.MODEL_REQUEST_ERROR` | package | `harness.llm.llm_retry` / agent request events | 0.1 |
| `harness.core.agent_loop.ModelRequestErrorAction` | package | `harness.llm.llm_retry` | 0.1 |
| `harness.core.agent_loop.ModelRequestFailed` | package | `harness.llm.llm_retry` | 0.1 |
| `harness.core.agent_loop.ask_more_tool` | pepgpt-plugin | PepGPT tool on `ctx.tools` | — |
| `harness.core.agent_loop.handoff_tool` | pepgpt-plugin | PepGPT tool on `ctx.tools` | — |
| `harness.core.agent_loop.human_wait.current_turn_clock` | pepgpt-plugin | PepGPT turn-time accounting via `harness.interaction.user_questions` events | 0.3 |
| `harness.config.AgentBudgets` | package | agent-loop config + `harness.guard.timeout_policy` | 0.1 / 0.2 |

## Model adapters

| PepGPT import | Status | Target (proposed) | Milestone |
|---|---|---|---|
| `harness.llm.LLMAdapter` | package | `harness.llm.llm` adapter seam | 0.1 |
| `harness.llm.LLMRegistry` | package | `harness.llm.llm` (`ctx.llm`) | 0.1 |
| `harness.llm.AdapterCapabilities` | package | `harness.llm.llm` | 0.1 |
| `harness.llm.ModelCapacity` | package | `harness.llm.llm` / `harness.llm.token_meter` | 0.1 |
| `harness.llm.ModelRequest` | package | `harness.llm.llm` prepared call | 0.1 |
| `harness.llm.ModelResponse` | package | `harness.llm.llm` | 0.1 |
| `harness.llm.ModelStreamDelta` | package | `harness.llm.llm` stream chunks | 0.1 |
| `harness.llm.ModelStreamEvent` | package | `harness.llm.llm` stream chunks | 0.1 |
| `harness.llm.FinishReason` | package | `harness.llm.llm` | 0.1 |
| `harness.llm.LLMAdapterError` | package | `harness.llm.llm` | 0.1 |
| `harness.llm.ContextOverflowError` | package | `harness.llm.llm` | 0.1 |
| `harness.llm.is_context_overflow_error` | package | `harness.llm.llm` | 0.1 |
| `harness.llm.LangChainChatModelAdapter` | pepgpt-plugin | PepGPT adapter on the `ctx.llm` seam, checked with `harness.testing.llm_adapter_contract` | 0.1 |

PepGPT's `BedrockClaudeAdapter` and `PepGenXGeminiAdapter` (in
`app/harness_agent/providers.py`) move onto the same seam and run the same
contract suite.

## Context management and compaction

| PepGPT import | Status | Target (proposed) | Milestone |
|---|---|---|---|
| `harness.context_management.CompactionPlugin` | package | `harness.compaction.compaction_basic` | 0.3 |
| `harness.context_management.CompactionPolicy` | package | `harness.compaction.compaction_basic` config | 0.3 |
| `harness.context_management.ModelContextSummarizer` | package | `harness.compaction.compaction_basic` | 0.3 |
| `harness.context_management.ToolResultPruner` | package | `harness.compaction.tool_result_pruner` | 0.3 |
| `harness.context_management.CharacterTokenEstimator` | package | `harness.llm.token_meter` | 0.1 |
| `harness.context_management.measure.estimate_request_usage` | package | `harness.llm.token_meter` | 0.1 |

## Filesystem, shell, attachments, sandbox

| PepGPT import | Status | Target (proposed) | Milestone |
|---|---|---|---|
| `harness.plugins.FilesystemPlugin` | package | `harness.fs.tool_fs` | 0.2 |
| `harness.shell.BashToolPlugin` | package | `harness.shell.tool_bash` | 0.2 |
| `harness.attachments.Attachment` | package | `harness.attachment.attachment` | 0.2 |
| `harness.attachments.AttachmentError` | package | `harness.attachment.attachment` | 0.2 |
| `harness.attachments.AttachmentsPlugin` | package | `harness.attachment.attachment_local` | 0.2 |
| `harness.attachments.SandboxFiles` | package | `harness.fs.fs` seam | 0.2 |
| `harness.attachments.SharedFile` | pepgpt-plugin | PepGPT file sharing over `harness.attachment` | 0.2 |
| `harness.attachments.shared_file_result` | pepgpt-plugin | same | 0.2 |
| `harness.attachments.safe_filename` | package | `harness.attachment.attachment` | 0.2 |
| `harness.code_interpreter.PythonToolPlugin` | pepgpt-plugin | PepGPT tool over `harness.subprocess` | 0.2 |
| `harness.integrations.azure_sessions.AzureSessionPool` | package | `harness.azure_sessions` | 0.2 |
| `harness.integrations.azure_sessions.AzureSessionPoolError` | package | `harness.azure_sessions` | 0.2 |
| `harness.integrations.azure_sessions.AzureShellSession` | package | `harness.azure_sessions` | 0.2 |
| `harness.integrations.azure_sessions.AzureShellExecutor` | package | `harness.azure_sessions` subprocess provider | 0.2 |
| `harness.integrations.azure_sessions.AzureShellFilesystem` | package | `harness.azure_sessions` fs provider | 0.2 |
| `harness.integrations.azure_sessions.AzureSandboxFiles` | package | `harness.azure_sessions` fs provider | 0.2 |
| `harness.integrations.azure_sessions.AzurePythonInterpreter` | pepgpt-plugin | PepGPT code interpreter on the Azure subprocess provider | 0.2 |

## Web

| PepGPT import | Status | Target (proposed) | Milestone |
|---|---|---|---|
| `harness.web.WebRuntime` | package | `harness.web.web` (`ctx.web`) | 0.4 |
| `harness.web.WebToolsPlugin` | package | `harness.web.tool_web` | 0.4 |
| `harness.web.SafeHttpFetchProvider` | package | `harness.web.web_fetch_http` | 0.4 |
| `harness.web.GoogleCustomSearchProvider` | pepgpt-plugin | PepGPT search provider on `ctx.web`, checked with the search provider contract | 0.4 |
| `harness.web.GoogleSearchPlugin` | pepgpt-plugin | same | 0.4 |

## Skills

| PepGPT import | Status | Target (proposed) | Milestone |
|---|---|---|---|
| `harness.skills.SkillDefinition` | package | `harness.skill.skill` | 0.4 |
| `harness.skills.SkillRuntime` | package | `harness.skill.skill` (`ctx.skills`) | 0.4 |
| `harness.skills.StaticSkillProvider` | package | `harness.skill.skill` provider registry | 0.4 |
| `harness.skills.render_skill_content` | package | `harness.skill.tool_skill` | 0.4 |
| `harness.skills.strip_skill_content` | pepgpt-plugin | PepGPT search-budget helper | 0.4 |
| `harness.plugins.AutoSkillsPlugin` | pepgpt-plugin | PepGPT plugin over `ctx.skills` | 0.4 |

## Telemetry and durable tools

| PepGPT import | Status | Target (proposed) | Milestone |
|---|---|---|---|
| `harness.plugins.TelemetryPlugin` | package | `harness.telemetry.otel` + `harness.session.telemetry_otel` | 0.5 |
| `harness.plugins.ToolTelemetryPlugin` | package | same | 0.5 |
| `harness.plugins.TelemetryContext` | package | `harness.telemetry` | 0.5 |
| `harness.plugins.bind_telemetry_context` | package | `harness.telemetry` | 0.5 |
| `harness.plugins.telemetry.TelemetryContext` | package | `harness.telemetry` | 0.5 |
| `harness.plugins.telemetry.bind_telemetry_context` | package | `harness.telemetry` | 0.5 |
| `harness.plugins.DurableToolCallsPlugin` | pepgpt-plugin | PepGPT plugin on `tools/*` events | 0.1 |

## Memory (no upstream counterpart)

All stay in PepGPT as its own plugins. They can move to `harness.contrib.memory`
later if another team needs them.

| PepGPT import | Status |
|---|---|
| `harness.plugins.auto_memory.AutoMemoryPlugin` | pepgpt-plugin |
| `harness.memory.control.JobSnapshot`, `MemoryControlStore`, `MemoryJob`, `MemorySettings` | pepgpt-plugin |
| `harness.memory.markdown.MemoryDocumentError`, `MemoryDraft`, `MemorySummary`, `validate_memory_name` | pepgpt-plugin |
| `harness.memory.matching.best_match` | pepgpt-plugin |
| `harness.memory.privacy.redact_memory_input` | pepgpt-plugin |
| `harness.memory.prompt.render_memory_preview` | pepgpt-plugin |
| `harness.memory.store.MemoryConflictError`, `MemoryDocument`, `MemoryLimitError`, `MemoryStorageError`, `StoredMemory`, `UserMemoryStore`, `account_key` | pepgpt-plugin |

## PepGPT integrations

| PepGPT import | Status | Notes |
|---|---|---|
| `harness.integrations.PepGPTAgentUiAdapter` | pepgpt-app | rebuilt over `ctx.agents` and `session/event`; see `examples/fastapi_sse_server.py` |
| `harness.integrations.AgentUiError` | pepgpt-app | |
| `harness.integrations.SessionOwnership`, `MemorySessionOwnership` | pepgpt-app | |
| `harness.integrations.pepgpt_agent_ui.SessionOwnership` | pepgpt-app | |
| `harness.integrations.PersistentAgentProvider` | pepgpt-app | |
| `harness.integrations.pepgpt.PepGPTTurnContext` | pepgpt-app | |
| `harness.integrations.PepGPTCanaryAdapter`, `PepGPTCanaryPolicy` | pepgpt-app | |
| `harness.integrations.PepGPTPostgresSessionRepository` | pepgpt-plugin | becomes the Postgres `SessionPersistence` backend |
| `harness.integrations.pepgpt_telemetry.ModelTelemetryIdentity`, `PepGPTArizeTelemetrySink`, `PepGPTCanaryTraceProvider` | pepgpt-plugin | Arize listeners on telemetry events |
| `harness.integrations.pepgpt_tool_telemetry.PepGPTArizeToolTelemetrySink` | pepgpt-plugin | same |
| `harness.integrations.turn_relay.Handler`, `TurnRelay`, `question_channel` | pepgpt-app | cross-pod relay; answers go through `harness.interaction.user_questions` |

## Session event mapping

PepGPT event types and their v4 equivalents, so PepGPT can convert stored sessions.
Confirmed in Phase 2 against the pinned inventory (`tests/upstream_assets/persistence-schema.json`,
upstream `ce7073d`); `tests/support/persistence_schema.py` checks a converted event against it.

| PepGPT event | v4 | Conversion |
|---|---|---|
| `session/created` | not an event | v4 has no durable `session/created`; creation metadata lives in the session header (`version`, `id`, `createdAt`, `cwd`, `isSeeded`, …). Drop the event and build the header. |
| `session/end-seed` | `session/end-seed` | Same. A fork child's marker at its inherited cut carries `{"inherited": true}`. |
| `session/forked` | not an event | v4 records fork lineage as header `isSeeded: true` plus the inherited `session/end-seed` marker and the exact inherited prefix length. |
| `turn/start`, `turn/end` | same | `turn/end.reason.kind` must be one of `completed`, `aborted`, `blocked`, `error`, `max-tokens`, `interrupted`, `forked`. |
| `step/start`, `step/end` | same | |
| `system/message`, `developer/message`, `user/message` | same | Messages need `id`, `role`, `content` and a `source` whose `kind` is in v4's closed list (e.g. `user`, `system-prompt`, `tool-registry`, `runtime-context`); PepGPT's own producers need a listed kind to conform. |
| `assistant/message`, `assistant/attempt` | same | v4 requires the embedded compact `stream` array (may be empty) and `source: {kind: "model", provider, model}`. |
| `tool/call`, `tool/result` | same | `tool/result.message` needs `toolCallId` equal to `source.callId`; failure details go in `error: {name, code, reason?}` with `message.isError: true`. |
| `request/header`, `request/context` | same | Headers must omit empty `tools` and empty `adapterDefaults`, and never carry `header.system`. |
| `context/summary` | `compaction/start`, `compaction/summary`, `compaction/end` | Plus a surface `replace` of the summarized range. Exact shape confirmed when `compaction` is ported (0.3). |
| `agent/child-created`, `agent/lineage` | not events | v4 keeps subagent lineage in the child's header (`parentSession`, `origin: "subagent"`, `delegationDepth`) and the `subagent/*` events. Exact mapping confirmed when `subagent` is ported (0.4). |
