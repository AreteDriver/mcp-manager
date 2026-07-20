# Registry Durability Assessment

**Date:** 2026-07-20
**Scope:** Server registry, telemetry store, lockfile persistence

## Current State

| Component | Backend | Approx. Size | Access Pattern |
|---|---|---|---|
| `ServerRegistry` | JSON file (`~/.config/mcp-manager/registry.json`) | < 100 KB | Read-on-start, write-on-mutation |
| `TelemetryStore` | SQLite (`telemetry.db`) | Unbounded (event log) | Append-only, aggregate queries |
| `.mcp-manager.lock` | YAML (project-scoped) | < 10 KB | Write-on-resolve, read-on-check |

## Assessment

### TelemetryStore — SQLite is correct

Telemetry is already on SQLite with WAL mode. This is the right call because:

- Event volume grows unbounded over months of CLI usage.
- Queries are aggregate (`COUNT`, `GROUP BY DATE`, `MIN/MAX timestamp`).
- SQLite handles concurrent reads safely; WAL prevents writers from blocking readers.
- No migration needed.

### ServerRegistry — JSON is sufficient

The registry holds a flat map of `name → RegistryEntry`. JSON is the right choice because:

- Typical user has 5–50 servers. At 1 KB per entry, the file is < 50 KB.
- Load is a single `json.loads()` on startup; save is a single `json.dumps()` on mutation.
- Human-readable — users can inspect or hand-edit `registry.json`.
- No relational queries, no unbounded growth, no concurrent writers (single CLI process).

**When to reconsider SQLite:**

- Registry exceeds ~1,000 entries (unusual for a personal CLI tool).
- Need cross-process concurrent writes (e.g., daemon mode with multiple clients).
- Need indexed queries (e.g., "find all servers last healthy > 30 days ago").

None of these are on the near-term roadmap.

### Lockfile — YAML is sufficient

The lockfile is project-scoped config, not operational state:

- Written once per `mcp-manager lock` invocation.
- Read once per `mcp-manager lock --check` in CI.
- YAML preserves comments and ordering better than JSON; diff-friendly in git.

## Recommendation

**Keep JSON for registry, keep SQLite for telemetry, keep YAML for lockfile.**

If a daemon mode or multi-user scenario emerges, revisit registry → SQLite. Until then, the complexity cost outweighs the benefit.
