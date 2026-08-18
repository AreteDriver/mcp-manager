"""Server install command implementation."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from mcp_manager.adapters import ConfigScope
from mcp_manager.commands.common import (
    _STATUS_ICON,
    _STATUS_STYLE,
    console,
)
from mcp_manager.discovery import ConfigDiscovery
from mcp_manager.exceptions import McpManagerError, WritebackError
from mcp_manager.health import HealthChecker
from mcp_manager.models import ServerStatus
from mcp_manager.registry import ServerRegistry
from mcp_manager.telemetry import track_command
from mcp_manager.writeback import ConfigWriteback


def install_impl(
    name: str,
    ide: str | None,
    all_ides: bool,
    create: bool,
    dry_run: bool,
    force: bool,
    verify: bool,
    project: Path | None,
    scope: str = "user",
) -> None:
    """Install a single server from the registry into IDE config(s)."""
    track_command("server_install")

    # 1. Resolve server from registry.
    reg = _get_registry()
    entry = reg.get(name)
    if entry is None:
        console.print(
            f"[red]Server not found in registry:[/red] {name}\n"
            f"[dim]Add it first with:[/dim] mcp-manager add {name} --command ..."
        )
        raise McpManagerError(f"Server not found in registry: {name}")

    server = entry.server

    # 2. Determine target IDEs.
    writeback = ConfigWriteback()
    supported = set(writeback.get_supported_ides())
    if scope not in {"user", "project"}:
        raise McpManagerError("Scope must be 'user' or 'project'")
    target_scope: ConfigScope = "project" if scope == "project" else "user"
    target_project = project or Path.cwd()

    if ide:
        if ide not in supported:
            console.print(
                f"[red]Unknown IDE:[/red] {ide}\n"
                f"[dim]Supported:[/dim] {', '.join(sorted(supported))}"
            )
            raise McpManagerError(f"Unknown IDE: {ide}")
        targets = [ide]
    elif all_ides:
        targets = [
            name for name in sorted(supported) if writeback.supports_scope(name, target_scope)
        ]
    else:
        targets = _auto_detect_targets(
            writeback,
            supported,
            scope=target_scope,
            project_dir=target_project,
        )

    if not targets:
        console.print(
            "[yellow]No client configs detected.[/yellow]\n"
            "[dim]Use --ide <name> to target a specific client, or --all to target all.[/dim]"
        )
        raise McpManagerError("No client configs detected")

    # 3. Install per-target.
    results: list[tuple[str, Path | None, str, str | None]] = []
    # (ide_name, config_path_or_None, status, detail)

    for target_ide in targets:
        for warning in writeback.translation_warnings(target_ide, [server]):
            console.print(f"[yellow]{target_ide} translation warning:[/yellow] {warning}")
        result = _install_to_ide(
            writeback=writeback,
            ide=target_ide,
            server=server,
            create=create,
            dry_run=dry_run,
            force=force,
            scope=target_scope,
            project_dir=target_project,
        )
        results.append((target_ide, *result))

    # 4. Render results.
    _render_results(results, dry_run)

    # 5. Optional verify.
    if verify and not dry_run:
        _verify_install(results, server)


def _get_registry() -> ServerRegistry:
    """Load the mcp-manager registry."""
    reg = ServerRegistry()
    reg.load()
    return reg


def _auto_detect_targets(
    writeback: ConfigWriteback,
    supported: set[str],
    *,
    scope: ConfigScope = "user",
    project_dir: Path | None = None,
) -> list[str]:
    """Return IDEs whose config files already exist on disk."""
    targets = []
    for ide_name in sorted(supported):
        try:
            path = writeback.get_config_path(ide_name, scope=scope, project_dir=project_dir)
        except WritebackError:
            continue
        if path is not None and path.is_file():
            targets.append(ide_name)
    return targets


def _install_to_ide(
    writeback: ConfigWriteback,
    ide: str,
    server: Any,  # McpServer — avoid circular import if any
    create: bool,
    dry_run: bool,
    force: bool,
    scope: ConfigScope = "user",
    project_dir: Path | None = None,
) -> tuple[Path | None, str, str | None]:
    """Install a single server to a single IDE. Returns (path, status, detail)."""
    from mcp_manager.models import McpServer

    assert isinstance(server, McpServer)

    # Check if config exists.
    config_path = _get_config_path(writeback, ide, scope=scope, project_dir=project_dir)
    config_exists = config_path is not None and config_path.exists()

    if not config_exists and not create:
        return (config_path, "skipped", "config missing (use --create)")

    # Check if already installed.
    if config_exists and not force:
        # Use discovery to see if this server is already in the IDE.
        discovery = ConfigDiscovery()
        existing = discovery.discover_tool(ide, scope=scope, project_dir=project_dir)
        if any(s.name == server.name for s in existing):
            return (config_path, "skipped", "already installed (use --force)")

    try:
        if dry_run:
            _ = writeback.preview(ide, [server], scope=scope, project_dir=project_dir)
            return (config_path, "dry-run", None)

        path = writeback.write_servers(
            ide,
            [server],
            create_if_missing=create,
            scope=scope,
            project_dir=project_dir,
        )
        return (path, "installed", None)
    except WritebackError as exc:
        return (config_path, "error", str(exc))


def _get_config_path(
    writeback: ConfigWriteback,
    ide: str,
    *,
    scope: ConfigScope = "user",
    project_dir: Path | None = None,
) -> Path | None:
    """Return the expected config path for an IDE, or None if unknown."""
    return writeback.get_config_path(ide, scope=scope, project_dir=project_dir)


def _render_results(
    results: list[tuple[str, Path | None, str, str | None]],
    dry_run: bool,
) -> None:
    """Print a Rich table of install results."""
    action = "Would install" if dry_run else "Installed"
    count = sum(1 for _, _, status, _ in results if status in ("installed", "dry-run"))
    console.print(f"\n{action} to {count} client target(s):\n")

    for ide_name, path, status, detail in results:
        if status == "installed":
            icon = "[green]✅[/green]"
            line = f"  {icon} {ide_name:12} — {path}"
        elif status == "dry-run":
            icon = "[dim]📝[/dim]"
            line = f"  {icon} {ide_name:12} — {path or 'new config'}"
        elif status == "skipped":
            icon = "[yellow]⚠️[/yellow]"
            line = f"  {icon} {ide_name:12} — skipped ({detail})"
        else:
            icon = "[red]❌[/red]"
            line = f"  {icon} {ide_name:12} — error: {detail}"
        console.print(line)

    console.print()


def _verify_install(
    results: list[tuple[str, Path | None, str, str | None]],
    server: Any,
) -> None:
    """Run health check on the installed server and report."""
    from mcp_manager.models import McpServer

    assert isinstance(server, McpServer)

    # Only verify if at least one IDE succeeded.
    succeeded = any(status == "installed" for _, _, status, _ in results)
    if not succeeded:
        console.print("[dim]Skipping verify: no successful installs.[/dim]")
        return

    checker = HealthChecker(timeout=10)
    result = asyncio.run(checker.check(server))

    icon = _STATUS_ICON.get(result.status, "")
    status = _STATUS_STYLE.get(result.status, str(result.status))
    latency = f" ({result.latency_ms:.0f}ms)" if result.latency_ms is not None else ""

    if result.status == ServerStatus.HEALTHY:
        console.print(f"{icon} Verify: {status}{latency}\n")
    else:
        console.print(f"{icon} Verify: {status}{latency}")
        if result.error_message:
            console.print(f"[red]  {result.error_message}[/red]")
        console.print()
