"""Tests for mcp_manager.mapper."""

from __future__ import annotations

from pathlib import Path

from mcp_manager.mapper import _server_identity, build_server_map
from mcp_manager.models import McpServer, NetworkConfig, StdioConfig, TransportType


def _make_stdio(name: str, command: str, args: list[str], tool: str) -> McpServer:
    return McpServer(
        name=name,
        transport=TransportType.STDIO,
        stdio_config=StdioConfig(command=command, args=args),
        source_tool=tool,
        source_path=Path(f"/fake/{tool}.json"),
    )


def _make_http(name: str, url: str, tool: str) -> McpServer:
    return McpServer(
        name=name,
        transport=TransportType.HTTP,
        network_config=NetworkConfig(type="http", url=url),
        source_tool=tool,
        source_path=Path(f"/fake/{tool}.json"),
    )


class TestServerIdentity:
    def test_stdio_identity(self) -> None:
        s = _make_stdio("fs", "npx", ["-y", "server"], "claude")
        assert _server_identity(s) == "stdio:npx -y server"

    def test_http_identity(self) -> None:
        s = _make_http("slack", "https://mcp.slack.com/mcp", "cursor")
        assert _server_identity(s) == "http:https://mcp.slack.com/mcp"

    def test_same_command_same_identity(self) -> None:
        s1 = _make_stdio("fs", "npx", ["-y", "server"], "claude")
        s2 = _make_stdio("filesystem", "npx", ["-y", "server"], "cursor")
        assert _server_identity(s1) == _server_identity(s2)

    def test_different_command_different_identity(self) -> None:
        s1 = _make_stdio("a", "npx", ["-y", "server-a"], "claude")
        s2 = _make_stdio("b", "npx", ["-y", "server-b"], "claude")
        assert _server_identity(s1) != _server_identity(s2)


class TestBuildServerMap:
    def test_groups_same_server_across_tools(self) -> None:
        servers = [
            _make_stdio("filesystem", "npx", ["-y", "fs-server"], "claude-code"),
            _make_stdio("filesystem", "npx", ["-y", "fs-server"], "cursor"),
        ]
        mappings = build_server_map(servers)
        assert len(mappings) == 1
        assert set(mappings[0].tools) == {"claude-code", "cursor"}

    def test_different_servers_stay_separate(self) -> None:
        servers = [
            _make_stdio("filesystem", "npx", ["-y", "fs-server"], "claude-code"),
            _make_http("slack", "https://mcp.slack.com/mcp", "cursor"),
        ]
        mappings = build_server_map(servers)
        assert len(mappings) == 2

    def test_empty_input(self) -> None:
        assert build_server_map([]) == []

    def test_sorted_by_name(self) -> None:
        servers = [
            _make_http("z-server", "https://z.com", "claude"),
            _make_http("a-server", "https://a.com", "claude"),
        ]
        mappings = build_server_map(servers)
        assert mappings[0].server_name == "a-server"
        assert mappings[1].server_name == "z-server"
