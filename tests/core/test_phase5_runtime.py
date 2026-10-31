from __future__ import annotations

import asyncio
from collections.abc import AsyncIterable, Mapping
from pathlib import Path
from typing import Any

import pytest
from deepseek_cordis import Context

from harness.core import AgentLoop, AgentRegistry, SystemPrompt, ToolsService, define_tool
from harness.core.session import SessionStore
from harness.core.tools import NativeToolExecutor
from harness.llm import LlmAdapter, LlmRuntime, create_user_message
from harness.session import SessionTitleService, persistence_jsonl
from harness.testing import ScriptedAdapter


async def runtime(
    scripts: list[list[Mapping[str, Any]]],
) -> tuple[Context, Any, ScriptedAdapter]:
    ctx = Context()
    await ctx.plugin(LlmRuntime)
    await ctx.plugin(SessionStore)
    await ctx.plugin(SystemPrompt, {"includeHarnessIdentity": False, "personaPrefix": "Helpful"})
    await ctx.plugin(ToolsService)
    tools = ctx.get("tools")
    assert isinstance(tools, ToolsService)
    tools.set_executor(NativeToolExecutor(ctx), ctx=ctx)
    await ctx.plugin(AgentRegistry)
    await ctx.plugin(AgentLoop)
    adapter = ScriptedAdapter(scripts)
    llm = ctx.get("llm")
    assert isinstance(llm, LlmRuntime)
    llm.register_adapter(["test"], adapter)
    return ctx, ctx.get("agents"), adapter


@pytest.mark.asyncio
@pytest.mark.upstream(
    "packages/core/system-prompt/tests/system-prompt.spec.ts::"
    "assembles sections in order with context-resolved text and collected tools"
)
async def test_prompt_assembly() -> None:
    ctx = Context()
    await ctx.plugin(SystemPrompt, {"includeHarnessIdentity": False, "personaPrefix": "A"})
    prompt = ctx.get("systemPrompt")
    assert isinstance(prompt, SystemPrompt)
    prompt.section({"name": "b", "order": 20, "text": lambda context: context["value"]})
    prompt.section({"name": "a", "order": 10, "text": "first"})
    prompt.variable("who", lambda context: context["who"])
    prompt.section({"name": "variable", "order": 30, "text": "Hi {{who}}"})
    prompt.tools(lambda context: {"schemas": [{"name": "z", "description": "Z", "parameters": {}}]})
    assembly = await prompt.assemble({"value": "second", "who": "Sol"})
    assert [item["name"] for item in assembly["sections"]] == [
        "deployment:persona-prefix",
        "a",
        "b",
        "variable",
        "deployment:persona-suffix",
    ]
    assert assembly["tools"][0]["name"] == "z"
    await ctx.fiber.dispose()


@pytest.mark.asyncio
@pytest.mark.upstream(
    "packages/core/tools/tests/tools.spec.ts::"
    "registry round-trips a defineTool definition (register→schemas→execute)"
)
async def test_native_tool_round_trip() -> None:
    ctx = Context()
    await ctx.plugin(SystemPrompt)
    await ctx.plugin(ToolsService)
    tools = ctx.get("tools")
    assert isinstance(tools, ToolsService)
    tools.set_executor(NativeToolExecutor(ctx), ctx=ctx)

    async def execute(args: Mapping[str, Any], execution: object) -> object:
        del execution
        return {"answer": args["value"] + 1}

    definition = define_tool(
        name="increment",
        description="Increment",
        parameters={"value": {"type": "integer", "required": True}},
        output={
            "schema": {
                "type": "object",
                "properties": {"answer": {"type": "integer"}},
                "required": ["answer"],
                "additionalProperties": False,
            },
            "render": lambda args, value: [{"type": "text", "text": str(value["answer"])}],
        },
        execute=execute,
    )
    tools.register(definition)
    signal = type("Signal", (), {"aborted": False})()
    result = await tools.execute(
        {
            "calls": [
                {
                    "type": "tool-call",
                    "id": "call-1",
                    "name": "increment",
                    "arguments": '{"value":4}',
                }
            ],
            "signal": signal,
        }
    )
    assert result["results"][0]["result"]["content"] == [{"type": "text", "text": "5"}]
    await ctx.fiber.dispose()


@pytest.mark.asyncio
async def test_scripted_agent_no_tool_turn() -> None:
    ctx, agents, adapter = await runtime(
        [
            [
                {"type": "text-delta", "index": 0, "text": "hello"},
                {"type": "finish", "reason": {"kind": "stop"}},
            ]
        ]
    )
    handle = await agents.create(
        {
            "sessionId": "phase5-no-tool",
            "agentOptions": {"provider": "test", "model": "scripted"},
        }
    )
    handle.agent.followup(
        create_user_message(content=[{"type": "text", "text": "hi"}], source={"kind": "user"})
    )
    await handle.agent.when_idle()
    types = [event["type"] for event in handle.agent.session.snapshot_events()]
    assert types[-5:] == [
        "request/header",
        "request/context",
        "assistant/message",
        "step/end",
        "turn/end",
    ]
    assert adapter.requests[0]["messages"][-1]["role"] == "user"
    await handle.dispose()
    await ctx.fiber.dispose()


