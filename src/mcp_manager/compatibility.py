"""MCP 2026-07-28 compatibility probing through the official SDK."""

from __future__ import annotations

import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx2
from mcp.client import Client
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamable_http_client
from mcp.types import Implementation

from mcp_manager.config import MCP_CLIENT_NAME, MCP_CLIENT_VERSION, MCP_PROTOCOL_VERSION
from mcp_manager.exceptions import ProtocolError
from mcp_manager.models import McpServer, NetworkConfig, ProtocolProbeResult, TransportType


def _http_headers(network_cfg: NetworkConfig) -> dict[str, str]:
    """Resolve configured HTTP credentials without exposing their values."""
    if network_cfg.auth:
        raise ProtocolError(
            "Protocol doctor cannot resolve client-managed HTTP auth mode "
            f"{network_cfg.auth!r}; use that client or an environment-backed credential"
        )
    headers = dict(network_cfg.headers)
    missing_env: list[str] = []
    for header_name, env_name in network_cfg.env_headers.items():
        value = os.environ.get(env_name)
        if value is None:
            missing_env.append(env_name)
        else:
            headers[header_name] = value
    if network_cfg.bearer_token_env_var:
        value = os.environ.get(network_cfg.bearer_token_env_var)
        if value is None:
            missing_env.append(network_cfg.bearer_token_env_var)
        else:
            headers["Authorization"] = f"Bearer {value}"
    if missing_env:
        names = ", ".join(sorted(set(missing_env)))
        raise ProtocolError(f"Missing HTTP credential environment variables: {names}")
    return headers


@asynccontextmanager
async def _open_client(
    server: McpServer,
    *,
    timeout: float,
    mode: str = "auto",
) -> AsyncIterator[Client]:
    """Open an official SDK client while preserving configured transport details."""
    client_info = Implementation(name=MCP_CLIENT_NAME, version=MCP_CLIENT_VERSION)

    if server.transport == TransportType.STDIO:
        if server.stdio_config is None:
            raise ProtocolError("No stdio config")
        stdio_cfg = server.stdio_config
        params = StdioServerParameters(
            command=stdio_cfg.command,
            args=stdio_cfg.args,
            env=stdio_cfg.env or None,
            cwd=stdio_cfg.cwd,
        )
        # Server stderr may contain local paths or credentials. Protocol doctor
        # returns a sanitized error instead of forwarding subprocess diagnostics.
        with open(os.devnull, "w", encoding="utf-8") as errlog:
            transport = stdio_client(params, errlog=errlog)
            async with Client(
                transport,
                mode=mode,
                read_timeout_seconds=timeout,
                client_info=client_info,
            ) as client:
                yield client
        return

    if server.transport == TransportType.HTTP:
        if server.network_config is None:
            raise ProtocolError("No HTTP config")
        network_cfg = server.network_config
        async with httpx2.AsyncClient(
            headers=_http_headers(network_cfg), timeout=timeout
        ) as http_client:
            transport = streamable_http_client(network_cfg.url, http_client=http_client)
            async with Client(
                transport,
                mode=mode,
                read_timeout_seconds=timeout,
                client_info=client_info,
            ) as client:
                yield client
        return

    raise ProtocolError(
        "Protocol compatibility probing supports stdio and Streamable HTTP; "
        "legacy SSE servers should use `mcp-manager health`."
    )


async def probe_protocol(
    server: McpServer,
    *,
    timeout: float = 10,
    strict_modern: bool = False,
    call_tool: str | None = None,
    call_arguments: dict[str, Any] | None = None,
) -> ProtocolProbeResult:
    """Probe discovery/fallback, list caching, and an optional benign tool call.

    ``strict_modern=False`` first attempts ``server/discover`` and lets the
    official SDK fall back to the legacy initialize handshake. Set
    ``strict_modern=True`` to reject servers that cannot speak 2026-07-28.

    The repeat comparison establishes stable client-visible results. Tests use
    an instrumented official server to additionally prove the second list is
    served from the SDK cache rather than crossing the transport.
    """
    start = time.monotonic()

    async def collect(mode: str) -> ProtocolProbeResult:
        async with _open_client(server, timeout=timeout, mode=mode) as client:
            return await _collect_probe_result(
                client,
                server=server,
                start=start,
                strict_modern=strict_modern,
                call_tool=call_tool,
                call_arguments=call_arguments,
            )

    connected = False
    try:
        async with _open_client(server, timeout=timeout, mode="auto") as client:
            connected = True
            return await _collect_probe_result(
                client,
                server=server,
                start=start,
                strict_modern=strict_modern,
                call_tool=call_tool,
                call_arguments=call_arguments,
            )
    except Exception:
        if connected or strict_modern or server.transport != TransportType.STDIO:
            raise

    # Some handshake-era stdio servers exit instead of returning method-not-found
    # for server/discover. Restart the process and negotiate explicitly in legacy
    # mode. Never retry failures that occur after a successful connection.
    return await collect("legacy")


async def _collect_probe_result(
    client: Client,
    *,
    server: McpServer,
    start: float,
    strict_modern: bool,
    call_tool: str | None,
    call_arguments: dict[str, Any] | None,
) -> ProtocolProbeResult:
    """Collect stable probe evidence from an already negotiated client."""
    if strict_modern and client.protocol_version != MCP_PROTOCOL_VERSION:
        raise ProtocolError(
            f"Server negotiated legacy protocol {client.protocol_version}; "
            f"required {MCP_PROTOCOL_VERSION}"
        )
    first = await client.list_tools(cache_mode="refresh")
    repeated = await client.list_tools(cache_mode="use")
    call_result = None
    if call_tool is not None:
        result = await client.call_tool(call_tool, call_arguments or {})
        call_result = result.model_dump(by_alias=True, mode="json", exclude_none=True)

    server_info = (
        client.server_info.model_dump(by_alias=True, mode="json", exclude_none=True)
        if client.server_info is not None
        else {}
    )
    capabilities = client.server_capabilities.model_dump(
        by_alias=True, mode="json", exclude_none=True
    )
    first_dump = first.model_dump(by_alias=True, mode="json", exclude_none=True)
    repeated_dump = repeated.model_dump(by_alias=True, mode="json", exclude_none=True)
    version = client.protocol_version

    return ProtocolProbeResult(
        server_name=server.name,
        transport=server.transport,
        protocol_era="modern" if version == MCP_PROTOCOL_VERSION else "legacy",
        protocol_version=version,
        latency_ms=round((time.monotonic() - start) * 1000, 1),
        server_info=server_info,
        capabilities=capabilities,
        tools=[tool.name for tool in first.tools],
        list_ttl_ms=first.ttl_ms,
        list_cache_scope=first.cache_scope,
        cached_repeat_identical=first_dump == repeated_dump,
        tool_call_result=call_result,
    )
