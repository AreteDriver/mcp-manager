"""Marketplace command implementations."""

from __future__ import annotations

import json as json_mod
from pathlib import Path

import yaml
from rich.table import Table

from mcp_manager.commands.common import console
from mcp_manager.exceptions import McpManagerError


def search_marketplace_impl(
    query: str,
    category: str,
    include_unverified: bool,
    json: bool,  # noqa: A002
) -> None:
    """Search the MCP server marketplace."""
    from mcp_manager.marketplace import MarketplaceError, load_index
    from mcp_manager.telemetry import track_command

    track_command("search")
    try:
        index = load_index()
    except MarketplaceError as exc:
        console.print(f"[red]Marketplace error:[/red] {exc}")
        raise

    results = index.search(
        query=query or None,
        category=category or None,
        verified_only=not include_unverified,
    )

    if json:
        data = {
            "query": query,
            "category": category or None,
            "verified_only": not include_unverified,
            "servers": [s.model_dump(mode="json") for s in results],
        }
        console.print_json(json_mod.dumps(data, indent=2))
        return

    if not results:
        console.print("[dim]No marketplace servers found.[/dim]")
        return

    table = Table(title="MCP Server Marketplace")
    table.add_column("Name", style="cyan")
    table.add_column("Description")
    table.add_column("Category")
    table.add_column("Quality")

    for server in results:
        badge = "⬜"
        if server.quality.verified and server.quality.health_pass_rate >= 0.9:
            badge = "🟢"
        elif server.quality.verified and server.quality.health_pass_rate >= 0.5:
            badge = "🟡"
        elif server.quality.verified:
            badge = "🔴"
        quality_str = f"{badge} {server.quality.health_pass_rate:.0%}"
        categories_str = ", ".join(server.categories)
        table.add_row(server.display_name, server.description, categories_str, quality_str)

    console.print(table)


def marketplace_info_impl(name: str, json: bool) -> None:  # noqa: A002
    """Show detailed info for a marketplace server."""
    from mcp_manager.marketplace import MarketplaceError, load_index
    from mcp_manager.telemetry import track_command

    track_command("info")
    try:
        index = load_index()
    except MarketplaceError as exc:
        console.print(f"[red]Marketplace error:[/red] {exc}")
        raise

    server = index.get(name)
    if not server:
        console.print(f"[red]Server not found:[/red] {name}")
        raise McpManagerError(f"Server not found: {name}")

    if json:
        console.print_json(json_mod.dumps(server.model_dump(mode="json"), indent=2))
        return

    console.print(f"[bold]{server.display_name}[/bold]")
    console.print(f"  Name:       {server.name}")
    console.print(f"  Repository: {server.repository}")
    console.print(f"  License:    {server.quality.license}")
    console.print(f"  Verified:   {'✅' if server.quality.verified else '⬜'}")
    console.print(f"  Health:     {server.quality.health_pass_rate:.0%}")
    console.print(f"  Tools:      {server.quality.tool_count}")
    console.print(f"  Categories: {', '.join(server.categories)}")
    console.print()
    console.print(f"  {server.description}")
    console.print()
    console.print("[bold]Install:[/bold]")
    console.print(f"  command: {server.install_spec.get('command')}")
    console.print(f"  args:    {server.install_spec.get('args', [])}")
    env = server.install_spec.get("env", {})
    if env:
        console.print("  env:")
        for k, v in env.items():
            console.print(f"    {k}: {v}")


def marketplace_install_impl(
    name: str,
    path: Path | None,
    dry_run: bool,
    no_prompt: bool,
    lock: bool,  # noqa: A002
) -> None:
    """Install a marketplace server into .mcp-manager.yml."""
    from mcp_manager.lockfile import generate_lockfile, write_lockfile
    from mcp_manager.marketplace import MarketplaceError, install_to_project, load_index
    from mcp_manager.project_config import load_servers_from_config
    from mcp_manager.telemetry import track_command

    track_command("install")
    target = path or Path.cwd()
    if target.is_file():
        target = target.parent

    try:
        index = load_index()
    except MarketplaceError as exc:
        console.print(f"[red]Marketplace error:[/red] {exc}")
        raise

    server = index.get(name)
    if not server:
        console.print(f"[red]Server not found:[/red] {name}")
        raise McpManagerError(f"Server not found: {name}")

    try:
        config_path = install_to_project(
            server,
            target,
            dry_run=dry_run,
            interactive=not no_prompt,
        )
    except MarketplaceError as exc:
        console.print(f"[red]Install error:[/red] {exc}")
        raise

    if dry_run:
        console.print(f"[dim]Dry-run: would add {name!r} to {config_path}[/dim]")
    else:
        console.print(f"[green]Added {name!r} to {config_path}[/green]")
        placeholders = server._env_var_placeholders()
        if placeholders and no_prompt:
            console.print(f"[yellow]Remember to set env vars:[/yellow] {', '.join(placeholders)}")

        if lock:
            try:
                servers = load_servers_from_config(config_path)
                lockfile = generate_lockfile(servers)
                lockfile_path = config_path.parent / ".mcp-manager.lock"
                write_lockfile(lockfile_path, lockfile)
                console.print(f"[green]Wrote lockfile:[/green] {lockfile_path}")
            except (McpManagerError, OSError, yaml.YAMLError) as exc:
                console.print(f"[yellow]Lockfile warning:[/yellow] {exc}")


def marketplace_refresh_impl(
    output: Path,
    timeout: int,
    dry_run: bool,
) -> None:
    """Refresh quality scores for all marketplace servers."""
    from mcp_manager.marketplace import MarketplaceError, refresh_marketplace
    from mcp_manager.telemetry import track_command

    track_command("marketplace-refresh")
    try:
        updated = refresh_marketplace(
            output,
            timeout=timeout,
            dry_run=dry_run,
            progress=lambda message: console.print(f"[dim]{message}[/dim]"),
        )
    except MarketplaceError as exc:
        console.print(f"[red]Refresh error:[/red] {exc}")
        raise

    if dry_run:
        console.print(f"[dim]Dry-run: would update marketplace scores in {output}.[/dim]")
    elif updated:
        console.print(f"[green]Updated marketplace scores in {output}.[/green]")
    else:
        console.print("[dim]No changes to marketplace scores.[/dim]")
