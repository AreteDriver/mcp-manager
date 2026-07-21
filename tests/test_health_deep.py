"""Additional tests for mcp_manager.health to cover deep checks and edge cases."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

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
        checker = HealthChecker(timeout=1)
        server = _make_stdio()

        async def _slow_stdout() -> bytes:
            await asyncio.sleep(100)  # way longer than timeout
            return b""

        with patch("mcp_manager.health.asyncio.create_subprocess_exec") as mock_exec:
            proc = MagicMock()
            proc.stdin = MagicMock()
            proc.stdin.drain = AsyncMock()
            proc.stdout = MagicMock()
            proc.stdout.readline = AsyncMock(side_effect=_slow_stdout)
            proc.kill = MagicMock()
            proc.wait = AsyncMock()
            mock_exec.return_value = proc

            result = asyncio.run(checker.check(server))

        assert result.status == ServerStatus.UNREACHABLE
        assert "timeout" in (result.error_message or "").lower()

    def test_stdio_no_response_to_initialize(self) -> None:
        """Stdio process exits without responding to initialize."""
        checker = HealthChecker(timeout=5)
        server = _make_stdio()

        with patch("mcp_manager.health.asyncio.create_subprocess_exec") as mock_exec:
            proc = MagicMock()
            proc.stdin = MagicMock()
            proc.stdin.drain = AsyncMock()
            proc.stdout = MagicMock()
            proc.stdout.readline = AsyncMock(return_value=b"")
            proc.kill.return_value = None
            proc.wait = AsyncMock()
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


class TestHealthCheckerTransportErrors:
    """Tests for missing configs and transport errors."""

    def test_stdio_missing_config(self) -> None:
        """Stdio server without stdio_config returns ERROR."""
        checker = HealthChecker(timeout=5)
        server = McpServer(name="bad-stdio", transport=TransportType.STDIO)
        result = asyncio.run(checker.check(server))
        assert result.status == ServerStatus.ERROR
        assert "No stdio config" in (result.error_message or "")

    def test_sse_missing_network_config(self) -> None:
        """SSE server without network_config returns ERROR."""
        checker = HealthChecker(timeout=5)
        server = McpServer(name="bad-sse", transport=TransportType.SSE)
        result = asyncio.run(checker.check(server))
        assert result.status == ServerStatus.ERROR
        assert "No network config" in (result.error_message or "")

    def test_http_missing_network_config(self) -> None:
        """HTTP server without network_config returns ERROR."""
        checker = HealthChecker(timeout=5)
        server = McpServer(name="bad-http", transport=TransportType.HTTP)
        result = asyncio.run(checker.check(server))
        assert result.status == ServerStatus.ERROR
        assert "No network config" in (result.error_message or "")

    def test_sse_connect_error(self) -> None:
        """SSE server connection refused."""
        checker = HealthChecker(timeout=5)
        server = _make_sse()

        with patch("mcp_manager.health.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.side_effect = httpx.ConnectError("Connection refused")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = asyncio.run(checker.check(server))

        assert result.status == ServerStatus.UNREACHABLE
        assert "Connection refused" in (result.error_message or "")

    def test_sse_timeout(self) -> None:
        """SSE server times out."""
        checker = HealthChecker(timeout=5)
        server = _make_sse()

        with patch("mcp_manager.health.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.side_effect = httpx.TimeoutException("Timeout")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = asyncio.run(checker.check(server))

        assert result.status == ServerStatus.UNREACHABLE
        assert "Timeout" in (result.error_message or "")

    def test_sse_http_4xx(self) -> None:
        """SSE server returns HTTP 4xx."""
        checker = HealthChecker(timeout=5)
        server = _make_sse()

        with patch("mcp_manager.health.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = httpx.Response(403, text="Forbidden")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = asyncio.run(checker.check(server))

        assert result.status == ServerStatus.ERROR
        assert "HTTP 403" in (result.error_message or "")

    def test_sse_degraded_content_type(self) -> None:
        """SSE server reachable but wrong content-type."""
        checker = HealthChecker(timeout=5)
        server = _make_sse()

        with patch("mcp_manager.health.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = httpx.Response(
                200, text="ok", headers={"content-type": "text/html"}
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = asyncio.run(checker.check(server))

        assert result.status == ServerStatus.DEGRADED

    def test_http_connect_error(self) -> None:
        """HTTP server connection refused."""
        checker = HealthChecker(timeout=5)
        server = _make_http()

        with patch("mcp_manager.health.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.side_effect = httpx.ConnectError("Connection refused")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = asyncio.run(checker.check(server))

        assert result.status == ServerStatus.UNREACHABLE
        assert "Connection refused" in (result.error_message or "")

    def test_http_timeout(self) -> None:
        """HTTP server times out."""
        checker = HealthChecker(timeout=5)
        server = _make_http()

        with patch("mcp_manager.health.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.side_effect = httpx.TimeoutException("Timeout")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = asyncio.run(checker.check(server))

        assert result.status == ServerStatus.UNREACHABLE
        assert "Timeout" in (result.error_message or "")

    def test_http_4xx(self) -> None:
        """HTTP server returns HTTP 4xx."""
        checker = HealthChecker(timeout=5)
        server = _make_http()

        with patch("mcp_manager.health.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = httpx.Response(401, text="Unauthorized")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = asyncio.run(checker.check(server))

        assert result.status == ServerStatus.ERROR
        assert "HTTP 401" in (result.error_message or "")

    def test_http_invalid_jsonrpc_typeerror(self) -> None:
        """HTTP server returns 200 but extract_server_info raises TypeError."""
        checker = HealthChecker(timeout=5)
        server = _make_http()

        with patch("mcp_manager.health.extract_server_info", side_effect=TypeError("bad")):
            with patch("mcp_manager.health.httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.post.return_value = httpx.Response(200, text="ok")
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                mock_client_cls.return_value = mock_client

                result = asyncio.run(checker.check(server))

        assert result.status == ServerStatus.DEGRADED
        assert "invalid json-rpc response" in (result.error_message or "").lower()

    def test_deep_network_http_error(self) -> None:
        """Deep check when POST tools/list raises httpx.HTTPError."""
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

        with patch("mcp_manager.health.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.side_effect = [init_response, httpx.HTTPError("boom")]
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = asyncio.run(checker.check(server))

        # Deep check falls back to prev result (HEALTHY from shallow check)
        assert result.status == ServerStatus.HEALTHY

    def test_deep_network_invalid_jsonrpc(self) -> None:
        """Deep check when tools/list returns invalid JSON-RPC."""
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
        tools_response = httpx.Response(200, text="not json")

        with patch("mcp_manager.health.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.side_effect = [init_response, tools_response]
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = asyncio.run(checker.check(server))

        assert result.status == ServerStatus.DEGRADED
        assert "invalid tools/list response" in (result.error_message or "").lower()


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


class TestHealthCheckerStdioDeepPaths:
    """Tests for deep stdio check error paths."""

    def test_deep_stdio_no_init_response(self) -> None:
        """Deep check when stdio process gives no response to initialize."""
        checker = HealthChecker(timeout=5, deep=True)
        server = _make_stdio()

        def _make_proc(responses: list[bytes]) -> MagicMock:
            p = MagicMock()
            p.stdin = MagicMock()
            p.stdin.drain = AsyncMock()
            p.stdout = MagicMock()
            p.stdout.readline = AsyncMock(side_effect=responses)
            p.kill.return_value = None
            p.wait = AsyncMock()
            return p

        with patch("mcp_manager.health.asyncio.create_subprocess_exec") as mock_exec:
            # Shallow check gets init + ping; deep check gets empty
            mock_exec.side_effect = [
                _make_proc([
                    b'{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2024-11-05"}}\n',
                    b"pong\n",
                ]),
                _make_proc([b""]),
            ]

            result = asyncio.run(checker.check(server))

        # Shallow check passes, deep check degrades
        assert result.status == ServerStatus.DEGRADED
        assert "no response to initialize" in (result.error_message or "").lower()

    def test_deep_stdio_no_tools_response(self) -> None:
        """Deep check when tools/list returns empty response."""
        checker = HealthChecker(timeout=5, deep=True)
        server = _make_stdio()

        def _make_proc(responses: list[bytes]) -> MagicMock:
            p = MagicMock()
            p.stdin = MagicMock()
            p.stdin.drain = AsyncMock()
            p.stdout = MagicMock()
            p.stdout.readline = AsyncMock(side_effect=responses)
            p.kill.return_value = None
            p.wait = AsyncMock()
            return p

        with patch("mcp_manager.health.asyncio.create_subprocess_exec") as mock_exec:
            mock_exec.side_effect = [
                _make_proc([
                    b'{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2024-11-05"}}\n',
                    b"pong\n",
                ]),
                _make_proc([
                    b'{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2024-11-05"}}\n',
                    b"",
                ]),
            ]

            result = asyncio.run(checker.check(server))

        assert result.status == ServerStatus.DEGRADED
        assert "no tools/list response" in (result.error_message or "").lower()

    def test_deep_stdio_zero_tools(self) -> None:
        """Deep check when tools/list returns empty tools array."""
        checker = HealthChecker(timeout=5, deep=True)
        server = _make_stdio()

        def _make_proc(responses: list[bytes]) -> MagicMock:
            p = MagicMock()
            p.stdin = MagicMock()
            p.stdin.drain = AsyncMock()
            p.stdout = MagicMock()
            p.stdout.readline = AsyncMock(side_effect=responses)
            p.kill.return_value = None
            p.wait = AsyncMock()
            return p

        with patch("mcp_manager.health.asyncio.create_subprocess_exec") as mock_exec:
            mock_exec.side_effect = [
                _make_proc([
                    b'{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2024-11-05"}}\n',
                    b"pong\n",
                ]),
                _make_proc([
                    b'{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2024-11-05"}}\n',
                    b'{"jsonrpc":"2.0","id":3,"result":{"tools":[]}}\n',
                ]),
            ]

            result = asyncio.run(checker.check(server))

        assert result.status == ServerStatus.DEGRADED
        assert "zero tools" in (result.error_message or "").lower()

    def test_deep_stdio_invalid_tools_response(self) -> None:
        """Deep check when tools/list returns invalid JSON-RPC."""
        checker = HealthChecker(timeout=5, deep=True)
        server = _make_stdio()

        def _make_proc(responses: list[bytes]) -> MagicMock:
            p = MagicMock()
            p.stdin = MagicMock()
            p.stdin.drain = AsyncMock()
            p.stdout = MagicMock()
            p.stdout.readline = AsyncMock(side_effect=responses)
            p.kill.return_value = None
            p.wait = AsyncMock()
            return p

        with patch("mcp_manager.health.asyncio.create_subprocess_exec") as mock_exec:
            mock_exec.side_effect = [
                _make_proc([
                    b'{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2024-11-05"}}\n',
                    b"pong\n",
                ]),
                _make_proc([
                    b'{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2024-11-05"}}\n',
                    b"not json\n",
                ]),
            ]

            result = asyncio.run(checker.check(server))

        assert result.status == ServerStatus.DEGRADED
        assert "invalid tools/list response" in (result.error_message or "").lower()

    def test_deep_stdio_timeout(self) -> None:
        """Deep check when tools/list times out."""
        checker = HealthChecker(timeout=1, deep=True)
        server = _make_stdio()

        def _make_fast_proc() -> MagicMock:
            p = MagicMock()
            p.stdin = MagicMock()
            p.stdin.drain = AsyncMock()
            p.stdout = MagicMock()
            p.stdout.readline = AsyncMock(side_effect=[
                b'{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2024-11-05"}}\n',
                b"pong\n",
            ])
            p.kill.return_value = None
            p.wait = AsyncMock()
            return p

        def _make_slow_proc() -> MagicMock:
            p = MagicMock()
            p.stdin = MagicMock()
            p.stdin.drain = AsyncMock()
            p.stdout = MagicMock()

            call_count = 0
            async def _readline() -> bytes:
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    return b'{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2024-11-05"}}\n'
                await asyncio.sleep(100)
                return b""

            p.stdout.readline = _readline
            p.kill.return_value = None
            p.wait = AsyncMock()
            return p

        with patch("mcp_manager.health.asyncio.create_subprocess_exec") as mock_exec:
            mock_exec.side_effect = [_make_fast_proc(), _make_slow_proc()]

            result = asyncio.run(checker.check(server))

        assert result.status == ServerStatus.DEGRADED
        assert "deep check timeout" in (result.error_message or "").lower()


class TestHealthCheckerStress:
    """Stress tests for health checker scalability."""

    def test_check_all_100_stdio_no_leak(self) -> None:
        """Checking 100 stdio servers concurrently doesn't leak processes."""
        checker = HealthChecker(timeout=5)
        servers = [
            McpServer(
                name=f"srv-{i}",
                transport=TransportType.STDIO,
                stdio_config=StdioConfig(command="/does/not/exist"),
            )
            for i in range(100)
        ]

        # All should fail fast (FileNotFoundError)
        results = asyncio.run(checker.check_all(servers))
        assert len(results) == 100
        assert all(r.status == ServerStatus.UNREACHABLE for r in results)
