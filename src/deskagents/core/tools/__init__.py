"""Scoped tool registry, execution pipeline, schemas, and native executor.

Upstream: packages/core/tools and packages/core/tool-executor-native at ce7073d.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import math
from collections.abc import Awaitable, Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast

from deepseek_cordis import Context, Service, current_context

from deskagents.core.scope import (
    AnonymousEntries,
    NamedEntries,
    ScopedLayers,
    ScopeKey,
    scope_of,
    scope_target,
)
from deskagents.llm import HarnessError, create_tool_result_message
from deskagents.util.values import deep_freeze, snapshot_json_value

from .json_schema import (
    JsonSchemaError,
    assert_object_json_schema,
    assert_supported_json_schema,
    check_supported_json_schema,
    validate_json_schema_value,
)
from .schema import (
    ToolArgsError,
    define_tool,
    parameter_schema_spec_to_json_schema,
    project_tool_schema,
    validate_args,
    value_schema_spec_to_json_schema,
)

RUN_CODE_NAME = "run_code"
TOOL_ABORTED = "ABORTED"
TOOL_ABORTED_BEFORE_DISPATCH = "ABORTED_BEFORE_DISPATCH"


class ToolNotFoundError(HarnessError):
    def __init__(self, name: str, reachable_from: str | None = None) -> None:
        message = (
            f'unknown tool "{name}"'
            if reachable_from is None
            else f'unknown tool "{name}": {reachable_from}'
        )
        super().__init__(message, "UNKNOWN_TOOL")


class ToolOutputError(HarnessError):
    def __init__(self, name: str, violations: Sequence[str]) -> None:
        self.violations = list(violations)
        super().__init__(
            f'tool "{name}" returned invalid output: {"; ".join(violations)}',
            "INVALID_TOOL_OUTPUT",
        )


class ToolActivationError(HarnessError):
    def __init__(self, name: str, cause: object) -> None:
        super().__init__(
            f'cannot resolve availability of tool "{name}"',
            "TOOL_ACTIVATION_FAILED",
            cause=cause,
        )


class ToolExecutorUnavailableError(HarnessError):
    def __init__(self) -> None:
        super().__init__(
            "The selected tool executor is unavailable. Load an executor before running the agent.",
            "TOOL_EXECUTOR_UNAVAILABLE",
        )


class ToolBatchExecutionError(Exception):
    def __init__(self, cause: object, partial: Mapping[str, Any]) -> None:
        super().__init__("Tool batch execution failed")
        self.cause = cause
        self.partial = partial


def _aborted(signal: object) -> bool:
    return bool(getattr(signal, "aborted", False))


def _failure(error: BaseException) -> dict[str, Any]:
    info = (
        {"name": type(error).__name__, "code": error.code}
        if isinstance(error, HarnessError)
        else None
    )
    return {
        "isError": True,
        "error": {"message": str(error), **({"info": info} if info else {})},
        "content": [{"type": "text", "text": f"Error: {error}"}],
    }


class ToolRunContext(Mapping[str, Any]):
    def __init__(self, values: Mapping[str, Any]) -> None:
        self._values = dict(values)
        self.additional_contexts: list[Mapping[str, Any]] = []
        self.concludes_turn = False

    def __getitem__(self, key: str) -> Any:
        return self._values[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)

    def defer_context(self, context: Mapping[str, Any]) -> None:
        self.additional_contexts.append(context)

    def conclude_turn(self) -> None:
        self.concludes_turn = True


@dataclass
class _Registration:
    definition: Mapping[str, Any]
    when: Callable[[Mapping[str, Any]], bool | Awaitable[bool]] | None


class _ToolLayer:
    def __init__(self, scope: ScopeKey | None) -> None:
        suffix = " globally" if scope is None else " in this scope"
        self.tools: NamedEntries[_Registration] = NamedEntries(
            lambda name: ValueError(f'tool "{name}" exists{suffix}')
        )
        self.restrictions: AnonymousEntries[Mapping[str, frozenset[str]]] = AnonymousEntries()

    def is_empty(self) -> bool:
        return self.tools.is_empty() and self.restrictions.is_empty()

    def admits(self, name: str) -> bool:
        return all(
            ("allow" not in item or name in item["allow"])
            and ("deny" not in item or name not in item["deny"])
            for item in self.restrictions.values()
        )


class _GuardLayer:
    def __init__(self, scope: ScopeKey | None) -> None:
        del scope
        self.guards: AnonymousEntries[Callable[[Mapping[str, Any]], str | None]] = (
            AnonymousEntries()
        )

    def is_empty(self) -> bool:
        return self.guards.is_empty()


class ResolvedToolSet:
    def __init__(
        self,
        owner: ScopeKey,
        admitted: Mapping[str, Mapping[str, Any]],
        service: ToolsService,
    ) -> None:
        self._owner, self._admitted, self._service = owner, dict(admitted), service
        self._closed = False

    def dispose(self) -> None:
        self._closed = True

    def view(self, scope: ScopeKey | None) -> Mapping[str, Mapping[str, Any]]:
        if self._closed or scope is not self._owner:
            return {}
        current = self._service._view(scope)[0]
        return {
            name: definition
            for name, definition in self._admitted.items()
            if current.get(name) is definition
        }


class ToolsService(Service):
    name = "tools"

    def __init__(self, ctx: Context, config: object = None) -> None:
        super().__init__(ctx, config)
        self._layers = ScopedLayers(_ToolLayer, lambda: ctx.emit("tools/change"))
        self._guards = ScopedLayers(_GuardLayer, lambda: None)
        self._executors: dict[int, object | None] = {}
        self._root_executor: object | None = None
        system_prompt = ctx.get("systemPrompt")
        from deskagents.core.system_prompt import SystemPrompt

        if not isinstance(system_prompt, SystemPrompt):
            raise RuntimeError("ToolsService requires SystemPrompt")
        system_prompt.tools(self._describe, ctx=ctx)

    def caller(self, ctx: Context | None = None) -> Context:
        candidate = ctx or current_context()
        return candidate if candidate is not None and candidate.root is self.ctx.root else self.ctx

    def register(
        self,
        definition: Mapping[str, Any],
        *,
        when: Callable[[Mapping[str, Any]], bool | Awaitable[bool]] | None = None,
        ctx: Context | None = None,
    ) -> Callable[[], object]:
        name = definition["name"]
        if name == RUN_CODE_NAME:
            raise ValueError(f'tool name "{RUN_CODE_NAME}" is reserved')
        output = definition.get("output")
        if not isinstance(output, Mapping) or not callable(output.get("render")):
            raise TypeError(f'tool "{name}" must declare output')
        assert_supported_json_schema(output.get("schema"))
        timeout = definition.get("timeoutMs")
        if timeout is not None and (
            not isinstance(timeout, int | float) or not math.isfinite(timeout) or timeout <= 0
        ):
            raise TypeError(f'tool "{name}" timeoutMs must be positive')
        return self._layers.effect(
            self.caller(ctx),
            lambda layer: layer.tools.insert(name, _Registration(definition, when)),
            label="tools.register()",
        )

    def _view(
        self, scope: ScopeKey | None
    ) -> tuple[dict[str, Mapping[str, Any]], dict[str, _Registration], set[str]]:
        layers = self._layers.chain_layers(scope)
        own = self._layers.peek(scope)
        inherited = dict(self._layers.global_.tools.entries())
        for layer in layers:
            if layer is own:
                continue
            inherited.update(layer.tools.entries())
        visible: dict[str, Mapping[str, Any]] = {}
        registrations: dict[str, _Registration] = {}
        known = set(inherited)
        for name, registration in inherited.items():
            if all(layer.admits(name) for layer in layers):
                visible[name] = registration.definition
                registrations[name] = registration
        if own is not None:
            for name, registration in own.tools.entries():
                known.add(name)
                visible[name] = registration.definition
                registrations[name] = registration
        return visible, registrations, known

    def restrict(
        self,
        *,
        allow: Sequence[str] | None = None,
        deny: Sequence[str] | None = None,
        ctx: Context | None = None,
    ) -> Callable[[], object]:
        owner = self.caller(ctx)
        scope = scope_of(owner)
        if scope is None:
            raise ValueError("tools.restrict() requires a scoped context")
        if allow is None and deny is None:
            raise ValueError("tools.restrict({}) is a no-op")
        known = self._view(scope)[2]
        unknown = (set(allow or ()) | set(deny or ())) - known
        if unknown:
            raise ValueError(f"tools.restrict() names unknown global tools {sorted(unknown)}")
        compiled = {
            **({"allow": frozenset(allow)} if allow is not None else {}),
            **({"deny": frozenset(deny)} if deny is not None else {}),
        }
        return self._layers.effect(
            owner,
            lambda layer: layer.restrictions.append(compiled),
            label="tools.restrict()",
        )

    def get(
        self,
        name: str,
        scope: ScopeKey | None = None,
        tool_set: ResolvedToolSet | None = None,
    ) -> Mapping[str, Any] | None:
        return (
            self._view(scope)[0].get(name) if tool_set is None else tool_set.view(scope).get(name)
        )

    def executable(
        self,
        name: str,
        scope: ScopeKey | None = None,
        tool_set: ResolvedToolSet | None = None,
    ) -> Mapping[str, Any] | None:
        if tool_set is not None:
            return tool_set.view(scope).get(name)
        visible, registrations, _ = self._view(scope)
        registration = registrations.get(name)
        return visible.get(name) if registration is not None and registration.when is None else None

    def definitions(
        self, scope: ScopeKey | None = None, tool_set: ResolvedToolSet | None = None
    ) -> list[Mapping[str, Any]]:
        return list(
            self._view(scope)[0].values() if tool_set is None else tool_set.view(scope).values()
        )

    def schemas(
        self, scope: ScopeKey | None = None, tool_set: ResolvedToolSet | None = None
    ) -> list[dict[str, Any]]:
        return [project_tool_schema(item) for item in self.definitions(scope, tool_set)]

    async def resolve(self, context: Mapping[str, Any]) -> ResolvedToolSet:
        agent, signal = context["agent"], context["signal"]
        if _aborted(signal):
            raise asyncio.CancelledError
        visible, registrations, _ = self._view(agent)
        admitted: dict[str, Mapping[str, Any]] = {}
        for name, definition in visible.items():
            when = registrations[name].when
            try:
                enabled = True if when is None else when(context)
                if inspect.isawaitable(enabled):
                    enabled = await enabled
            except Exception as error:
                raise ToolActivationError(name, error) from error
            if _aborted(signal):
                raise asyncio.CancelledError
            if enabled:
                admitted[name] = definition
        return ResolvedToolSet(agent, admitted, self)

    def _describe(self, context: Mapping[str, Any]) -> Mapping[str, Any]:
        executor = self._select_executor(context.get("scope"))
        result = executor.describe(self.definitions(context.get("scope"), context.get("toolSet")))
        return {
            **result,
            "knownNames": result.get("knownNames", list(self._view(context.get("scope"))[2])),
        }

    def set_executor(self, executor: object, *, ctx: Context | None = None) -> Callable[[], object]:
        owner = self.caller(ctx)
        scope = scope_of(owner)
        key = 0 if scope is None else id(scope)
        if (
            self._root_executor is not None
            if scope is None
            else key in self._executors and self._executors[key] is not None
        ):
            raise ValueError("Only one tool executor may be registered in each scope")

        def setup() -> Callable[[], None]:
            if scope is None:
                self._root_executor = executor
            else:
                self._executors[key] = executor

            def cleanup() -> None:
                if scope is None:
                    self._root_executor = None
                else:
                    self._executors[key] = None

            return cleanup

        return owner.effect(setup, "tools.setExecutor()")

    def _select_executor(self, scope: ScopeKey | None) -> Any:
        from deskagents.core.scope import scope_chain_of

        for key in scope_chain_of(scope):
            if id(key) in self._executors:
                executor = self._executors[id(key)]
                if executor is None:
                    break
                return executor
        if self._root_executor is None:
            raise ToolExecutorUnavailableError
        return self._root_executor

    async def execute(self, input_: Mapping[str, Any]) -> Mapping[str, Any]:
        result = await self._select_executor(input_.get("agent")).execute(input_)
        return cast(Mapping[str, Any], result)

    def guard(
        self,
        guard: Callable[[Mapping[str, Any]], str | None],
        *,
        ctx: Context | None = None,
    ) -> Callable[[], object]:
        return self._guards.effect(
            self.caller(ctx),
            lambda layer: layer.guards.append(guard),
            label="tools.guard()",
        )

    def check_guards(self, execution: Mapping[str, Any]) -> str | None:
        for layer in [
            self._guards.global_,
            *self._guards.chain_layers(execution.get("agent")),
        ]:
            for guard in layer.guards.values():
                if (reason := guard(execution)) is not None:
                    return reason
        return None


class NativeToolExecutor:
    def __init__(self, ctx: Context, max_parallel: Callable[[], int] = lambda: 10) -> None:
        self.ctx, self.max_parallel = ctx, max_parallel
        tools = ctx.get("tools")
        if not isinstance(tools, ToolsService):
            raise RuntimeError("NativeToolExecutor requires ToolsService")
        self.tools = tools

    def describe(self, tools: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
        return {"schemas": [project_tool_schema(tool, False) for tool in tools]}

    async def _one(
        self,
        call: Mapping[str, Any],
        input_: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        signal = input_["signal"]
        arguments: object
        try:
            arguments = json.loads(call.get("arguments") or "{}")
        except json.JSONDecodeError:
            arguments = call.get("arguments")
        values = {
            "callId": call["id"],
            "rootCallId": call["id"],
            "name": call["name"],
            "arguments": deep_freeze(snapshot_json_value(arguments)),
            "agent": input_.get("agent"),
            "toolSet": input_.get("toolSet"),
            "signal": signal,
            "token": object(),
        }
        execution = ToolRunContext(values)
        if _aborted(signal):
            return {
                "callId": call["id"],
                "result": _failure(
                    HarnessError(
                        "tool call aborted before dispatch",
                        TOOL_ABORTED_BEFORE_DISPATCH,
                    )
                ),
            }
        try:
            decision = self.ctx.waterfall(
                "tools/pre-execute",
                execution,
                next_=lambda: {"kind": "allow"},
                filter_=scope_target(self.tools, input_.get("agent")),
            )
            if inspect.isawaitable(decision):
                decision = await decision
            decision = cast(Mapping[str, Any], decision)
            reason = (
                decision.get("reason")
                if decision["kind"] in ("deny", "ask")
                else self.tools.check_guards(execution)
            )
            if decision["kind"] == "cancel":
                raise HarnessError(
                    "tool call aborted before dispatch", TOOL_ABORTED_BEFORE_DISPATCH
                )
            if reason is not None:
                raise HarnessError(reason, (decision.get("info") or {}).get("code", "DENIED"))
            tool = self.tools.executable(call["name"], input_.get("agent"), input_.get("toolSet"))
            if tool is None:
                raise ToolNotFoundError(call["name"])
            value = await tool["execute"](arguments, execution)
            detached = snapshot_json_value(value)
            if detached is None:
                raise ToolOutputError(call["name"], ["value is not lossless JSON"])
            violations = validate_json_schema_value(tool["output"]["schema"], detached)
            if violations:
                raise ToolOutputError(call["name"], violations)
            content = tool["output"]["render"](arguments, detached)
            result: dict[str, Any] = {
                "isError": False,
                "value": deep_freeze(detached),
                "content": content,
                **(
                    {"meta": tool["output"]["presentationMeta"](arguments, detached)}
                    if "presentationMeta" in tool["output"]
                    else {}
                ),
                **(
                    {"additionalContexts": execution.additional_contexts}
                    if execution.additional_contexts
                    else {}
                ),
                **({"concludesTurn": True} if execution.concludes_turn else {}),
            }
            post = self.ctx.waterfall(
                "tools/post-execute",
                execution,
                result,
                next_=lambda: {"kind": "accept"},
                filter_=scope_target(self.tools, input_.get("agent")),
            )
            if inspect.isawaitable(post):
                post = await post
            post = cast(Mapping[str, Any], post)
            if post["kind"] == "block":
                result = {
                    "isError": True,
                    "error": {"message": "tool result blocked by post-execute policy"},
                    "content": post["feedback"],
                }
            elif "content" in post:
                result = {**result, "content": post["content"]}
        except BaseException as error:
            result = _failure(error if isinstance(error, BaseException) else Exception(str(error)))
        final = snapshot_json_value(result, freeze=True)
        self.ctx.emit(
            "tools/result",
            execution,
            final,
            filter_=scope_target(self.tools, input_.get("agent")),
        )
        return {"callId": call["id"], "result": final}

    async def execute(self, input_: Mapping[str, Any]) -> Mapping[str, Any]:
        limit = input_.get("maxParallelToolCalls", self.max_parallel())
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
            raise ValueError("maxParallelToolCalls must be a positive integer")
        results: list[Mapping[str, Any]] = []
        calls = list(input_["calls"])

        def is_parallel(call: Mapping[str, Any]) -> bool:
            tool = self.tools.executable(call["name"], input_.get("agent"), input_.get("toolSet"))
            classifier = None if tool is None else tool.get("isConcurrencySafe")
            if not callable(classifier):
                return False
            try:
                arguments = json.loads(call.get("arguments") or "{}")
                return classifier(arguments) is True
            except Exception:
                return False

        async def run_group(
            group: Sequence[Mapping[str, Any]],
        ) -> list[tuple[Mapping[str, Any], int | None]]:
            call_seqs: list[int | None] = []
            for call in group:
                log = input_.get("log")
                agent = input_.get("agent")
                if log is None:
                    call_seqs.append(None)
                else:
                    if agent is None:
                        raise ValueError("logged tool batches require an agent")
                    event = agent.session.append(
                        "tool/call",
                        {
                            **log,
                            "callId": call["id"],
                            "name": call["name"],
                            "arguments": call.get("arguments", ""),
                        },
                    )
                    call_seqs.append(event["seq"])
            semaphore = asyncio.Semaphore(limit)

            async def settled(call: Mapping[str, Any]) -> Mapping[str, Any]:
                async with semaphore:
                    return await self._one(call, input_)

            outcomes = await asyncio.gather(*(settled(call) for call in group))
            return list(zip(outcomes, call_seqs, strict=True))

        index = 0
        while index < len(calls):
            if is_parallel(calls[index]):
                end = index + 1
                while end < len(calls) and is_parallel(calls[end]):
                    end += 1
                group = calls[index:end]
            else:
                end = index + 1
                group = calls[index:end]
            settled_group = await run_group(group)
            for call, (settled, call_seq) in zip(group, settled_group, strict=True):
                result = settled["result"]
                log = input_.get("log")
                agent = input_.get("agent")
                if log is not None:
                    assert agent is not None
                    assert call_seq is not None
                    agent.session.append(
                        "tool/result",
                        {
                            **log,
                            "message": create_tool_result_message(
                                call_id=call["id"],
                                content=result["content"],
                                is_error=result["isError"],
                            ),
                            **(
                                {"error": result["error"]["info"]}
                                if result.get("error", {}).get("info")
                                else {}
                            ),
                            **({"meta": result["meta"]} if "meta" in result else {}),
                        },
                        surface_op="append",
                        source_event_seqs=[call_seq],
                    )
                results.append(settled)
            if any(item["result"].get("concludesTurn") is True for item in results):
                break
            index = end
        contexts = [
            context
            for settled in results
            for context in settled["result"].get("additionalContexts", ())
        ]
        return {
            "results": results,
            "additionalContexts": contexts,
            "concluded": any(item["result"].get("concludesTurn") is True for item in results),
        }


def install_native_tool_executor(ctx: Context, config: object = None) -> NativeToolExecutor:
    del config
    tools = ctx.get("tools")
    if not isinstance(tools, ToolsService):
        raise RuntimeError("ToolsService is not installed")
    executor = NativeToolExecutor(ctx)
    tools.set_executor(executor, ctx=ctx)
    return executor


__all__ = [
    "JsonSchemaError",
    "NativeToolExecutor",
    "RUN_CODE_NAME",
    "ResolvedToolSet",
    "TOOL_ABORTED",
    "TOOL_ABORTED_BEFORE_DISPATCH",
    "ToolActivationError",
    "ToolArgsError",
    "ToolBatchExecutionError",
    "ToolExecutorUnavailableError",
    "ToolNotFoundError",
    "ToolOutputError",
    "ToolRunContext",
    "ToolsService",
    "assert_object_json_schema",
    "assert_supported_json_schema",
    "check_supported_json_schema",
    "define_tool",
    "install_native_tool_executor",
    "parameter_schema_spec_to_json_schema",
    "project_tool_schema",
    "validate_args",
    "validate_json_schema_value",
    "value_schema_spec_to_json_schema",
]
