"""Dependency checking for MCP servers.

Verifies that required binaries (node, python, npx, etc.) are available on PATH.
"""

from __future__ import annotations

import shutil

from mcp_manager.models import McpServer, StdioConfig, TransportType


# Known command → binary mapping for dependency checking.
# Keys are the first token of a command string; values are the binaries to verify.
_KNOWN_DEPS: dict[str, list[str]] = {
    "node": ["node"],
    "npx": ["npx"],
    "python": ["python3", "python"],
    "python3": ["python3", "python"],
    "docker": ["docker"],
    "uvx": ["uvx", "uv"],
    "uv": ["uv"],
}


def check_dependencies(server: McpServer) -> list[str]:
    """Check that required binaries exist on PATH for a server.

    Returns:
        List of missing binary names (empty if all found).
    """
    if server.transport != TransportType.STDIO or not server.stdio_config:
        return []

    cmd = server.stdio_config.command
    deps = _KNOWN_DEPS.get(cmd)
    if deps is None:
        # Unknown command — let transport check determine reachability.
        return []

    missing: list[str] = []
    for dep in deps:
        if shutil.which(dep) is None:
            missing.append(dep)

    return missing


def check_dependencies_all(servers: list[McpServer]) -> dict[str, list[str]]:
    """Check dependencies for all servers.

    Returns:
        Mapping of server name → list of missing binaries.
    """
    return {s.name: check_dependencies(s) for s in servers if check_dependencies(s)}
