"""Operations command implementations (sync, validate, monitor, stats, lock)."""

from __future__ import annotations

import asyncio
import json as json_mod
from pathlib import Path

from rich.table import Table

from mcp_manager.adapters import ConfigScope
from mcp_manager.commands.common import (
    _discover,
    _filter_by_tags,
    console,
)
from mcp_manager.exceptions import McpManagerError
from mcp_manager.health import HealthChecker
from mcp_manager.models import ServerStatus, TransportType
from mcp_manager.telemetry import track_command


def sync_servers_impl(
    ide: str,
    project: Path | None,
    dry_run: bool,
    create: bool,
    tag: list[str] | None = None,
    exclude_tag: list[str] | None = None,
    scope: str = "user",
) -> None:
    """Write discovered MCP servers to an IDE config file."""
    from mcp_manager.writeback import ConfigWriteback

    track_command("sync")
    try:
        servers = _discover(project_dir=project)
    except McpManagerError as exc:
        console.print(f"[red]Discovery error:[/red] {exc}")
        raise

    servers = _filter_by_tags(servers, include=tag, exclude=exclude_tag)

    if not servers:
        console.print("[dim]No MCP servers found to sync.[/dim]")
        return

    writeback = ConfigWriteback()
    if scope not in {"user", "project"}:
        raise McpManagerError("Scope must be 'user' or 'project'")
    target_scope: ConfigScope = "project" if scope == "project" else "user"
    target_project = project or Path.cwd()
    for warning in writeback.translation_warnings(ide, servers):
        console.print(f"[yellow]Translation warning:[/yellow] {warning}")

    if dry_run:
        preview = writeback.preview(
            ide,
            servers,
            scope=target_scope,
            project_dir=target_project,
        )
        if isinstance(preview, str):
            console.print(preview, markup=False)
        else:
            console.print_json(json_mod.dumps(preview, indent=2))
        return

    try:
        path = writeback.write_servers(
            ide,
            servers,
            create_if_missing=create,
            scope=target_scope,
            project_dir=target_project,
        )
        console.print(f"[green]Synced {len(servers)} server(s) to[/green] {path}")
    except McpManagerError as exc:
        console.print(f"[red]Sync error:[/red] {exc}")
        raise


def validate_ci_impl(
    path: Path | None,
    strict: bool,
) -> None:
    """Validate .mcp-manager.yml (for CI gates)."""
    from mcp_manager.project_config import (
        DEFAULT_FILENAME,
        load_servers_from_config,
        validate_project_config,
    )

    track_command("validate")
    target = path or Path.cwd()
    if target.is_dir():
        target = target / DEFAULT_FILENAME

    if not target.exists():
        console.print(f"[red]Config not found:[/red] {target}")
        raise McpManagerError(f"Config not found: {target}")

    errors = validate_project_config(target)
    if errors:
        console.print(f"[red]{len(errors)} error(s) found:[/red]")
        for err in errors:
            console.print(f"  • {err}")
        raise McpManagerError(f"{len(errors)} validation error(s)")

    if strict:
        servers = load_servers_from_config(target)
        if servers:
            checker = HealthChecker(deep=True)
            results = asyncio.run(checker.check_all(servers))
            failed = [r for r in results if r.status not in (ServerStatus.HEALTHY,)]
            if failed:
                console.print(f"[red]{len(failed)} server(s) failed deep health check:[/red]")
                for r in failed:
                    console.print(f"  • {r.server_name}: {r.error_message}")
                raise McpManagerError(f"{len(failed)} server(s) failed deep health check")
            console.print(f"[green]{len(results)} server(s) passed deep health check.[/green]")

    console.print(f"[green]{target} is valid.[/green]")


def monitor_servers_impl(
    project: Path | None,
    restart_delay: float,
    json: bool,  # noqa: A002
    tag: list[str] | None = None,
    exclude_tag: list[str] | None = None,
) -> None:
    """Keep stdio MCP servers alive with auto-restart."""
    from mcp_manager.monitor import ServerMonitor
    from mcp_manager.project_config import DEFAULT_FILENAME, load_servers_from_config

    track_command("monitor")
    target = (project or Path.cwd()) / DEFAULT_FILENAME

    if not target.exists():
        console.print(f"[red]Config not found:[/red] {target}")
        raise McpManagerError(f"Config not found: {target}")

    servers = load_servers_from_config(target)
    servers = _filter_by_tags(servers, include=tag, exclude=exclude_tag)
    stdio_servers = [s for s in servers if s.transport == TransportType.STDIO]

    if not stdio_servers:
        console.print("[dim]No stdio servers to monitor.[/dim]")
        return

    monitor = ServerMonitor(stdio_servers, restart_delay=restart_delay)
    console.print(f"Monitoring {len(stdio_servers)} stdio server(s). Press Ctrl+C to stop.")

    try:
        summary = asyncio.run(monitor.run())
    except KeyboardInterrupt:
        return

    if json:
        console.print_json(json_mod.dumps(summary, indent=2))
    else:
        table = Table(title="Monitor Summary")
        table.add_column("Server", style="cyan")
        table.add_column("Restarts", style="yellow", justify="right")
        table.add_column("Final Exit", style="red")
        for name, data in summary.items():
            table.add_row(
                name,
                str(data["restart_count"]),
                str(data["final_exit_code"]) if data["final_exit_code"] is not None else "—",
            )
        console.print(table)


