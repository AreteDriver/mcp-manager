# arete-mcp

**One CLI to discover, diagnose, health-check, and sync MCP servers across Codex, Claude Code, Cursor, Windsurf, and more.**

Think of it as **docker-compose for MCP** — a single `.mcp-manager.yml` in your repo that describes which AI tools your project needs, with one command to sync them to every IDE your team uses.

---

## Why arete-mcp?

The Model Context Protocol (MCP) is the open standard for connecting AI agents to external tools — databases, browsers, filesystems, APIs. But every IDE stores MCP configs differently:

| IDE | Config File |
|-----|-------------|
| Codex | `~/.codex/config.toml` |
| Claude Code | `~/.claude.json` |
| Cursor | `~/.cursor/mcp.json` |
| Windsurf | `~/.codeium/windsurf/mcp_config.json` |

Your team can't share configs via git. Switching projects means manual copy-paste. One IDE has a server the others don't. You have no idea which servers are actually healthy.

**arete-mcp solves this** with one CLI and one `.mcp-manager.yml` in your repo:

```bash
# See every MCP server across every IDE
arete-mcp list

# Inspect supported target dialects and diagnose local configs
arete-mcp targets
arete-mcp doctor

# Check if they actually work (not just "starts")
arete-mcp health --deep

# Scaffold a project config
arete-mcp init

# Sync it to Cursor (dry-run first, then commit)
arete-mcp sync --ide cursor --dry-run
arete-mcp sync --ide cursor
```

---

## What Makes This Different

| | **arete-mcp** | Manual IDE Config |
|---|---|---|
| **Config lives in repo** | ✅ `.mcp-manager.yml` committed with your code | ❌ Global client-native config files |
| **Atomic write-back** | ✅ Backups + dry-run before touching IDE configs | ❌ Direct overwrite, no rollback |
| **Deep health checks** | ✅ Verifies `tools/list` responds, deps on PATH | ❌ "Process started" only |
| **Zero daemon** | ✅ CLI-only, no background services | ❌ Some require persistent gateway/web UI |
| **Python-native** | ✅ `pip install`, works wherever Python 3.11+ does | ❌ Node/Go binaries, extra tooling |
| **Cross-client discovery** | ✅ Reads Codex, Claude, Cursor, Windsurf, and project-scoped configs | ⚠️ Partial coverage |

---

## Installation

```bash
pip install arete-mcp
```

Requires Python 3.11+.

Use `arete-mcp` for new scripts and documentation. The historical
`mcp-manager` command remains available as a compatibility alias; project
configuration filenames and the `mcp_manager` Python import namespace are
unchanged.

---

## Quick Links

- [Quickstart](quickstart.md) — Get running in 2 minutes
- [Configuration](configuration.md) — `.mcp-manager.yml` reference
- [Authentication](authentication.md) — Private registries, login/logout, env vars
- [Team Features](team.md) — Shared configs, tags, onboarding
- [Client Target Support](ide-support.md) — Target capabilities, scopes, and paths
- [Contributing](contributing.md) — How to contribute
- [Changelog](changelog.md) — What's new
- [Repository-renaming checklist](repository-renaming-checklist.md) — Separate
  checklist for a future GitHub repository rename

---

## Status

[![CI](https://github.com/AreteDriver/mcp-manager/actions/workflows/ci.yml/badge.svg)](https://github.com/AreteDriver/mcp-manager/actions)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/AreteDriver/mcp-manager/blob/main/LICENSE)
[![PyPI](https://img.shields.io/badge/PyPI-arete--mcp-blue)](https://pypi.org/project/arete-mcp/)
