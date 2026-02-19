"""CLI entry point for mcp-manager."""

from __future__ import annotations

import asyncio
import json as json_mod
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from mcp_manager import __version__
from mcp_manager.discovery import ConfigDiscovery
from mcp_manager.exceptions import McpManagerError
from mcp_manager.exporters import export_servers, import_servers
from mcp_manager.health import HealthChecker
from mcp_manager.mapper import build_server_map
from mcp_manager.models import McpServer, NetworkConfig, ServerStatus, StdioConfig, TransportType
from mcp_manager.registry import ServerRegistry

app = typer.Typer(
    name="mcp-manager",
    help="Manage MCP servers across agentic IDEs.",
)
console = Console()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Root callback
# ---------------------------------------------------------------------------


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        is_eager=True,
        help="Show version and exit.",
    ),
) -> None:
    """Manage MCP servers across agentic IDEs."""
    if version:
        console.print(f"mcp-manager {__version__}")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        console.print(ctx.get_help())
        raise typer.Exit()


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


@app.command(name="list")
def list_servers(
    tool: str | None = typer.Option(None, "--tool", "-t", help="Filter by IDE/tool name."),
    transport: str | None = typer.Option(None, "--transport", help="Filter by transport type."),
    project: Path | None = typer.Option(None, "--project", "-p", help="Project dir for .mcp.json."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """List all configured MCP servers across tools."""
    try:
        servers = _discover(tool=tool, project_dir=project)
    except McpManagerError as exc:
        console.print(f"[red]Discovery error:[/red] {exc}")
        raise typer.Exit(1) from exc

    # Filter by transport.
    if transport:
        try:
            tt = TransportType(transport.lower())
        except ValueError:
            console.print(f"[red]Unknown transport:[/red] {transport}")
            raise typer.Exit(1) from None
        servers = [s for s in servers if s.transport == tt]

    if not servers:
        console.print("[dim]No MCP servers found.[/dim]")
        raise typer.Exit()

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


# ---------------------------------------------------------------------------
# map
# ---------------------------------------------------------------------------


@app.command(name="map")
def map_servers(
    project: Path | None = typer.Option(None, "--project", "-p", help="Project dir for .mcp.json."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Show which tools/IDEs use which servers."""
    try:
        servers = _discover(project_dir=project)
    except McpManagerError as exc:
        console.print(f"[red]Discovery error:[/red] {exc}")
        raise typer.Exit(1) from exc

    if not servers:
        console.print("[dim]No MCP servers found.[/dim]")
        raise typer.Exit()

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


# ---------------------------------------------------------------------------
# health
# ---------------------------------------------------------------------------

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


@app.command()
def health(
    server_name: str | None = typer.Option(None, "--server", "-s", help="Check specific server."),
    timeout: int = typer.Option(10, "--timeout", help="Timeout per server in seconds."),
    project: Path | None = typer.Option(None, "--project", "-p", help="Project dir for .mcp.json."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Health check all servers (status, latency, version)."""
    try:
        servers = _discover(project_dir=project)
    except McpManagerError as exc:
        console.print(f"[red]Discovery error:[/red] {exc}")
        raise typer.Exit(1) from exc

    if server_name:
        servers = [s for s in servers if s.name == server_name]

    if not servers:
        console.print("[dim]No MCP servers found.[/dim]")
        raise typer.Exit()

    checker = HealthChecker(timeout=timeout)
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


# ---------------------------------------------------------------------------
# add / remove
# ---------------------------------------------------------------------------


def _get_registry(path: Path | None = None) -> ServerRegistry:
    """Load the mcp-manager registry."""
    reg = ServerRegistry(path=path)
    reg.load()
    return reg


@app.command()
def add(
    name: str = typer.Argument(..., help="Server name."),
    command: str | None = typer.Option(None, "--command", "-c", help="Command for stdio server."),
    url: str | None = typer.Option(None, "--url", "-u", help="URL for SSE/HTTP server."),
    transport: str = typer.Option("stdio", "--transport", "-t", help="Transport type."),
    args: list[str] | None = typer.Option(None, "--arg", help="Args for stdio (repeatable)."),
) -> None:
    """Add a new MCP server to the mcp-manager registry."""
    if command and url:
        console.print("[red]Specify --command (stdio) or --url (network), not both.[/red]")
        raise typer.Exit(1)

    if not command and not url:
        console.print("[red]Specify --command for stdio or --url for SSE/HTTP.[/red]")
        raise typer.Exit(1)

    try:
        tt = TransportType(transport.lower())
    except ValueError:
        console.print(f"[red]Unknown transport:[/red] {transport}")
        raise typer.Exit(1) from None

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


@app.command()
def remove(
    name: str = typer.Argument(..., help="Server name to remove."),
) -> None:
    """Remove a server from the mcp-manager registry."""
    reg = _get_registry()
    if reg.remove(name):
        reg.save()
        console.print(f"[green]Removed:[/green] {name}")
    else:
        console.print(f"[yellow]Server not found in registry:[/yellow] {name}")
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# export / import
# ---------------------------------------------------------------------------


@app.command(name="export")
def export_config(
    output: Path = typer.Argument(..., help="Output file path."),
    fmt: str = typer.Option("yaml", "--format", "-f", help="Export format (yaml|json)."),
    tool: str | None = typer.Option(None, "--tool", "-t", help="Export only from specific tool."),
    project: Path | None = typer.Option(None, "--project", "-p", help="Project dir."),
) -> None:
    """Export all discovered servers to a portable YAML/JSON file."""
    try:
        servers = _discover(tool=tool, project_dir=project)
    except McpManagerError as exc:
        console.print(f"[red]Discovery error:[/red] {exc}")
        raise typer.Exit(1) from exc

    if not servers:
        console.print("[dim]No servers to export.[/dim]")
        raise typer.Exit()

    try:
        export_servers(servers, output, fmt=fmt)
    except McpManagerError as exc:
        console.print(f"[red]Export error:[/red] {exc}")
        raise typer.Exit(1) from exc

    console.print(f"[green]Exported {len(servers)} server(s) to:[/green] {output}")


@app.command(name="import")
def import_config(
    input_file: Path = typer.Argument(..., help="Input YAML/JSON file."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be imported."),
) -> None:
    """Import servers from a YAML/JSON file into the registry."""
    try:
        servers = import_servers(input_file)
    except McpManagerError as exc:
        console.print(f"[red]Import error:[/red] {exc}")
        raise typer.Exit(1) from exc

    if not servers:
        console.print("[dim]No servers found in file.[/dim]")
        raise typer.Exit()

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


# ---------------------------------------------------------------------------
# test (capability probing)
# ---------------------------------------------------------------------------


@app.command(name="test")
def test_server(
    server_name: str = typer.Argument(..., help="Name of server to test."),
    project: Path | None = typer.Option(None, "--project", "-p", help="Project dir."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Test a specific server's capabilities via full protocol handshake."""
    try:
        servers = _discover(project_dir=project)
    except McpManagerError as exc:
        console.print(f"[red]Discovery error:[/red] {exc}")
        raise typer.Exit(1) from exc

    matches = [s for s in servers if s.name == server_name]
    if not matches:
        console.print(f"[red]Server not found:[/red] {server_name}")
        raise typer.Exit(1)

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


# ---------------------------------------------------------------------------
# status (license info)
# ---------------------------------------------------------------------------


@app.command()
def status() -> None:
    """Show license status and available features."""
    from mcp_manager.licensing import TIER_DEFINITIONS, get_license_info

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
