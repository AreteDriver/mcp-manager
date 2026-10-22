# Protocol compatibility

MCP 2026-07-28 replaces transport initialization and protocol sessions with
self-describing requests. `mcp-manager` supports the modern protocol through
the official Python SDK while retaining an explicit compatibility path for
handshake-era servers.

## Read-only compatibility probe

Probe a server already present in a discovered client configuration:

```bash
mcp-manager doctor --protocol my-server
```

The probe performs this sequence:

1. Attempt `server/discover` using MCP 2026-07-28.
2. Fall back to the legacy initialization handshake when the server does not
   implement discovery. If a handshake-era stdio server exits on the unknown
   discovery request, restart it once in explicit legacy mode.
3. Request `tools/list` with a cache refresh.
4. Repeat `tools/list` through the SDK cache and compare the client-visible
   result.

The doctor command never calls a tool, so it is safe for routine diagnostics.
Use `--json` for automation. Use `--strict-modern` to fail when the server
requires legacy fallback:

```bash
mcp-manager doctor --protocol my-server --strict-modern --json
```

The result identifies the negotiated protocol era and version, tool count,
list cache hint, and whether the repeated list result remained stable.

## HTTP routing and credentials

Modern Streamable HTTP requests are self-contained and do not require an
`Mcp-Session-Id`. The protocol requires `MCP-Protocol-Version`, `Mcp-Method`,
and, for named operations, `Mcp-Name` headers so an HTTP gateway can route and
authorize requests without parsing the JSON body.

The official SDK supplies the protocol routing headers. `mcp-manager` resolves
configured header and bearer-token environment references immediately before
opening the HTTP client. Diagnostic output reports missing variable names but
never prints credential values. Client-managed Codex authentication modes such
as `oauth` and `chatgpt` cannot be reproduced by this standalone diagnostic;
run the server through that client or configure an environment-backed
credential for the probe.

If the same server name has different connection settings across clients,
select the intended configuration with `--target`.

## Migration and rollback

Adopt the protocol in two stages:

1. Run the default probe to inventory modern and legacy servers without
   changing their configuration.
2. Enable `--strict-modern` in CI only after required servers pass.

Legacy compatibility remains available through automatic negotiation. If a
modern server migration regresses, restore the prior server release and remove
the strict gate; no mcp-manager registry or client configuration migration is
required. Legacy SSE remains available through `mcp-manager health`, but the
new compatibility probe is intentionally limited to stdio and Streamable HTTP.

## Verification coverage

The integration suite exercises an official modern client/server pair, cache
reuse, a benign tool call, and legacy fallback. A separate HTTP test routes
discover, list, repeat-list, and call requests across two independent server
instances and verifies that no protocol session identifier is used.
