"""Shims for deepseek-cordis gaps G1 and G2 (docs/cordis-alignment.md).

Every use of a missing Cordis API goes through here, so closing a gap in deepseek-cordis
means changing this module only.
"""

from __future__ import annotations

from collections.abc import Callable

from deepseek_cordis import Context, CordisError, Fiber
from deepseek_cordis.events import EventFilter


def dispatch(
    ctx: Context, mode: str, name: str, args: tuple[object, ...], filter_: EventFilter | None
) -> list[Callable[..., object]]:
    """Upstream ``ctx.events.dispatch(mode, args)``: the listener snapshot, uninvoked (G1).

    The caller invokes each listener itself, to contain failures per listener.
    """
    return list(ctx.events._dispatch(mode, name, args, filter_))


def assert_active(fiber: Fiber) -> None:
    """Upstream ``fiber.assertActive()`` (G2): raise once the fiber has been disposed."""
    if fiber.uid is None:
        raise CordisError("INACTIVE_EFFECT")