def stats_impl(json: bool) -> None:  # noqa: A002
    """Show local usage telemetry (requires MCP_MANAGER_TELEMETRY=1)."""
    from mcp_manager.telemetry import TelemetryStore, _telemetry_dir, is_enabled

    track_command("stats")

    if not is_enabled():
        console.print(
            "[dim]Telemetry is disabled. "
            "Set MCP_MANAGER_TELEMETRY=1 to enable local usage tracking.[/dim]"
        )
        return

    db_file = _telemetry_dir() / "telemetry.db"
    if not db_file.exists():
        console.print("[dim]No telemetry data yet.[/dim]")
        return

    ts = TelemetryStore(db_file)
    try:
        commands = ts.get_command_counts()
        pro_gates = ts.get_pro_gate_counts()
        total = ts.get_total_events()
        first = ts.get_first_event_time()
        last = ts.get_last_event_time()
        activity = ts.get_daily_activity()

        if json:
            data = {
                "total_events": total,
                "first_event": first,
                "last_event": last,
                "commands": commands,
                "pro_gate_hits": pro_gates,
                "daily_activity": [{"date": d, "count": c} for d, c in activity],
            }
            console.print_json(json_mod.dumps(data, indent=2))
        else:
            overview = Table(title="Telemetry Overview")
            overview.add_column("Metric", style="cyan")
            overview.add_column("Value", style="green")
            overview.add_row("Total Events", str(total))
            overview.add_row("First Event", first or "n/a")
            overview.add_row("Last Event", last or "n/a")
            console.print(overview)

            if commands:
                cmd_table = Table(title="Command Usage")
                cmd_table.add_column("Command", style="cyan")
                cmd_table.add_column("Count", style="green", justify="right")
                for name, count in commands.items():
                    cmd_table.add_row(name, str(count))
                console.print(cmd_table)

            if pro_gates:
                gate_table = Table(title="Pro Feature Gate Hits")
                gate_table.add_column("Feature", style="cyan")
                gate_table.add_column("Attempts", style="yellow", justify="right")
                for name, count in pro_gates.items():
                    gate_table.add_row(name, str(count))
                console.print(gate_table)

            if activity:
                act_table = Table(title="Daily Activity (Last 7 Days)")
                act_table.add_column("Date", style="cyan")
                act_table.add_column("Events", style="green", justify="right")
                for day, count in activity:
                    act_table.add_row(day, str(count))
                console.print(act_table)
    finally:
        ts.close()


def lock_versions_impl(
    path: Path | None,
    check: bool,
    json: bool,  # noqa: A002
) -> None:
    """Resolve and pin MCP server versions to .mcp-manager.lock."""
    from mcp_manager.lockfile import (
        check_lockfile,
        generate_lockfile,
        read_lockfile,
        write_lockfile,
    )
    from mcp_manager.project_config import DEFAULT_FILENAME, load_servers_from_config

    track_command("lock")
    target = path or Path.cwd()
    if target.is_dir():
        target = target / DEFAULT_FILENAME

    if not target.exists():
        console.print(f"[red]Config not found:[/red] {target}")
        raise McpManagerError(f"Config not found: {target}")

    try:
        servers = load_servers_from_config(target)
    except McpManagerError as exc:
        console.print(f"[red]Config error:[/red] {exc}")
        raise

    lockfile_path = target.parent / ".mcp-manager.lock"

    if check:
        if not lockfile_path.exists():
            console.print(f"[red]Lockfile not found:[/red] {lockfile_path}")
            raise McpManagerError(f"Lockfile not found: {lockfile_path}")

        try:
            lockfile = read_lockfile(lockfile_path)
        except McpManagerError as exc:
            console.print(f"[red]Lockfile error:[/red] {exc}")
            raise

        errors = check_lockfile(servers, lockfile)
        if errors:
            if json:
                console.print_json(json_mod.dumps({"errors": errors}, indent=2))
            else:
                console.print(f"[red]{len(errors)} lockfile error(s):[/red]")
                for err in errors:
                    console.print(f"  • {err}")
            raise McpManagerError(f"{len(errors)} lockfile error(s)")

        console.print("[green]Lockfile is current.[/green]")
        return

    lockfile = generate_lockfile(servers)
    write_lockfile(lockfile_path, lockfile)

    if json:
        data = {
            "lockfile": str(lockfile_path),
            "servers": {name: entry.to_dict() for name, entry in lockfile.servers.items()},
        }
        console.print_json(json_mod.dumps(data, indent=2))
    else:
        console.print(f"[green]Wrote lockfile:[/green] {lockfile_path}")
        for name, entry in lockfile.servers.items():
            if entry.error:
                console.print(f"  [yellow]{name}:[/yellow] {entry.error}")
            elif entry.resolved_version:
                console.print(f"  [green]{name}:[/green] {entry.resolved_version}")
            else:
                console.print(f"  [dim]{name}:[/dim] no version resolved")
