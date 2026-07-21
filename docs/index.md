# mcp-manager

**One CLI to discover, health-check, and sync MCP servers across Claude Code, Cursor, Windsurf, and more.**

Think of it as **docker-compose for MCP** — a single `.mcp-manager.yml` in your repo that describes which AI tools your project needs, with one command to sync them to every IDE your team uses.

---

## Why mcp-manager?

The Model Context Protocol (MCP) is the open standard for connecting AI agents to external tools — databases, browsers, filesystems, APIs. But every IDE stores MCP configs differently:

| IDE | Config File |
|-----|-------------|
| Claude Code | `~/.claude.json` |
| Cursor | `~/.cursor/mcp.json` |
| Windsurf | `~/.windsurf/mcp_config.json` |

Your team can't share configs via git. Switching projects means manual copy-paste. One IDE has a server the others don't. You have no idea which servers are actually healthy.

**mcp-manager solves this** with one CLI and one `.mcp-manager.yml` in your repo:

```bash
# See every MCP server across every IDE
mcp-manager list

# Check if they actually work (not just "starts")
mcp-manager health --deep

# Scaffold a project config
mcp-manager init

# Sync it to Cursor (dry-run first, then commit)
mcp-manager sync --ide cursor --dry-run
mcp-manager sync --ide cursor
```

---

## What Makes This Different

| | **mcp-manager** | Manual IDE Config |
|---|---|---|
| **Config lives in repo** | ✅ `.mcp-manager.yml` committed with your code | ❌ Global per-IDE JSON files |
| **Atomic write-back** | ✅ Backups + dry-run before touching IDE configs | ❌ Direct overwrite, no rollback |
| **Deep health checks** | ✅ Verifies `tools/list` responds, deps on PATH | ❌ "Process started" only |
| **Zero daemon** | ✅ CLI-only, no background services | ❌ Some require persistent gateway/web UI |
| **Python-native** | ✅ `pip install`, works wherever Python 3.11+ does | ❌ Node/Go binaries, extra tooling |
| **Cross-IDE discovery** | ✅ Reads Claude, Cursor, Windsurf, project-level `.mcp.json` | ⚠️ Partial coverage |

---

## Installation

```bash
pip install arete-mcp
```

Requires Python 3.11+.

---

## Quick Links

- [Quickstart](quickstart.md) — Get running in 2 minutes
- [Configuration](configuration.md) — `.mcp-manager.yml` reference
- [Team Features](team.md) — Shared configs, tags, onboarding
- [IDE Support](ide-support.md) — Per-IDE quirks and paths
- [Contributing](contributing.md) — How to contribute
- [Changelog](changelog.md) — What's new

---

## Status

[![CI](https://github.com/AreteDriver/mcp-manager/actions/workflows/ci.yml/badge.svg)](https://github.com/AreteDriver/mcp-manager/actions)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![PyPI](https://img.shields.io/badge/PyPI-arete--mcp-blue)](https://pypi.org/project/arete-mcp/)
