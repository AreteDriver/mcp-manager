"""Tests for mcp_manager.discovery."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from mcp_manager.discovery import ConfigDiscovery
from mcp_manager.models import TransportType
from tests.conftest import SAMPLE_NETWORK_SERVERS, SAMPLE_STDIO_SERVERS


class TestClassifyTransport:
    def setup_method(self) -> None:
        self.discovery = ConfigDiscovery()

    def test_command_is_stdio(self) -> None:
        assert self.discovery._classify_transport({"command": "npx"}) == TransportType.STDIO

    def test_type_sse(self) -> None:
        result = self.discovery._classify_transport({"type": "sse", "url": "https://example.com"})
        assert result == TransportType.SSE

    def test_type_http(self) -> None:
        result = self.discovery._classify_transport({"type": "http", "url": "https://example.com"})
        assert result == TransportType.HTTP

    def test_url_without_type_defaults_sse(self) -> None:
        result = self.discovery._classify_transport({"url": "https://example.com"})
        assert result == TransportType.SSE

    def test_empty_defaults_stdio(self) -> None:
        assert self.discovery._classify_transport({}) == TransportType.STDIO

    def test_command_takes_priority_over_type(self) -> None:
        result = self.discovery._classify_transport(
            {"command": "npx", "type": "sse", "url": "https://x.com"}
        )
        assert result == TransportType.STDIO


class TestScanConfig:
    def setup_method(self) -> None:
        self.discovery = ConfigDiscovery()

    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        result = self.discovery._scan_config("test", tmp_path / "nope.json", "mcpServers")
        assert result == []

    def test_invalid_json_returns_empty(self, tmp_path: Path) -> None:
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("{invalid json", encoding="utf-8")
        result = self.discovery._scan_config("test", bad_file, "mcpServers")
        assert result == []

    def test_non_dict_root_returns_empty(self, tmp_path: Path) -> None:
        f = tmp_path / "list.json"
        f.write_text("[1, 2, 3]", encoding="utf-8")
        result = self.discovery._scan_config("test", f, "mcpServers")
        assert result == []

    def test_missing_wrapper_key_returns_empty(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.json"
        f.write_text(json.dumps({"other": "stuff"}), encoding="utf-8")
        result = self.discovery._scan_config("test", f, "mcpServers")
        assert result == []

    def test_parses_stdio_servers(self, tmp_claude_config: Path) -> None:
        result = self.discovery._scan_config("claude-code", tmp_claude_config, "mcpServers")
        assert len(result) == 2
        names = {s.name for s in result}
        assert names == {"filesystem", "github"}
        for s in result:
            assert s.transport == TransportType.STDIO
            assert s.stdio_config is not None
            assert s.source_tool == "claude-code"

    def test_parses_network_servers(self, tmp_cursor_config: Path) -> None:
        config_file = tmp_cursor_config
        result = self.discovery._scan_config("cursor", config_file, "mcpServers")
        assert len(result) == 2
        names = {s.name for s in result}
        assert names == {"slack", "asana"}

        slack = next(s for s in result if s.name == "slack")
        assert slack.transport == TransportType.HTTP
        assert slack.network_config is not None
        assert slack.network_config.url == "https://mcp.slack.com/mcp"

        asana = next(s for s in result if s.name == "asana")
        assert asana.transport == TransportType.SSE

    def test_no_wrapper_key_parses_top_level(self, tmp_project_config: Path) -> None:
        result = self.discovery._scan_config("project", tmp_project_config, None)
        assert len(result) == 4
        names = {s.name for s in result}
        assert names == {"filesystem", "github", "slack", "asana"}


class TestScanProjectConfigs:
    def setup_method(self) -> None:
        self.discovery = ConfigDiscovery()

    def test_finds_project_config(self, tmp_path: Path) -> None:
        config = tmp_path / ".mcp.json"
        config.write_text(json.dumps(SAMPLE_STDIO_SERVERS), encoding="utf-8")

        result = self.discovery._scan_project_configs(tmp_path)
        assert len(result) == 2

    def test_walks_parents(self, tmp_path: Path) -> None:
        config = tmp_path / ".mcp.json"
        config.write_text(json.dumps({"test": {"command": "echo"}}), encoding="utf-8")

        child = tmp_path / "src" / "app"
        child.mkdir(parents=True)

        result = self.discovery._scan_project_configs(child)
        assert len(result) == 1
        assert result[0].name == "test"

    def test_no_config_returns_empty(self, tmp_path: Path) -> None:
        result = self.discovery._scan_project_configs(tmp_path)
        assert result == []


class TestDiscoverAll:
    def setup_method(self) -> None:
        self.discovery = ConfigDiscovery()

    def test_with_patched_paths(self, tmp_path: Path) -> None:
        """Patch IDE_CONFIG_PATHS to point at temp files."""
        claude_config = tmp_path / "claude.json"
        claude_config.write_text(
            json.dumps({"mcpServers": SAMPLE_STDIO_SERVERS}),
            encoding="utf-8",
        )

        cursor_config = tmp_path / "cursor.json"
        cursor_config.write_text(
            json.dumps({"mcpServers": SAMPLE_NETWORK_SERVERS}),
            encoding="utf-8",
        )

        patched_paths = [
            ("claude-code", str(claude_config), "mcpServers"),
            ("cursor", str(cursor_config), "mcpServers"),
        ]

        with patch("mcp_manager.discovery.IDE_CONFIG_PATHS", patched_paths):
            result = self.discovery.discover_all()

        assert len(result) == 4
        tools = {s.source_tool for s in result}
        assert tools == {"claude-code", "cursor"}

    def test_includes_project_config(self, tmp_path: Path) -> None:
        project_config = tmp_path / ".mcp.json"
        project_config.write_text(
            json.dumps({"local-server": {"command": "python", "args": ["server.py"]}}),
            encoding="utf-8",
        )

        with patch("mcp_manager.discovery.IDE_CONFIG_PATHS", []):
            result = self.discovery.discover_all(project_dir=tmp_path)

        assert len(result) == 1
        assert result[0].name == "local-server"
        assert result[0].source_tool == "project"


class TestBuildServer:
    def setup_method(self) -> None:
        self.discovery = ConfigDiscovery()

    def test_stdio_server(self, tmp_path: Path) -> None:
        server = self.discovery._build_server(
            "test",
            {"command": "npx", "args": ["-y", "server"], "env": {"KEY": "val"}},
            "claude-code",
            tmp_path / "config.json",
        )
        assert server.name == "test"
        assert server.transport == TransportType.STDIO
        assert server.stdio_config is not None
        assert server.stdio_config.command == "npx"
        assert server.stdio_config.args == ["-y", "server"]
        assert server.stdio_config.env == {"KEY": "val"}

    def test_http_server(self, tmp_path: Path) -> None:
        server = self.discovery._build_server(
            "slack",
            {"type": "http", "url": "https://mcp.slack.com/mcp"},
            "cursor",
            tmp_path / "config.json",
        )
        assert server.transport == TransportType.HTTP
        assert server.network_config is not None
        assert server.network_config.url == "https://mcp.slack.com/mcp"

    def test_stdio_no_command_raises(self, tmp_path: Path) -> None:
        from mcp_manager.exceptions import DiscoveryError

        with pytest.raises(DiscoveryError, match="no command"):
            self.discovery._build_server("bad", {}, "test", tmp_path / "config.json")

    def test_network_no_url_raises(self, tmp_path: Path) -> None:
        from mcp_manager.exceptions import DiscoveryError

        with pytest.raises(DiscoveryError, match="no url"):
            self.discovery._build_server("bad", {"type": "http"}, "test", tmp_path / "config.json")


class TestDiscoverTool:
    def setup_method(self) -> None:
        self.discovery = ConfigDiscovery()

    def test_unknown_tool_returns_empty(self) -> None:
        result = self.discovery.discover_tool("nonexistent")
        assert result == []
