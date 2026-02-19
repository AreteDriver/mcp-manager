"""Configuration constants and defaults for mcp-manager."""

from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# IDE config discovery paths.
# Each entry: (tool_name, config_path_str, wrapper_key_or_None)
#   - wrapper_key: JSON key that wraps the server dict (e.g. "mcpServers").
#     None means servers are at the top level of the file.
# ---------------------------------------------------------------------------
IDE_CONFIG_PATHS: list[tuple[str, str, str | None]] = [
    ("claude-code", "~/.claude.json", "mcpServers"),
    ("claude-desktop", "~/.config/Claude/claude_desktop_config.json", "mcpServers"),
    ("cursor", "~/.cursor/mcp.json", "mcpServers"),
    ("windsurf", "~/.windsurf/mcp_config.json", "mcpServers"),
]

# Project-level config (searched in cwd and parent directories).
PROJECT_CONFIG_NAME = ".mcp.json"
PROJECT_CONFIG_TOOL = "project"

# ---------------------------------------------------------------------------
# mcp-manager own paths.
# ---------------------------------------------------------------------------
MANAGER_CONFIG_DIR: Path = Path("~/.mcp-manager").expanduser()
MANAGER_REGISTRY_FILE: Path = MANAGER_CONFIG_DIR / "registry.json"

# ---------------------------------------------------------------------------
# Health check defaults.
# ---------------------------------------------------------------------------
HEALTH_TIMEOUT_SECONDS: int = 10
HEALTH_STDIO_TIMEOUT_SECONDS: int = 15

# ---------------------------------------------------------------------------
# MCP protocol.
# ---------------------------------------------------------------------------
MCP_PROTOCOL_VERSION: str = "2024-11-05"
MCP_CLIENT_NAME: str = "mcp-manager"
MCP_CLIENT_VERSION: str = "0.1.0"
