"""Default event-sourced Agent driver.

Upstream: packages/core/agent-loop at ce7073d. Asyncio task cancellation is the
Python control boundary replacing Node AbortController listener plumbing.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Mapping, Sequence
from typing import Any, cast

from deepseek_cordis import Context, Service

from deskagents.core.agent import (
    AgentEvents,
    AgentModel,
    AgentRegistry,
    agent_events,
    assemble_context_for,
    turn_boundary_of,
)
from deskagents.core.scope import Scope, create_scope
from deskagents.core.session import (
    RestoredSessionOptions,
    Session,
    SessionStore,
    interrupted_turn_closers,
)
from deskagents.core.system_prompt import (
    SystemPrompt,
    render_context_sections,
    render_context_snapshot,
    render_prompt,
)
from deskagents.core.tools import ResolvedToolSet, ToolBatchExecutionError, ToolsService
from deskagents.llm import (
    AssistantStreamAccumulator,
    BlockAssembler,
    LlmError,
    LlmRuntime,
    create_assistant_message,
    create_system_message,
)
from deskagents.session.persistence import SessionHandle, SessionPersistence

DEFAULT_MAX_PARALLEL_TOOL_CALLS = 10


def inbox_state(session: Session) -> dict[str, list[Mapping[str, Any]]]:
    state: dict[str, list[Mapping[str, Any]]] = {"next-turn": [], "next-step": []}
    for event in session.snapshot_events():
        if event["type"] != "agent/inbox/spliced":
            continue
        data = event["data"]
        target = data["target"]
        state[target] = [
            *state[target][: data["start"]],
            *data["inserted"],
            *state[target][data["start"] + data.get("removedCount", 0) :],
        ]
    return state


class ReactLoopInbox:
    def __init__(self, session: Session, dispatch: AgentEvents) -> None:
        self.session, self.dispatch = session, dispatch

    @property
    def next_turn(self) -> list[Mapping[str, Any]]:
        return inbox_state(self.session)["next-turn"]

    @property
    def next_step(self) -> list[Mapping[str, Any]]:
        return inbox_state(self.session)["next-step"]

    @property
    def has_pending(self) -> bool:
        state = inbox_state(self.session)
        return bool(state["next-turn"] or state["next-step"])

    def splice(
        self,
        target: str,
        start: int,
        delete_count: int,
        inserted: Sequence[Mapping[str, Any]],
        *,
        canceled: bool = True,
    ) -> list[Mapping[str, Any]]:
        state = inbox_state(self.session)
        current = state[target]
        actual_start = min(max(start if start >= 0 else len(current) + start, 0), len(current))
        actual_delete = min(max(delete_count, 0), len(current) - actual_start)
        candidate = [
            *current[:actual_start],
            *inserted,
            *current[actual_start + actual_delete :],
        ]
        other = state["next-step" if target == "next-turn" else "next-turn"]
        ids = [message["id"] for message in [*candidate, *other]]
        if len(ids) != len(set(ids)):
            raise ValueError("message is already pending")
        removed = current[actual_start : actual_start + actual_delete]
        if not removed and not inserted:
            return []
        self.session.append(
            "agent/inbox/spliced",
            {
                "target": target,
                "start": actual_start,
                **({"removedCount": actual_delete} if actual_delete else {}),
                "inserted": list(inserted),
                **({"outcome": "canceled"} if canceled and actual_delete else {}),
            },
        )
        if canceled:
            for message in removed:
                self.dispatch.emit("agent/inbox/discarded", {"message": message})
        for message in inserted:
            self.dispatch.emit("agent/inbox/inserted", {"message": message})
        return removed

    def claim(self, target: str, turn: int) -> list[Mapping[str, Any]]:
        claimed = self.splice("next-step", 0, len(self.next_step), [], canceled=False)
        if target == "next-turn":
            claimed.extend(self.splice("next-turn", 0, 1, [], canceled=False))
        for message in claimed:
            self.dispatch.emit("agent/inbox/claimed", {"message": message, "turn": turn})
        return claimed

    def append(self, target: str, message: Mapping[str, Any]) -> None:
        current = self.next_turn if target == "next-turn" else self.next_step
        self.splice(target, len(current), 0, [message])

    def prepend(self, target: str, message: Mapping[str, Any]) -> None:
        self.splice(target, 0, 0, [message])

    def replace(self, message_id: str, message: Mapping[str, Any]) -> bool:
        for target, current in (("next-turn", self.next_turn), ("next-step", self.next_step)):
            for index, existing in enumerate(current):
                if existing["id"] == message_id:
                    self.splice(target, index, 1, [message])
                    return True
        return False

    def remove(self, message_id: str) -> bool:
        for target, current in (("next-turn", self.next_turn), ("next-step", self.next_step)):
            for index, existing in enumerate(current):
                if existing["id"] == message_id:
                    self.splice(target, index, 1, [])
                    return True
        return False

    def clear(self) -> None:
        self.splice("next-step", 0, len(self.next_step), [])
        self.splice("next-turn", 0, len(self.next_turn), [])


class _Signal:
    aborted = False
    reason: object = None

    def abort(self, reason: object) -> None:
        self.aborted, self.reason = True, reason


class ReactLoopAgent:
    def __init__(
        self,
        loop_ctx: Context,
        id_: str,
        options: Mapping[str, Any],
        session: Session,
    ) -> None:
        self.loop_ctx, self.id, self.options, self.session = loop_ctx, id_, options, session
        self.scope: Scope = create_scope(loop_ctx, self)
        self.ctx = self.scope.ctx
        self.dispatch = agent_events(loop_ctx, self)
        self.model = AgentModel(session, options)
        self.inbox = ReactLoopInbox(session, self.dispatch)
        self._task: asyncio.Task[None] | None = None
        self._signal: _Signal | None = None
        self._disposed = False
        self._last_turn = turn_boundary_of(session)["lastTurn"]

    @property
    def status(self) -> str:
        return "running" if self._task is not None and not self._task.done() else "idle"

    def followup(self, message: Mapping[str, Any]) -> None:
        self.send(message, "next-turn", True)

    def steer(self, message: Mapping[str, Any]) -> None:
        self.send(message, "next-step", True)

    def inject(self, message: Mapping[str, Any]) -> None:
        self.send(message, "next-step", False)

    def send(self, message: Mapping[str, Any], target: str, wakeup: bool) -> None:
        self.inbox.append(target, message)
        if wakeup and self.status == "idle" and not self._disposed:
            self._task = asyncio.create_task(self._drive())

    def cancel(
        self,
        reason: Mapping[str, Any] | None = None,
        *,
        keep_inbox: bool = False,
    ) -> None:
        if not keep_inbox:
            self.inbox.clear()
        if self._signal is not None:
            self._signal.abort(reason or {"kind": "user"})
        if self._task is not None and not self._task.done():
            self._task.cancel()

    async def when_idle(self) -> None:
        while self._task is not None:
            task = self._task
            await task
            if task is self._task:
                break

    async def dispose(self) -> None:
        self._disposed = True
        self.cancel({"kind": "disposed"})
        await self.when_idle()
        await self.scope.dispose()

    async def _drive(self) -> None:
        agents = self.loop_ctx.get("agents")
        if not isinstance(agents, AgentRegistry):
            raise RuntimeError("agent registry is unavailable")
        await agents.with_initiator(self, self._drive_active)

    async def _drive_active(self) -> None:
        self.dispatch.emit("agent/status", {"status": "running"})
        try:
            while self.inbox.has_pending and not self._disposed:
                await self._turn()
        finally:
            self._task = None
            self._signal = None
            self.dispatch.emit("agent/status", {"status": "idle"})

    async def _turn(self) -> None:
        turn = self._last_turn + 1
        self._last_turn = turn
        self._signal = _Signal()
        signal = self._signal
        self.session.append("turn/start", {"turn": turn})
        reason: Mapping[str, Any] = {"kind": "completed"}
        target = "next-turn"
        step = 0
        try:
            while True:
                if signal.aborted:
                    raise asyncio.CancelledError
                proposed = self.inbox.claim(target, turn)
                selection = self.model.current()
                if not proposed and step == 0:
                    break
                if selection is None:
                    raise RuntimeError(f'agent "{self.id}" has no model selection')
                offered = proposed
                tools = self.loop_ctx.get("tools")
                prompt = self.loop_ctx.get("systemPrompt")
                llm = self.loop_ctx.get("llm")
                if (
                    not isinstance(tools, ToolsService)
                    or not isinstance(prompt, SystemPrompt)
                    or not isinstance(llm, LlmRuntime)
                ):
                    raise RuntimeError("agent loop dependencies are unavailable")
                tool_set: ResolvedToolSet = await tools.resolve(
                    {"agent": self, "modelSelection": selection, "signal": signal}
                )
                try:

                    def enter_offered(
                        messages: Sequence[Mapping[str, Any]] = offered,
                    ) -> Mapping[str, Any]:
                        return {"kind": "enter", "messages": messages}

                    decision = self.dispatch.waterfall(
                        "agent/pre-step",
                        {
                            "messages": proposed,
                            "signal": signal,
                            "step": step + 1,
                            "modelSelection": selection,
                        },
                        next_=enter_offered,
                    )
                    if asyncio.iscoroutine(decision):
                        decision = await decision
                    decision = cast(Mapping[str, Any], decision)
                    if decision["kind"] == "reject":
                        reason = {"kind": "blocked"}
                        break
                    proposed = decision["messages"]
                    if not proposed and step == 0:
                        break
                    step += 1
                    self.session.append("step/start", {"turn": turn, "step": step})
                    try:
                        result = await self._step(turn, step, proposed, selection, tool_set, signal)
                    finally:
                        self.session.append("step/end", {"turn": turn, "step": step})
                finally:
                    tool_set.dispose()
                if result in ("completed", "max-tokens"):
                    reason = {"kind": result}
                    if not self.inbox.next_step:
                        break
                target = "next-step"
        except asyncio.CancelledError:
            cause = signal.reason if isinstance(signal.reason, Mapping) else {"kind": "user"}
            reason = {"kind": "aborted", "reason": cause}
        except Exception as error:
            reason = {
                "kind": "error",
                "error": {
                    "message": str(error),
                    "code": getattr(error, "code", "UNKNOWN"),
                },
            }
            self.dispatch.emit("agent/error", {"error": error})
        finally:
            self.session.append("turn/end", {"turn": turn, "reason": reason})

    async def _step(
        self,
        turn: int,
        step: int,
        messages: Sequence[Mapping[str, Any]],
        selection: Mapping[str, Any],
        tool_set: ResolvedToolSet,
        signal: _Signal,
    ) -> str | None:
        prompt = self.loop_ctx.get("systemPrompt")
        llm = self.loop_ctx.get("llm")
        tools = self.loop_ctx.get("tools")
        assert isinstance(prompt, SystemPrompt)
        assert isinstance(llm, LlmRuntime)
        assert isinstance(tools, ToolsService)
        assembly = await prompt.assemble(
            {
                **assemble_context_for(self, signal),
                "modelSelection": selection,
                "toolSet": tool_set,
            }
        )
        rendered = render_prompt(assembly)
        system_events = [
            event for event in self.session.snapshot_events() if event["type"] == "system/message"
        ]
        if not system_events:
            self.session.append(
                "system/message",
                {"turn": turn, "step": step, "message": create_system_message(rendered)},
                surface_op="append",
            )
        else:
            active = self.session.derive_messages()
            current = active[0] if active and active[0].get("role") == "system" else None
            current_text = (
                current["content"][0]["text"]
                if current is not None
                and len(current["content"]) == 1
                and current["content"][0]["type"] == "text"
                else ""
            )
            if current_text != rendered:
                seq = system_events[0]["seq"]
                self.session.append(
                    "system/message",
                    {"turn": turn, "step": step, "message": create_system_message(rendered)},
                    surface_op={"op": "replace", "startSeq": seq, "endSeq": seq},
                    source_event_seqs=[seq],
                )
        context_text = render_context_snapshot(assembly)
        context_sections = render_context_sections(assembly)
        retained_context = next(
            (
                event
                for event in reversed(self.session.snapshot_events())
                if event["type"] == "user/message"
                and event["data"].get("source", {}).get("kind") == "runtime-context"
            ),
            None,
        )
        context_snapshot = (
            context_text
            if context_text
            else "Current runtime context: none. Earlier runtime-context snapshots no longer apply."
        )
        retained_text = (
            retained_context["data"]["content"][0]["text"]
            if retained_context is not None
            and len(retained_context["data"]["content"]) == 1
            and retained_context["data"]["content"][0]["type"] == "text"
            else None
        )
        if (retained_context is not None or context_text) and retained_text != context_snapshot:
            context_message = {
                "id": f"runtime-context-{turn}-{step}",
                "role": "user",
                "content": [{"type": "text", "text": context_snapshot}],
                "source": {
                    "kind": "runtime-context",
                    **(
                        {
                            "form": "snapshot",
                            "sections": context_sections,
                        }
                        if context_sections
                        else {}
                    ),
                },
            }
            if retained_context is None:
                self.session.append("user/message", context_message, surface_op="append")
            else:
                seq = retained_context["seq"]
                self.session.append(
                    "user/message",
                    context_message,
                    surface_op={"op": "replace", "startSeq": seq, "endSeq": seq},
                    source_event_seqs=[seq],
                )
        for message in messages:
            self.session.append("user/message", message, surface_op="append")
        config = dict(selection)
        if "maxTokens" in self.options:
            config["maxTokens"] = self.options["maxTokens"]
        proposed = self.dispatch.waterfall(
            "agent/request",
            {"turn": turn, "step": step, "signal": signal},
            next_=lambda: config,
        )
        if asyncio.iscoroutine(proposed):
            proposed = await proposed
        proposed = cast(Mapping[str, Any], proposed)
        prepared = None
        try:
            prepared = await llm.prepare_call(proposed, signal)
            config = dict(prepared.config)
        except LlmError as error:
            if error.code != "NO_ADAPTER":
                raise
            config = dict(proposed)
        header = {
            "config": config,
            **(
                {"adapterDefaults": prepared.adapter_defaults}
                if prepared and prepared.adapter_defaults
                else {}
            ),
            **({"tools": assembly["tools"]} if assembly["tools"] else {}),
        }
        baseline = self.session.request_header()
        self.session.append(
            "request/header",
            {
                "header": header,
                "reason": "initial" if baseline is None else "change",
            },
        )
        request_context = {
            "provider": config["provider"],
            "model": config["model"],
            **(
                {"contextWindow": prepared.context["contextWindow"]}
                if prepared
                and isinstance(prepared.context, Mapping)
                and "contextWindow" in prepared.context
                else {}
            ),
            **(
                {"systemPromptUpdate": prepared.system_prompt_update}
                if prepared and prepared.system_prompt_update is not None
                else {}
            ),
        }
        if self.session.request_context() != request_context:
            self.session.append("request/context", request_context)
        request = {
            **config,
            "messages": self.session.derive_messages(),
            "toolHistory": self.session.tool_history(),
            **({"tools": assembly["tools"]} if assembly["tools"] else {}),
            "sessionId": self.id,
            "signal": signal,
        }
        accumulator, assembler = AssistantStreamAccumulator(), BlockAssembler()
        stream = prepared.stream(request) if prepared else llm.stream(request)
        async for chunk in stream:
            timed = {"time": time.time_ns() // 1_000_000, "chunk": chunk}
            accumulator.push(timed)
            assembler.push(dict(chunk))
        if signal.aborted:
            raise asyncio.CancelledError
        finish = assembler.finish
        stream_record = list(accumulator.snapshot())
        if finish["kind"] in ("error", "aborted"):
            self.session.append(
                "assistant/attempt",
                {"turn": turn, "step": step, "stream": stream_record},
            )
            action = self.dispatch.waterfall(
                "agent/request-error",
                {
                    "turn": turn,
                    "step": step,
                    "provider": config["provider"],
                    "failure": finish["failure"],
                    "retryPolicy": prepared.retry_policy if prepared else None,
                    "signal": signal,
                },
                next_=lambda: None,
            )
            if asyncio.iscoroutine(action):
                action = await action
            if isinstance(action, Mapping) and action.get("kind") == "retry":
                return await self._step(turn, step, [], selection, tool_set, signal)
            raise LlmError(finish["failure"]["message"], finish["failure"]["code"])
        message = create_assistant_message(
            content=assembler.blocks(),
            source={
                "provider": config["provider"],
                "model": config["model"],
                **(
                    {"replayState": assembler.replay_state}
                    if assembler.replay_state is not None
                    else {}
                ),
            },
        )
        self.session.append(
            "assistant/message",
            {
                "turn": turn,
                "step": step,
                "message": message,
                **({"usage": assembler.usage} if assembler.usage else {}),
                "stream": stream_record,
            },
            surface_op="append",
        )
        if finish["kind"] == "max-tokens":
            return "max-tokens"
        calls = [block for block in message["content"] if block["type"] == "tool-call"]
        if not calls:
            return "completed"
        try:
            result = await tools.execute(
                {
                    "calls": calls,
                    "signal": signal,
                    "agent": self,
                    "log": {"turn": turn, "step": step},
                    "maxParallelToolCalls": self.options.get(
                        "maxParallelToolCalls", DEFAULT_MAX_PARALLEL_TOOL_CALLS
                    ),
                    "toolSet": tool_set,
                }
            )
        except ToolBatchExecutionError as error:
            result = error.partial
            if isinstance(error.cause, BaseException):
                raise error.cause from error
            raise RuntimeError(str(error.cause)) from error
        for context in result["additionalContexts"]:
            self.inbox.append("next-step", context)
        return "completed" if result["concluded"] else None


class AgentHandle:
    def __init__(
        self,
        agent: ReactLoopAgent,
        detach_agent: Any,
        detach_session: Any,
        storage: SessionHandle | None = None,
    ) -> None:
        self.agent, self._detach_agent, self._detach_session = (
            agent,
            detach_agent,
            detach_session,
        )
        self._storage = storage
        self._disposed = False

    async def dispose(self) -> None:
        if self._disposed:
            return
        self._disposed = True
        await self.agent.dispose()
        if self._storage is not None:
            await self._storage.close()
        self._detach_agent()
        self._detach_session()


class AgentLoop(Service):
    name = "agentLoop"

    def __init__(self, ctx: Context, config: Mapping[str, Any] | None = None) -> None:
        super().__init__(ctx, config)
        self.loop_config = config or {}
        agents = ctx.get("agents")
        if not isinstance(agents, AgentRegistry):
            raise RuntimeError("AgentLoop requires AgentRegistry")
        self.agents = agents
        agents.set_factory(self, ctx=ctx)

    async def create_agent(self, owner_ctx: Context, options: Mapping[str, Any]) -> AgentHandle:
        sessions = self.ctx.get("sessions")
        if not isinstance(sessions, SessionStore):
            raise RuntimeError("AgentLoop requires SessionStore")
        agent_options = options.get("agentOptions", {})
        max_tokens = agent_options.get("maxTokens")
        if max_tokens is not None and (
            not isinstance(max_tokens, int) or isinstance(max_tokens, bool) or max_tokens <= 0
        ):
            raise TypeError("agent maxTokens must be a positive integer")
        session = sessions.prepare(options["sessionId"], options.get("sessionOptions"))
        persistence = self.ctx.get("sessionPersistence")
        storage: SessionHandle | None = None
        if isinstance(persistence, SessionPersistence):
            storage = await persistence.create(
                session.header,
                inherited_event_count=session.inherited_event_count,
            )
            seed = session.snapshot_events()
            if seed:
                await storage.append(seed)
        detach_session = sessions.enter(session, ctx=owner_ctx)
        try:
            sessions.announce(session)
            agent = ReactLoopAgent(
                self.ctx,
                session.id,
                agent_options,
                session,
            )
            setup = options.get("setup")
            if setup is not None:
                commit = setup(agent.ctx, agent)
                if asyncio.iscoroutine(commit):
                    commit = await commit
                if commit is not None:
                    commit.commit()
            detach_agent = self.agents.enter(agent, options.get("parentAgent"))
            await self.agents.announce(agent, "create", options.get("signal"))
            return AgentHandle(agent, detach_agent, detach_session, storage)
        except BaseException:
            detach_session()
            if storage is not None:
                await storage.close()
            raise

    async def resume_agent(self, owner_ctx: Context, options: Mapping[str, Any]) -> AgentHandle:
        sessions = self.ctx.get("sessions")
        persistence = self.ctx.get("sessionPersistence")
        if not isinstance(sessions, SessionStore):
            raise RuntimeError("AgentLoop requires SessionStore")
        if not isinstance(persistence, SessionPersistence):
            raise RuntimeError(
                "cannot resume: session persistence is not configured "
                "(load a session-persistence backend)"
            )
        session_id = options.get("resumeSessionId", options.get("sessionId"))
        if not isinstance(session_id, str) or not session_id:
            raise ValueError("resumeSessionId is required")
        storage = await persistence.open(session_id, "write")
        detach_session = None
        try:
            cold = await storage.read()
            events = list(cold.events)
            closers = interrupted_turn_closers(events)
            if closers:
                await storage.append(closers)
                events.extend(closers)
            session = sessions.prepare(
                session_id,
                RestoredSessionOptions(
                    seed=events,
                    meta=storage.header,
                    inherited_event_count=storage.inherited_event_count,
                    event_state=cold.event_state,
                ),
            )
            normalized_suffix = session.snapshot_events()[len(events) :]
            if normalized_suffix:
                await storage.append(normalized_suffix)
            detach_session = sessions.enter(session, ctx=owner_ctx)
            sessions.announce(session)
            agent = ReactLoopAgent(
                self.ctx,
                session.id,
                options.get("agentOptions", {}),
                session,
            )
            setup = options.get("setup")
            if setup is not None:
                commit = setup(agent.ctx, agent)
                if asyncio.iscoroutine(commit):
                    commit = await commit
                if commit is not None:
                    commit.commit()
            detach_agent = self.agents.enter(agent, options.get("parentAgent"))
            await self.agents.announce(agent, "resume", options.get("signal"))
            return AgentHandle(agent, detach_agent, detach_session, storage)
        except BaseException:
            if detach_session is not None:
                detach_session()
            await storage.close()
            raise


__all__ = [
    "AgentHandle",
    "AgentLoop",
    "DEFAULT_MAX_PARALLEL_TOOL_CALLS",
    "ReactLoopAgent",
    "ReactLoopInbox",
    "inbox_state",
]
