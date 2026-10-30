"""Pinned upstream assets match their manifest and share the package map's pin."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "tests" / "upstream_assets"
MANIFEST: dict[str, Any] = json.loads((ASSETS / "MANIFEST.json").read_text())


def test_assets_share_the_map_pin() -> None:
    upstream_map = json.loads((ROOT / "docs" / "upstream.json").read_text())
    assert MANIFEST["commit"] == upstream_map["upstream"]["commit"]


def test_manifest_lists_every_asset() -> None:
    listed = {entry["local"] for entry in MANIFEST["files"]}
    present = {path.name for path in ASSETS.iterdir() if path.name != "MANIFEST.json"}
    assert listed == present


@pytest.mark.parametrize("entry", MANIFEST["files"], ids=lambda entry: entry["local"])
def test_asset_checksum(entry: dict[str, str]) -> None:
    data = (ASSETS / entry["local"]).read_bytes()
    assert hashlib.sha256(data).hexdigest() == entry["sha256"]


def test_finalized_baseline_is_session_format_v4() -> None:
    baseline = json.loads((ASSETS / "v4.json").read_text())
    assert baseline["sessionFormatVersion"] == 4


def test_inventory_contains_every_finalized_v4_root() -> None:
    # persistence-schema.json is upstream's type inventory (its own formatVersion is the
    # inventory layout, not the session format). Every root accepted into the finalized
    # v4 baseline must still be present; a digest change marks a reviewed v4 addition.
    inventory = json.loads((ASSETS / "persistence-schema.json").read_text())
    baseline = json.loads((ASSETS / "v4.json").read_text())
    present = {root["key"] for root in inventory["roots"]}
    assert set(baseline["roots"]) <= present
