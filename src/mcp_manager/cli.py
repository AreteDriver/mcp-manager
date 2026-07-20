"""CLI entry point for mcp-manager."""

from __future__ import annotations

from pathlib import Path

import typer

from mcp_manager import __version__
from mcp_manager.commands.common import console
from mcp_manager.commands.init_wizard import init_wizard_impl
from mcp_manager.commands.marketplace import (
    marketplace_info_impl,
    marketplace_install_impl,
    marketplace_refresh_impl,
    search_marketplace_impl,
)
from mcp_manager.commands.ops import (
    lock_versions_impl,
    monitor_servers_impl,
    stats_impl,
    sync_servers_impl,
    validate_ci_impl,
)
from mcp_manager.commands.project import project_app
from mcp_manager.commands.servers import (
    add_impl,
    export_config_impl,
    health_impl,
    import_config_impl,
    list_servers_impl,
    map_servers_impl,
    remove_impl,
    status_impl,
    test_server_impl,
)
from mcp_manager.commands.templates_cmd import (
    template_list_impl,
    template_use_impl,
)
from mcp_manager.exceptions import McpManagerError

app = typer.Typer(
    name="mcp-manager",
    help="Manage MCP servers across agentic IDEs.",
)
app.add_typer(project_app, name="project")

# Template sub-typer
template_app = typer.Typer(name="template", help="Project template commands.")
app.add_typer(template_app, name="template")


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


@app.command(name="init")
def init_wizard(
    ide: str | None = typer.Option(
        None, "--ide", "-i", help="IDE name (auto-detected if omitted)."
    ),
    template: str | None = typer.Option(
        None, "--template", "-t", help="Template name (default: python)."
    ),
    import_existing: bool = typer.Option(
        False, "--import-existing", help="Import servers from existing IDE config."
    ),
    project_name: str = typer.Option(
        "my-project", "--project-name", help="Project name for the config."
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Skip confirmations and overwrite if needed."
    ),
) -> None:
    """Onboarding wizard: scaffold .mcp-manager.yml for a new project."""
    try:
        init_wizard_impl(
            ide=ide,
            template=template,
            import_existing=import_existing,
            project_name=project_name,
            yes=yes,
        )
    except McpManagerError:
        raise typer.Exit(1) from None


@template_app.command(name="list")
def template_list() -> None:
    """List available built-in project templates."""
    template_list_impl()


@template_app.command(name="use")
def template_use(
    name: str = typer.Argument(..., help="Template name (e.g. 'python', 'data')."),
    project_dir: Path | None = typer.Option(
        None, "--project-dir", "-p", help="Directory to create config in."
    ),
    project_name: str = typer.Option(
        "my-project", "--project-name", help="Project name for the template."
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Overwrite existing config."
    ),
) -> None:
    """Scaffold a .mcp-manager.yml from a built-in template."""
    target_dir = project_dir or Path.cwd()
    try:
        template_use_impl(
            name=name,
            project_dir=target_dir,
            project_name=project_name,
            force=force,
        )
    except McpManagerError:
        raise typer.Exit(1) from None


