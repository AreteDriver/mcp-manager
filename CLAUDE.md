# CLAUDE.md — mcp-manager

## Project Overview
MCP server manager CLI — discovers, monitors, and manages MCP (Model Context Protocol) servers across agentic IDEs (Claude Code, Cursor, Windsurf, Claude Desktop).

## Quick Start
```bash
cd /home/arete/projects/mcp-manager
source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/ -v
ruff check src/ tests/ && ruff format --check src/ tests/
```

## Architecture
- **src layout**: `src/mcp_manager/` with 12 modules
- **Entry point**: `mcp-manager = "mcp_manager.cli:app"` (Typer)
- **Models**: Pydantic v2 (`models.py`)
- **Config discovery**: Read-only scanning of IDE config files (`discovery.py`)
- **Health checks**: Async via `asyncio.gather`, bridged to sync CLI via `asyncio.run()` (`health.py`)
- **Registry**: JSON persistence at `~/.mcp-manager/registry.json` (`registry.py`)
- **Export/Import**: YAML/JSON portable format (`exporters.py`)
- **Licensing**: HMAC-checksum keys, prefix `MCPM`, salt `mcp-manager-v1` (`licensing.py`)

## Key Commands
```bash
mcp-manager list                    # List all MCP servers across IDEs
mcp-manager list --tool cursor      # Filter by IDE
mcp-manager list --json             # JSON output
mcp-manager map                     # Show server → IDE mapping
mcp-manager health                  # Health check all servers
mcp-manager test <name>             # Full protocol handshake test
mcp-manager add <name> --command x  # Add stdio server to registry
mcp-manager add <name> --url x      # Add network server to registry
mcp-manager remove <name>           # Remove from registry
mcp-manager export out.yaml         # Export to YAML/JSON
mcp-manager import config.yaml      # Import from YAML/JSON
mcp-manager status                  # Show license tier
```

## Transport Types
- **stdio**: Local subprocess, JSON-RPC over stdin/stdout
- **sse**: Server-Sent Events over HTTP
- **http**: HTTP POST JSON-RPC

## IDE Config Paths
| Tool | Path | Key |
|------|------|-----|
| Claude Code | `~/.claude.json` | `mcpServers` |
| Claude Desktop | `~/.config/Claude/claude_desktop_config.json` | `mcpServers` |
| Cursor | `~/.cursor/mcp.json` | `mcpServers` |
| Windsurf | `~/.windsurf/mcp_config.json` | `mcpServers` |
| Project | `.mcp.json` (cwd + parents) | top-level |

## Testing
- 139 tests, pytest
- `tests/conftest.py` has shared fixtures with sample server configs
- Health checks are mocked (no real subprocess/HTTP in tests)

## Conventions
- Python 3.11+, `from __future__ import annotations` everywhere
- Ruff lint + format (B008 suppressed for cli.py — Typer pattern)
- Dependencies: typer, rich, pydantic, httpx, pyyaml
