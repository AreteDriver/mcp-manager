"""Tests for mcp_manager.models."""

from __future__ import annotations

from pathlib import Path

from mcp_manager.models import (
    ExportConfig,
    HealthResult,
    McpServer,
    NetworkConfig,
    RegistryEntry,
    ServerMapping,
    ServerStatus,
    StdioConfig,
    TransportType,
)


class TestTransportType:
    def test_values(self) -> None:
        assert TransportType.STDIO == "stdio"
        assert TransportType.SSE == "sse"
        assert TransportType.HTTP == "http"

    def test_from_string(self) -> None:
        assert TransportType("stdio") is TransportType.STDIO
        assert TransportType("sse") is TransportType.SSE


class TestServerStatus:
    def test_values(self) -> None:
        assert ServerStatus.HEALTHY == "healthy"
        assert ServerStatus.DEGRADED == "degraded"
        assert ServerStatus.UNREACHABLE == "unreachable"
        assert ServerStatus.UNKNOWN == "unknown"
        assert ServerStatus.ERROR == "error"


class TestStdioConfig:
    def test_minimal(self) -> None:
        cfg = StdioConfig(command="npx")
        assert cfg.command == "npx"
        assert cfg.args == []
        assert cfg.env == {}

    def test_full(self) -> None:
        cfg = StdioConfig(
            command="node",
            args=["server.js", "--port", "3000"],
            env={"NODE_ENV": "production"},
        )
        assert cfg.command == "node"
        assert len(cfg.args) == 3
        assert cfg.env["NODE_ENV"] == "production"


class TestNetworkConfig:
    def test_sse(self) -> None:
        cfg = NetworkConfig(type="sse", url="https://mcp.example.com/sse")
        assert cfg.type == "sse"
        assert cfg.url == "https://mcp.example.com/sse"
        assert cfg.headers == {}

    def test_http_with_headers(self) -> None:
        cfg = NetworkConfig(
            type="http",
            url="https://api.example.com/mcp",
            headers={"Authorization": "Bearer token123"},
        )
        assert cfg.type == "http"
        assert "Authorization" in cfg.headers


class TestMcpServer:
    def test_stdio_server(self) -> None:
        server = McpServer(
            name="filesystem",
            transport=TransportType.STDIO,
            stdio_config=StdioConfig(
                command="npx",
                args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
            ),
            source_tool="claude-code",
            source_path=Path("~/.claude.json"),
        )
        assert server.name == "filesystem"
        assert server.transport == TransportType.STDIO
        assert server.stdio_config is not None
        assert server.network_config is None
        assert server.source_tool == "claude-code"

    def test_http_server(self) -> None:
        server = McpServer(
            name="slack",
            transport=TransportType.HTTP,
            network_config=NetworkConfig(
                type="http",
                url="https://mcp.slack.com/mcp",
            ),
            source_tool="cursor",
        )
        assert server.name == "slack"
        assert server.transport == TransportType.HTTP
        assert server.network_config is not None
        assert server.stdio_config is None

    def test_defaults(self) -> None:
        server = McpServer(name="test", transport=TransportType.STDIO)
        assert server.tags == []
        assert server.description == ""
        assert server.source_tool == ""
        assert server.source_path is None

    def test_serialization_round_trip(self) -> None:
        server = McpServer(
            name="test",
            transport=TransportType.SSE,
            network_config=NetworkConfig(type="sse", url="https://example.com/sse"),
            tags=["prod", "slack"],
            description="Slack integration",
        )
        data = server.model_dump()
        restored = McpServer.model_validate(data)
        assert restored.name == server.name
        assert restored.transport == server.transport
        assert restored.network_config == server.network_config
        assert restored.tags == server.tags


class TestHealthResult:
    def test_healthy(self) -> None:
        result = HealthResult(
            server_name="test",
            status=ServerStatus.HEALTHY,
            latency_ms=45.2,
            transport=TransportType.STDIO,
            protocol_version="2024-11-05",
        )
        assert result.status == ServerStatus.HEALTHY
        assert result.latency_ms == 45.2
        assert result.error_message is None
        assert result.checked_at > 0

    def test_unreachable(self) -> None:
        result = HealthResult(
            server_name="test",
            status=ServerStatus.UNREACHABLE,
            transport=TransportType.HTTP,
            error_message="Connection refused",
        )
        assert result.status == ServerStatus.UNREACHABLE
        assert result.latency_ms is None
        assert result.error_message == "Connection refused"


class TestServerMapping:
    def test_multi_tool(self) -> None:
        mapping = ServerMapping(
            server_name="github",
            transport=TransportType.STDIO,
            tools=["claude-code", "cursor"],
            config_paths=["~/.claude.json", "~/.cursor/mcp.json"],
        )
        assert len(mapping.tools) == 2
        assert "claude-code" in mapping.tools


class TestRegistryEntry:
    def test_creation(self) -> None:
        server = McpServer(name="test", transport=TransportType.STDIO)
        entry = RegistryEntry(server=server)
        assert entry.added_at > 0
        assert entry.last_health is None


class TestExportConfig:
    def test_defaults(self) -> None:
        config = ExportConfig(servers={"test": {"command": "echo"}})
        assert config.version == "1"
        assert config.metadata == {}
        assert "test" in config.servers