@app.command(name="list")
def list_servers(
    tool: str | None = typer.Option(None, "--tool", "-t", help="Filter by IDE/tool name."),
    transport: str | None = typer.Option(None, "--transport", help="Filter by transport type."),
    project: Path | None = typer.Option(None, "--project", "-p", help="Project dir for .mcp.json."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
    tag: list[str] | None = typer.Option(
        None, "--tag", help="Include servers with this tag (repeatable)."
    ),
    exclude_tag: list[str] | None = typer.Option(
        None, "--exclude-tag", help="Exclude servers with this tag (repeatable)."
    ),
) -> None:
    """List all configured MCP servers across tools."""
    try:
        list_servers_impl(
            tool=tool, transport=transport, project=project, json=json,
            tag=tag, exclude_tag=exclude_tag,
        )
    except McpManagerError:
        raise typer.Exit(1) from None


@app.command(name="map")
def map_servers(
    project: Path | None = typer.Option(None, "--project", "-p", help="Project dir for .mcp.json."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Show which tools/IDEs use which servers."""
    try:
        map_servers_impl(project=project, json=json)
    except McpManagerError:
        raise typer.Exit(1) from None


@app.command()
def health(
    server_name: str | None = typer.Option(None, "--server", "-s", help="Check specific server."),
    timeout: int = typer.Option(10, "--timeout", help="Timeout per server in seconds."),
    project: Path | None = typer.Option(None, "--project", "-p", help="Project dir for .mcp.json."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
    deep: bool = typer.Option(
        False, "--deep", help="Run deep checks (tools/list validation, dependency checks)."
    ),
    tag: list[str] | None = typer.Option(
        None, "--tag", help="Include servers with this tag (repeatable)."
    ),
    exclude_tag: list[str] | None = typer.Option(
        None, "--exclude-tag", help="Exclude servers with this tag (repeatable)."
    ),
) -> None:
    """Health check all servers (status, latency, version)."""
    try:
        health_impl(
            server_name=server_name, timeout=timeout, project=project,
            json=json, deep=deep, tag=tag, exclude_tag=exclude_tag,
        )
    except McpManagerError:
        raise typer.Exit(1) from None


@app.command()
def add(
    name: str = typer.Argument(..., help="Server name."),
    command: str | None = typer.Option(None, "--command", "-c", help="Command for stdio server."),
    url: str | None = typer.Option(None, "--url", "-u", help="URL for SSE/HTTP server."),
    transport: str = typer.Option("stdio", "--transport", "-t", help="Transport type."),
    args: list[str] | None = typer.Option(None, "--arg", help="Args for stdio (repeatable)."),
) -> None:
    """Add a new MCP server to the mcp-manager registry."""
    try:
        add_impl(name=name, command=command, url=url, transport=transport, args=args)
    except McpManagerError:
        raise typer.Exit(1) from None


@app.command()
def remove(
    name: str = typer.Argument(..., help="Server name to remove."),
) -> None:
    """Remove a server from the mcp-manager registry."""
    try:
        remove_impl(name=name)
    except McpManagerError:
        raise typer.Exit(1) from None


@app.command(name="export")
def export_config(
    output: Path = typer.Argument(..., help="Output file path."),
    fmt: str = typer.Option("yaml", "--format", "-f", help="Export format (yaml|json)."),
    tool: str | None = typer.Option(None, "--tool", "-t", help="Export only from specific tool."),
    project: Path | None = typer.Option(None, "--project", "-p", help="Project dir."),
) -> None:
    """Export all discovered servers to a portable YAML/JSON file."""
    try:
        export_config_impl(output=output, fmt=fmt, tool=tool, project=project)
    except McpManagerError:
        raise typer.Exit(1) from None


@app.command(name="import")
def import_config(
    input_file: Path = typer.Argument(..., help="Input YAML/JSON file."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be imported."),
) -> None:
    """Import servers from a YAML/JSON file into the registry."""
    try:
        import_config_impl(input_file=input_file, dry_run=dry_run)
    except McpManagerError:
        raise typer.Exit(1) from None


@app.command(name="test")
def test_server(
    server_name: str = typer.Argument(..., help="Name of server to test."),
    project: Path | None = typer.Option(None, "--project", "-p", help="Project dir."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Test a specific server's capabilities via full protocol handshake."""
    try:
        test_server_impl(server_name=server_name, project=project, json=json)
    except McpManagerError:
        raise typer.Exit(1) from None


@app.command()
def status() -> None:
    """Show license status and available features."""
    status_impl()


@app.command()
def stats(
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Show local usage telemetry (requires MCP_MANAGER_TELEMETRY=1)."""
    try:
        stats_impl(json=json)
    except McpManagerError:
        raise typer.Exit(1) from None


@app.command(name="sync")
def sync_servers(
    ide: str = typer.Option(..., "--ide", "-i", help="IDE to sync configs to."),
    project: Path | None = typer.Option(None, "--project", "-p", help="Project dir."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview changes without writing."),
    create: bool = typer.Option(False, "--create", help="Create config file if missing."),
    tag: list[str] | None = typer.Option(
        None, "--tag", help="Include servers with this tag (repeatable)."
    ),
    exclude_tag: list[str] | None = typer.Option(
        None, "--exclude-tag", help="Exclude servers with this tag (repeatable)."
    ),
) -> None:
    """Write discovered MCP servers to an IDE config file."""
    try:
        sync_servers_impl(
            ide=ide, project=project, dry_run=dry_run, create=create,
            tag=tag, exclude_tag=exclude_tag,
        )
    except McpManagerError:
        raise typer.Exit(1) from None


@app.command(name="validate")
def validate_ci(
    path: Path | None = typer.Option(
        None, "--path", "-p", help="Path to .mcp-manager.yml or its directory."
    ),
    strict: bool = typer.Option(
        False, "--strict", help="Also run deep health checks on discovered servers."
    ),
) -> None:
    """Validate .mcp-manager.yml (for CI gates)."""
    try:
        validate_ci_impl(path=path, strict=strict)
    except McpManagerError:
        raise typer.Exit(1) from None


@app.command(name="monitor")
def monitor_servers(
    project: Path | None = typer.Option(
        None, "--project", "-p", help="Project dir for .mcp-manager.yml."
    ),
    restart_delay: float = typer.Option(
        1.0, "--restart-delay", help="Base delay in seconds between restarts."
    ),
    json: bool = typer.Option(False, "--json", help="Output summary as JSON."),
    tag: list[str] | None = typer.Option(
        None, "--tag", help="Include servers with this tag (repeatable)."
    ),
    exclude_tag: list[str] | None = typer.Option(
        None, "--exclude-tag", help="Exclude servers with this tag (repeatable)."
    ),
) -> None:
    """Keep stdio MCP servers alive with auto-restart."""
    try:
        monitor_servers_impl(
            project=project, restart_delay=restart_delay, json=json,
            tag=tag, exclude_tag=exclude_tag,
        )
    except McpManagerError:
        raise typer.Exit(1) from None


@app.command(name="lock")
def lock_versions(
    path: Path | None = typer.Option(
        None, "--path", "-p", help="Path to .mcp-manager.yml or its directory."
    ),
    check: bool = typer.Option(
        False, "--check", help="Validate lockfile is current instead of writing."
    ),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Resolve and pin MCP server versions to .mcp-manager.lock."""
    try:
        lock_versions_impl(path=path, check=check, json=json)
    except McpManagerError:
        raise typer.Exit(1) from None


@app.command(name="search")
def search_marketplace(
    query: str = typer.Argument("", help="Search query (name or description)."),
    category: str = typer.Option("", "--category", "-c", help="Filter by category."),
    include_unverified: bool = typer.Option(
        False,
        "--include-unverified",
        help="Include servers that are not verified.",
    ),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Search the MCP server marketplace."""
    try:
        search_marketplace_impl(
            query=query, category=category, include_unverified=include_unverified, json=json
        )
    except McpManagerError:
        raise typer.Exit(1) from None


@app.command(name="info")
def marketplace_info(
    name: str = typer.Argument(..., help="Marketplace server name (e.g. 'postgres')."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Show detailed info for a marketplace server."""
    try:
        marketplace_info_impl(name=name, json=json)
    except McpManagerError:
        raise typer.Exit(1) from None


@app.command(name="install")
def marketplace_install(
    name: str = typer.Argument(..., help="Marketplace server name (e.g. 'postgres')."),
    path: Path | None = typer.Option(
        None, "--path", "-p", help="Project directory (default: cwd)."
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview changes without writing."),
    no_prompt: bool = typer.Option(False, "--no-prompt", help="Skip interactive env var prompts."),
    lock: bool = typer.Option(
        False, "--lock", help="Auto-generate .mcp-manager.lock after install."
    ),
) -> None:
    """Install a marketplace server into .mcp-manager.yml."""
    try:
        marketplace_install_impl(
            name=name, path=path, dry_run=dry_run, no_prompt=no_prompt, lock=lock
        )
    except McpManagerError:
        raise typer.Exit(1) from None


@app.command(name="marketplace-refresh")
def marketplace_refresh(
    output: Path = typer.Option(
        ..., "--output", "-o", help="Path to marketplace index.yaml to update."
    ),
    timeout: int = typer.Option(30, "--timeout", "-t", help="Health check timeout in seconds."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview changes without writing."),
) -> None:
    """Refresh quality scores for all marketplace servers."""
    try:
        marketplace_refresh_impl(output=output, timeout=timeout, dry_run=dry_run)
    except McpManagerError:
        raise typer.Exit(1) from None
