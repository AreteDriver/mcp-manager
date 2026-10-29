"""Health check implementations for MCP servers."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import time
import warnings
from typing import Any

import httpx
from mcp.shared.exceptions import MCPDeprecationWarning
from mcp.types import InitializeResult, Tool
from pydantic import ValidationError

from mcp_manager.compatibility import _open_client
from mcp_manager.config import HEALTH_TIMEOUT_SECONDS, MCP_PROTOCOL_VERSION
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
MAX_TOOL_PAGES = 100


def _rpc_result(body: Any, request_id: int) -> dict[str, Any]:
    """Validate a response without exposing untrusted error or payload content."""
    if (
        not isinstance(body, dict)
        or body.get("jsonrpc") != "2.0"
        or type(body.get("id")) is not int
        or body["id"] != request_id
        or "error" in body
        or not isinstance(body.get("result"), dict)
    ):
        raise ProtocolError("Invalid JSON-RPC response")
    result: dict[str, Any] = body["result"]
    return result


def _listed_tools(body: Any, request_id: int = 3) -> list[Any]:
    tools = _rpc_result(body, request_id).get("tools")
    if not isinstance(tools, list) or any(
        not isinstance(tool, dict) or not isinstance(tool.get("name"), str) for tool in tools
    ):
        raise ProtocolError("Invalid tools/list response")
    try:
        for tool in tools:
            Tool.model_validate(tool)
    except ValidationError:
        raise ProtocolError("Invalid tools/list schema") from None
    return tools


def _add_tool_name(name: str, names: set[str]) -> None:
    """A complete listing must identify each callable tool unambiguously."""
    if not name or name in names:
        raise ProtocolError("Invalid or duplicate tool name")
    names.add(name)


def _next_tool_cursor(cursor: Any, seen: set[str]) -> str | None:
    """Reject cyclic or malformed pagination without reporting a partial count."""
    if cursor is None:
        return None
    if not isinstance(cursor, str) or cursor in seen:
        raise ProtocolError("Invalid tools/list pagination")
    seen.add(cursor)
    return cursor


def _initialize_info(body: Any) -> dict[str, Any]:
    result = _rpc_result(body, 1)
    try:
        InitializeResult.model_validate(result)
    except ValidationError:
        raise ProtocolError("Invalid initialize result") from None
    return extract_server_info(body)


async def _read_stdio_response(stream: asyncio.StreamReader) -> bytes:
    """Skip valid notifications within the enclosing handshake deadline."""
    while data := await stream.readline():
        try:
            message = parse_jsonrpc_response(data)
        except ProtocolError:
            return data  # Let the caller classify malformed responses.
        if (
            message.get("jsonrpc") == "2.0"
            and isinstance(message.get("method"), str)
            and "id" not in message
            and "result" not in message
            and "error" not in message
            and ("params" not in message or isinstance(message["params"], dict))
        ):
            continue
        return data
    return b""


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
            elif server.transport in (TransportType.SSE, TransportType.HTTP):
                return await self._check_network_session(server)
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
        ) as exc:
            return HealthResult(
                server_name=server.name,
                status=ServerStatus.ERROR,
                transport=server.transport,
                error_message=f"Health check failed ({type(exc).__name__})",
            )

    async def check_all(self, servers: list[McpServer]) -> list[HealthResult]:
        """Check all servers concurrently."""
        tasks = [self.check(s) for s in servers]
        return list(await asyncio.gather(*tasks))

    async def _deep_check(self, server: McpServer, prev: HealthResult) -> HealthResult:
        """Run deep health checks: verify tools/list responds."""
        if server.transport == TransportType.STDIO:
            return await self._check_stdio_deep(server, prev)
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
        spawn_options: dict[str, Any] = {
            "stdin": asyncio.subprocess.PIPE,
            "stdout": asyncio.subprocess.PIPE,
            "stderr": asyncio.subprocess.PIPE,
            "env": {**os.environ, **cfg.env} if cfg.env else None,
        }
        if os.name == "posix":
            # MCP launchers such as npx commonly spawn a shell and a Node child.
            # A separate session lets cleanup terminate the whole process tree.
            spawn_options["start_new_session"] = True
        try:
            return await asyncio.create_subprocess_exec(
                cfg.command,
                *cfg.args,
                **spawn_options,
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
                error_message=f"Health check failed ({type(exc).__name__})",
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

        init_data = await _read_stdio_response(proc.stdout)
        if not init_data:
            return None

        init_response = parse_jsonrpc_response(init_data)
        server_info = _initialize_info(init_response)

        proc.stdin.write(build_initialized_notification())
        await proc.stdin.drain()

        return server_info

    @staticmethod
    async def _stdio_cleanup(proc: asyncio.subprocess.Process) -> None:
        """Terminate a stdio subprocess tree and bound the reap wait."""
        try:
            if os.name == "posix" and isinstance(proc.pid, int):
                os.killpg(proc.pid, signal.SIGKILL)
            else:
                proc.kill()
        except ProcessLookupError:
            pass
        try:
            if isinstance(proc, asyncio.subprocess.Process):
                # communicate() closes stdin and drains stdout/stderr after the
                # process group is gone, avoiding leaked asyncio pipe transports.
                await asyncio.wait_for(proc.communicate(), timeout=5)
            else:
                await asyncio.wait_for(proc.wait(), timeout=5)
        except TimeoutError:
            logger.warning("Timed out waiting for MCP subprocess cleanup")

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
        _rpc_result(parse_jsonrpc_response(await _read_stdio_response(proc.stdout)), 2)

        latency = (time.monotonic() - start) * 1000

        return HealthResult(
            server_name=name,
            status=ServerStatus.HEALTHY,
            latency_ms=round(latency, 1),
            transport=TransportType.STDIO,
            protocol_version=server_info.get("protocol_version"),
            server_info=server_info,
        )

    async def _check_network_session(self, server: McpServer) -> HealthResult:
        """Negotiate and check one SDK-managed session, including deep requests."""
        if server.network_config is None:
            return HealthResult(
                server_name=server.name,
                transport=server.transport,
                status=ServerStatus.ERROR,
                error_message="No network config",
            )
        start = time.monotonic()
        try:
            async with asyncio.timeout(self._timeout):
                async with _open_client(server, timeout=self._timeout) as client:
                    if client.protocol_version != MCP_PROTOCOL_VERSION:
                        with warnings.catch_warnings():
                            warnings.simplefilter("ignore", MCPDeprecationWarning)
                            await client.send_ping()
                    info = client.server_info
                    # Legacy metadata is required by the SDK; modern discovery permits no stamp.
                    if info is not None and (not info.name or not info.version):
                        raise ProtocolError("Invalid server metadata")
                    status = ServerStatus.HEALTHY
                    error = None
                    tool_count: int | None = None
                    if self._deep:
                        names: set[str] = set()
                        seen: set[str] = set()
                        cursor = None
                        for _ in range(MAX_TOOL_PAGES):
                            listed = await client.list_tools(cursor=cursor, cache_mode="refresh")
                            for tool in listed.tools:
                                Tool.model_validate(tool.model_dump(by_alias=True))
                                _add_tool_name(tool.name, names)
                            cursor = _next_tool_cursor(listed.next_cursor, seen)
                            if cursor is None:
                                break
                        else:
                            raise ProtocolError("Too many tools/list pages")
                        tool_count = len(names)
                        if tool_count == 0:
                            status = ServerStatus.DEGRADED
                            error = "Server returned zero tools"
                    return HealthResult(
                        server_name=server.name,
                        transport=server.transport,
                        status=status,
                        latency_ms=round((time.monotonic() - start) * 1000, 1),
                        protocol_version=client.protocol_version,
                        server_info={
                            "protocol_version": client.protocol_version,
                            "server_name": info.name if info else None,
                            "server_version": info.version if info else None,
                            "capabilities": client.server_capabilities.model_dump(
                                by_alias=True, exclude_none=True
                            ),
                            **({"tool_count": tool_count} if tool_count is not None else {}),
                        },
                        error_message=error,
                    )
        except Exception as exc:
            # SDK task groups can wrap transport/protocol failures. Never expose payloads.
            return HealthResult(
                server_name=server.name,
                transport=server.transport,
                status=ServerStatus.ERROR,
                error_message=f"MCP session check failed ({type(exc).__name__})",
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
            return spawn_result
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

            names: set[str] = set()
            seen: set[str] = set()
            cursor = None
            try:
                for page in range(MAX_TOOL_PAGES):
                    request_id = 3 + page
                    request = json.loads(build_list_tools_request(request_id=request_id))
                    if cursor is not None:
                        request["params"] = {"cursor": cursor}
                    proc.stdin.write(json.dumps(request).encode("utf-8") + b"\n")
                    await proc.stdin.drain()
                    tools_data = await _read_stdio_response(proc.stdout)
                    if not tools_data:
                        return HealthResult(
                            server_name=server.name,
                            status=ServerStatus.DEGRADED,
                            transport=TransportType.STDIO,
                            latency_ms=prev.latency_ms,
                            error_message="No tools/list response",
                        )
                    parsed = parse_jsonrpc_response(tools_data)
                    tools = _listed_tools(parsed, request_id=request_id)
                    for tool in tools:
                        _add_tool_name(tool["name"], names)
                    cursor = _next_tool_cursor(
                        _rpc_result(parsed, request_id).get("nextCursor"), seen
                    )
                    if cursor is None:
                        break
                else:
                    raise ProtocolError("Too many tools/list pages")
            except (ProtocolError, KeyError, TypeError):
                return HealthResult(
                    server_name=server.name,
                    status=ServerStatus.DEGRADED,
                    transport=TransportType.STDIO,
                    latency_ms=prev.latency_ms,
                    error_message="Invalid tools/list response",
                )

            return prev.model_copy(
                update={
                    "status": prev.status if names else ServerStatus.DEGRADED,
                    "server_info": {**prev.server_info, "tool_count": len(names)},
                    "error_message": prev.error_message if names else "Server returned zero tools",
                }
            )

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
