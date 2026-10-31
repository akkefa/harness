from __future__ import annotations

import pytest
from deepseek_cordis import Context

from deskagents.bundle import (
    MINIMAL_BUNDLE,
    BundleBuilder,
    BundleLoader,
    apply_row_patches,
    load_bundle_rows,
)
from deskagents.session import SessionTitleService


def test_row_patches_preserve_unmentioned_fields() -> None:
    rows = [{"id": "service", "name": "example.plugin", "config": {"old": True}}]
    assert apply_row_patches(rows, [{"id": "service", "config": {"new": True}}]) == [
        {"id": "service", "name": "example.plugin", "config": {"new": True}}
    ]


def test_builder_produces_loader_rows() -> None:
    assert BundleBuilder().plugin(
        "disabled", "example.plugin", config={"value": 1}, disabled=True
    ).rows() == [
        {
            "id": "disabled",
            "name": "example.plugin",
            "config": {"value": 1},
            "disabled": True,
        }
    ]


@pytest.mark.asyncio
async def test_minimal_bundle_mounts_through_cordis_loader() -> None:
    rows = load_bundle_rows(MINIMAL_BUNDLE)
    assert [row["id"] for row in rows][-2:] == [
        "agent-loop",
        "session-checkpoint-policy",
    ]
    ctx = Context()
    loader = BundleLoader(ctx)
    batch = await loader.load(rows)
    assert set(batch.fibers) == {row["id"] for row in rows}
    assert isinstance(ctx.get("sessionTitle"), SessionTitleService)
    await loader.dispose()
    await ctx.fiber.dispose()
