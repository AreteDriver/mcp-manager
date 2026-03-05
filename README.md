# mcp-manager

**Discover, monitor, and manage MCP servers across agentic IDEs.**

[![CI](https://github.com/AreteDriver/mcp-manager/actions/workflows/ci.yml/badge.svg)](https://github.com/AreteDriver/mcp-manager/actions)
[![CodeQL](https://github.com/AreteDriver/mcp-manager/actions/workflows/codeql.yml/badge.svg)](https://github.com/AreteDriver/mcp-manager/actions)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## The Problem

MCP servers are configured per-IDE in different JSON files with different schemas. If you use Claude Code, Cursor, and Windsurf, your servers are scattered across three configs with no unified view.

`mcp-manager` gives you one CLI to see, health-check, and manage all of them.

---

## Install

```bash
pip install mcp-manager
```

---

## Usage

```bash
# List all MCP servers across all IDEs
mcp-manager list

# Filter by IDE
mcp-manager list --tool cursor

# Health check all servers
mcp-manager health

# Show server-to-IDE mapping
mcp-manager map

# Export/import configs (portable YAML/JSON)
mcp-manager export servers.yaml
mcp-manager import servers.yaml

# Add/remove servers from the registry
mcp-manager add my-server --command "node server.js"
mcp-manager remove my-server
```

---

## Supported IDEs

| IDE | Config Path |
|-----|-------------|
| Claude Code | `~/.claude.json` |
| Claude Desktop | `~/.config/Claude/claude_desktop_config.json` |
| Cursor | `~/.cursor/mcp.json` |
| Windsurf | `~/.windsurf/mcp_config.json` |
| Project-level | `.mcp.json` (walks parent dirs) |

---

## Transport Types

- **stdio** — local subprocess, JSON-RPC over stdin/stdout
- **sse** — Server-Sent Events over HTTP
- **http** — HTTP POST JSON-RPC

---

## Status

- [x] Read-only config discovery across 5 IDE configs
- [x] Async health checks with timeout
- [x] JSON registry with add/remove
- [x] YAML/JSON export/import
- [x] Protocol handshake testing
- [ ] Config write-back (edit IDE configs directly)
- [ ] Server auto-restart on failure

---

*Part of the [AreteDriver](https://github.com/AreteDriver) AI tooling ecosystem.*
