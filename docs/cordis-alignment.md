# Cordis alignment (plan Phase 1)

Date: 2026-10-30. Upstream pin: DeepSeek Harness `ce7073d` (vendored Cordis
`4.0.6-alpha.1`). Python runtime checked: deepseek-cordis `0.1.1` from PyPI (the
version locked here); the PyCordis repo at `0.1.2` (`f804a26`) has the same API.

## Method

1. `scripts/cordis_usage.py` reads every mapped package's sources at the pin (tests
   excluded) and lists the Cordis features they use, with the packages and the
   earliest milestone that needs each one. Re-run it whenever the pin moves.
2. Each feature was checked against deepseek-cordis's public API and documented
   behaviour (`PyCordis/docs/compatibility.md`), and the ones the harness depends on
   were probed against the installed package.
3. `tests/test_cordis_contract.py` keeps those probes. Each gap is a strict `xfail`, so
   it starts failing (XPASS) the moment deepseek-cordis gains the feature.

## Result

deepseek-cordis covers almost everything the in-scope packages use. **Three small gaps
block 0.1** (G1–G3). They are all additive to deepseek-cordis. Everything else is
either already there, a deliberate Python difference, or not needed before 0.5.

### Covered

| Feature | Upstream use at the pin | deepseek-cordis |
|---|---|---|
| `ctx.on` / `once`, with `prepend` and `global` | 31 packages | `on(name, listener, prepend=, global_=)` |
| `ctx.emit`, `parallel`, `serial` | 6, 1, 1 packages | same names; `parallel` is all-settled |
| `ctx.waterfall`, listener `(*args, next)` | 7 packages (tool pipeline, prompt, fs intents) | same shape: `waterfall(name, *args, next_=)`; zero-argument `next()` |
| `ctx.effect` with a dispose callback, `function*`, `async function*` | 33 packages | callable, sync and async generator effects |
| `ctx.inject([...], callback)` with reactive reload | 16 packages | same; consumer returns to `PENDING` when a provider leaves (probed) |
| `ctx.plugin(plugin, config)` | 5 packages | same |
| `ctx.get(name)`, `ctx.provide(name, value)` | 24, 2 packages | same, plus `require` and `set` |
| `ctx.extend(meta)` | `core/scope` (0.1), `preset/agent-preset-registry` | same |
| `Service` subclasses registered by name | 33 packages | `Service(ctx, config, name=...)` or a class `name` |
| `[Service.init]` (async setup after construction) | 15 packages | `Service.start()` |
| `fiber.state`, `FiberState.*`, `fiber.uid` | 7, 4 packages | same; all six states |
| `fiber.await()` | `preset/agent-preset-registry` (0.5) | `fiber.wait()` |
| Isolated service slots (`Context.isolate`) | `preset/agent-preset-registry` (0.5) | `ctx.isolate(name, label)` and `ScopeLabel` |

### Gaps

| Id | Feature | Needed by | First needed | deepseek-cordis today | Proposed fix |
|---|---|---|---|---|---|
| **G1** | `ctx.events.dispatch(mode, args)`: the snapshot of listener callables, which the caller invokes itself to contain listener failures | `core/session`, `core/agent`, `core/agent-loop`, `core/tools`, `credentials/credentials` +5 | **0.1, Phase 2** (`core/session`) | private `Events._dispatch(mode, name, args, filter_)` | make it public as `Events.dispatch`, with the same snapshot and filter rules |
| **G2** | `fiber.assertActive()`: raise if the owning fiber has been disposed | `core/agent-loop`, `session/session-projection`, `session/working-directory`, `context/time-context`, `subagent/tool-subagent` | **0.1, Phase 3** (`session-projection`) | missing | add `Fiber.assert_active()`: raise `CordisError` when `uid is None`, as upstream does |
| **G3** | lifecycle events `internal/status(fiber, old_state)` on every state change, and `internal/plugin(fiber)` when a fiber is published or disposed | `core/agent` (`internal/status`); `mcp/mcp-client` (`internal/plugin`) | **0.1, Phase 5** (`core/agent`); 0.4 | only `internal/dispatch` is emitted | emit both from the fiber state machine, global to every context |
| G4 | `fiber.entry`: the loader row that created a fiber | `core/agent-default-model`, `llm/llm-deepseek-api-key`, `preset/agent-preset-registry` | 0.5 | missing | have `Loader` record the row id on the fibers it creates. Upstream code always falls back when `entry` is missing, so 0.1 does not need it. |
| G5 | Config access: `fiber.effectiveConfig`, `resolveConfig(candidate)`, raw config replacement | `settings/settings` | 0.5 | deferred in the 2026-10-28 PyCordis audit | follow upstream's Cordis rc.11 PR 1, which is defining this API now |
| G6 | Loader features: entry trees and groups, `include`, `interpolate`, JS expressions, `ctx.root.loader`, `ctx.reflect.store` | `preset/agent-preset`, `preset/agent-preset-registry`, `settings/settings` | 0.5 | deterministic flat-row loader only | revisit with presets in 0.5, after upstream's Loader rc.8 upgrade |

