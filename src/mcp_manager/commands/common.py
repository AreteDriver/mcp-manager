"""Shared CLI helpers and console."""

from __future__ import annotations

from pathlib import Path

from rich.console import Console

from mcp_manager.discovery import ConfigDiscovery
from mcp_manager.models import McpServer, ServerStatus
from mcp_manager.registry import ServerRegistry

console = Console()

_STATUS_STYLE: dict[ServerStatus, str] = {
    ServerStatus.HEALTHY: "[green]healthy[/green]",
    ServerStatus.DEGRADED: "[yellow]degraded[/yellow]",
    ServerStatus.UNREACHABLE: "[red]unreachable[/red]",
    ServerStatus.ERROR: "[red]error[/red]",
    ServerStatus.UNKNOWN: "[dim]unknown[/dim]",
}

_STATUS_ICON: dict[ServerStatus, str] = {
    ServerStatus.HEALTHY: "[green]✅[/green]",
    ServerStatus.DEGRADED: "[yellow]⚠️[/yellow]",
    ServerStatus.UNREACHABLE: "[red]❌[/red]",
    ServerStatus.ERROR: "[red]❌[/red]",
    ServerStatus.UNKNOWN: "[dim]?[/dim]",
}


def _discover(
    tool: str | None = None,
    project_dir: Path | None = None,
) -> list[McpServer]:
    """Run discovery, optionally filtered by tool."""
    discovery = ConfigDiscovery()
    if tool:
        return discovery.discover_tool(tool)
    return discovery.discover_all(project_dir=project_dir)


def _server_summary(server: McpServer) -> str:
    """One-line summary of a server's connection target."""
    if server.stdio_config:
        cmd = server.stdio_config.command
        args = " ".join(server.stdio_config.args[:2])
        suffix = " ..." if len(server.stdio_config.args) > 2 else ""
        return f"{cmd} {args}{suffix}".strip()
    if server.network_config:
        return server.network_config.url
    return "—"


def _get_registry(path: Path | None = None) -> ServerRegistry:
    """Load the mcp-manager registry."""
    reg = ServerRegistry(path=path)
    reg.load()
    return reg
