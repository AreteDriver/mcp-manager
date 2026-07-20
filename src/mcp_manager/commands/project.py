"""Project-scoped MCP configuration commands."""

from __future__ import annotations

from pathlib import Path

import typer

from mcp_manager.commands.common import console
from mcp_manager.exceptions import McpManagerError

project_app = typer.Typer(help="Manage project-scoped MCP configurations.")


@project_app.command(name="init")
def project_init(
    name: str = typer.Option("my-project", "--name", "-n", help="Project name for the template."),
    path: Path | None = typer.Option(
        None, "--path", "-p", help="Directory to create .mcp-manager.yml in."
    ),
) -> None:
    """Scaffold a new .mcp-manager.yml in the target directory."""
    from mcp_manager.project_config import init_project_config
    from mcp_manager.telemetry import track_command

    track_command("project_init")
    try:
        target = init_project_config(path, project_name=name)
        console.print(f"[green]Created[/green] {target}")
    except McpManagerError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1) from exc


@project_app.command(name="validate")
def project_validate(
    path: Path | None = typer.Option(
        None, "--path", "-p", help="Path to .mcp-manager.yml or its directory."
    ),
) -> None:
    """Validate a .mcp-manager.yml file."""
    from mcp_manager.project_config import DEFAULT_FILENAME, validate_project_config

    target = path or Path.cwd()
    if target.is_dir():
        target = target / DEFAULT_FILENAME

    errors = validate_project_config(target)
    if errors:
        console.print(f"[red]{len(errors)} error(s) found:[/red]")
        for err in errors:
            console.print(f"  • {err}")
        raise typer.Exit(1)
    else:
        console.print(f"[green]{target} is valid.[/green]")


@project_app.command(name="export")
def project_export(
    ide: str = typer.Option(..., "--ide", "-i", help="IDE to export to."),
    path: Path | None = typer.Option(
        None, "--path", "-p", help="Path to .mcp-manager.yml or its directory."
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview changes without writing."),
    create: bool = typer.Option(False, "--create", help="Create IDE config if missing."),
) -> None:
    """Export project config to an IDE config file."""
    from mcp_manager.project_config import DEFAULT_FILENAME, export_to_ide

    target = path or Path.cwd()
    if target.is_dir():
        target = target / DEFAULT_FILENAME

    try:
        out_path = export_to_ide(target, ide, dry_run=dry_run, create=create)
        if dry_run:
            console.print(f"[dim]Dry-run: would export to[/dim] {out_path}")
        else:
            console.print(f"[green]Exported to[/green] {out_path}")
    except McpManagerError as exc:
        console.print(f"[red]Export error:[/red] {exc}")
        raise typer.Exit(1) from exc
