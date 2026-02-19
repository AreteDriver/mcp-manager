"""Map MCP servers to IDE/tool usage."""

from __future__ import annotations

from mcp_manager.models import McpServer, ServerMapping, TransportType


def _server_identity(server: McpServer) -> str:
    """Derive a stable identity key for a server.

    Two servers are considered "the same" if they share the same command+args
    (stdio) or the same URL (network).
    """
    if server.transport == TransportType.STDIO and server.stdio_config:
        parts = [server.stdio_config.command, *server.stdio_config.args]
        return f"stdio:{' '.join(parts)}"

    if server.network_config:
        return f"{server.network_config.type}:{server.network_config.url}"

    return f"unknown:{server.name}"


def build_server_map(servers: list[McpServer]) -> list[ServerMapping]:
    """Group servers by identity and collect the tools that reference each."""
    identity_to_servers: dict[str, list[McpServer]] = {}

    for server in servers:
        key = _server_identity(server)
        identity_to_servers.setdefault(key, []).append(server)

    mappings: list[ServerMapping] = []
    for group in identity_to_servers.values():
        representative = group[0]
        tools = sorted({s.source_tool for s in group})
        config_paths = sorted({str(s.source_path) for s in group if s.source_path})

        mappings.append(
            ServerMapping(
                server_name=representative.name,
                transport=representative.transport,
                tools=tools,
                config_paths=config_paths,
            )
        )

    return sorted(mappings, key=lambda m: m.server_name)
