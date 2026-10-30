"""Runs the reusable handle contract (harness.testing) against the JSONL backend.

Upstream: packages/session/session-persistence-jsonl/tests/jsonl.spec.ts invokes
``runPersistenceContract('jsonl-none', …)`` from session-persistence/tests/contract.ts.
The cases are unmarked: their describe title is a template literal in contract.ts, so no
``jsonl.spec.ts::title`` source can name them literally.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path

import pytest
import pytest_asyncio
from deepseek_cordis import Context

from harness.core.session import SessionId
from harness.session import persistence_jsonl
from harness.session.persistence import SessionPersistence
from harness.session.persistence_jsonl import log_path
from harness.testing import (
    ContractBackend,
    ContractBackendInstance,
    ContractCheck,
    ContractSkip,
    persistence_contract_cases,
)

CASES = persistence_contract_cases()


def append_text(path: Path, text: str) -> None:
    with path.open("a") as stream:
        stream.write(text)


ContractFactory = Callable[[], Awaitable[ContractBackend]]


@pytest_asyncio.fixture
async def make_backend(tmp_path: Path) -> AsyncIterator[ContractFactory]:
    """The ``jsonl-none`` factory: each call gets its own empty root under ``tmp_path``."""
    contexts: list[Context] = []
    counter = 0

    async def make() -> ContractBackend:
        nonlocal counter
        counter += 1
        root = tmp_path / f"store-{counter}"
        root.mkdir()

        async def instance() -> ContractBackendInstance:
            ctx = Context()
            contexts.append(ctx)
            await ctx.plugin(persistence_jsonl, {"root": str(root), "compression": "none"})
            service = ctx.get("sessionPersistence")
            assert isinstance(service, SessionPersistence)
            return ContractBackendInstance(service, ctx.fiber.dispose)

        async def corrupt_tail(session_id: SessionId, cwd: str | None) -> None:
            # A half-written record with no trailing newline: an uncommitted crash
            # fragment, so the write path sees a torn tail to truncate.
            path = Path(log_path(str(root), cwd, session_id, "none"))
            await asyncio.to_thread(append_text, path, '{"type":"assistant/chunk","seq":8,"ti')

        primary = await instance()
        return ContractBackend(
            primary.persistence, primary.dispose, reopen=instance, corrupt_tail=corrupt_tail
        )

    yield make
    for ctx in contexts:
        await ctx.fiber.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize(("title", "check"), CASES, ids=[title for title, _ in CASES])
async def test_persistence_contract(
    title: str, check: ContractCheck, make_backend: ContractFactory
) -> None:
    try:
        await check(make_backend)
    except ContractSkip as skip:
        pytest.skip(str(skip))
