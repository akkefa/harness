"""docs/upstream.json stays well formed, and ported modules really exist."""

from __future__ import annotations

import importlib
import json
import re
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
DATA: dict[str, Any] = json.loads((ROOT / "docs" / "upstream.json").read_text())
MILESTONES = {"0.1", "0.2", "0.3", "0.4", "0.5"}
STATUSES = {"planned", "in-progress", "ported"}
MODULE = re.compile(r"deskagents(\.[a-z][a-z0-9_]*)+$|deskagents$")
ENTRIES = [*DATA["packages"], *DATA["new_modules"]]


def test_pin_is_a_full_commit() -> None:
    assert re.fullmatch(r"[0-9a-f]{40}", DATA["upstream"]["commit"])


def test_modules_are_unique_and_valid() -> None:
    modules = [entry["module"] for entry in ENTRIES]
    assert len(modules) == len(set(modules))
    assert all(MODULE.fullmatch(module) for module in modules)


def test_upstream_paths_are_unique_packages() -> None:
    paths = [entry["upstream"] for entry in DATA["packages"]]
    assert len(paths) == len(set(paths))
    assert all(re.fullmatch(r"packages/[a-z0-9-]+/[a-z0-9-]+", path) for path in paths)
    assert all(entry["npm"].startswith("@deepseek-ai/") for entry in DATA["packages"])


@pytest.mark.parametrize("entry", ENTRIES, ids=lambda entry: entry["module"])
def test_entry_fields(entry: dict[str, Any]) -> None:
    assert entry["milestone"] in MILESTONES
    assert entry["status"] in STATUSES


def test_ported_modules_name_their_upstream() -> None:
    for entry in DATA["packages"]:
        if entry["status"] != "ported":
            continue
        module = importlib.import_module(entry["module"])
        assert module.__doc__ is not None and entry["upstream"] in module.__doc__, entry
