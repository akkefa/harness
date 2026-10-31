"""Id-addressable YAML bundle loader for the Python runtime."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml
from deepseek_cordis import Context
from deepseek_cordis.loader import LoadedPlugins, Loader, PluginEntry

from deskagents.core import AgentLoop, AgentRegistry, SystemPrompt, ToolsService
from deskagents.core.agent_default_model import AgentDefaultModelConfig
from deskagents.core.session import SessionStore
from deskagents.core.tools import install_native_tool_executor
from deskagents.llm import LlmRuntime
from deskagents.session.checkpoint_policy import install_checkpoint_policy
from deskagents.session.projection import SessionProjectionRegistry
from deskagents.session.title import SessionTitleService


def _native_executor_plugin(ctx: Context, config: object = None) -> Any:
    install_native_tool_executor(ctx, config)
    return lambda: None


def _checkpoint_policy_plugin(ctx: Context, config: object = None) -> Any:
    install_checkpoint_policy(ctx, config)
    return lambda: None


def apply_row_patches(
    rows: Sequence[Mapping[str, Any]],
    patches: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Apply ordered id-addressed inserts and top-level field patches."""
    result = [dict(row) for row in rows]
    positions = {row["id"]: index for index, row in enumerate(result)}
    for patch in patches:
        for inserted in patch.get("insert", ()):
            row = dict(inserted)
            if row["id"] in positions:
                raise ValueError(f'bundle insert duplicates row "{row["id"]}"')
            positions[row["id"]] = len(result)
            result.append(row)
        row_id = patch.get("id")
        if row_id is None:
            continue
        if patch.get("remove") is True:
            if row_id in positions:
                result.pop(positions[row_id])
                positions = {row["id"]: index for index, row in enumerate(result)}
            continue
        if row_id not in positions:
            raise ValueError(f'bundle patch names unknown row "{row_id}"')
        current = result[positions[row_id]]
        if "name" in patch and patch["name"] != current.get("name"):
            continue
        replacement = {
            key: value for key, value in patch.items() if key not in {"id", "insert", "remove"}
        }
        result[positions[row_id]] = {**current, **replacement}
    return result


def load_bundle_rows(path: str | Path) -> list[dict[str, Any]]:
    document = yaml.safe_load(Path(path).read_text())
    if not isinstance(document, list):
        raise ValueError("bundle document must be a patch list")
    return apply_row_patches([], document)


class BundleBuilder:
    def __init__(self) -> None:
        self._rows: list[dict[str, Any]] = []

    def plugin(
        self,
        id_: str,
        name: str,
        *,
        config: Mapping[str, Any] | None = None,
        disabled: bool = False,
    ) -> BundleBuilder:
        self._rows.append(
            {
                "id": id_,
                "name": name,
                **({"config": dict(config)} if config is not None else {}),
                **({"disabled": True} if disabled else {}),
            }
        )
        return self

    def rows(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self._rows]


class BundleLoader:
    DEFAULT_PLUGINS: Mapping[str, Any] = {
        "deskagents.llm": LlmRuntime,
        "deskagents.core.session": SessionStore,
        "deskagents.session.projection": SessionProjectionRegistry,
        "deskagents.session.title": SessionTitleService,
        "deskagents.session.checkpoint_policy": _checkpoint_policy_plugin,
        "deskagents.core.system_prompt": SystemPrompt,
        "deskagents.core.tools": ToolsService,
        "deskagents.core.agent": AgentRegistry,
        "deskagents.core.agent_default_model": AgentDefaultModelConfig,
        "deskagents.core.agent_loop": AgentLoop,
        "deskagents.core.tool_executor_native": _native_executor_plugin,
    }

    def __init__(self, ctx: Context, plugins: Mapping[str, Any] | None = None) -> None:
        self.ctx = ctx
        self.plugins = {**self.DEFAULT_PLUGINS, **(plugins or {})}
        self.batches: list[LoadedPlugins] = []

    async def load(self, rows: Sequence[Mapping[str, Any]]) -> LoadedPlugins:
        entries: list[PluginEntry] = []
        for row in rows:
            name = row["name"]
            if name not in self.plugins:
                raise ValueError(f'bundle row "{row["id"]}" names unknown plugin "{name}"')
            entries.append(
                PluginEntry(
                    id=row["id"],
                    plugin=self.plugins[name],
                    config=row.get("config"),
                    enabled=row.get("disabled") is not True,
                )
            )
        batch = await Loader(self.ctx).load(entries)
        self.batches.append(batch)
        return batch

    async def load_file(self, path: str | Path) -> LoadedPlugins:
        return await self.load(load_bundle_rows(path))

    async def dispose(self) -> None:
        while self.batches:
            await self.batches.pop().dispose()


MINIMAL_BUNDLE = Path(__file__).with_name("minimal.yml")

__all__ = [
    "BundleBuilder",
    "BundleLoader",
    "MINIMAL_BUNDLE",
    "apply_row_patches",
    "load_bundle_rows",
]
