# IDE Support

mcp-manager reads and writes MCP configs for the following IDEs and tools.

---

## Supported IDEs

| IDE | Config Path | Read | Write | Notes |
|-----|-------------|------|-------|-------|
| **Claude Code** | `~/.claude.json` | ✅ | ✅ | Global config |
| **Claude Desktop** | `~/.config/Claude/claude_desktop_config.json` | ✅ | ✅ | macOS/Linux |
| **Cursor** | `~/.cursor/mcp.json` | ✅ | ✅ | Global config |
| **Windsurf** | `~/.windsurf/mcp_config.json` | ✅ | ✅ | Global config |
| **Project-level** | `.mcp.json` | ✅ | ✅ | Walks parent directories |

---

## Claude Code

**Config file:** `~/.claude.json`

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

Write-back wraps servers under `mcpServers`.

---

## Claude Desktop

**Config file:** `~/.config/Claude/claude_desktop_config.json`

Same schema as Claude Code. mcp-manager preserves existing keys (settings, etc.) when writing back.

---

## Cursor

**Config file:** `~/.cursor/mcp.json`

Cursor uses the same schema as Claude Code. mcp-manager reads and writes the `mcpServers` key.

---

## Windsurf

**Config file:** `~/.windsurf/mcp_config.json`

Windsurf wraps MCP servers under a `mcpServers` key in a broader config file. mcp-manager preserves other keys.

---

## Project-Level `.mcp.json`

Some projects include a `.mcp.json` in the repo root. mcp-manager walks parent directories to discover these.

```json
{
  "filesystem": {
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-filesystem"]
  }
}
```

No wrapper key — servers are top-level.

---

## Adding a New IDE

To add support for a new IDE, edit `src/mcp_manager/config.py`:

```python
IDE_CONFIG_PATHS: list[tuple[str, str, str | None]] = [
    # (tool_name, config_path, wrapper_key)
    ("my-ide", "~/.my-ide/mcp.json", "mcpServers"),
]
```

- `tool_name`: Short name used in CLI
- `config_path`: Path to the IDE's MCP config file (`~` expanded)
- `wrapper_key`: JSON key wrapping the servers dict (e.g. `mcpServers`), or `None` for top-level

No code changes needed beyond this — discovery and write-back are generic.
