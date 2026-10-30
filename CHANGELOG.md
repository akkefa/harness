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
