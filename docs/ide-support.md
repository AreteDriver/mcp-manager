# Client Target Support

`mcp-manager` uses a target adapter for each MCP client. Adapters own the native
file format, supported scopes and transports, target-only fields, and translation
warnings.

## Support Matrix

| Target | User config | Project config | Format | Transports |
|--------|-------------|----------------|--------|------------|
| Codex | `~/.codex/config.toml` | `.codex/config.toml` | TOML | stdio, HTTP |
| Claude Code | `~/.claude.json` | `.mcp.json` | JSON | stdio, HTTP, SSE |
| Claude Desktop | Platform-specific (see below) | — | JSON | stdio, HTTP, SSE |
| Cursor | `~/.cursor/mcp.json` | `.cursor/mcp.json` | JSON | stdio, HTTP, SSE |
| Windsurf | `~/.codeium/windsurf/mcp_config.json` | — | JSON | stdio, HTTP, SSE |

Inspect the runtime matrix instead of relying on copied paths:

```bash
mcp-manager targets
mcp-manager targets --json
```

## Codex

Codex stores MCP servers as TOML tables:

```toml
[mcp_servers.arete-context]
command = "python"
args = ["server.py"]
enabled = true
required = true
enabled_tools = ["search_notes"]
startup_timeout_sec = 20
```

The adapter preserves unrelated root settings, comments, target extensions,
authentication references, tool policy, and timeout settings. Codex supports
stdio and streamable HTTP; an SSE-to-Codex translation is rejected rather than
silently changed.

## Claude Code

User-scoped servers live under `mcpServers` in `~/.claude.json`. Shared project
servers use the same wrapper in `.mcp.json`:

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem"]
    }
  }
}
```

Discovery also reads the older mcp-manager top-level `.mcp.json` shape for
backward compatibility. New writes always use Claude Code's official wrapper.

## Claude Desktop

Claude Desktop uses the `mcpServers` JSON shape. The user path is selected by
platform:

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Linux: `~/.config/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\\Claude\\claude_desktop_config.json`

Claude Desktop chat configuration is separate from Claude Code configuration.

## Cursor

Cursor uses `mcpServers` in `~/.cursor/mcp.json` globally and
`.cursor/mcp.json` per project. Modern untyped remote URLs are treated as
streamable HTTP; explicit `type: sse` remains SSE.

## Windsurf

Windsurf uses `mcpServers` in `~/.codeium/windsurf/mcp_config.json`. Both `url`
and `serverUrl` remote forms are accepted. Windsurf does not currently document
a repository-scoped MCP file, so `--scope project` is rejected for this target.

## Safe Translation

```bash
# Validate syntax, executable paths, cwd values, and env-var presence.
mcp-manager doctor --project .

# Preview target-native output and translation warnings.
mcp-manager sync --ide codex --dry-run

# Write a shared project config.
mcp-manager sync --ide cursor --scope project --project . --create
```

Static diagnostics never print credential values. They report only missing
environment-variable names. Existing files are backed up before atomic writes.

## Adding a Target

1. Implement `TargetAdapter` in `src/mcp_manager/adapters/`.
2. Declare paths, format, scopes, transports, and policy capabilities.
3. Preserve same-target extensions and warn for fields that cannot translate.
4. Register the adapter in `adapters/registry.py` and `config.py`.
5. Add parse/render/remove round-trip tests plus user/project scope tests.

## Format Sources

- [Codex MCP and config reference](https://developers.openai.com/codex/mcp)
- [Claude Code MCP scopes](https://code.claude.com/docs/en/mcp)
- [Cursor MCP configuration](https://docs.cursor.com/context/model-context-protocol)
- [Windsurf MCP configuration](https://docs.windsurf.com/windsurf/cascade/mcp)
