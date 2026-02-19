"""Tests for mcp_manager.health."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

import httpx

from mcp_manager.health import HealthChecker
from mcp_manager.models import (
    HealthResult,
    McpServer,
    NetworkConfig,
    ServerStatus,
    StdioConfig,
    TransportType,
)


def _make_stdio(name: str = "test-stdio") -> McpServer:
    return McpServer(
        name=name,
        transport=TransportType.STDIO,
        stdio_config=StdioConfig(command="echo", args=["hello"]),
    )


def _make_http(name: str = "test-http", url: str = "https://mcp.example.com/mcp") -> McpServer:
    return McpServer(
        name=name,
        transport=TransportType.HTTP,
        network_config=NetworkConfig(type="http", url=url),
    )


def _make_sse(name: str = "test-sse", url: str = "https://mcp.example.com/sse") -> McpServer:
    return McpServer(
        name=name,
        transport=TransportType.SSE,
        network_config=NetworkConfig(type="sse", url=url),
    )


def _init_response() -> bytes:
    return (
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {"name": "test-server", "version": "1.0.0"},
                    "capabilities": {},
                },
            }
        ).encode()
        + b"\n"
    )


def _ping_response() -> bytes:
    return json.dumps({"jsonrpc": "2.0", "id": 2, "result": {}}).encode() + b"\n"


class TestHealthCheckerHTTP:
    def test_healthy_http(self) -> None:
        checker = HealthChecker(timeout=5)
        server = _make_http()

        mock_response = httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {"name": "test", "version": "1.0"},
                    "capabilities": {},
                },
            },
        )

        with patch("mcp_manager.health.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = asyncio.run(checker.check(server))

        assert result.status == ServerStatus.HEALTHY
        assert result.latency_ms is not None
        assert result.server_info.get("server_name") == "test"

    def test_connection_refused(self) -> None:
        checker = HealthChecker(timeout=5)
        server = _make_http()

        with patch("mcp_manager.health.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.side_effect = httpx.ConnectError("refused")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = asyncio.run(checker.check(server))

        assert result.status == ServerStatus.UNREACHABLE
        assert "refused" in (result.error_message or "")

    def test_timeout(self) -> None:
        checker = HealthChecker(timeout=5)
        server = _make_http()

        with patch("mcp_manager.health.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.side_effect = httpx.TimeoutException("timeout")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = asyncio.run(checker.check(server))

        assert result.status == ServerStatus.UNREACHABLE

    def test_http_error_status(self) -> None:
        checker = HealthChecker(timeout=5)
        server = _make_http()

        mock_response = httpx.Response(500, text="Internal Server Error")

        with patch("mcp_manager.health.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = asyncio.run(checker.check(server))

        assert result.status == ServerStatus.ERROR
        assert "500" in (result.error_message or "")


class TestHealthCheckerSSE:
    def test_healthy_sse(self) -> None:
        checker = HealthChecker(timeout=5)
        server = _make_sse()

        mock_response = httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
        )

        with patch("mcp_manager.health.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = asyncio.run(checker.check(server))

        assert result.status == ServerStatus.HEALTHY
        assert result.latency_ms is not None

    def test_wrong_content_type_is_degraded(self) -> None:
        checker = HealthChecker(timeout=5)
        server = _make_sse()

        mock_response = httpx.Response(
            200,
            headers={"content-type": "text/html"},
        )

        with patch("mcp_manager.health.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = asyncio.run(checker.check(server))

        assert result.status == ServerStatus.DEGRADED


class TestHealthCheckerStdio:
    def test_command_not_found(self) -> None:
        checker = HealthChecker(timeout=5)
        server = McpServer(
            name="bad",
            transport=TransportType.STDIO,
            stdio_config=StdioConfig(command="nonexistent_command_xyz_12345"),
        )

        result = asyncio.run(checker.check(server))
        assert result.status == ServerStatus.UNREACHABLE
        assert "not found" in (result.error_message or "").lower()

    def test_no_stdio_config(self) -> None:
        checker = HealthChecker(timeout=5)
        server = McpServer(name="bad", transport=TransportType.STDIO)

        result = asyncio.run(checker.check(server))
        assert result.status == ServerStatus.ERROR

    def test_no_network_config_http(self) -> None:
        checker = HealthChecker(timeout=5)
        server = McpServer(name="bad", transport=TransportType.HTTP)

        result = asyncio.run(checker.check(server))
        assert result.status == ServerStatus.ERROR

    def test_no_network_config_sse(self) -> None:
        checker = HealthChecker(timeout=5)
        server = McpServer(name="bad", transport=TransportType.SSE)

        result = asyncio.run(checker.check(server))
        assert result.status == ServerStatus.ERROR


class TestCheckAll:
    def test_parallel_execution(self) -> None:
        checker = HealthChecker(timeout=5)
        servers = [_make_http("s1"), _make_http("s2")]

        mock_response = httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "result": {"protocolVersion": "2024-11-05", "capabilities": {}},
            },
        )

        with patch("mcp_manager.health.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            results = asyncio.run(checker.check_all(servers))

        assert len(results) == 2
        assert all(isinstance(r, HealthResult) for r in results)

    def test_empty_servers(self) -> None:
        checker = HealthChecker(timeout=5)
        results = asyncio.run(checker.check_all([]))
        assert results == []
