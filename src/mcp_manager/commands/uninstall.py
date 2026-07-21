"""Server uninstall command implementation."""

from __future__ import annotations

import asyncio
from pathlib import Path

from mcp_manager.commands.common import (
    console,
)
from mcp_manager.discovery import ConfigDiscovery
from mcp_manager.exceptions import McpManagerError, WritebackError
from mcp_manager.health import HealthChecker
from mcp_manager.models import McpServer, ServerStatus
from mcp_manager.telemetry import track_command
from mcp_manager.writeback import ConfigWriteback


def uninstall_impl(
    name: str,
    ide: str | None,
    all_ides: bool,
    dry_run: bool,
    force: bool,
    project: Path | None,
) -> None:
    """Uninstall a server from IDE config(s)."""
    track_command("server_uninstall")

    # 1. Discover which IDEs have this server.
    discovery = ConfigDiscovery()
    all_servers = discovery.discover_all(project_dir=project)
    matches = [s for s in all_servers if s.name == name]

    if not matches:
        console.print(
            f"[yellow]Server not found in any IDE config:[/yellow] {name}\n"
            f"[dim]Use `mcp-manager list` to see configured servers.[/dim]"
        )
        raise McpManagerError(f"Server not found in any IDE config: {name}")

    # Group by source_tool (IDE).
    ide_to_servers: dict[str, list[McpServer]] = {}
    for s in matches:
        ide_to_servers.setdefault(s.source_tool, []).append(s)

    # 2. Determine target IDEs.
    writeback = ConfigWriteback()
    supported = set(writeback.get_supported_ides())

    if ide:
        if ide not in supported:
            console.print(
                f"[red]Unknown IDE:[/red] {ide}\n"
                f"[dim]Supported:[/dim] {', '.join(sorted(supported))}"
            )
            raise McpManagerError(f"Unknown IDE: {ide}")
        targets = [ide]
    elif all_ides:
        targets = sorted(ide_to_servers.keys())
    else:
        targets = sorted(ide_to_servers.keys())

    if not targets:
        console.print(f"[yellow]Server {name!r} not found in any supported IDE config.[/yellow]")
        raise McpManagerError(f"Server not found in any supported IDE config: {name}")

    # 3. Pre-flight health check (warn unless --force).
    if not force and not dry_run:
        _warn_if_healthy(matches)

    # 4. Uninstall per-target.
    results: list[tuple[str, Path | None, list[str], str | None]] = []
    # (ide_name, config_path_or_None, removed_names, detail_or_None)

    for target_ide in targets:
        result = _uninstall_from_ide(
            writeback=writeback,
            ide=target_ide,
            server_name=name,
            dry_run=dry_run,
        )
        results.append((target_ide, *result))

    # 5. Render results.
    _render_uninstall_results(results, dry_run)


def _warn_if_healthy(matches: list[McpServer]) -> None:
    """Run a quick health check and warn if the server is still healthy."""
    # Pick the first match for health check; they should all be the same server.
    server = matches[0]
    checker = HealthChecker(timeout=5)
    try:
        result = asyncio.run(checker.check(server))
    except Exception:
        return  # Ignore health check failures during uninstall.

    if result.status == ServerStatus.HEALTHY:
        console.print(
            f"[yellow]⚠️  Warning:[/yellow] {server.name} is still {result.status.value}.\n"
            f"   Use [bold]--force[/bold] to uninstall anyway.\n"
        )


def _uninstall_from_ide(
    writeback: ConfigWriteback,
    ide: str,
    server_name: str,
    dry_run: bool,
) -> tuple[Path | None, list[str], str | None]:
    """Remove a server from a single IDE. Returns (path, removed, detail)."""
    try:
        path, removed = writeback.remove_servers(ide, {server_name}, dry_run=dry_run)
        if not removed:
            return (path, [], "server not found in this IDE config")
        return (path, removed, None)
    except WritebackError as exc:
        return (None, [], str(exc))


def _render_uninstall_results(
    results: list[tuple[str, Path | None, list[str], str | None]],
    dry_run: bool,
) -> None:
    """Print uninstall results."""
    action = "Would uninstall" if dry_run else "Uninstalled"
    count = sum(1 for _, _, removed, _ in results if removed)
    console.print(f"\n{action} from {count} IDE(s):\n")

    for ide_name, path, removed, detail in results:
        if removed:
            icon = "[green]✅[/green]"
            line = f"  {icon} {ide_name:12} — {path}"
        elif detail:
            icon = "[yellow]⚠️[/yellow]"
            line = f"  {icon} {ide_name:12} — skipped ({detail})"
        else:
            icon = "[dim]—[/dim]"
            line = f"  {icon} {ide_name:12} — no change"
        console.print(line)

    console.print()
