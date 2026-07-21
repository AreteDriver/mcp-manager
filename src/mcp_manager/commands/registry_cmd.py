"""Remote registry sync command implementations."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.table import Table

from mcp_manager.commands.common import console
from mcp_manager.exceptions import McpManagerError
from mcp_manager.models import ServerStatus
from mcp_manager.project_config import DEFAULT_FILENAME, load_servers_from_config
from mcp_manager.registry_sync import (
    compute_diff,
    fetch_remote_servers,
    merge_servers,
    verify_servers,
    write_project_servers,
)

registry_app = typer.Typer(name="registry", help="Remote registry sync commands.")


@registry_app.command(name="diff")
def registry_diff(
    url: str = typer.Argument(..., help="URL to remote registry YAML/JSON."),
    project_dir: Path | None = typer.Option(None, "--project-dir", "-p", help="Project directory."),
) -> None:
    """Preview changes from a remote registry without applying them."""
    from mcp_manager.telemetry import track_command

    track_command("registry_diff")

    project_dir = project_dir or Path.cwd()
    config_path = project_dir / DEFAULT_FILENAME
    if not config_path.exists():
        console.print(f"[red]Project config not found:[/red] {config_path}")
        raise typer.Exit(1)

    try:
        local = load_servers_from_config(config_path)
    except McpManagerError as exc:
        console.print(f"[red]Failed to load local config:[/red] {exc}")
        raise typer.Exit(1) from exc

    try:
        remote = fetch_remote_servers(url)
    except McpManagerError as exc:
        console.print(f"[red]Failed to fetch registry:[/red] {exc}")
        raise typer.Exit(1) from exc

    diff = compute_diff(local, remote)

    if not diff.added and not diff.updated and not diff.removed:
        console.print("[dim]No changes — local config matches remote registry.[/dim]")
        return

    table = Table(title=f"Registry Diff: {url}")
    table.add_column("Action", style="bold")
    table.add_column("Server", style="cyan")
    table.add_column("Transport")
    table.add_column("Details")

    for s in diff.added:
        table.add_row("[green]+ add[/green]", s.name, s.transport.value, "new from remote")
    for local_s, remote_s in diff.updated:
        table.add_row(
            "[yellow]~ change[/yellow]",
            local_s.name,
            remote_s.transport.value,
            "differs from remote",
        )
    for s in diff.removed:
        table.add_row("[red]- remove[/red]", s.name, s.transport.value, "not in remote")

    console.print(table)


@registry_app.command(name="pull")
def registry_pull(
    url: str = typer.Argument(..., help="URL to remote registry YAML/JSON."),
    project_dir: Path | None = typer.Option(None, "--project-dir", "-p", help="Project directory."),
    verify: bool = typer.Option(False, "--verify", "-v", help="Run health checks before merging."),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Preview without writing."),
    strategy: str = typer.Option(
        "union", "--strategy", "-s", help="Merge strategy: union or replace."
    ),
) -> None:
    """Pull server definitions from a remote registry into local project config."""
    from mcp_manager.telemetry import track_command

    track_command("registry_pull")

    project_dir = project_dir or Path.cwd()
    config_path = project_dir / DEFAULT_FILENAME
    if not config_path.exists():
        console.print(f"[red]Project config not found:[/red] {config_path}")
        raise typer.Exit(1)

    if strategy not in ("union", "replace"):
        console.print(f"[red]Unknown strategy:[/red] {strategy}. Use 'union' or 'replace'.")
        raise typer.Exit(1)

    try:
        local = load_servers_from_config(config_path)
    except McpManagerError as exc:
        console.print(f"[red]Failed to load local config:[/red] {exc}")
        raise typer.Exit(1) from exc

    try:
        remote = fetch_remote_servers(url)
    except McpManagerError as exc:
        console.print(f"[red]Failed to fetch registry:[/red] {exc}")
        raise typer.Exit(1) from exc

    if verify:
        console.print("[dim]Verifying remote servers...[/dim]")
        results = verify_servers(remote)
        failed = [
            (s, status, err)
            for s, status, err in results
            if status in (ServerStatus.ERROR, ServerStatus.UNREACHABLE)
        ]
        if failed:
            table = Table(title="Verification Failed")
            table.add_column("Server", style="cyan")
            table.add_column("Status", style="red")
            table.add_column("Error")
            for s, status, err in failed:
                table.add_row(s.name, status.value, err or "")
            console.print(table)
            console.print("[red]Aborting pull due to verification failures.[/red]")
            raise typer.Exit(1)
        console.print("[green]All remote servers passed verification.[/green]")

    merged = merge_servers(local, remote, strategy)

    if dry_run:
        console.print(f"[dim]Would write {len(merged)} servers to {config_path}[/dim]")
        return

    try:
        write_project_servers(config_path, merged)
    except McpManagerError as exc:
        console.print(f"[red]Failed to write project config:[/red] {exc}")
        raise typer.Exit(1) from exc

    console.print(
        f"[green]Updated {config_path} with {len(merged)} servers "
        f"({len(remote)} from remote).[/green]"
    )
