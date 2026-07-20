"""Project-scoped MCP configuration (.mcp-manager.yml).

Provides init, validation, and IDE export for project-level server configs.
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Any

import yaml

from mcp_manager.exceptions import WritebackError
from mcp_manager.models import McpServer, NetworkConfig, StdioConfig, TransportType
from mcp_manager.writeback import ConfigWriteback

logger = logging.getLogger(__name__)

DEFAULT_FILENAME = ".mcp-manager.yml"

_TEMPLATE: str = """# mcp-manager project configuration
# Docs: https://github.com/AreteDriver/mcp-manager
project: {name}

servers:
  # Example stdio server
  # my-local-server:
  #   command: node
  #   args: ["./dist/index.js"]
  #   env:
  #     DATABASE_URL: ${{DATABASE_URL}}
  #   auto_start: true
  #   health_check:
  #     timeout: 5
  #     retry: 3

  # Example SSE server
  # my-remote-server:
  #   type: sse
  #   url: http://localhost:3000/sse
"""


def init_project_config(path: Path | None = None, *, project_name: str = "my-project") -> Path:
    """Scaffold a new .mcp-manager.yml in the given directory.

    Args:
        path: Directory to create the file in. Defaults to cwd.
        project_name: Name to use in the template.

    Returns:
        Path to the created file.
    """
    target = (path or Path.cwd()) / DEFAULT_FILENAME
    if target.exists():
        raise WritebackError(f"{target} already exists")
    target.write_text(_TEMPLATE.format(name=project_name), encoding="utf-8")
    return target


def parse_project_config(path: Path) -> dict[str, Any]:
    """Parse a .mcp-manager.yml file.

    Args:
        path: Path to the YAML file.

    Returns:
        Parsed dict with keys: project, servers.

    Raises:
        WritebackError: On parse failure or schema violation.
    """
    if not path.is_file():
        raise WritebackError(f"Project config not found: {path}")

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise WritebackError(f"Failed to parse {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise WritebackError(f"{path} must contain a YAML mapping")

    project = raw.get("project", "")
    servers_raw = raw.get("servers", {})
    if not isinstance(servers_raw, dict):
        raise WritebackError(f"{path}: 'servers' must be a mapping")

    return {"project": project, "servers": servers_raw}


def validate_project_config(path: Path) -> list[str]:
    """Validate a .mcp-manager.yml file.

    Checks:
    - YAML is valid
    - Server configs have required fields (command or url)
    - Environment variables referenced in env values are present
    - Commands exist on PATH (best-effort)

    Args:
        path: Path to the YAML file.

    Returns:
        List of validation errors (empty if valid).
    """
    errors: list[str] = []

    try:
        data = parse_project_config(path)
    except WritebackError as exc:
        return [str(exc)]

    servers = data.get("servers", {})
    if not isinstance(servers, dict):
        return [f"{path}: 'servers' must be a mapping"]

    for name, config in servers.items():
        if not isinstance(config, dict):
            errors.append(f"Server {name!r} is not a mapping")
            continue

        # Check required fields
        if "command" not in config and "url" not in config:
            errors.append(f"Server {name!r}: missing 'command' or 'url'")

        # Validate env vars
        env = config.get("env", {})
        if isinstance(env, dict):
            for _key, value in env.items():
                if isinstance(value, str) and ":-" in value:
                    continue  # Has explicit default — safe even if unset
                var_names = _extract_env_var_names(value)
                for var_name in var_names:
                    if var_name not in os.environ:
                        errors.append(f"Server {name!r}: env var {var_name!r} is not set")

        # Check command exists (best-effort)
        cmd = config.get("command")
        if isinstance(cmd, str) and shutil.which(cmd) is None:
            errors.append(f"Server {name!r}: command {cmd!r} not found on PATH")

    return errors


def load_servers_from_config(path: Path) -> list[McpServer]:
    """Parse .mcp-manager.yml and return McpServer objects.

    Args:
        path: Path to the YAML file.

    Returns:
        List of McpServer instances.
    """
    data = parse_project_config(path)
    servers_raw = data.get("servers", {})
    results: list[McpServer] = []

    for name, config in servers_raw.items():
        if not isinstance(config, dict):
            logger.warning("Skipping non-dict server %r", name)
            continue
        try:
            results.append(_config_to_server(name, config))
        except (WritebackError, KeyError, TypeError, ValueError) as exc:
            logger.warning("Failed to parse server %r: %s", name, exc)

    return results


def export_to_ide(
    project_path: Path,
    ide: str,
    *,
    dry_run: bool = False,
    create: bool = False,
) -> Path:
    """Export project config to an IDE config file.

    Merges project servers with global registry (project wins on conflicts).

    Args:
        project_path: Path to .mcp-manager.yml or its parent directory.
        ide: IDE name.
        dry_run: Preview without writing.
        create: Create IDE config if missing.

    Returns:
        Path to the written IDE config file.
    """
    if project_path.is_dir():
        project_path = project_path / DEFAULT_FILENAME

    project_servers = load_servers_from_config(project_path)
    writeback = ConfigWriteback()
    return writeback.write_servers(ide, project_servers, create_if_missing=create, dry_run=dry_run)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_env_var_names(value: str) -> list[str]:
    """Extract referenced env var names from $VAR or ${VAR:-...} syntax."""
    if not isinstance(value, str) or not value.startswith("$"):
        return []
    if value.startswith("${") and value.endswith("}"):
        inner = value[2:-1]
        if ":-" in inner:
            var_name, _ = inner.split(":-", 1)
            return [var_name]
        if ":?" in inner:
            var_name, _ = inner.split(":?", 1)
            return [var_name]
        return [inner]
    return [value[1:]]


def _resolve_env_var(value: str) -> str:
    """Resolve $VAR, ${VAR}, ${VAR:-default}, or ${VAR:?error}."""
    if not isinstance(value, str) or not value.startswith("$"):
        return value
    if value.startswith("${") and value.endswith("}"):
        inner = value[2:-1]
        if ":-" in inner:
            var_name, default = inner.split(":-", 1)
            return os.environ.get(var_name, default)
        if ":?" in inner:
            var_name, _ = inner.split(":?", 1)
            if var_name not in os.environ:
                raise WritebackError(f"Required env var {var_name!r} is not set")
            return os.environ[var_name]
        return os.environ.get(inner, value)
    # Simple $VAR
    var_name = value[1:]
    return os.environ.get(var_name, value)


def _config_to_server(name: str, config: dict[str, Any]) -> McpServer:
    """Convert a .mcp-manager.yml server dict to McpServer."""
    if "command" in config:
        env = config.get("env", {})
        # Resolve shell env vars
        resolved_env = {}
        for key, value in env.items():
            if isinstance(value, str) and value.startswith("$"):
                resolved_env[key] = _resolve_env_var(value)
            else:
                resolved_env[key] = str(value)

        return McpServer(
            name=name,
            transport=TransportType.STDIO,
            stdio_config=StdioConfig(
                command=str(config["command"]),
                args=[str(a) for a in config.get("args", [])],
                env=resolved_env,
            ),
            source_tool="project",
        )

    url = str(config.get("url", ""))
    if not url:
        raise WritebackError(f"Server {name!r} has no command or url")

    transport_type = str(config.get("type", "sse")).lower()
    transport = TransportType.SSE if transport_type == "sse" else TransportType.HTTP

    return McpServer(
        name=name,
        transport=transport,
        network_config=NetworkConfig(
            type=transport.value,  # type: ignore[arg-type]
            url=url,
            headers={str(k): str(v) for k, v in config.get("headers", {}).items()},
        ),
        source_tool="project",
    )
