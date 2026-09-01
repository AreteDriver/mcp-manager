"""Dual-era compatibility tests against the official MCP SDK client/server."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from mcp_manager.compatibility import _http_headers, probe_protocol
from mcp_manager.exceptions import ProtocolError
from mcp_manager.models import McpServer, NetworkConfig, StdioConfig, TransportType

FIXTURES = Path(__file__).parent / "fixtures"


def test_http_headers_resolve_credentials_without_changing_static_headers(monkeypatch) -> None:
    monkeypatch.setenv("MCP_API_KEY", "private-api-key")
    monkeypatch.setenv("MCP_BEARER_TOKEN", "private-token")
    config = NetworkConfig(
        type="http",
        url="https://example.com/mcp",
        headers={"Accept-Language": "en"},
        env_headers={"X-API-Key": "MCP_API_KEY"},
        bearer_token_env_var="MCP_BEARER_TOKEN",
    )

    assert _http_headers(config) == {
        "Accept-Language": "en",
        "X-API-Key": "private-api-key",
        "Authorization": "Bearer private-token",
    }


def test_http_headers_reports_only_missing_variable_name(monkeypatch) -> None:
    monkeypatch.delenv("MCP_MISSING_TOKEN", raising=False)
    config = NetworkConfig(
        type="http",
        url="https://example.com/mcp",
        bearer_token_env_var="MCP_MISSING_TOKEN",
    )

    with pytest.raises(ProtocolError, match="MCP_MISSING_TOKEN") as error:
        _http_headers(config)

    assert "Bearer" not in str(error.value)


def test_http_headers_rejects_client_managed_auth() -> None:
    config = NetworkConfig(
        type="http",
        url="https://example.com/mcp",
        auth="oauth",
    )

    with pytest.raises(ProtocolError, match="client-managed HTTP auth mode 'oauth'"):
        _http_headers(config)


@pytest.mark.asyncio
async def test_modern_probe_discovers_caches_and_calls_tool() -> None:
    server = McpServer(
        name="modern-fixture",
        transport=TransportType.STDIO,
        stdio_config=StdioConfig(
            command=sys.executable,
            args=[str(FIXTURES / "modern_mcp_server.py")],
        ),
    )

    result = await probe_protocol(
        server,
        strict_modern=True,
        call_tool="probe_stats",
    )

    assert result.protocol_era == "modern"
    assert result.protocol_version == "2026-07-28"
    assert result.server_info["name"] == "mcp-manager-modern-fixture"
    assert result.tools == ["probe_stats"]
    assert result.list_ttl_ms == 60_000
    assert result.list_cache_scope == "private"
    assert result.cached_repeat_identical is True
    assert result.tool_call_result is not None
    assert result.tool_call_result["structuredContent"] == {"list_calls": 1}


@pytest.mark.asyncio
async def test_auto_probe_falls_back_to_legacy_handshake() -> None:
    server = McpServer(
        name="legacy-fixture",
        transport=TransportType.STDIO,
        stdio_config=StdioConfig(
            command=sys.executable,
            args=[str(FIXTURES / "legacy_mcp_server.py")],
        ),
    )

    result = await probe_protocol(
        server,
        call_tool="legacy_echo",
        call_arguments={"value": "ok"},
    )

    assert result.protocol_era == "legacy"
    assert result.protocol_version == "2024-11-05"
    assert result.server_info["name"] == "legacy-fixture"
    assert result.tools == ["legacy_echo"]
    assert result.cached_repeat_identical is True
    assert result.tool_call_result is not None
    assert result.tool_call_result["content"] == [{"type": "text", "text": "ok"}]


@pytest.mark.asyncio
async def test_auto_probe_restarts_stdio_server_that_exits_on_discover(capsys) -> None:
    server = McpServer(
        name="brittle-legacy-fixture",
        transport=TransportType.STDIO,
        stdio_config=StdioConfig(
            command=sys.executable,
            args=[str(FIXTURES / "legacy_mcp_server.py"), "--exit-on-discover"],
        ),
    )

    result = await probe_protocol(server)

    assert result.protocol_era == "legacy"
    assert result.protocol_version == "2024-11-05"
    assert result.tools == ["legacy_echo"]
    assert "private server diagnostic" not in capsys.readouterr().err


@pytest.mark.asyncio
async def test_strict_modern_does_not_restart_brittle_legacy_server() -> None:
    server = McpServer(
        name="brittle-legacy-fixture",
        transport=TransportType.STDIO,
        stdio_config=StdioConfig(
            command=sys.executable,
            args=[str(FIXTURES / "legacy_mcp_server.py"), "--exit-on-discover"],
        ),
    )

    with pytest.raises(ExceptionGroup):
        await probe_protocol(server, strict_modern=True)
