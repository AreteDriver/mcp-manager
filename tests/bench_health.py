"""Benchmarks for health check operations."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import httpx

from mcp_manager.health import HealthChecker
from mcp_manager.models import (
    McpServer,
    NetworkConfig,
    ServerStatus,
    StdioConfig,
    TransportType,
)


def _make_stdio_servers(n: int) -> list[McpServer]:
    return [
        McpServer(
            name=f"stdio-{i}",
            transport=TransportType.STDIO,
            stdio_config=StdioConfig(command="echo", args=["hello"]),
        )
        for i in range(n)
    ]


def _make_http_servers(n: int) -> list[McpServer]:
    return [
        McpServer(
            name=f"http-{i}",
            transport=TransportType.HTTP,
            network_config=NetworkConfig(
                type="http",
                url=f"https://mcp{i}.example.com/mcp",
            ),
        )
        for i in range(n)
    ]


def test_bench_check_stdio_unreachable(benchmark) -> None:
    """Benchmark stdio check when command is missing (fast path)."""
    checker = HealthChecker(timeout=5)
    server = McpServer(
        name="missing",
        transport=TransportType.STDIO,
        stdio_config=StdioConfig(command="/does/not/exist"),
    )

    def _run() -> ServerStatus:
        return asyncio.run(checker.check(server)).status

    result = benchmark(_run)
    assert result == ServerStatus.UNREACHABLE


def test_bench_check_http_healthy(benchmark) -> None:
    """Benchmark HTTP check with mocked healthy response."""
    checker = HealthChecker(timeout=5)
    server = _make_http_servers(1)[0]

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

    def _run() -> ServerStatus:
        with patch("mcp_manager.health.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client
            return asyncio.run(checker.check(server)).status

    result = benchmark(_run)
    assert result == ServerStatus.HEALTHY


def test_bench_check_all_10_http(benchmark) -> None:
    """Benchmark concurrent health check for 10 HTTP servers."""
    checker = HealthChecker(timeout=5)
    servers = _make_http_servers(10)

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

    def _run() -> list[ServerStatus]:
        with patch("mcp_manager.health.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client
            results = asyncio.run(checker.check_all(servers))
            return [r.status for r in results]

    statuses = benchmark(_run)
    assert all(s == ServerStatus.HEALTHY for s in statuses)
