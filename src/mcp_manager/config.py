"""Configuration constants and defaults for mcp-manager."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from mcp_manager import __version__

# ---------------------------------------------------------------------------
# IDE config discovery paths.
# Each entry: (tool_name, config_path_str, wrapper_key_or_None)
#   - wrapper_key: JSON key that wraps the server dict (e.g. "mcpServers").
#     None means servers are at the top level of the file.
# ---------------------------------------------------------------------------
if sys.platform == "darwin":
    _CLAUDE_DESKTOP_CONFIG = "~/Library/Application Support/Claude/claude_desktop_config.json"
elif sys.platform == "win32":
    _appdata = os.environ.get("APPDATA", "~/AppData/Roaming")
    _CLAUDE_DESKTOP_CONFIG = str(Path(_appdata) / "Claude/claude_desktop_config.json")
else:
    _CLAUDE_DESKTOP_CONFIG = "~/.config/Claude/claude_desktop_config.json"


IDE_CONFIG_PATHS: list[tuple[str, str, str | None]] = [
    ("claude-code", "~/.claude.json", "mcpServers"),
    ("claude-desktop", _CLAUDE_DESKTOP_CONFIG, "mcpServers"),
    ("cursor", "~/.cursor/mcp.json", "mcpServers"),
    ("windsurf", "~/.codeium/windsurf/mcp_config.json", "mcpServers"),
    ("codex", "~/.codex/config.toml", "mcp_servers"),
]

# Targets whose configuration syntax differs from the default JSON dialect.
TARGET_FORMATS: dict[str, str] = {
    "codex": "toml",
}

# Project-scoped target configuration paths. Targets omitted here currently
# support user-scoped write-back only.
TARGET_PROJECT_PATHS: dict[str, str] = {
    "claude-code": ".mcp.json",
    "cursor": ".cursor/mcp.json",
    "codex": ".codex/config.toml",
}

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

# ---------------------------------------------------------------------------
# MCP protocol.
# ---------------------------------------------------------------------------
MCP_PROTOCOL_VERSION: str = "2026-07-28"
MCP_LEGACY_PROTOCOL_VERSION: str = "2024-11-05"
MCP_CLIENT_NAME: str = "mcp-manager"
MCP_CLIENT_VERSION: str = __version__
