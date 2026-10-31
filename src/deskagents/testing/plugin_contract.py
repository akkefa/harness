"""Reusable lifecycle contract for external deskagents plugin families.

The contract is deliberately capability-neutral. A plugin package supplies fresh
mounted backends plus probes for the capabilities it owns; the shared cases verify
mounting, exercise through public seams, and cleanup while the host remains alive.
"""

from __future__ import annotations

import inspect
import traceback
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

__all__ = [
    "PLUGIN_CONTRACT_SUITE",
    "PluginContractBackend",
    "PluginContractFactory",
    "PluginContractResult",
    "plugin_contract_cases",
    "run_plugin_contract",
]

PLUGIN_CONTRACT_SUITE = "External plugin family contract"

PluginContractProbe = Callable[[], object]


@dataclass
class PluginContractBackend:
    """One fresh host with an external plugin family mounted.

    ``dispose_plugin`` removes only the external family. ``dispose`` tears down the
    complete host and must be safe after ``dispose_plugin``.
    """

    assert_active: PluginContractProbe
    exercise: PluginContractProbe
    dispose_plugin: PluginContractProbe
    assert_disposed: PluginContractProbe
    dispose: PluginContractProbe


PluginContractFactory = Callable[[], Awaitable[PluginContractBackend]]
PluginContractCheck = Callable[[PluginContractFactory], Awaitable[None]]


@dataclass(frozen=True)
class PluginContractResult:
    title: str
    outcome: Literal["passed", "failed"]
    error: BaseException | None = None
    detail: str = ""


async def _invoke(callback: PluginContractProbe) -> object:
    result = callback()
    return await result if inspect.isawaitable(result) else result


async def _mounts(factory: PluginContractFactory) -> None:
    backend = await factory()
    try:
        await _invoke(backend.assert_active)
    finally:
        await _invoke(backend.dispose)


async def _exercises(factory: PluginContractFactory) -> None:
    backend = await factory()
    try:
        await _invoke(backend.assert_active)
        await _invoke(backend.exercise)
        await _invoke(backend.assert_active)
    finally:
        await _invoke(backend.dispose)


async def _unloads(factory: PluginContractFactory) -> None:
    backend = await factory()
    try:
        await _invoke(backend.assert_active)
        await _invoke(backend.dispose_plugin)
        await _invoke(backend.assert_disposed)
    finally:
        await _invoke(backend.dispose)


_CASES: tuple[tuple[str, PluginContractCheck], ...] = (
    ("mounts and exposes its declared capabilities", _mounts),
    ("executes through public harness seams", _exercises),
    ("unloads without leaking owned registrations", _unloads),
)


def plugin_contract_cases() -> tuple[tuple[str, PluginContractCheck], ...]:
    """Return stable case titles and their pytest-independent checks."""
    return _CASES


async def run_plugin_contract(
    factory: PluginContractFactory,
) -> list[PluginContractResult]:
    """Run every external-plugin check and collect outcomes."""
    results: list[PluginContractResult] = []
    for title, check in _CASES:
        try:
            await check(factory)
        except BaseException as error:
            results.append(
                PluginContractResult(
                    title,
                    "failed",
                    error,
                    "".join(traceback.format_exception(error)),
                )
            )
        else:
            results.append(PluginContractResult(title, "passed"))
    return results