### Python differences (not gaps)

| Upstream | Harness | Why |
|---|---|---|
| `ctx.logger(...)` (34 packages) | `logging.getLogger(__name__)` per module | deepseek-cordis has no LoggerService and uses stdlib logging; the package logger already has a `NullHandler` |
| `getTraceable(ctx, target)`, `symbols.original` (`core/agent`) | pass the owner context explicitly | deepseek-cordis has no tracing proxies. `core/agent` uses them only to bind an agent factory to the context that registered it; Phase 5 does that binding explicitly and records it in the compatibility catalog. |
| `Volatile<T>` / `isVolatile` (cosmokit, 14 packages, including `core/agent-loop` and `llm/llm-deepseek`) | a harness-owned `Volatile` holder | `Volatile` comes from cosmokit, not from Cordis core; Cordis only re-exports the type. The harness adds a small equivalent in Phase 5 (a current value plus change notification) without changing deepseek-cordis. |
| schemastery config schemas (57 packages) | Pydantic models behind the deepseek-cordis `ConfigValidator` protocol | per the plan's translation rules; Phase 2 adds the adapter |

### Not used by any mapped package

`ctx.bail`, `[Service.check]`, `ctx.intercept`, `ctx.set`, `ctx.accessor`, `ctx.mixin`,
and the timer plugin (`ctx.setTimeout`, `ctx.sleep` and friends). None of them is
needed by this package.

## Upstream Cordis rc.11

Upstream's `vendor/cordis-rc11-upgrade-plan.md` is still a proposal. Its PR 1 (config
access) is exactly G5, and its Loader work overlaps G6. G1–G4 match the current vendored
Cordis and don't depend on rc.11. The `ce7073d` vendored Cordis (`4.0.6-alpha.1`) is the
one deepseek-cordis was last audited against (Harness `f3803c9`), so there's no other
known drift.

## Recommendation

1. Add G1, G2 and G3 to deepseek-cordis, with tests ported from the vendored Cordis
   specs, and release it as `0.1.3` on PyPI.
2. Raise this package's floor to `deepseek-cordis>=0.1.3,<0.2` and remove the three
   xfail markers in `tests/test_cordis_contract.py`.
3. G1 is needed first (Phase 2), so the deepseek-cordis release should come before
   Phase 2 starts. If it can't, Phase 2 can call the private `_dispatch` behind one
   wrapper function and switch over when 0.1.3 lands.
4. Leave G4–G6 for 0.5 and re-check them against upstream's rc.11 work then.

None of these deepseek-cordis changes has been made. They touch the PyCordis repo and
wait for the maintainer's approval.

## Dependencies on deepseek-cordis internals

Added in Phase 3. Recheck these whenever the deepseek-cordis pin moves:

- `harness.session.projection` subclasses `deepseek_cordis.Effect`, through its public
  constructor `(owner, setup, label)`, so that a registration is both its handle and its
  disposer, as upstream's is. A change to that constructor or to how effects adopt
  returned values would break it; `tests/session/projection/test_compatibility.py`
  covers the adoption cases.
- `harness._cordis` holds the G1/G2 shims (`Events._dispatch`, `Fiber.uid`).
