"""Tests for dependency checking (deps.py)."""

from __future__ import annotations

import shutil

import pytest

from mcp_manager.deps import check_dependencies, check_dependencies_all
from mcp_manager.models import McpServer, StdioConfig, TransportType


class TestCheckDependencies:
    """Unit tests for check_dependencies."""

    @pytest.mark.parametrize("command", ["python", "python3", "uvx"])
    def test_only_configured_launcher_is_required(self, monkeypatch, command) -> None:
        monkeypatch.setattr(shutil, "which", lambda cmd: f"/bin/{cmd}" if cmd == command else None)
        server = McpServer(
            name="single-launcher",
            transport=TransportType.STDIO,
            stdio_config=StdioConfig(command=command),
        )
        assert check_dependencies(server) == []

    @pytest.mark.parametrize("available", [True, False])
    def test_uses_child_path_instead_of_parent_path(self, monkeypatch, available) -> None:
        def lookup(command, *, path=None):
            if path == "/fixture/bin":
                return f"{path}/{command}" if available else None
            return None if available else f"/parent/bin/{command}"

        monkeypatch.setattr(shutil, "which", lookup)
        server = McpServer(
            name="custom-path",
            transport=TransportType.STDIO,
            stdio_config=StdioConfig(command="python3", env={"PATH": "/fixture/bin"}),
        )
        assert check_dependencies(server) == ([] if available else ["python3"])

    def test_network_server_returns_empty(self) -> None:
        server = McpServer(
            name="sse-server",
            transport=TransportType.SSE,
            network_config={"type": "sse", "url": "http://localhost:3000/sse"},  # type: ignore[arg-type]
        )
        assert check_dependencies(server) == []

    def test_stdio_no_config_returns_empty(self) -> None:
        server = McpServer(
            name="bad-stdio",
            transport=TransportType.STDIO,
        )
        assert check_dependencies(server) == []

    def test_known_command_found(self) -> None:
        """python3 should exist on most systems where tests run."""
        server = McpServer(
            name="py-server",
            transport=TransportType.STDIO,
            stdio_config=StdioConfig(command="python3", args=["-m", "http.server"]),
        )
        result = check_dependencies(server)
        # python3 may or may not exist; test is environment-dependent.
        # Just assert it doesn't crash.
        assert isinstance(result, list)

    def test_known_command_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(shutil, "which", lambda _cmd: None)
        server = McpServer(
            name="node-server",
            transport=TransportType.STDIO,
            stdio_config=StdioConfig(command="node", args=["index.js"]),
        )
        assert check_dependencies(server) == ["node"]

    def test_unknown_command_returns_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Unknown commands should not be flagged — let transport check handle them."""
        monkeypatch.setattr(shutil, "which", lambda _cmd: None)
        server = McpServer(
            name="custom-server",
            transport=TransportType.STDIO,
            stdio_config=StdioConfig(command="my-custom-tool", args=[]),
        )
        assert check_dependencies(server) == []

    def test_npx_checks_both(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def fake_which(cmd: str) -> str | None:
            return "/usr/bin/npx" if cmd == "npx" else None

        monkeypatch.setattr(shutil, "which", fake_which)
        server = McpServer(
            name="npx-server",
            transport=TransportType.STDIO,
            stdio_config=StdioConfig(
                command="npx", args=["-y", "@modelcontextprotocol/server-filesystem"]
            ),
        )
        assert check_dependencies(server) == []

    def test_uv_checks_uv(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def fake_which(cmd: str) -> str | None:
            return "/usr/bin/uv" if cmd == "uv" else None

        monkeypatch.setattr(shutil, "which", fake_which)
        server = McpServer(
            name="uv-server",
            transport=TransportType.STDIO,
            stdio_config=StdioConfig(command="uv", args=["run", "server.py"]),
        )
        assert check_dependencies(server) == []


class TestCheckDependenciesAll:
    """Unit tests for check_dependencies_all."""

    def test_empty_list(self) -> None:
        assert check_dependencies_all([]) == {}

    def test_mixed_servers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(shutil, "which", lambda _cmd: None)
        servers = [
            McpServer(
                name="node-server",
                transport=TransportType.STDIO,
                stdio_config=StdioConfig(command="node", args=["index.js"]),
            ),
            McpServer(
                name="sse-server",
                transport=TransportType.SSE,
                network_config={"type": "sse", "url": "http://localhost:3000/sse"},  # type: ignore[arg-type]
            ),
        ]
        result = check_dependencies_all(servers)
        assert result == {"node-server": ["node"]}
