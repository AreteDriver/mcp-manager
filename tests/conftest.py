"""Shared test fixtures for mcp-manager."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Sample MCP config data
# ---------------------------------------------------------------------------

SAMPLE_STDIO_SERVERS = {
    "filesystem": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
    },
    "github": {
        "command": "node",
        "args": ["github-server.js"],
        "env": {"GITHUB_TOKEN": "ghp_test123"},
    },
}

SAMPLE_NETWORK_SERVERS = {
    "slack": {
        "type": "http",
        "url": "https://mcp.slack.com/mcp",
        "headers": {"Authorization": "Bearer xoxb-test"},
    },
    "asana": {
        "type": "sse",
        "url": "https://mcp.asana.com/sse",
    },
}

SAMPLE_MIXED_SERVERS = {**SAMPLE_STDIO_SERVERS, **SAMPLE_NETWORK_SERVERS}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_claude_config(tmp_path: Path) -> Path:
    """Create a fake ~/.claude.json with stdio servers."""
    config_file = tmp_path / ".claude.json"
    config_file.write_text(
        json.dumps({"mcpServers": SAMPLE_STDIO_SERVERS}),
        encoding="utf-8",
    )
    return config_file


@pytest.fixture
def tmp_cursor_config(tmp_path: Path) -> Path:
    """Create a fake ~/.cursor/mcp.json with network servers."""
    cursor_dir = tmp_path / ".cursor"
    cursor_dir.mkdir()
    config_file = cursor_dir / "mcp.json"
    config_file.write_text(
        json.dumps({"mcpServers": SAMPLE_NETWORK_SERVERS}),
        encoding="utf-8",
    )
    return config_file


@pytest.fixture
def tmp_project_config(tmp_path: Path) -> Path:
    """Create a project-level .mcp.json (top-level, no wrapper key)."""
    config_file = tmp_path / ".mcp.json"
    config_file.write_text(
        json.dumps(SAMPLE_MIXED_SERVERS),
        encoding="utf-8",
    )
    return config_file


@pytest.fixture
def tmp_multi_ide(tmp_path: Path) -> Path:
    """Create config files for multiple IDEs with overlapping servers.

    Returns the base directory (simulating ~/).
    """
    # Claude Code global
    claude_config = tmp_path / ".claude.json"
    claude_config.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "filesystem": SAMPLE_STDIO_SERVERS["filesystem"],
                    "github": SAMPLE_STDIO_SERVERS["github"],
                }
            }
        ),
        encoding="utf-8",
    )

    # Cursor
    cursor_dir = tmp_path / ".cursor"
    cursor_dir.mkdir()
    cursor_config = cursor_dir / "mcp.json"
    cursor_config.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "filesystem": SAMPLE_STDIO_SERVERS["filesystem"],
                    "slack": SAMPLE_NETWORK_SERVERS["slack"],
                }
            }
        ),
        encoding="utf-8",
    )

    return tmp_path
