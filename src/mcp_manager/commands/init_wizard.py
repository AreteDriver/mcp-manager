"""Onboarding wizard implementation for `mcp-manager init`."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from mcp_manager.commands.common import console
from mcp_manager.discovery import ConfigDiscovery
from mcp_manager.exceptions import McpManagerError
from mcp_manager.project_config import DEFAULT_FILENAME
from mcp_manager.templates import get_template, list_templates


def _detect_ides() -> list[str]:
    """Detect installed IDEs by checking for their config files."""
    from mcp_manager.config import IDE_CONFIG_PATHS

    detected: list[str] = []
    for tool_name, path_str, _wrapper_key in IDE_CONFIG_PATHS:
        if Path(path_str).expanduser().is_file():
            detected.append(tool_name)
    return detected


def _import_existing_servers(ide: str) -> dict[str, dict[str, Any]]:
    """Read servers from an IDE config file and return as project-config dict."""
    discovery = ConfigDiscovery()
    servers = discovery.discover_tool(ide)
    result: dict[str, dict[str, Any]] = {}
    for s in servers:
        if s.stdio_config:
            result[s.name] = {
                "command": s.stdio_config.command,
                "args": s.stdio_config.args,
                "env": s.stdio_config.env,
                "tags": s.tags or ["imported"],
            }
        elif s.network_config:
            result[s.name] = {
                "type": s.network_config.type,
                "url": s.network_config.url,
                "headers": s.network_config.headers,
                "tags": s.tags or ["imported"],
            }
    return result


def _suggest_servers(ide: str | None) -> dict[str, dict[str, Any]]:
    """Return a small set of recommended servers based on IDE."""
    common: dict[str, dict[str, Any]] = {
        "filesystem": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem"],
            "env": {},
            "tags": ["core", "filesystem"],
        },
        "git": {
            "command": "uvx",
            "args": ["mcp-server-git", "--repository", "."],
            "env": {},
            "tags": ["core", "vcs"],
        },
    }
    return dict(common)


def _is_tty() -> bool:
    """Check if stdin is a TTY (interactive terminal)."""
    return sys.stdin.isatty()


def _prompt_yes_no(question: str, default: bool = True) -> bool:
    """Ask a yes/no question, respecting default."""
    if not _is_tty():
        return default
    suffix = " [Y/n]" if default else " [y/N]"
    answer = input(f"{question}{suffix}: ").strip().lower()
    if not answer:
        return default
    return answer in ("y", "yes")


def _prompt_choice(question: str, choices: list[str], default: str | None = None) -> str:
    """Ask user to pick from a list of choices."""
    if not _is_tty():
        return default or choices[0]
    for i, choice in enumerate(choices, 1):
        marker = " (default)" if choice == default else ""
        console.print(f"  [{i}] {choice}{marker}")
    while True:
        answer = input(f"{question}: ").strip()
        if not answer and default:
            return default
        if answer.isdigit():
            idx = int(answer) - 1
            if 0 <= idx < len(choices):
                return choices[idx]
        if answer in choices:
            return answer
        console.print("[red]Invalid choice, try again.[/red]")


def _warn_if_shared_files_ignored(project_dir: Path) -> None:
    """Warn when Git ignores files intended for team sharing."""
    gitignore = project_dir / ".gitignore"
    entries = [".mcp-manager.yml", ".mcp-manager.lock"]
    if not gitignore.is_file():
        return

    ignored = set(gitignore.read_text(encoding="utf-8").splitlines()).intersection(entries)
    if ignored:
        console.print(
            "[yellow]Team config is ignored by Git:[/yellow] "
            + ", ".join(sorted(ignored))
            + "\n[dim]Remove those entries from .gitignore to share reproducible MCP config.[/dim]"
        )


def init_wizard_impl(
    ide: str | None,
    template: str | None,
    import_existing: bool,
    project_name: str,
    yes: bool,
) -> None:
    """Run the onboarding wizard to scaffold a new .mcp-manager.yml."""
    project_dir = Path.cwd()
    config_path = project_dir / DEFAULT_FILENAME

    if config_path.exists():
        console.print(f"[yellow]{config_path} already exists.[/yellow]")
        if not yes and _is_tty():
            overwrite = _prompt_yes_no("Overwrite?", default=False)
            if not overwrite:
                console.print("[dim]Skipped.[/dim]")
                return
        elif not yes:
            console.print("[dim]Use --yes to overwrite.[/dim]")
            return

    # Detect IDE
    detected = _detect_ides()
    selected_ide = ide
    if selected_ide is None and detected:
        if len(detected) == 1:
            selected_ide = detected[0]
            console.print(f"[green]Detected IDE:[/green] {selected_ide}")
        elif _is_tty():
            selected_ide = _prompt_choice("Which IDE are you using?", detected, default=detected[0])
        else:
            selected_ide = detected[0]

    # Template selection
    available_templates = list_templates()
    selected_template = template
    if selected_template is None:
        if _is_tty():
            selected_template = _prompt_choice(
                "Pick a template", available_templates, default="python"
            )
        else:
            selected_template = "python"
    if selected_template not in available_templates:
        console.print(f"[red]Unknown template:[/red] {selected_template}")
        raise McpManagerError(f"Unknown template: {selected_template}")

    # Build servers dict
    servers: dict[str, dict[str, Any]] = {}

    # Import existing if requested or auto-detected
    if import_existing and selected_ide:
        imported = _import_existing_servers(selected_ide)
        servers.update(imported)
        if imported:
            console.print(f"[green]Imported {len(imported)} server(s)[/green] from {selected_ide}")
    elif selected_ide and not yes and _is_tty():
        if _prompt_yes_no(f"Import existing servers from {selected_ide}?", default=True):
            imported = _import_existing_servers(selected_ide)
            servers.update(imported)
            if imported:
                console.print(
                    f"[green]Imported {len(imported)} server(s)[/green] from {selected_ide}"
                )

    # Add recommended servers if template is used and no import
    if not servers:
        suggested = _suggest_servers(selected_ide)
        servers.update(suggested)
        console.print(f"[green]Added {len(suggested)} recommended server(s).[/green]")

    # Write config
    yaml_text = get_template(selected_template, project_name=project_name)
    # Parse template to inject imported/suggested servers
    import yaml as yaml_mod

    parsed = yaml_mod.safe_load(yaml_text)
    if isinstance(parsed, dict):
        parsed["servers"] = servers
        yaml_text = yaml_mod.dump(parsed, sort_keys=False, allow_unicode=True)

    config_path.write_text(yaml_text, encoding="utf-8")
    console.print(f"[green]Created {config_path}[/green] ({selected_template} template)")

    _warn_if_shared_files_ignored(project_dir)