def tool_call(call_id: str = "call-1") -> list[Mapping[str, Any]]:
    return [
        {
            "type": "block-end",
            "index": 0,
            "block": {
                "type": "tool-call",
                "id": call_id,
                "name": "echo",
                "arguments": '{"value":"ok"}',
            },
        },
        {"type": "finish", "reason": {"kind": "stop"}},
    ]


def answer(text: str = "done") -> list[Mapping[str, Any]]:
    return [
        {"type": "text-delta", "index": 0, "text": text},
        {"type": "finish", "reason": {"kind": "stop"}},
    ]


async def register_echo(ctx: Context) -> None:
    tools = ctx.get("tools")
    assert isinstance(tools, ToolsService)

    async def execute(args: Mapping[str, Any], execution: object) -> object:
        del execution
        return args["value"]

    tools.register(
        define_tool(
            name="echo",
            description="Echo",
            parameters={"value": {"type": "string", "required": True}},
            output={
                "schema": {"type": "string"},
                "render": lambda args, value: [{"type": "text", "text": value}],
            },
            execute=execute,
        )
    )


@pytest.mark.asyncio
async def test_scripted_agent_single_tool_turn() -> None:
    ctx, agents, adapter = await runtime([tool_call(), answer()])
    await register_echo(ctx)
    handle = await agents.create(
        {
            "sessionId": "phase5-tool",
            "agentOptions": {"provider": "test", "model": "scripted"},
        }
    )
    handle.agent.followup(
        create_user_message(
            content=[{"type": "text", "text": "use echo"}],
            source={"kind": "user"},
        )
    )
    await handle.agent.when_idle()
    types = [event["type"] for event in handle.agent.session.snapshot_events()]
    assert types.count("assistant/message") == 2
    assert types.count("tool/call") == types.count("tool/result") == 1
    assert len(adapter.requests) == 2
    await handle.dispose()
    await ctx.fiber.dispose()


@pytest.mark.asyncio
async def test_scripted_agent_recursive_tool_turn() -> None:
    ctx, agents, adapter = await runtime([tool_call("call-1"), tool_call("call-2"), answer()])
    await register_echo(ctx)
    handle = await agents.create(
        {
            "sessionId": "phase5-recursive",
            "agentOptions": {"provider": "test", "model": "scripted"},
        }
    )
    handle.agent.followup(
        create_user_message(content=[{"type": "text", "text": "twice"}], source={"kind": "user"})
    )
    await handle.agent.when_idle()
    types = [event["type"] for event in handle.agent.session.snapshot_events()]
    assert types.count("tool/result") == 2
    assert len(adapter.requests) == 3
    await handle.dispose()
    await ctx.fiber.dispose()


@pytest.mark.asyncio
async def test_scripted_agent_failed_step_is_balanced() -> None:
    ctx, agents, _ = await runtime(
        [
            [
                {
                    "type": "finish",
                    "reason": {"kind": "error", "failure": {"message": "boom", "code": "FAILED"}},
                }
            ]
        ]
    )
    handle = await agents.create(
        {
            "sessionId": "phase5-failed",
            "agentOptions": {"provider": "test", "model": "scripted"},
        }
    )
    handle.agent.followup(
        create_user_message(content=[{"type": "text", "text": "fail"}], source={"kind": "user"})
    )
    await handle.agent.when_idle()
    events = handle.agent.session.snapshot_events()
    assert events[-2]["type"] == "step/end"
    assert events[-1]["type"] == "turn/end"
    assert events[-1]["data"]["reason"]["kind"] == "error"
    await handle.dispose()
    await ctx.fiber.dispose()


class WaitingAdapter(LlmAdapter):
    def __init__(self) -> None:
        self.started = asyncio.Event()

    def stream(self, options: Mapping[str, Any]) -> AsyncIterable[Mapping[str, Any]]:
        async def generate() -> AsyncIterable[Mapping[str, Any]]:
            self.started.set()
            signal = options["signal"]
            while not signal.aborted:  # noqa: ASYNC110 - adapter observes the runtime signal
                await asyncio.sleep(0)
            yield {
                "type": "finish",
                "reason": {
                    "kind": "aborted",
                    "failure": {"message": "aborted", "code": "ABORTED"},
                },
            }

        return generate()


