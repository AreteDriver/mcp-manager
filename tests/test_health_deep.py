"""Additional tests for mcp_manager.health to cover deep checks and edge cases."""

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


class TestHealthCheckerDeep:
    """Tests for deep health check paths."""

    def test_deep_network_http_with_tools(self) -> None:
        """Deep check HTTP server returning tools."""
        checker = HealthChecker(timeout=5, deep=True)
        server = _make_http()

        init_response = httpx.Response(
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
        tools_response = httpx.Response(
            200,
            json={"jsonrpc": "2.0", "id": 3, "result": {"tools": [{"name": "tool1"}]}},
        )

        with patch("mcp_manager.health.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.side_effect = [init_response, tools_response]
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = asyncio.run(checker.check(server))

        assert result.status == ServerStatus.HEALTHY

    def test_deep_network_http_zero_tools(self) -> None:
        """Deep check HTTP server returning zero tools."""
        checker = HealthChecker(timeout=5, deep=True)
        server = _make_http()

        init_response = httpx.Response(
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
        tools_response = httpx.Response(
            200,
            json={"jsonrpc": "2.0", "id": 3, "result": {"tools": []}},
        )

        with patch("mcp_manager.health.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.side_effect = [init_response, tools_response]
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = asyncio.run(checker.check(server))

        assert result.status == ServerStatus.DEGRADED
        assert "zero tools" in (result.error_message or "").lower()

    def test_deep_network_http_tools_4xx(self) -> None:
        """Deep check HTTP server where tools/list returns 4xx."""
        checker = HealthChecker(timeout=5, deep=True)
        server = _make_http()

        init_response = httpx.Response(
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
        tools_response = httpx.Response(404, text="Not Found")

        with patch("mcp_manager.health.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.side_effect = [init_response, tools_response]
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = asyncio.run(checker.check(server))

        assert result.status == ServerStatus.DEGRADED
        assert "404" in (result.error_message or "")


class TestHealthCheckerStdioEdgeCases:
    """Edge cases for stdio transport health checks."""

    def test_stdio_os_error(self) -> None:
        """Stdio check raises OSError (e.g., permission denied)."""
        checker = HealthChecker(timeout=5)
        server = _make_stdio()

        with patch(
            "mcp_manager.health.asyncio.create_subprocess_exec",
            side_effect=OSError("Permission denied"),
        ):
            result = asyncio.run(checker.check(server))

        assert result.status == ServerStatus.UNREACHABLE
        assert "Permission denied" in (result.error_message or "")

    def test_stdio_timeout(self) -> None:
        """Stdio handshake times out."""
        checker = HealthChecker(timeout=5)
        server = _make_stdio()

        async def _slow_stdout() -> bytes:
            await asyncio.sleep(100)  # way longer than timeout
            return b""

        with patch("mcp_manager.health.asyncio.create_subprocess_exec") as mock_exec:
            proc = AsyncMock()
            proc.stdin = AsyncMock()
            proc.stdout = AsyncMock()
            proc.stdout.readline = AsyncMock(side_effect=_slow_stdout)
            mock_exec.return_value = proc

            result = asyncio.run(checker.check(server))

        assert result.status == ServerStatus.UNREACHABLE
        assert "timeout" in (result.error_message or "").lower()

    def test_stdio_no_response_to_initialize(self) -> None:
        """Stdio process exits without responding to initialize."""
        checker = HealthChecker(timeout=5)
        server = _make_stdio()

        with patch("mcp_manager.health.asyncio.create_subprocess_exec") as mock_exec:
            proc = AsyncMock()
            proc.stdin = AsyncMock()
            proc.stdin.write = lambda data: None
            proc.stdout = AsyncMock()
            proc.stdout.readline = AsyncMock(return_value=b"")
            mock_exec.return_value = proc

            result = asyncio.run(checker.check(server))

        assert result.status == ServerStatus.ERROR
        assert "no response to initialize" in (result.error_message or "").lower()

    def test_stdio_deep_file_not_found(self) -> None:
        """Deep check stdio with FileNotFoundError returns prev result unchanged."""
        checker = HealthChecker(timeout=5, deep=True)
        server = _make_stdio()

        with patch(
            "mcp_manager.health.asyncio.create_subprocess_exec",
            side_effect=FileNotFoundError("not found"),
        ):
            result = asyncio.run(checker.check(server))

        # Should fall through to prev result (which was UNREACHABLE from _check_stdio)
        assert result.status == ServerStatus.UNREACHABLE


class TestHealthCheckerHTTPEdgeCases:
    """Edge cases for HTTP transport health checks."""

    def test_http_invalid_jsonrpc(self) -> None:
        """HTTP server returns 200 but body is not valid JSON-RPC."""
        checker = HealthChecker(timeout=5)
        server = _make_http()

        mock_response = httpx.Response(200, text="not json")

        with patch("mcp_manager.health.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = asyncio.run(checker.check(server))

        assert result.status == ServerStatus.DEGRADED
        assert "invalid JSON-RPC" in (result.error_message or "")


class TestHealthCheckerMissingDeps:
    """Tests for dependency validation in health checks."""

    def test_missing_dependencies(self) -> None:
        """Server with missing dependencies returns ERROR before transport check."""
        checker = HealthChecker(timeout=5)
        server = McpServer(
            name="missing-docker",
            transport=TransportType.STDIO,
            stdio_config=StdioConfig(command="docker", args=["run", "hello"]),
        )

        with patch("mcp_manager.deps.shutil.which", return_value=None):
            result = asyncio.run(checker.check(server))

        assert result.status == ServerStatus.ERROR
        assert "missing dependencies" in (result.error_message or "").lower()


class TestHealthCheckerDeepCheckSkips:
    """Tests for deep check skip conditions."""

    def test_deep_check_skips_on_error_status(self) -> None:
        """Deep check is skipped if basic check already returned ERROR."""
        checker = HealthChecker(timeout=5, deep=True)
        server = McpServer(name="bad", transport=TransportType.STDIO)

        result = asyncio.run(checker.check(server))
        # No stdio config = ERROR, deep check should be skipped
        assert result.status == ServerStatus.ERROR
        assert result.error_message == "No stdio config"
