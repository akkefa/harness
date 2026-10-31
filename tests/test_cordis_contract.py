"""The deepseek-cordis behaviour the harness relies on, checked against the installed version.

docs/cordis-alignment.md lists where upstream packages use each item. Gaps are strict
xfails: when deepseek-cordis gains the feature the test passes, fails as XPASS, and
points here to remove the marker and the workaround.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterator

import pytest
from deepseek_cordis import Context, CordisError, Fiber, FiberState, Service

from harness._cordis import assert_active, dispatch

pytestmark = pytest.mark.asyncio


def state(fiber: Fiber) -> FiberState:
    # A call keeps mypy from narrowing fiber.state across awaits.
    return fiber.state


async def test_waterfall_passes_arguments_then_next() -> None:
    root = Context()
    seen: list[object] = []

    def middleware(value: object, next_: Callable[[], object]) -> object:
        seen.append(value)
        return ("wrapped", next_())

    root.on("probe/waterfall", middleware)
    assert root.waterfall("probe/waterfall", 1, next_=lambda: "inner") == ("wrapped", "inner")
    assert seen == [1]
    await root.fiber.dispose()


async def test_generator_effect_cleans_up_on_dispose() -> None:
    root = Context()
    log: list[str] = []

    def setup() -> Iterator[Callable[[], None]]:
        log.append("setup")
        yield lambda: log.append("cleanup")

    root.effect(setup, "probe")
    assert log == ["setup"]
    await root.fiber.dispose()
    assert log == ["setup", "cleanup"]


async def test_inject_waits_for_a_service_and_unloads_with_it() -> None:
    root = Context()

    class Database(Service):
        name = "database"

    async def consumer(ctx: Context, config: object) -> None:
        assert isinstance(ctx.get("database"), Database)

    fiber = root.inject(["database"], consumer)
    await asyncio.sleep(0)
    assert state(fiber) is FiberState.PENDING
    provider = await root.plugin(Database)
    await fiber.wait()
    assert state(fiber) is FiberState.ACTIVE
    await provider.dispose()
    await asyncio.sleep(0)
    assert state(fiber) is FiberState.PENDING
    await root.fiber.dispose()


async def test_listener_options_prepend_and_global() -> None:
    root = Context()
    order: list[str] = []
    root.on("probe/order", lambda: order.append("second"))
    root.on("probe/order", lambda: order.append("first"), prepend=True, global_=True)
    root.emit("probe/order")
    assert order == ["first", "second"]
    await root.fiber.dispose()


async def test_fiber_states_match_upstream() -> None:
    names = {state.name for state in FiberState}
    assert {"PENDING", "LOADING", "ACTIVE", "FAILED", "UNLOADING", "DISPOSED"} <= names


async def test_harness_dispatch_shim_returns_uninvoked_listener_snapshot() -> None:
    root = Context()
    seen: list[int] = []
    root.on("probe/shim", seen.append)

    callbacks = dispatch(root, "emit", "probe/shim", (1,), None)
    assert seen == []
    for callback in callbacks:
        callback(1)
    assert seen == [1]
    await root.fiber.dispose()


async def test_harness_assert_active_shim_rejects_a_disposed_fiber() -> None:
    root = Context()
    child = await root.plugin(lambda _ctx, _config: None)
    assert_active(child)
    await child.dispose()
    with pytest.raises(CordisError, match="INACTIVE_EFFECT"):
        assert_active(child)
    await root.fiber.dispose()


# Gaps (docs/cordis-alignment.md). Remove a marker when its feature lands.


@pytest.mark.xfail(strict=True, reason="gap G1: Events.dispatch is private (_dispatch)")
async def test_events_dispatch_is_public() -> None:
    root = Context()
    root.on("probe/dispatch", lambda value: value)
    callbacks = root.events.dispatch("emit", "probe/dispatch", (1,))  # type: ignore[attr-defined]
    assert [callback(1) for callback in callbacks] == [1]
    await root.fiber.dispose()


@pytest.mark.xfail(strict=True, reason="gap G2: Fiber.assert_active is missing")
async def test_fiber_assert_active() -> None:
    root = Context()
    root.fiber.assert_active()  # type: ignore[attr-defined]
    await root.fiber.dispose()


@pytest.mark.xfail(strict=True, reason="gap G3: internal/status is not emitted")
async def test_internal_status_is_emitted() -> None:
    root = Context()
    changes: list[tuple[Fiber, FiberState]] = []
    root.on("internal/status", lambda fiber, old: changes.append((fiber, old)), global_=True)

    def plugin(ctx: Context, config: object) -> None:
        return None

    fiber = await root.plugin(plugin)
    await fiber.dispose()
    assert changes
    await root.fiber.dispose()


@pytest.mark.xfail(strict=True, reason="gap G3: internal/plugin is not emitted")
async def test_internal_plugin_is_emitted() -> None:
    root = Context()
    fibers: list[Fiber] = []
    root.on("internal/plugin", fibers.append, global_=True)

    def plugin(ctx: Context, config: object) -> None:
        return None

    fiber = await root.plugin(plugin)
    assert fiber in fibers
    await root.fiber.dispose()
