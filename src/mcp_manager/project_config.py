"""Project-scoped MCP configuration (.mcp-manager.yml).

Provides init, validation, and IDE export for project-level server configs.
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Any, cast

import httpx
import yaml

from mcp_manager.exceptions import WritebackError
from mcp_manager.models import McpServer, NetworkConfig, StdioConfig, TransportType
from mcp_manager.writeback import ConfigWriteback

logger = logging.getLogger(__name__)

DEFAULT_FILENAME = ".mcp-manager.yml"
_MAX_REMOTE_CONFIG_BYTES = 1024 * 1024

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


def parse_project_config(
    path: Path,
    *,
    resolve_extends: bool = True,
    _visited: set[str] | None = None,
) -> dict[str, Any]:
    """Parse a .mcp-manager.yml file.

    Supports ``extends:`` inheritance from local files, URLs, or GitHub
    repositories. Resolution order: base → project → env overrides.
    Project servers override base servers with the same name.

    Args:
        path: Path to the YAML file.
        resolve_extends: Whether to resolve ``extends`` references.
        _visited: Internal set to detect circular extends.

    Returns:
        Parsed dict with keys: project, servers.

    Raises:
        WritebackError: On parse failure, schema violation, or circular
            extends reference.
    """
    if not path.is_file():
        raise WritebackError(f"Project config not found: {path}")

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise WritebackError(f"Failed to parse {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise WritebackError(f"{path} must contain a YAML mapping")

    if resolve_extends and "extends" in raw:
        visited = _visited or set()
        canonical = str(path.resolve())
        if canonical in visited:
            raise WritebackError(f"Circular extends reference detected: {path}")
        visited.add(canonical)
        raw = _resolve_extends(raw, path.parent, visited)
        visited.discard(canonical)

    project = raw.get("project", "")
    servers_raw = raw.get("servers", {})
    if not isinstance(servers_raw, dict):
        raise WritebackError(f"{path}: 'servers' must be a mapping")

    # Return full dict so callers can access custom keys (e.g. from extends).
    result: dict[str, Any] = {**raw, "project": project, "servers": servers_raw}
    return result


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


def _resolve_extends(
    raw: dict[str, Any],
    base_dir: Path,
    visited: set[str],
    *,
    allow_local: bool = True,
) -> dict[str, Any]:
    """Resolve ``extends`` references and merge configs.

    Supports:
    - ``file:///absolute/path.yml`` — local file
    - ``github:owner/repo/path.yml@ref`` — raw GitHub content
    - ``https://...`` or ``http://...`` — direct fetch

    Args:
        raw: Parsed YAML dict (may contain ``extends``).
        base_dir: Directory to resolve relative paths against.
        visited: Set of already-visited canonical paths (circular detection).

    Returns:
        Merged config dict with resolved inheritance.
    """
    extends = raw.get("extends")
    if extends is None:
        return raw

    sources: list[str]
    if isinstance(extends, str):
        sources = [extends]
    elif isinstance(extends, list):
        sources = [str(s) for s in extends]
    else:
        raise WritebackError(f"'extends' must be a string or list, got {type(extends).__name__}")

    merged: dict[str, Any] = {"project": "", "servers": {}}

    for source in sources:
        base = _fetch_base_config(source, base_dir, visited, allow_local=allow_local)
        merged["project"] = base.get("project", merged["project"])
        base_servers = base.get("servers", {})
        if isinstance(base_servers, dict):
            merged["servers"] = {**merged["servers"], **base_servers}

    # Project-level values override base
    merged["project"] = raw.get("project", merged["project"])
    project_servers = raw.get("servers", {})
    if isinstance(project_servers, dict):
        merged["servers"] = {**merged["servers"], **project_servers}

    # Preserve any other top-level keys from the project config
    for key, value in raw.items():
        if key not in ("extends", "project", "servers"):
            merged[key] = value

    return merged


def _fetch_base_config(
    source: str,
    base_dir: Path,
    visited: set[str],
    *,
    allow_local: bool = True,
) -> dict[str, Any]:
    """Fetch and parse a single base config source.

    Args:
        source: URI or path string.
        base_dir: Directory for relative path resolution.
        visited: Circular-detection set.

    Returns:
        Parsed base config dict.
    """
    if source.startswith("file://"):
        if not allow_local:
            raise WritebackError("Remote configs cannot extend local files")
        path = Path(source[7:])
        if not path.is_absolute():
            path = base_dir / path
        return parse_project_config(path, _visited=visited)

    if source.startswith("github:"):
        source = _github_to_raw_url(source)

    if source.startswith(("http://", "https://")):
        return _fetch_remote_config(source, visited)

    # Treat as local relative path
    if not allow_local:
        raise WritebackError("Remote configs cannot extend local files")
    local_path = base_dir / source
    if not local_path.is_file():
        raise WritebackError(f"Extends source not found: {source} (looked in {base_dir})")
    return parse_project_config(local_path, _visited=visited)


def _github_to_raw_url(source: str) -> str:
    """Convert ``github:owner/repo/path@ref`` to raw GitHub URL.

    Examples:
        ``github:AreteDriver/mcp-manager/base.yml@v0.4.0`` →
        ``https://raw.githubusercontent.com/AreteDriver/mcp-manager/v0.4.0/base.yml``
    """
    if not source.startswith("github:"):
        raise WritebackError(f"Invalid github source: {source}")
    rest = source[7:]  # strip "github:"
    if "@" not in rest:
        raise WritebackError(
            f"GitHub source must include @ref: {source} (e.g. github:owner/repo/file.yml@main)"
        )
    repo_path, ref = rest.rsplit("@", 1)
    # repo_path is like owner/repo/path/to/file.yml
    parts = repo_path.split("/", 2)
    if len(parts) < 3:
        raise WritebackError(f"GitHub source must be owner/repo/path: {source}")
    owner, repo, file_path = parts
    return f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{file_path}"


def _fetch_remote_config(
    url: str,
    visited: set[str],
) -> dict[str, Any]:
    """Fetch a remote config over HTTP(S).

    Args:
        url: URL to fetch.
        visited: Circular-detection set.

    Returns:
        Parsed config dict.
    """
    canonical = f"remote:{url}"
    if canonical in visited:
        raise WritebackError(f"Circular extends reference detected: {url}")
    visited.add(canonical)
    try:
        try:
            resp = httpx.get(url, timeout=15, follow_redirects=True)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise WritebackError(f"Failed to fetch extends source {url}: {exc}") from exc

        if len(resp.text.encode("utf-8")) > _MAX_REMOTE_CONFIG_BYTES:
            raise WritebackError(
                f"Remote config exceeds the {_MAX_REMOTE_CONFIG_BYTES}-byte limit: {url}"
            )

        try:
            raw = yaml.safe_load(resp.text)
        except yaml.YAMLError as exc:
            raise WritebackError(f"Failed to parse YAML from {url}: {exc}") from exc

        if not isinstance(raw, dict):
            raise WritebackError(f"Remote config at {url} must contain a YAML mapping")

        # A remote config may inherit other remote configs, but never local
        # files. This prevents an untrusted shared config from reading paths on
        # the operator's machine through nested ``extends`` directives.
        if "extends" in raw:
            raw = _resolve_extends(
                raw,
                Path.cwd(),
                visited,
                allow_local=False,
            )

        return cast(dict[str, Any], raw)
    finally:
        visited.discard(canonical)


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

        tags = [str(t) for t in config.get("tags", []) if t is not None]

        return McpServer(
            name=name,
            transport=TransportType.STDIO,
            stdio_config=StdioConfig(
                command=str(config["command"]),
                args=[str(a) for a in config.get("args", [])],
                env=resolved_env,
            ),
            tags=tags,
            source_tool="project",
        )

    url = str(config.get("url", ""))
    if not url:
        raise WritebackError(f"Server {name!r} has no command or url")

    transport_type = str(config.get("type", "sse")).lower()
    transport = TransportType.SSE if transport_type == "sse" else TransportType.HTTP
    tags = [str(t) for t in config.get("tags", []) if t is not None]

    return McpServer(
        name=name,
        transport=transport,
        network_config=NetworkConfig(
            type=transport.value,  # type: ignore[arg-type]
            url=url,
            headers={str(k): str(v) for k, v in config.get("headers", {}).items()},
        ),
        tags=tags,
        source_tool="project",
    )
