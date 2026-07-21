# Architecture Debt: asyncio.run() in Sync CLI Layer

## Context

The MCP Manager CLI uses Typer (Click-based), which runs synchronous command
callbacks. Several commands need to invoke async health checkers:

- `health` → `asyncio.run(checker.check_all(servers))`
- `install --verify` → `asyncio.run(checker.check(server))`
- `uninstall` (warn if healthy) → `asyncio.run(checker.check(server))`
- `monitor` → `asyncio.run(monitor.run())`
- `validate --strict` → `asyncio.run(checker.check_all(servers))`

## Why This Is Debt

1. **Nesting risk**: `asyncio.run()` cannot be called when an event loop is
   already running. If future code composes these functions in an async context,
   it will raise `RuntimeError`.
2. **Test complexity**: Tests must patch both the async method AND `asyncio.run`,
   which led to AsyncMock coroutine leaks (fixed in v0.7.1).
3. **Performance**: Each `asyncio.run()` spins up and tears down a fresh event
   loop. For batch health checks this is wasteful.

## Proper Fix

Migrate the command layer to async using `typer.AsyncCommand` (Typer ≥0.12):

```python
@app.async_command(name="health")
async def health_command(...) -> None:
    results = await checker.check_all(servers)
```

This requires:
1. Marking all command functions in `cli.py` with `@app.async_command`
2. Updating all `*_impl` functions in `commands/` to be `async def`
3. Removing all `asyncio.run()` wrappers
4. Updating tests to `await` directly or use `pytest-asyncio`

## Effort Estimate

~2 hours, touches 6 files, 100% test-safe refactor (no behavior change).

## When To Do It

- Before adding any new async surface area (e.g., WebSocket monitor, SSE streaming)
- Before v0.8.0 if v0.8.0 adds async features (OAuth2 device flow callback server)

## Status

**Acknowledged, deferred.** Tracked here and in ROADMAP.md v0.8.0 notes.
