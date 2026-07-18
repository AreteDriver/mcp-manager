# arete-mcp

**One CLI to discover, health-check, and sync MCP servers across Claude Code, Cursor, Windsurf, and more.**

[![CI](https://github.com/AreteDriver/mcp-manager/actions/workflows/ci.yml/badge.svg)](https://github.com/AreteDriver/mcp-manager/actions)
[![CodeQL](https://github.com/AreteDriver/mcp-manager/actions/workflows/codeql.yml/badge.svg)](https://github.com/AreteDriver/mcp-manager/actions)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![PyPI](https://img.shields.io/badge/PyPI-arete--mcp-blue)](https://pypi.org/project/arete-mcp/)

---

## The Problem

You use Claude Code, Cursor, and Windsurf. Each stores MCP servers in a different JSON file with a different schema.

```
~/.claude.json
~/.cursor/mcp.json
~/.windsurf/mcp_config.json
```

Your team can't share configs via git. Switching projects means manual copy-paste. One IDE has a server the others don't. You have no idea which servers are actually healthy.

**`mcp-manager` gives you one CLI — and one `.mcp-manager.yml` in your repo — to rule them all.**

---

## 30-Second Quickstart

```bash
# Install
pip install arete-mcp

# See every MCP server across every IDE
mcp-manager list

# Check if they actually work (not just "starts")
mcp-manager health --deep

# Scaffold a project config
mcp-manager project init

# Sync it to Cursor (dry-run first, then commit)
mcp-manager sync --ide cursor --dry-run
mcp-manager sync --ide cursor
```

---

## What Makes This Different

|  | **arete-mcp** | Other Managers |
|---|---|---|
| **Config lives in repo** | ✅ `.mcp-manager.yml` committed with your code | ❌ Global per-IDE JSON files |
| **Atomic write-back** | ✅ Backups + dry-run before touching IDE configs | ❌ Direct overwrite, no rollback |
| **Deep health checks** | ✅ Verifies `tools/list` responds, deps on PATH | ❌ "Process started" only |
| **Zero daemon** | ✅ CLI-only, no background services | ❌ Some require persistent gateway/web UI |
| **Python-native** | ✅ `pip install`, works wherever Python 3.11+ does | ❌ Node/Go binaries, extra tooling |
| **Cross-IDE discovery** | ✅ Reads Claude, Cursor, Windsurf, project-level `.mcp.json` | ⚠️ Partial coverage |

---

## Features

### 🔍 Discovery
Reads MCP server configs from:
- Claude Code (`~/.claude.json`)
- Claude Desktop (`~/.config/Claude/claude_desktop_config.json`)
- Cursor (`~/.cursor/mcp.json`)
- Windsurf (`~/.windsurf/mcp_config.json`)
- Project-level (`.mcp.json`, walks parent dirs)

### 🏥 Health Checks
- **Fast**: Process spawn (stdio) or HTTP ping (SSE) — 10s timeout
- **Deep**: Dependency validation (`node`, `python`, `docker` on PATH) + verify `tools/list` returns non-empty
- **Batch**: Check all servers in parallel with `mcp-manager health`

### 📝 Config Write-Back (Atomic & Safe)
- Writes discovered/merged configs back to IDE-specific JSON files
- **Atomic**: temp file + rename (never corrupts your IDE config)
- **Backups**: `.mcp-manager-backup` created before any modification
- **Dry-run**: Preview changes without touching disk

### 📁 Project-Scoped Configs
Create `.mcp-manager.yml` in any repo root:

```yaml
project: my-service
servers:
  postgres-local:
    command: node
    args: ["./mcp/postgres-server/dist/index.js"]
    env:
      DATABASE_URL: ${DATABASE_URL}
  stripe-mcp:
    command: npx
    args: ["-y", "@stripe/mcp"]
    env:
      STRIPE_SECRET_KEY: ${STRIPE_SECRET_KEY}
```

- Environment variables (`${VAR}`) resolved at load time
- Validated before write-back (missing env vars or commands caught early)
- Project config wins on merge conflicts with global registry

### 🔄 Export / Import
Portable YAML/JSON for backup, sharing, and CI:
```bash
mcp-manager export servers.yaml
mcp-manager import servers.yaml
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

# Deep health check — validate dependencies and verify tools/list
mcp-manager health --deep

# Show server-to-IDE mapping
mcp-manager map

# Export/import configs (portable YAML/JSON)
mcp-manager export servers.yaml
mcp-manager import servers.yaml

# Add/remove servers from the registry
mcp-manager add my-server --command "node server.js"
mcp-manager remove my-server

# Sync project config to IDE
mcp-manager sync --ide cursor --dry-run
mcp-manager sync --ide cursor

# Project-level MCP config
mcp-manager project init              # Scaffold .mcp-manager.yml
mcp-manager project validate          # Check env vars, commands on PATH
mcp-manager project export --ide cursor
```

---

## Supported IDEs

| IDE | Config Path | Write-Back |
|-----|-------------|------------|
| Claude Code | `~/.claude.json` | ✅ |
| Claude Desktop | `~/.config/Claude/claude_desktop_config.json` | ✅ |
| Cursor | `~/.cursor/mcp.json` | ✅ |
| Windsurf | `~/.windsurf/mcp_config.json` | ✅ |
| Project-level | `.mcp.json` (walks parent dirs) | ✅ |

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

See [ROADMAP.md](ROADMAP.md) for what's next.

---

## Contributing

```bash
git clone https://github.com/AreteDriver/mcp-manager.git
cd mcp-manager
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

PRs welcome. Please run `ruff check .` and `pytest` before submitting.

---

[Discord](https://discord.gg/fdzQkrt8) — Join the community

*Part of the [AreteDriver](https://github.com/AreteDriver) AI tooling ecosystem.*
