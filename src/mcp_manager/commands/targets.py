"""Target inventory and configuration diagnostics."""

from __future__ import annotations

import json as json_mod
import os
import shutil
from pathlib import Path
from typing import Any

from rich.table import Table

from mcp_manager.adapters import ConfigScope, TargetAdapter, build_target_adapters
from mcp_manager.commands.common import console
from mcp_manager.config import IDE_CONFIG_PATHS
from mcp_manager.exceptions import DiscoveryError, McpManagerError
from mcp_manager.models import McpServer
from mcp_manager.telemetry import track_command


def targets_impl(*, json: bool) -> None:  # noqa: A002
    """List supported clients and their configuration capabilities."""
    adapters = build_target_adapters(IDE_CONFIG_PATHS)
    rows = [_capability_row(adapter) for adapter in adapters.values()]
    if json:
        console.print_json(json_mod.dumps(rows, indent=2))
        return

    table = Table(title="MCP Client Targets")
    table.add_column("Target", style="cyan")
    table.add_column("Format")
    table.add_column("User config")
    table.add_column("Project")
    table.add_column("Transports")
    table.add_column("Policy")
    for row in rows:
        table.add_row(
            row["target"],
            row["format"],
            row["user_path"],
            "yes" if row["project_scope"] else "—",
            ", ".join(row["transports"]),
            "yes" if row["tool_policy"] else "—",
        )
    console.print(table)


def doctor_impl(
    *,
    target: str | None,
    project: Path | None,
    json: bool,  # noqa: A002
) -> None:
    """Validate config syntax, referenced paths, and credential presence."""
    track_command("doctor")
    adapters = build_target_adapters(IDE_CONFIG_PATHS)
    if target is not None:
        adapter = adapters.get(target)
        if adapter is None:
            supported = ", ".join(sorted(adapters))
            raise McpManagerError(f"Unknown target {target!r}. Supported: {supported}")
        adapters = {target: adapter}

    results: list[dict[str, Any]] = []
    for adapter in adapters.values():
        results.append(_check_location(adapter, scope="user", project_dir=None))
        if project is not None and adapter.capabilities.project_scope:
            results.append(_check_location(adapter, scope="project", project_dir=project))

    if json:
        console.print_json(json_mod.dumps({"targets": results}, indent=2))
    else:
        _render_doctor(results)

    if any(result["status"] == "error" for result in results):
        raise McpManagerError("One or more target configurations are invalid")


def _capability_row(adapter: TargetAdapter) -> dict[str, Any]:
    return {
        "target": adapter.name,
        "format": adapter.capabilities.format,
        "user_path": str(adapter.user_path),
        "project_scope": adapter.capabilities.project_scope,
        "project_path": str(adapter.project_path) if adapter.project_path else None,
        "transports": list(adapter.capabilities.transports),
        "oauth": adapter.capabilities.oauth,
        "codex_auth_translation": adapter.capabilities.codex_auth_translation,
        "tool_policy": adapter.capabilities.tool_policy,
        "approval_policy": adapter.capabilities.approval_policy,
        "server_controls": adapter.capabilities.server_controls,
        "environment_passthrough": adapter.capabilities.environment_passthrough,
        "environment_headers": adapter.capabilities.environment_headers,
        "timeouts": adapter.capabilities.timeouts,
    }


def _check_location(
    adapter: TargetAdapter,
    *,
    scope: ConfigScope,
    project_dir: Path | None,
) -> dict[str, Any]:
    path = adapter.resolve_path(scope=scope, project_dir=project_dir)
    result: dict[str, Any] = {
        "target": adapter.name,
        "scope": scope,
        "path": str(path),
        "format": adapter.capabilities.format,
        "exists": path.is_file(),
        "server_count": 0,
        "status": "not-configured",
        "issues": [],
    }
    if not path.is_file():
        return result

    try:
        servers = adapter.parse(
            path.read_text(encoding="utf-8"),
            source_path=path,
            strict=True,
        )
    except (OSError, DiscoveryError) as exc:
        result["status"] = "error"
        result["issues"].append({"severity": "error", "message": str(exc)})
        return result

    result["server_count"] = len(servers)
    for server in servers:
        result["issues"].extend(_server_issues(server))

    severities = {issue["severity"] for issue in result["issues"]}
    if "error" in severities:
        result["status"] = "error"
    elif "warning" in severities:
        result["status"] = "warning"
    else:
        result["status"] = "ok"
    return result


def _server_issues(server: McpServer) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if server.stdio_config:
        stdio_config = server.stdio_config
        command = stdio_config.command
        command_path = Path(command).expanduser()
        if command_path.is_absolute() and not command_path.exists():
            issues.append(_issue("error", server.name, f"command does not exist: {command}"))
        elif not command_path.is_absolute() and ("/" in command or "\\" in command):
            cwd = Path(stdio_config.cwd).expanduser() if stdio_config.cwd else None
            if cwd is not None and cwd.is_absolute():
                resolved_command = cwd / command_path
                if not resolved_command.exists():
                    issues.append(
                        _issue(
                            "error",
                            server.name,
                            f"command does not exist relative to cwd: {command}",
                        )
                    )
            else:
                issues.append(
                    _issue(
                        "warning",
                        server.name,
                        f"relative command requires a runtime cwd to verify: {command}",
                    )
                )
        elif not command_path.is_absolute() and shutil.which(command) is None:
            issues.append(_issue("warning", server.name, f"command is not on PATH: {command}"))

        if stdio_config.cwd and not Path(stdio_config.cwd).expanduser().is_dir():
            issues.append(_issue("error", server.name, f"cwd does not exist: {stdio_config.cwd}"))
        for argument in stdio_config.args:
            argument_path = Path(argument).expanduser()
            if argument_path.is_absolute() and not argument_path.exists():
                issues.append(
                    _issue("error", server.name, f"argument path does not exist: {argument}")
                )
        for env_ref in stdio_config.env_vars:
            if isinstance(env_ref, str) and env_ref not in os.environ:
                issues.append(
                    _issue("warning", server.name, f"environment variable is not set: {env_ref}")
                )

    if server.network_config:
        network_config = server.network_config
        if (
            network_config.bearer_token_env_var
            and network_config.bearer_token_env_var not in os.environ
        ):
            issues.append(
                _issue(
                    "warning",
                    server.name,
                    "bearer-token environment variable is not set: "
                    f"{network_config.bearer_token_env_var}",
                )
            )
        for env_name in network_config.env_headers.values():
            if env_name not in os.environ:
                issues.append(
                    _issue(
                        "warning",
                        server.name,
                        f"header environment variable is not set: {env_name}",
                    )
                )
    return issues


def _issue(severity: str, server: str, message: str) -> dict[str, str]:
    return {"severity": severity, "server": server, "message": message}


def _render_doctor(results: list[dict[str, Any]]) -> None:
    table = Table(title="MCP Target Doctor")
    table.add_column("Target", style="cyan")
    table.add_column("Scope")
    table.add_column("Status")
    table.add_column("Servers", justify="right")
    table.add_column("Config path")
    for result in results:
        status = result["status"]
        style = {"ok": "green", "warning": "yellow", "error": "red"}.get(status, "dim")
        table.add_row(
            result["target"],
            result["scope"],
            f"[{style}]{status}[/{style}]",
            str(result["server_count"]),
            result["path"],
        )
    console.print(table)

    for result in results:
        for issue in result["issues"]:
            style = "red" if issue["severity"] == "error" else "yellow"
            console.print(
                f"[{style}]{issue['severity']}[/{style}] "
                f"{result['target']}:{issue.get('server', 'config')} — {issue['message']}"
            )
