"""Server management command implementations."""

from __future__ import annotations

import asyncio
import json as json_mod
from pathlib import Path

from rich.table import Table

from mcp_manager.commands.common import (
    _STATUS_ICON,
    _STATUS_STYLE,
    _discover,
    _get_registry,
    _server_summary,
    console,
)
from mcp_manager.exceptions import McpManagerError
from mcp_manager.health import HealthChecker
from mcp_manager.mapper import build_server_map
from mcp_manager.models import McpServer, NetworkConfig, StdioConfig, TransportType
from mcp_manager.telemetry import track_command


def list_servers_impl(
    tool: str | None,
    transport: str | None,
    project: Path | None,
    json: bool,  # noqa: A002
) -> None:
    """List all configured MCP servers across tools."""
    track_command("list")
    try:
        servers = _discover(tool=tool, project_dir=project)
    except McpManagerError as exc:
        console.print(f"[red]Discovery error:[/red] {exc}")
        raise

    if transport:
        try:
            tt = TransportType(transport.lower())
        except ValueError as exc:
            console.print(f"[red]Unknown transport:[/red] {transport}")
            raise McpManagerError(f"Unknown transport: {transport}") from exc
        servers = [s for s in servers if s.transport == tt]

    if not servers:
        console.print("[dim]No MCP servers found.[/dim]")
        return

    if json:
        data = [s.model_dump(mode="json", exclude_none=True) for s in servers]
        console.print_json(json_mod.dumps(data, indent=2))
        return

    table = Table(title="MCP Servers")
    table.add_column("Name", style="cyan")
    table.add_column("Transport", style="green")
    table.add_column("Source", style="yellow")
    table.add_column("Target")

    for s in sorted(servers, key=lambda x: x.name):
        table.add_row(s.name, s.transport.value, s.source_tool, _server_summary(s))

    console.print(table)


def map_servers_impl(
    project: Path | None,
    json: bool,  # noqa: A002
) -> None:
    """Show which tools/IDEs use which servers."""
    track_command("map")
    try:
        servers = _discover(project_dir=project)
    except McpManagerError as exc:
        console.print(f"[red]Discovery error:[/red] {exc}")
        raise

    if not servers:
        console.print("[dim]No MCP servers found.[/dim]")
        return

    mappings = build_server_map(servers)

    if json:
        data = [m.model_dump(mode="json") for m in mappings]
        console.print_json(json_mod.dumps(data, indent=2))
        return

    table = Table(title="Server → Tool Mapping")
    table.add_column("Server", style="cyan")
    table.add_column("Transport", style="green")
    table.add_column("Used By", style="yellow")

    for m in mappings:
        table.add_row(m.server_name, m.transport.value, ", ".join(m.tools))

    console.print(table)


def health_impl(
    server_name: str | None,
    timeout: int,
    project: Path | None,
    json: bool,  # noqa: A002
    deep: bool,
) -> None:
    """Health check all servers (status, latency, version)."""
    track_command("health")
    try:
        servers = _discover(project_dir=project)
    except McpManagerError as exc:
        console.print(f"[red]Discovery error:[/red] {exc}")
        raise

    if server_name:
        servers = [s for s in servers if s.name == server_name]

    if not servers:
        console.print("[dim]No MCP servers found.[/dim]")
        return

    checker = HealthChecker(timeout=timeout, deep=deep)
    results = asyncio.run(checker.check_all(servers))

    if json:
        data = [r.model_dump(mode="json", exclude_none=True) for r in results]
        console.print_json(json_mod.dumps(data, indent=2))
        return

    table = Table(title="Health Check Results")
    table.add_column("", width=3)
    table.add_column("Server", style="cyan")
    table.add_column("Status")
    table.add_column("Transport", style="dim")
    table.add_column("Latency", justify="right")
    table.add_column("Details")

    for r in sorted(results, key=lambda x: x.server_name):
        icon = _STATUS_ICON.get(r.status, "")
        status = _STATUS_STYLE.get(r.status, str(r.status))
        latency = f"{r.latency_ms:.0f}ms" if r.latency_ms is not None else "—"
        details = r.error_message or r.server_info.get("server_name", "")
        table.add_row(icon, r.server_name, status, r.transport.value, latency, details)

    console.print(table)


def add_impl(
    name: str,
    command: str | None,
    url: str | None,
    transport: str,
    args: list[str] | None,
) -> None:
    """Add a new MCP server to the mcp-manager registry."""
    track_command("add")
    if command and url:
        console.print("[red]Specify --command (stdio) or --url (network), not both.[/red]")
        raise McpManagerError("Specify --command or --url, not both")

    if not command and not url:
        console.print("[red]Specify --command for stdio or --url for SSE/HTTP.[/red]")
        raise McpManagerError("Specify --command or --url")

    try:
        tt = TransportType(transport.lower())
    except ValueError as exc:
        console.print(f"[red]Unknown transport:[/red] {transport}")
        raise McpManagerError(f"Unknown transport: {transport}") from exc

    stdio_config: StdioConfig | None = None
    network_config: NetworkConfig | None = None

    if command:
        tt = TransportType.STDIO
        stdio_config = StdioConfig(command=command, args=args or [])
    elif url:
        if tt == TransportType.STDIO:
            tt = TransportType.SSE  # URL provided but transport defaulted to stdio.
        network_config = NetworkConfig(type=tt.value, url=url)  # type: ignore[arg-type]

    server = McpServer(
        name=name,
        transport=tt,
        stdio_config=stdio_config,
        network_config=network_config,
        source_tool="mcp-manager",
    )

    reg = _get_registry()
    reg.add(server)
    reg.save()

    console.print(f"[green]Added server:[/green] {name} ({tt.value})")