@pytest.mark.asyncio
async def test_scripted_agent_cancelled_turn_is_balanced() -> None:
    ctx, agents, _ = await runtime([])
    llm = ctx.get("llm")
    assert isinstance(llm, LlmRuntime)
    waiting = WaitingAdapter()
    llm.register_adapter(["wait"], waiting)
    handle = await agents.create(
        {
            "sessionId": "phase5-cancelled",
            "agentOptions": {"provider": "wait", "model": "model"},
        }
    )
    handle.agent.followup(
        create_user_message(content=[{"type": "text", "text": "wait"}], source={"kind": "user"})
    )
    await waiting.started.wait()
    handle.agent.cancel({"kind": "user"}, keep_inbox=True)
    await handle.agent.when_idle()
    events = handle.agent.session.snapshot_events()
    assert events[-2]["type"] == "step/end"
    assert events[-1]["type"] == "turn/end"
    assert events[-1]["data"]["reason"] == {
        "kind": "aborted",
        "reason": {"kind": "user"},
    }
    await handle.dispose()
    await ctx.fiber.dispose()


@pytest.mark.asyncio
async def test_concurrency_safe_tools_use_bounded_parallel_pool() -> None:
    ctx = Context()
    await ctx.plugin(SystemPrompt)
    await ctx.plugin(ToolsService)
    tools = ctx.get("tools")
    assert isinstance(tools, ToolsService)
    tools.set_executor(NativeToolExecutor(ctx), ctx=ctx)
    active = 0
    peak = 0
    release = asyncio.Event()
    pool_filled = asyncio.Event()

    async def execute(args: Mapping[str, Any], execution: object) -> object:
        nonlocal active, peak
        del args, execution
        active += 1
        peak = max(peak, active)
        if active == 2:
            pool_filled.set()
        await release.wait()
        active -= 1
        return "ok"

    tools.register(
        define_tool(
            name="parallel",
            description="Parallel",
            parameters={},
            output={
                "schema": {"type": "string"},
                "render": lambda args, value: [{"type": "text", "text": value}],
            },
            execute=execute,
            isConcurrencySafe=lambda args: True,
        )
    )
    signal = type("Signal", (), {"aborted": False})()
    task = asyncio.create_task(
        tools.execute(
            {
                "calls": [
                    {"id": f"call-{index}", "name": "parallel", "arguments": "{}"}
                    for index in range(3)
                ],
                "signal": signal,
                "maxParallelToolCalls": 2,
            }
        )
    )
    await pool_filled.wait()
    release.set()
    result = await task
    assert peak == 2
    assert [item["callId"] for item in result["results"]] == [
        "call-0",
        "call-1",
        "call-2",
    ]
    await ctx.fiber.dispose()


@pytest.mark.asyncio
async def test_agent_can_resume_persisted_session(tmp_path: Path) -> None:
    ctx, agents, _ = await runtime([[*answer("first")], [*answer("second")]])
    await ctx.plugin(
        persistence_jsonl,
        {"root": str(tmp_path), "compression": "none"},
    )
    created = await agents.create(
        {
            "sessionId": "phase5-resume",
            "agentOptions": {"provider": "test", "model": "scripted"},
        }
    )
    created.agent.followup(
        create_user_message(content=[{"type": "text", "text": "one"}], source={"kind": "user"})
    )
    await created.agent.when_idle()
    await created.dispose()
    resumed = await agents.resume(
        {
            "resumeSessionId": "phase5-resume",
            "agentOptions": {"provider": "test", "model": "scripted"},
        }
    )
    resumed.agent.followup(
        create_user_message(content=[{"type": "text", "text": "two"}], source={"kind": "user"})
    )
    await resumed.agent.when_idle()
    assert (
        len(
            [
                event
                for event in resumed.agent.session.snapshot_events()
                if event["type"] == "assistant/message"
            ]
        )
        == 2
    )
    await resumed.dispose()
    await ctx.fiber.dispose()


@pytest.mark.asyncio
async def test_fallback_session_title_is_logged() -> None:
    ctx = Context()
    await ctx.plugin(SessionStore)
    await ctx.plugin(
        SessionTitleService,
        {"fallbackMaxWords": 3, "fallbackMaxBytes": 30, "maxTitleBytes": 50},
    )
    sessions = ctx.get("sessions")
    assert isinstance(sessions, SessionStore)
    session = sessions.create("title")
    session.append(
        "user/message",
        create_user_message(
            content=[{"type": "text", "text": "  A useful title with extras  "}],
            source={"kind": "user"},
        ),
        surface_op="append",
    )
    await asyncio.sleep(0)
    title = ctx.get("sessionTitle")
    assert isinstance(title, SessionTitleService)
    snapshot = title.get(session)
    assert snapshot is not None
    assert snapshot["title"] == "A useful title"
    await ctx.fiber.dispose()
