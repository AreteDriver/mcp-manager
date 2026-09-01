# Sprint 0 — MCP compatibility foundation

**Date:** 2026-08-26
**Status:** implemented and locally verified

## Objective

Establish a small, falsifiable foundation for Agent Operations Architecture:
prove that mcp-manager can negotiate MCP 2026-07-28, retain controlled legacy
compatibility, validate deterministic tool-list caching, and work without
transport-level session affinity.

## Delivered

- Official Python SDK 2.x integration using the modern `MCPServer` API.
- Auto-negotiated modern discovery with legacy handshake fallback.
- `mcp-manager doctor --protocol <server>` as a read-only operator probe.
- `--strict-modern` for migration enforcement and `--json` for CI evidence.
- Secret-safe HTTP header and bearer-token environment resolution.
- Modern stdio fixture proving discovery, cache reuse, and a benign tool call.
- Legacy fixture proving fallback behavior remains available.
- Cross-instance Streamable HTTP test proving self-contained requests, required
  routing headers, deterministic list results, and absence of
  `Mcp-Session-Id`.
- Migration, rollback, and operator documentation.

## Acceptance evidence

| Control | Evidence |
|---|---|
| Modern negotiation | Strict probe negotiates `2026-07-28` |
| Legacy compatibility | Auto mode falls back to `2024-11-05` fixture |
| Cache semantics | Instrumented server receives one list request across refresh/use calls |
| Stateless routing | Four requests alternate between two independent HTTP server instances |
| Safe operator surface | Doctor performs discovery and list only; it never calls a tool |
| Credential hygiene | Tests resolve environment credentials and expose missing names, never values |

## Rollout

1. Ship the default auto-negotiating probe.
2. Inventory modern versus legacy servers in non-production environments.
3. Add strict-modern CI gates only for servers already shown compatible.
4. Preserve `health` for legacy SSE diagnostics.

Rollback requires restoring the prior server release and removing the strict
gate. Client configuration and registry data do not need migration.

## Deferred

- A treatment-based evaluation run is specified in the adjacent
  `arete-evals` repository. Engine implementation is deferred until the
  canonical `evalcore` source is available; creating another harness in the
  practice repository would violate its documented architecture.
- Production gateway authorization policies and runtime evidence records are
  later sprints, after protocol compatibility is proven.
