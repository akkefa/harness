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
- Phase 2, scope and session log:
  - `harness.core.scope` (upstream `core/scope`).
  - `harness.session.format` (upstream `session/session-format`): JSON coordinates,
    header snapshots, log filenames, the migration chain and the codec catalog.
  - `harness.core.session` (upstream `core/session`): the append-only Session log, the
    `sessions` store, the model-visible surface and message projections, request headers,
    tool history, repair, fork and plugin records. Store operations act for the calling
    fiber through `SessionStore.caller`.
  - `harness.util.values`: frozen JSON values and a `JSON.stringify`/`JSON.parse`
    compatible encoder and parser.
  - `harness.llm`: the message and call-config vocabulary the session log needs; the
    adapter seam follows in Phase 4.
  - 325 upstream test cases from 26 spec files are ported, 35 of them adapted with notes;
    42 cannot apply in Python and 2 wait on Phase 4.
  - A conformance check validates Python-written events and headers against upstream's
    pinned v4 type inventory.
