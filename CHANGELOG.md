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
- Phase 3, session persistence:
  - `harness.session.persistence` (upstream `session/session-persistence`): the
    `sessionPersistence` service definition, handles, errors and shared storage checks.
  - `harness.session.persistence_jsonl` (upstream `session/session-persistence-jsonl`):
    the JSONL backend with upstream's directory layout, single-writer lease, durable
    publication, live write batching and torn-tail repair. Format v4 and uncompressed
    files only for now; zstd and v0–v3 migration are not ported.
  - The v4 codec stack: `harness.session.format_v1_to_v2` (the v2 row framing v4 reuses),
    `harness.session.format_v3_to_v4` (v4 admission and relationship checks) and
    `harness.session.format_catalog` (v4 current; v0–v3 reported unsupported).
  - `harness.session.projection` (upstream `session/session-projection`).
  - `harness.testing`: the upstream persistence and live-write contract suites as a
    pytest-free public API, so any `SessionPersistence` backend can run them.
  - 740 catalogued upstream cases from 63 files (629 ported, 35 adapted, 31 run through
    the contract suites). Cases not ported yet (migrations, zstd, Node-only, JavaScript-only)
    are listed by reason in `docs/upstream.md`.
  - `session-checkpoint-policy` and `session-title` move to Phase 5: both need the agent
    package.