def remove_impl(name: str) -> None:
    """Remove a server from the mcp-manager registry."""
    track_command("remove")
    reg = _get_registry()
    if reg.remove(name):
        reg.save()
        console.print(f"[green]Removed:[/green] {name}")
    else:
        console.print(f"[yellow]Server not found in registry:[/yellow] {name}")
        raise McpManagerError(f"Server not found: {name}")


def test_server_impl(
    server_name: str,
    project: Path | None,
    json: bool,  # noqa: A002
) -> None:
    """Test a specific server's capabilities via full protocol handshake."""
    track_command("test")
    try:
        servers = _discover(project_dir=project)
    except McpManagerError as exc:
        console.print(f"[red]Discovery error:[/red] {exc}")
        raise

    matches = [s for s in servers if s.name == server_name]
    if not matches:
        console.print(f"[red]Server not found:[/red] {server_name}")
        raise McpManagerError(f"Server not found: {server_name}")

    server = matches[0]
    checker = HealthChecker(timeout=15)
    result = asyncio.run(checker.check(server))

    if json:
        console.print_json(
            json_mod.dumps(result.model_dump(mode="json", exclude_none=True), indent=2)
        )
        return

    console.print(f"\n[bold]Server:[/bold] {server.name}")
    console.print(f"[bold]Transport:[/bold] {server.transport.value}")
    console.print(f"[bold]Source:[/bold] {server.source_tool}")

    if server.stdio_config:
        cmd = f"{server.stdio_config.command} {' '.join(server.stdio_config.args)}"
        console.print(f"[bold]Command:[/bold] {cmd}")
    if server.network_config:
        console.print(f"[bold]URL:[/bold] {server.network_config.url}")

    icon = _STATUS_ICON.get(result.status, "")
    status = _STATUS_STYLE.get(result.status, str(result.status))
    console.print(f"\n{icon} [bold]Status:[/bold] {status}")

    if result.latency_ms is not None:
        console.print(f"[bold]Latency:[/bold] {result.latency_ms:.0f}ms")
    if result.protocol_version:
        console.print(f"[bold]Protocol:[/bold] {result.protocol_version}")
    if result.server_info.get("server_name"):
        console.print(f"[bold]Server Name:[/bold] {result.server_info['server_name']}")
    if result.server_info.get("server_version"):
        console.print(f"[bold]Server Version:[/bold] {result.server_info['server_version']}")
    if result.server_info.get("capabilities"):
        caps = list(result.server_info["capabilities"].keys())
        console.print(f"[bold]Capabilities:[/bold] {', '.join(caps) if caps else 'none'}")
    if result.error_message:
        console.print(f"[red]Error:[/red] {result.error_message}")
    console.print()


def export_config_impl(
    output: Path,
    fmt: str,
    tool: str | None,
    project: Path | None,
) -> None:
    """Export all discovered servers to a portable YAML/JSON file."""
    from mcp_manager.exporters import export_servers

    track_command("export")
    try:
        servers = _discover(tool=tool, project_dir=project)
    except McpManagerError as exc:
        console.print(f"[red]Discovery error:[/red] {exc}")
        raise

    if not servers:
        console.print("[dim]No servers to export.[/dim]")
        return

    try:
        export_servers(servers, output, fmt=fmt)
    except McpManagerError as exc:
        console.print(f"[red]Export error:[/red] {exc}")
        raise

    console.print(f"[green]Exported {len(servers)} server(s) to:[/green] {output}")


def import_config_impl(
    input_file: Path,
    dry_run: bool,
) -> None:
    """Import servers from a YAML/JSON file into the registry."""
    from mcp_manager.exporters import import_servers

    track_command("import")
    try:
        servers = import_servers(input_file)
    except McpManagerError as exc:
        console.print(f"[red]Import error:[/red] {exc}")
        raise

    if not servers:
        console.print("[dim]No servers found in file.[/dim]")
        return

    if dry_run:
        console.print(f"[dim]Would import {len(servers)} server(s):[/dim]")
        for s in servers:
            console.print(f"  {s.name} ({s.transport.value})")
        return

    reg = _get_registry()
    for s in servers:
        reg.add(s)
    reg.save()
    console.print(f"[green]Imported {len(servers)} server(s) to registry.[/green]")


def status_impl() -> None:
    """Show license status and available features."""
    from mcp_manager import __version__
    from mcp_manager.licensing import TIER_DEFINITIONS, get_license_info
    from mcp_manager.telemetry import track_command

    track_command("status")
    info = get_license_info()
    tier_config = TIER_DEFINITIONS[info.tier]

    console.print(f"\n[bold]mcp-manager {__version__}[/bold]")
    console.print(f"[bold]Tier:[/bold] {tier_config.name} ({tier_config.price_label})")

    if info.license_key:
        masked = info.license_key[:9] + "****-****"
        console.print(f"[bold]Key:[/bold] {masked}")
        valid_str = "[green]valid[/green]" if info.valid else "[red]invalid[/red]"
        console.print(f"[bold]Valid:[/bold] {valid_str}")

    console.print(f"\n[bold]Features:[/bold] {', '.join(tier_config.features)}")
    console.print()
