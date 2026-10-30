# Tracking upstream DeepSeek Harness

The pinned upstream TypeScript source is the specification for this package.

## The pin

[upstream.json](upstream.json) records one upstream commit for the whole package, and
maps every upstream package in scope to its Python module, release milestone and
porting status (`planned`, `in-progress`, `ported`). It also lists the modules that
have no upstream package (`new_modules`).

Current pin: [`ce7073d`](https://github.com/deepseek-ai/deepseek-harness/tree/ce7073d51254c26cd63b22a60835b8f948deb447)
(2026-10-30).

Reference checkout: `/Users/iali/workplace/projects/personal/deepseek-harness`, or
wherever `HARNESS_UPSTREAM` points. It is read through git only.

## Module names

Each upstream package becomes one Python module:

| Upstream package | Rule | Example |
|---|---|---|
| `packages/core/<pkg>` | `harness.core.<pkg>` | `core/agent-loop` → `harness.core.agent_loop` |
| `packages/<group>/<group>` (the Service Definition) | `harness.<group>` | `fs/fs` → `harness.fs` |
| `packages/<group>/<group>-<rest>` | `harness.<group>.<rest>` | `fs/fs-local` → `harness.fs.local` |
| any other `packages/<group>/<pkg>` | `harness.<group>.<pkg>` | `fs/tool-fs` → `harness.fs.tool_fs` |

Dashes become underscores. Seams keep upstream's three roles: the group's package
holds the Service Definition, provider modules sit beside it, and consumers (usually
`tool_*` modules) depend on the definition only.

## Pinned assets

`tests/upstream_assets/` holds unmodified copies of upstream files that tests read:

- `persistence-schema.json`: upstream's normalized type inventory of the session format,
  with a SHA-256 digest per type. Its own `formatVersion` (2) is the inventory layout,
  not the session format.
- `v4.json`: the finalized session format v4 baseline.

At `ce7073d` the inventory has 65 roots against the baseline's 62: 8 event types have
changed digests since v4 was finalized (including `user/message` and
`developer/message`) and 3 are new (`job/registered`, `job/settled`,
`working-directory/change`). Session code targets the inventory at the pin.

`MANIFEST.json` records each file's upstream path, the commit and its checksum.

## Moving the pin

At the start of each milestone:

1. Fetch upstream and run `uv run python scripts/upstream_changes.py --to origin/master`.
   It lists commits since the pin for every mapped package, new upstream packages in
   mapped groups, and pinned assets that changed.
2. Write `docs/upstream-audit-<date>.md`: for each change, adopt, defer, or record an
   intentional Python difference.
3. Port the adopted changes with their tests, update the pin in `upstream.json`, refresh
   the assets and `MANIFEST.json`, and update spec checksums in `compatibility-cases.json`.
4. Run `uv run python scripts/upstream_changes.py --check`.
