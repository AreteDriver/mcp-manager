"""Instrumented official MCP SDK v2 server for compatibility tests."""

from __future__ import annotations

from typing import Any

from mcp.server import CacheHint
from mcp.server.mcpserver import MCPServer


class CountingServer(MCPServer[None]):
    """Count wire-level tools/list handler calls to verify client caching."""

    def __init__(self) -> None:
        super().__init__(
            "mcp-manager-modern-fixture",
            version="1.0.0",
            cache_hints={"tools/list": CacheHint(ttl_ms=60_000, scope="private")},
        )
        self.list_calls = 0

    async def list_tools(self) -> list[Any]:
        self.list_calls += 1
        return await super().list_tools()


server = CountingServer()


@server.tool(name="probe_stats", description="Return non-sensitive probe counters.")
def probe_stats() -> dict[str, int]:
    return {"list_calls": server.list_calls}


if __name__ == "__main__":
    server.run(transport="stdio")
