"""Tests for mcp_manager.cli."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from mcp_manager import __version__
from mcp_manager.cli import app
from mcp_manager.models import McpServer, NetworkConfig, StdioConfig, TransportType

runner = CliRunner()


def _sample_servers() -> list[McpServer]:
    """Return a small set of servers for CLI tests."""
    return [
        McpServer(
            name="filesystem",
            transport=TransportType.STDIO,
            stdio_config=StdioConfig(command="npx", args=["-y", "server-fs"]),
            source_tool="claude-code",
            source_path=Path("/home/test/.claude.json"),
        ),
        McpServer(
            name="slack",
            transport=TransportType.HTTP,
            network_config=NetworkConfig(type="http", url="https://mcp.slack.com/mcp"),
            source_tool="cursor",
            source_path=Path("/home/test/.cursor/mcp.json"),
        ),
    ]


class TestVersion:
    def test_version_flag(self) -> None:
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert __version__ in result.output

    def test_short_version_flag(self) -> None:
        result = runner.invoke(app, ["-V"])
        assert result.exit_code == 0
        assert __version__ in result.output


class TestNoArgs:
    def test_shows_help(self) -> None:
        result = runner.invoke(app, [])
        assert result.exit_code == 0
        assert "Manage MCP servers" in result.output


class TestListCommand:
    def test_list_no_servers(self) -> None:
        with patch("mcp_manager.cli._discover", return_value=[]):
            result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "No MCP servers found" in result.output

    def test_list_shows_table(self) -> None:
        with patch("mcp_manager.cli._discover", return_value=_sample_servers()):
            result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "filesystem" in result.output
        assert "slack" in result.output
        assert "claude-code" in result.output
        assert "cursor" in result.output

    def test_list_filter_transport(self) -> None:
        with patch("mcp_manager.cli._discover", return_value=_sample_servers()):
            result = runner.invoke(app, ["list", "--transport", "http"])
        assert result.exit_code == 0
        assert "slack" in result.output
        assert "filesystem" not in result.output

    def test_list_invalid_transport(self) -> None:
        with patch("mcp_manager.cli._discover", return_value=_sample_servers()):
            result = runner.invoke(app, ["list", "--transport", "invalid"])
        assert result.exit_code == 1
        assert "Unknown transport" in result.output

    def test_list_json_output(self) -> None:
        with patch("mcp_manager.cli._discover", return_value=_sample_servers()):
            result = runner.invoke(app, ["list", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 2
        names = {s["name"] for s in data}
        assert names == {"filesystem", "slack"}


class TestMapCommand:
    def test_map_no_servers(self) -> None:
        with patch("mcp_manager.cli._discover", return_value=[]):
            result = runner.invoke(app, ["map"])
        assert result.exit_code == 0
        assert "No MCP servers found" in result.output

    def test_map_shows_table(self) -> None:
        with patch("mcp_manager.cli._discover", return_value=_sample_servers()):
            result = runner.invoke(app, ["map"])
        assert result.exit_code == 0
        assert "filesystem" in result.output
        assert "slack" in result.output

    def test_map_json_output(self) -> None:
        with patch("mcp_manager.cli._discover", return_value=_sample_servers()):
            result = runner.invoke(app, ["map", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
