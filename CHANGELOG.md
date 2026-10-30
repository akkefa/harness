# Changelog

## Unreleased

- Repository tooling (plan Phase 0): `cordis-harness` packaging on hatchling and uv,
  CI on Python 3.11–3.13 (Linux) and 3.11 (macOS), tag-triggered PyPI release through
  trusted publishing, wheel and source-archive audits, and a core-only installation
  check.
- Upstream tracking: [docs/upstream.json](docs/upstream.json) pins DeepSeek Harness
  `ce7073d` and maps its 88 in-scope packages to Python modules;
  `scripts/upstream_changes.py` reports upstream changes since the pin.
- Pinned copies of upstream's session-format inventory and finalized v4 baseline.
- Boundary tests that reject product imports and undeclared dependencies, and a
  catalog check tying `@pytest.mark.upstream` tests to their upstream sources.
- Cordis alignment (plan Phase 1): `scripts/cordis_usage.py` inventories the Cordis
  features mapped upstream packages use, [docs/cordis-alignment.md](docs/cordis-alignment.md)
  records the result, and `tests/test_cordis_contract.py` checks the behaviour the harness
  relies on against the installed deepseek-cordis. Three gaps block 0.1 (public
  `Events.dispatch`, `Fiber.assert_active`, `internal/status` and `internal/plugin`
  events); they are tracked as strict xfails until deepseek-cordis adds them.
