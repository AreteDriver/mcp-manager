"""Template command implementations (`mcp-manager template list`, `template use`)."""

from __future__ import annotations

from pathlib import Path

from mcp_manager.commands.common import console
from mcp_manager.exceptions import McpManagerError
from mcp_manager.project_config import DEFAULT_FILENAME
from mcp_manager.templates import get_template, get_template_description, list_templates


def template_list_impl() -> None:
    """List available built-in project templates."""
    names = list_templates()
    if not names:
        console.print("[dim]No built-in templates available.[/dim]")
        return

    console.print("[bold]Available templates:[/bold]")
    for name in names:
        desc = get_template_description(name)
        console.print(f"  [cyan]{name}[/cyan] — {desc}")


def template_use_impl(
    name: str,
    project_dir: Path,
    project_name: str,
    force: bool,
) -> None:
    """Scaffold a .mcp-manager.yml from a built-in template.

    Args:
        name: Template name.
        project_dir: Directory to write config into.
        project_name: Project name for the template.
        force: Overwrite existing config if True.
    """
    if name not in list_templates():
        console.print(
            f"[red]Unknown template:[/red] {name}. "
            "Run `mcp-manager template list` to see options."
        )
        raise McpManagerError(
            f"Unknown template: {name}. Run `mcp-manager template list` to see options."
        )

    config_path = project_dir / DEFAULT_FILENAME
    if config_path.exists() and not force:
        console.print(f"[red]{config_path} already exists.[/red] Use --force to overwrite.")
        raise McpManagerError(
            f"{config_path} already exists. Use --force to overwrite."
        )

    yaml_text = get_template(name, project_name=project_name)
    config_path.write_text(yaml_text, encoding="utf-8")
    console.print(f"[green]Created {config_path}[/green] from [cyan]{name}[/cyan] template")
