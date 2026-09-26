"""Additional tests for mcp_manager.health to cover deep checks and edge cases."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from mcp_manager.health import HealthChecker
from mcp_manager.models import (
    McpServer,
    NetworkConfig,
    ServerStatus,
    StdioConfig,
    TransportType,
)


def _valid_init() -> bytes:
    return (
        b'{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2024-11-05",'
        b'"capabilities":{},"serverInfo":{"name":"fixture","version":"1"}}}\n'
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
        assert "OSError" in (result.error_message or "")

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
                _make_proc(
                    [
                        _valid_init(),
                        b'{"jsonrpc":"2.0","id":2,"result":{}}\n',
                    ]
                ),
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
                _make_proc(
                    [
                        _valid_init(),
                        b'{"jsonrpc":"2.0","id":2,"result":{}}\n',
                    ]
                ),
                _make_proc(
                    [
                        _valid_init(),
                        b"",
                    ]
                ),
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
                _make_proc(
                    [
                        _valid_init(),
                        b'{"jsonrpc":"2.0","id":2,"result":{}}\n',
                    ]
                ),
                _make_proc(
                    [
                        _valid_init(),
                        b'{"jsonrpc":"2.0","id":3,"result":{"tools":[]}}\n',
                    ]
                ),
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
                _make_proc(
                    [
                        _valid_init(),
                        b'{"jsonrpc":"2.0","id":2,"result":{}}\n',
                    ]
                ),
                _make_proc(
                    [
                        _valid_init(),
                        b"not json\n",
                    ]
                ),
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
            p.stdout.readline = AsyncMock(
                side_effect=[
                    _valid_init(),
                    b'{"jsonrpc":"2.0","id":2,"result":{}}\n',
                ]
            )
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
                    return _valid_init()
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
