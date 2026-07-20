"""Health check implementations for MCP servers."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

import httpx

from mcp_manager.config import HEALTH_TIMEOUT_SECONDS
from mcp_manager.deps import check_dependencies
from mcp_manager.exceptions import ProtocolError
from mcp_manager.models import HealthResult, McpServer, ServerStatus, TransportType
from mcp_manager.protocol import (
    build_initialize_request,
    build_initialized_notification,
    build_list_tools_request,
    build_ping_request,
    extract_server_info,
    parse_jsonrpc_response,
)

logger = logging.getLogger(__name__)


class HealthChecker:
    """Check health of MCP servers across transport types."""

    def __init__(self, timeout: int | None = None, *, deep: bool = False) -> None:
        self._timeout = timeout or HEALTH_TIMEOUT_SECONDS
        self._deep = deep

    async def check(self, server: McpServer) -> HealthResult:
        """Route to the correct transport-specific check."""
        # Dependency check (fast, local).
        missing_deps = check_dependencies(server)
        if missing_deps:
            return HealthResult(
                server_name=server.name,
                status=ServerStatus.ERROR,
                transport=server.transport,
                error_message=f"Missing dependencies: {', '.join(missing_deps)}",
            )

        try:
            if server.transport == TransportType.STDIO:
                result = await self._check_stdio(server)
            elif server.transport == TransportType.SSE:
                result = await self._check_sse(server)
            elif server.transport == TransportType.HTTP:
                result = await self._check_http(server)
            else:
                return HealthResult(
                    server_name=server.name,
                    status=ServerStatus.ERROR,
                    transport=server.transport,
                    error_message=f"Unknown transport: {server.transport}",
                )

            if self._deep and result.status in (ServerStatus.HEALTHY, ServerStatus.DEGRADED):
                result = await self._deep_check(server, result)

            return result
        except (
            OSError,
            TimeoutError,
            ProtocolError,
            httpx.HTTPError,
            json.JSONDecodeError,
            ValueError,
            TypeError,
        ) as exc:
            return HealthResult(
                server_name=server.name,
                status=ServerStatus.ERROR,
                transport=server.transport,
                error_message=str(exc),
            )

    async def check_all(self, servers: list[McpServer]) -> list[HealthResult]:
        """Check all servers concurrently."""
        tasks = [self.check(s) for s in servers]
        return list(await asyncio.gather(*tasks))

    async def _deep_check(self, server: McpServer, prev: HealthResult) -> HealthResult:
        """Run deep health checks: verify tools/list responds."""
        if server.transport == TransportType.STDIO:
            return await self._check_stdio_deep(server, prev)
        if server.transport in (TransportType.SSE, TransportType.HTTP):
            return await self._check_network_deep(server, prev)
        return prev

    # ------------------------------------------------------------------
    # Transport-specific checks
    # ------------------------------------------------------------------

    async def _stdio_spawn(self, server: McpServer) -> asyncio.subprocess.Process | HealthResult:
        """Spawn a stdio subprocess for the given server.

        Returns the Process on success, or a HealthResult on failure.
        """
        assert server.stdio_config is not None
        cfg = server.stdio_config
        try:
            return await asyncio.create_subprocess_exec(
                cfg.command,
                *cfg.args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=cfg.env if cfg.env else None,
            )
        except FileNotFoundError:
            return HealthResult(
                server_name=server.name,
                status=ServerStatus.UNREACHABLE,
                transport=TransportType.STDIO,
                error_message=f"Command not found: {cfg.command}",
            )
        except OSError as exc:
            return HealthResult(
                server_name=server.name,
                status=ServerStatus.UNREACHABLE,
                transport=TransportType.STDIO,
                error_message=str(exc),
            )

    @staticmethod
    async def _stdio_init_sequence(
        proc: asyncio.subprocess.Process,
    ) -> dict[str, Any] | None:
        """Send initialize, read response, send initialized notification.

        Returns server_info dict, or None if the process closed stdout.
        """
        assert proc.stdin is not None
        assert proc.stdout is not None

        proc.stdin.write(build_initialize_request())
        await proc.stdin.drain()

        init_data = await proc.stdout.readline()
        if not init_data:
            return None

        init_response = parse_jsonrpc_response(init_data)
        server_info = extract_server_info(init_response)

        proc.stdin.write(build_initialized_notification())
        await proc.stdin.drain()

        return server_info

    @staticmethod
    async def _stdio_cleanup(proc: asyncio.subprocess.Process) -> None:
        """Kill a stdio subprocess and wait for it to exit."""
        try:
            proc.kill()
            await proc.wait()
        except ProcessLookupError:
            pass

    async def _check_stdio(self, server: McpServer) -> HealthResult:
        """Spawn process, send initialize + ping, measure latency."""
        if not server.stdio_config:
            return HealthResult(
                server_name=server.name,
                status=ServerStatus.ERROR,
                transport=TransportType.STDIO,
                error_message="No stdio config",
            )

        spawn_result = await self._stdio_spawn(server)
        if isinstance(spawn_result, HealthResult):
            return spawn_result
        proc = spawn_result

        start = time.monotonic()
        try:
            return await asyncio.wait_for(
                self._stdio_ping_handshake(server.name, proc, start),
                timeout=self._timeout,
            )
        except TimeoutError:
            return HealthResult(
                server_name=server.name,
                status=ServerStatus.UNREACHABLE,
                transport=TransportType.STDIO,
                error_message="Handshake timeout",
            )
        finally:
            await self._stdio_cleanup(proc)

    async def _stdio_ping_handshake(
        self,
        name: str,
        proc: asyncio.subprocess.Process,
        start: float,
    ) -> HealthResult:
        """Run the MCP initialize + ping handshake over stdio."""
        server_info = await self._stdio_init_sequence(proc)
        if server_info is None:
            return HealthResult(
                server_name=name,
                status=ServerStatus.ERROR,
                transport=TransportType.STDIO,
                error_message="No response to initialize",
            )

        assert proc.stdin is not None
        proc.stdin.write(build_ping_request())
        await proc.stdin.drain()

        # Read ping response.
        assert proc.stdout is not None
        await proc.stdout.readline()

        latency = (time.monotonic() - start) * 1000

        return HealthResult(
            server_name=name,
            status=ServerStatus.HEALTHY,
            latency_ms=round(latency, 1),
            transport=TransportType.STDIO,
            protocol_version=server_info.get("protocol_version"),
            server_info=server_info,
        )

    async def _check_sse(self, server: McpServer) -> HealthResult:
        """Check SSE server reachability."""
        if not server.network_config:
            return HealthResult(
                server_name=server.name,
                status=ServerStatus.ERROR,
                transport=TransportType.SSE,
                error_message="No network config",
            )

        url = server.network_config.url
        headers = dict(server.network_config.headers)
        start = time.monotonic()

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(url, headers=headers)
        except httpx.ConnectError:
            return HealthResult(
                server_name=server.name,
                status=ServerStatus.UNREACHABLE,
                transport=TransportType.SSE,
                error_message=f"Connection refused: {url}",
            )
        except httpx.TimeoutException:
            return HealthResult(
                server_name=server.name,
                status=ServerStatus.UNREACHABLE,
                transport=TransportType.SSE,
                error_message="Timeout",
            )

        latency = (time.monotonic() - start) * 1000
        content_type = resp.headers.get("content-type", "")

        if resp.status_code >= 400:
            return HealthResult(
                server_name=server.name,
                status=ServerStatus.ERROR,
                latency_ms=round(latency, 1),
                transport=TransportType.SSE,
                error_message=f"HTTP {resp.status_code}",
            )

        status = ServerStatus.HEALTHY
        if "text/event-stream" not in content_type:
            status = ServerStatus.DEGRADED

        return HealthResult(
            server_name=server.name,
            status=status,
            latency_ms=round(latency, 1),
            transport=TransportType.SSE,
        )

    async def _check_http(self, server: McpServer) -> HealthResult:
        """POST JSON-RPC initialize to HTTP server."""
        if not server.network_config:
            return HealthResult(
                server_name=server.name,
                status=ServerStatus.ERROR,
                transport=TransportType.HTTP,
                error_message="No network config",
            )

        url = server.network_config.url
        headers = {"Content-Type": "application/json", **server.network_config.headers}
        init_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "mcp-manager", "version": "0.1.0"},
            },
        }
        start = time.monotonic()

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(url, json=init_request, headers=headers)
        except httpx.ConnectError:
            return HealthResult(
                server_name=server.name,
                status=ServerStatus.UNREACHABLE,
                transport=TransportType.HTTP,
                error_message=f"Connection refused: {url}",
            )
        except httpx.TimeoutException:
            return HealthResult(
                server_name=server.name,
                status=ServerStatus.UNREACHABLE,
                transport=TransportType.HTTP,
                error_message="Timeout",
            )

        latency = (time.monotonic() - start) * 1000

        if resp.status_code >= 400:
            return HealthResult(
                server_name=server.name,
                status=ServerStatus.ERROR,
                latency_ms=round(latency, 1),
                transport=TransportType.HTTP,
                error_message=f"HTTP {resp.status_code}",
            )

        # Try to parse JSON-RPC response.
        try:
            body = resp.json()
            server_info = extract_server_info(body)
            return HealthResult(
                server_name=server.name,
                status=ServerStatus.HEALTHY,
                latency_ms=round(latency, 1),
                transport=TransportType.HTTP,
                protocol_version=server_info.get("protocol_version"),
                server_info=server_info,
            )
        except (json.JSONDecodeError, KeyError, TypeError):
            return HealthResult(
                server_name=server.name,
                status=ServerStatus.DEGRADED,
                latency_ms=round(latency, 1),
                transport=TransportType.HTTP,
                error_message="Reachable but invalid JSON-RPC response",
            )

    # ------------------------------------------------------------------
    # Deep checks
    # ------------------------------------------------------------------

    async def _check_stdio_deep(self, server: McpServer, prev: HealthResult) -> HealthResult:
        """Spawn process and verify tools/list returns non-empty."""
        if not server.stdio_config:
            return prev

        spawn_result = await self._stdio_spawn(server)
        if isinstance(spawn_result, HealthResult):
            return prev
        proc = spawn_result

        async def _deep_tools_check() -> HealthResult:
            server_info = await self._stdio_init_sequence(proc)
            if server_info is None:
                return HealthResult(
                    server_name=server.name,
                    status=ServerStatus.DEGRADED,
                    transport=TransportType.STDIO,
                    latency_ms=prev.latency_ms,
                    error_message="No response to initialize",
                )

            assert proc.stdin is not None
            assert proc.stdout is not None

            proc.stdin.write(build_list_tools_request())
            await proc.stdin.drain()
            tools_data = await proc.stdout.readline()

            if not tools_data:
                return HealthResult(
                    server_name=server.name,
                    status=ServerStatus.DEGRADED,
                    transport=TransportType.STDIO,
                    latency_ms=prev.latency_ms,
                    error_message="No tools/list response",
                )

            try:
                parsed = parse_jsonrpc_response(tools_data)
                tools = parsed.get("result", {}).get("tools", [])
                if not tools:
                    return HealthResult(
                        server_name=server.name,
                        status=ServerStatus.DEGRADED,
                        transport=TransportType.STDIO,
                        latency_ms=prev.latency_ms,
                        error_message="Server returned zero tools",
                    )
            except (ProtocolError, KeyError, TypeError):
                return HealthResult(
                    server_name=server.name,
                    status=ServerStatus.DEGRADED,
                    transport=TransportType.STDIO,
                    latency_ms=prev.latency_ms,
                    error_message="Invalid tools/list response",
                )

            return prev

        try:
            return await asyncio.wait_for(_deep_tools_check(), timeout=self._timeout)
        except TimeoutError:
            return HealthResult(
                server_name=server.name,
                status=ServerStatus.DEGRADED,
                transport=TransportType.STDIO,
                latency_ms=prev.latency_ms,
                error_message="Deep check timeout",
            )
        finally:
            await self._stdio_cleanup(proc)

    async def _check_network_deep(self, server: McpServer, prev: HealthResult) -> HealthResult:
        """POST tools/list to SSE/HTTP server and verify non-empty response."""
        if not server.network_config:
            return prev

        url = server.network_config.url
        headers = {"Content-Type": "application/json", **server.network_config.headers}
        request = build_list_tools_request()

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(url, content=request, headers=headers)
        except httpx.HTTPError:
            return prev

        if resp.status_code >= 400:
            return HealthResult(
                server_name=server.name,
                status=ServerStatus.DEGRADED,
                transport=server.transport,
                latency_ms=prev.latency_ms,
                error_message=f"tools/list returned HTTP {resp.status_code}",
            )

        try:
            body = resp.json()
            tools = body.get("result", {}).get("tools", [])
            if not tools:
                return HealthResult(
                    server_name=server.name,
                    status=ServerStatus.DEGRADED,
                    transport=server.transport,
                    latency_ms=prev.latency_ms,
                    error_message="Server returned zero tools",
                )
        except (json.JSONDecodeError, KeyError, TypeError):
            return HealthResult(
                server_name=server.name,
                status=ServerStatus.DEGRADED,
                transport=server.transport,
                latency_ms=prev.latency_ms,
                error_message="Invalid tools/list response",
            )

        return prev
