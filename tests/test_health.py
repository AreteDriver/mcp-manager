"""Tests for mcp_manager.health."""

from __future__ import annotations

import asyncio
import json

import pytest

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
    def test_empty_servers(self) -> None:
        checker = HealthChecker(timeout=5)
        results = asyncio.run(checker.check_all([]))
        assert results == []


@pytest.mark.parametrize(
    "ping",
    [
        b"",
        b"pong\n",
        b'{"jsonrpc":"2.0","id":2,"error":{"code":-1,"message":"bad"}}\n',
        b'{"jsonrpc":"2.0","id":99,"result":{}}\n',
    ],
)
async def test_invalid_stdio_ping_is_not_healthy(ping):
    from unittest.mock import AsyncMock, MagicMock, patch

    proc = MagicMock()
    proc.stdin.drain = AsyncMock()
    proc.stdout.readline = AsyncMock(side_effect=[_init_response(), ping])
    proc.wait = AsyncMock()
    with patch("mcp_manager.health.asyncio.create_subprocess_exec", return_value=proc):
        result = await HealthChecker().check(_make_stdio())
    assert result.status is not ServerStatus.HEALTHY
    proc.kill.assert_called_once()


async def test_stdio_notifications_can_precede_each_response(tmp_path):
    import sys

    script = tmp_path / "server.py"
    script.write_text("""
import json, sys
for line in sys.stdin:
    message = json.loads(line)
    if 'id' not in message:
        continue
    print(json.dumps({'jsonrpc':'2.0','method':'notifications/tools/list_changed'}), flush=True)
    result = ({'protocolVersion':'2024-11-05','capabilities':{'tools':{}},
               'serverInfo':{'name':'fixture','version':'1'}} if message['method']=='initialize'
              else {'tools':[{'name':'test','inputSchema':{'type':'object'}}]}
              if message['method']=='tools/list' else {})
    print(json.dumps({'jsonrpc':'2.0','id':message['id'],'result':result}), flush=True)
""")
    server = McpServer(
        name="fixture",
        transport="stdio",
        stdio_config=StdioConfig(command=sys.executable, args=[str(script)]),
    )
    result = await HealthChecker(timeout=2, deep=True).check(server)
    assert result.status is ServerStatus.HEALTHY
