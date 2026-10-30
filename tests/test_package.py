"""The installed package imports cleanly and declares itself typed."""

from __future__ import annotations

import importlib.resources
import logging

import harness


def test_package_import() -> None:
    assert harness.__name__ == "harness"
    assert all(hasattr(harness, name) for name in harness.__all__)


def test_package_is_typed() -> None:
    assert importlib.resources.files("harness").joinpath("py.typed").is_file()


def test_package_logger_is_quiet_by_default() -> None:
    handlers = logging.getLogger("harness").handlers
    assert any(isinstance(handler, logging.NullHandler) for handler in handlers)
