# Target Adapter Architecture

## Decision

MCP client configuration is modeled as a canonical `McpServer` plus a target
adapter. File I/O remains centralized in `ConfigWriteback`; syntax and
capability decisions belong to adapters.

```text
client JSON/TOML -> target adapter -> McpServer -> target adapter -> client JSON/TOML
                                      |
                                      +-> health, map, export, registry
```

## Why

A shared JSON writer cannot safely represent Codex TOML policy, authentication,
or timeout fields. It also cannot answer whether a target supports project scope
or a transport. Explicit adapters make those differences testable.

## Contracts

Each adapter must:

- parse native text into canonical servers;
- render and remove servers while preserving unrelated config;
- declare format, scope, transport, auth, and policy capabilities;
- reject transport changes that would alter behavior;
- warn before omitting canonical or foreign target-extension fields.

`ConfigWriteback` provides backups and atomic replacement. `ConfigDiscovery`
provides forgiving fleet discovery, while `doctor` uses strict parsing so a bad
entry cannot disappear from diagnostics.

## Compatibility

- Codex TOML is edited with `tomlkit` to preserve comments and root settings.
- JSON adapters preserve unknown same-target fields during round trips.
- Claude's official wrapped project file and mcp-manager's legacy top-level form
  are both discoverable; writes use the official form.
- SSE is retained for clients that support it and rejected for Codex.

## Future Adapters

Keep adapters client-specific, not command-specific. A future VS Code, Zed, or
Gemini adapter should implement the same contract and add conformance fixtures.
Runtime client verification can later extend `doctor` without moving process or
network behavior into the serialization layer.
