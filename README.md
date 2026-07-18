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

# Health check all servers (fast — process spawn / HTTP ping)
mcp-manager health

# Deep health check — validate dependencies on PATH and verify tools/list responds
mcp-manager health --deep

# Show server-to-IDE mapping
mcp-manager map

# Export/import configs (portable YAML/JSON)
mcp-manager export servers.yaml
mcp-manager import servers.yaml

# Add/remove servers from the registry
mcp-manager add my-server --command "node server.js"
mcp-manager remove my-server

# Sync project config to IDE (see Project-scoped Config below)
mcp-manager sync --ide cursor --dry-run
mcp-manager sync --ide cursor

# Project-level MCP config
mcp-manager project init              # Scaffold .mcp-manager.yml
mcp-manager project validate          # Check env vars, commands on PATH
mcp-manager project export --ide cursor
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

## Project-scoped Config

Create `.mcp-manager.yml` in any repo root to share MCP server configs with your team:

```yaml
project: my-project
servers:
  local-docs:
    command: node
    args: ["./dist/index.js"]
    env:
      API_KEY: ${API_KEY}
  remote-search:
    type: sse
    url: http://localhost:3000/sse
```

Environment variables (`${VAR}`) are resolved at load time. The config is validated before write-back (missing env vars or commands not on PATH are caught early).

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
- [x] Config write-back (atomic, with backups)
- [x] Project-scoped `.mcp-manager.yml` support
- [x] Deep health checks (dependency validation + `tools/list` verification)
- [ ] Server auto-restart on failure

---

[Discord](https://discord.gg/fdzQkrt8) — Join the community

*Part of the [AreteDriver](https://github.com/AreteDriver) AI tooling ecosystem.*
