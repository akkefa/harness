"""Live Agent registry, model selection, dispatch helpers, and log folds.

Upstream: packages/core/agent at ce7073d.
"""

from __future__ import annotations

import contextvars
import inspect
import logging
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Protocol

from deepseek_cordis import Context, Service, current_context

from harness.core.scope import scope_target

logger = logging.getLogger(__name__)


class Agent(Protocol):
    id: str
    session: Any
    ctx: Context

    @property
    def status(self) -> str: ...

    def cancel(self, reason: Mapping[str, Any] | None = None) -> None: ...


def _same_selection(left: Mapping[str, Any] | None, right: Mapping[str, Any] | None) -> bool:
    return left == right


def model_selection_state(events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    state: dict[str, Any] = {"lastUsed": None, "pending": None}
    for event in events:
        if event["type"] == "model/selection":
            if state["pending"] != event["data"]:
                state = {**state, "pending": event["data"]}
        elif event["type"] == "request/header":
            header = event["data"]["header"]
            config = header["config"]
            used = {
                "provider": config["provider"],
                "model": config["model"],
                **(
                    {"reasoningEffort": config["reasoningEffort"]}
                    if "reasoningEffort" in config
                    and not (header.get("adapterDefaults") or {}).get("reasoningEffort")
                    else {}
                ),
            }
            state = {
                "lastUsed": used,
                "pending": None if state["pending"] == used else state["pending"],
            }
    return state


class AgentModel:
    def __init__(self, session: Any, options: Mapping[str, Any]) -> None:
        self.session, self.options = session, options

    def current(self) -> Mapping[str, Any] | None:
        state = model_selection_state(self.session.snapshot_events())
        recorded = state["pending"] or state["lastUsed"]
        if recorded is not None:
            return dict(recorded)
        if self.options.get("provider") and self.options.get("model"):
            return {
                key: self.options[key]
                for key in ("provider", "model", "reasoningEffort")
                if key in self.options
            }
        return None

    def select(self, selection: Mapping[str, Any]) -> None:
        if _same_selection(self.current(), selection):
            return
        self.session.append(
            "model/selection",
            {
                key: selection[key]
                for key in ("provider", "model", "reasoningEffort")
                if key in selection
            },
        )


def turn_boundary_of(session: Any) -> dict[str, Any]:
    state: dict[str, Any] = {
        "openTurnStartSeq": None,
        "lastStepStartSeq": None,
        "lastStepBoundary": None,
        "lastTurn": 0,
    }
    for event in session.snapshot_events():
        kind = event["type"]
        if kind == "turn/start":
            state["openTurnStartSeq"] = event["seq"]
            state["lastTurn"] = event["data"]["turn"]
        elif kind == "turn/end":
            state["openTurnStartSeq"] = None
        elif kind == "step/start":
            state["lastStepStartSeq"] = event["seq"]
            state["lastStepBoundary"] = {"kind": "start", "seq": event["seq"]}
        elif kind == "step/end":
            state["lastStepBoundary"] = {"kind": "end", "seq": event["seq"]}
    return state


def fold_consumed_work(events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    stepped: set[int] = set()
    claimed: set[int] = set()
    open_turn: int | None = None
    end = None
    dropped = False
    for event in events:
        kind, data = event["type"], event["data"]
        if kind == "turn/start":
            open_turn = data["turn"]
        elif kind == "step/start":
            stepped.add(data["turn"])
        elif kind == "agent/inbox/spliced" and "removedCount" in data:
            if data.get("outcome") == "canceled":
                dropped = dropped or not data["inserted"]
            elif open_turn is not None:
                claimed.add(open_turn)
        elif kind == "turn/end":
            turn = data["turn"]
            open_turn = None
            accounts = data["reason"]["kind"] != "completed"
            if turn in stepped or (turn in claimed and accounts):
                end, dropped = event, False
            stepped.discard(turn)
            claimed.discard(turn)
    return {**({"end": end} if end is not None else {}), "droppedUnrun": dropped}


def assemble_context_for(agent: Agent, signal: object = None) -> dict[str, Any]:
    return {
        "agent": agent,
        "scope": agent,
        **({"signal": signal} if signal is not None else {}),
    }


class AgentEvents:
    def __init__(self, ctx: Context, agent: Agent) -> None:
        self.ctx, self.agent = ctx, agent
        self.filter = scope_target(agent, agent)

    def emit(self, name: str, payload: Mapping[str, Any]) -> None:
        self.ctx.emit(name, {**payload, "agent": self.agent}, filter_=self.filter)

    async def serial(self, name: str, payload: Mapping[str, Any]) -> object:
        return await self.ctx.serial(name, {**payload, "agent": self.agent}, filter_=self.filter)

    def waterfall(
        self,
        name: str,
        payload: Mapping[str, Any],
        next_: Callable[[], object],
    ) -> object:
        return self.ctx.waterfall(
            name,
            {**payload, "agent": self.agent},
            next_=next_,
            filter_=self.filter,
        )


def agent_events(ctx: Context, agent: Agent) -> AgentEvents:
    return AgentEvents(ctx, agent)


class _Entry:
    def __init__(self, agent: Agent, owner: Agent | None) -> None:
        self.agent, self.owner, self.announced = agent, owner, False


class AgentFactory(Protocol):
    async def create_agent(self, owner_ctx: Context, options: Mapping[str, Any]) -> Any: ...

    async def resume_agent(self, owner_ctx: Context, options: Mapping[str, Any]) -> Any: ...


class AgentRegistry(Service):
    name = "agents"

    def __init__(self, ctx: Context, config: object = None) -> None:
        super().__init__(ctx, config)
        self._entries: dict[str, _Entry] = {}
        self._factory: AgentFactory | None = None
        self._initiator: contextvars.ContextVar[Agent | None] = contextvars.ContextVar(
            "harness_agent_initiator", default=None
        )

    def caller(self, ctx: Context | None = None) -> Context:
        candidate = ctx or current_context()
        return candidate if candidate is not None and candidate.root is self.ctx.root else self.ctx

    def set_factory(
        self, factory: AgentFactory, *, ctx: Context | None = None
    ) -> Callable[[], object]:
        owner = self.caller(ctx)

        def setup() -> Callable[[], None]:
            if self._factory is not None:
                raise ValueError("an agent factory is already registered")
            self._factory = factory
            return lambda: setattr(self, "_factory", None)

        return owner.effect(setup, "agents.setFactory()")

    async def create(self, options: Mapping[str, Any], *, ctx: Context | None = None) -> Any:
        if self._factory is None:
            raise RuntimeError("no agent factory registered (load an agent-loop plugin)")
        return await self._factory.create_agent(self.caller(ctx), options)

    async def resume(self, options: Mapping[str, Any], *, ctx: Context | None = None) -> Any:
        if self._factory is None:
            raise RuntimeError("no agent factory registered (load an agent-loop plugin)")
        return await self._factory.resume_agent(self.caller(ctx), options)

    def enter(self, agent: Agent, owner: Agent | None = None) -> Callable[[], None]:
        if agent.id != agent.session.id:
            raise ValueError("agent id does not match session id")
        if agent.id in self._entries:
            raise ValueError(f'agent "{agent.id}" is already registered')
        entry = _Entry(agent, owner)
        self._entries[agent.id] = entry
        active = True

        def detach() -> None:
            nonlocal active
            if not active or self._entries.get(agent.id) is not entry:
                return
            active = False
            del self._entries[agent.id]
            if entry.announced:
                agent_events(self.ctx, agent).emit("agent/disposed", {})

        return detach

    async def announce(self, agent: Agent, source: str = "startup", signal: object = None) -> None:
        entry = self._entries.get(agent.id)
        if entry is None or entry.agent is not agent:
            raise ValueError(f'agent "{agent.id}" is not live in this registry')
        if entry.announced:
            raise ValueError(f'agent "{agent.id}" was already announced')
        entry.announced = True
        await agent_events(self.ctx, agent).serial(
            "agent/created",
            {"source": source, **({"signal": signal} if signal is not None else {})},
        )

    def register(self, agent: Agent, *, ctx: Context | None = None) -> Callable[[], object]:
        owner = self.caller(ctx)

        async def setup() -> Callable[[], None]:
            detach = self.enter(agent)
            try:
                await self.announce(agent)
            except BaseException:
                detach()
                raise
            return detach

        return owner.effect(setup, "agents.register()")

    def get(self, id_: str) -> Agent | None:
        entry = self._entries.get(id_)
        return None if entry is None else entry.agent

    def list(self) -> Sequence[Agent]:
        return [entry.agent for entry in self._entries.values()]

    def roots(self) -> Sequence[Agent]:
        return [entry.agent for entry in self._entries.values() if entry.owner is None]

    def is_owned_by(self, id_: str, owner: Agent) -> bool:
        entry = self._entries.get(id_)
        return entry is not None and entry.owner is owner

    def current_initiator(self) -> Agent | None:
        return self._initiator.get()

    def require_initiator(self) -> Agent:
        agent = self.current_initiator()
        if agent is None:
            raise RuntimeError("no initiating agent is active")
        return agent

    def with_initiator(self, agent: Agent, operation: Callable[[], Any]) -> Any:
        token = self._initiator.set(agent)
        try:
            result = operation()
            if inspect.isawaitable(result):

                async def finish() -> Any:
                    try:
                        return await result
                    finally:
                        self._initiator.reset(token)

                return finish()
            self._initiator.reset(token)
            return result
        except BaseException:
            self._initiator.reset(token)
            raise

    def without_initiator(self, operation: Callable[[], Any]) -> Any:
        token = self._initiator.set(None)
        try:
            result = operation()
            if inspect.isawaitable(result):

                async def finish() -> Any:
                    try:
                        return await result
                    finally:
                        self._initiator.reset(token)

                return finish()
            self._initiator.reset(token)
            return result
        except BaseException:
            self._initiator.reset(token)
            raise

    def turn_boundary_of(self, session: Any) -> Mapping[str, Any]:
        return turn_boundary_of(session)


__all__ = [
    "Agent",
    "AgentEvents",
    "AgentModel",
    "AgentRegistry",
    "agent_events",
    "assemble_context_for",
    "fold_consumed_work",
    "model_selection_state",
    "turn_boundary_of",
]
