"""Remote registry sync logic.

Fetch, diff, merge, and write server definitions from remote registries.
"""

from __future__ import annotations

import json
import logging
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import yaml

from mcp_manager.exceptions import WritebackError
from mcp_manager.health import HealthChecker
from mcp_manager.models import McpServer, ServerStatus, TransportType
from mcp_manager.project_config import (
    _config_to_server,
    parse_project_config,
)

logger = logging.getLogger(__name__)
_BACKUP_SUFFIX = ".mcp-manager-backup"


@dataclass
class RegistryDiff:
    """Difference between local and remote server sets."""

    added: list[McpServer]
    updated: list[tuple[McpServer, McpServer]]
    removed: list[McpServer]


def fetch_remote_servers(
    url: str, headers: dict[str, str] | None = None
) -> list[McpServer]:
    """Fetch server definitions from a remote URL.

    Supports YAML and JSON. Returns a list of McpServer objects.

    Args:
        url: HTTP(S) URL pointing to a registry file.
        headers: Optional HTTP headers (e.g. Authorization Bearer token).

    Returns:
        Parsed servers.

    Raises:
        WritebackError: On fetch or parse failure.
    """
    try:
        resp = httpx.get(url, headers=headers, timeout=15, follow_redirects=True)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise WritebackError(f"Failed to fetch registry {url}: {exc}") from exc

    try:
        raw = json.loads(resp.text) if url.endswith(".json") else yaml.safe_load(resp.text)
    except (yaml.YAMLError, json.JSONDecodeError) as exc:
        raise WritebackError(f"Failed to parse registry from {url}: {exc}") from exc

    if not isinstance(raw, dict):
        raise WritebackError(f"Remote registry at {url} must contain a mapping")

    servers_raw = raw.get("servers", raw)
    if not isinstance(servers_raw, dict):
        raise WritebackError(f"No servers found in registry at {url}")

    results: list[McpServer] = []
    for name, config in servers_raw.items():
        if not isinstance(config, dict):
            logger.warning("Skipping non-dict entry %r", name)
            continue
        try:
            results.append(_config_to_server(name, config))
        except (WritebackError, KeyError, TypeError, ValueError) as exc:
            logger.warning("Failed to parse server %r: %s", name, exc)

    return results


def compute_diff(local: list[McpServer], remote: list[McpServer]) -> RegistryDiff:
    """Compute differences between local and remote server lists.

    Args:
        local: Currently configured servers.
        remote: Servers from the remote registry.

    Returns:
        Structured diff showing added, updated, and removed servers.
    """
    local_by_name = {s.name: s for s in local}
    remote_by_name = {s.name: s for s in remote}

    added = [s for name, s in remote_by_name.items() if name not in local_by_name]
    removed = [s for name, s in local_by_name.items() if name not in remote_by_name]
    updated = [
        (local_by_name[name], remote_by_name[name])
        for name in local_by_name
        if name in remote_by_name
        and local_by_name[name].model_dump() != remote_by_name[name].model_dump()
    ]

    return RegistryDiff(added=added, updated=updated, removed=removed)


def merge_servers(
    local: list[McpServer], remote: list[McpServer], strategy: str
) -> list[McpServer]:
    """Merge remote servers into the local list.

    Args:
        local: Currently configured servers.
        remote: Servers from the remote registry.
        strategy: "union" (local wins on name collision) or "replace".

    Returns:
        Merged server list.
    """
    if strategy == "replace":
        return remote

    # union (default): remote merged into local; local names win on conflict
    remote_by_name = {s.name: s for s in remote}
    merged: list[McpServer] = []
    for s in local:
        if s.name in remote_by_name:
            merged.append(remote_by_name.pop(s.name))
        else:
            merged.append(s)
    merged.extend(remote_by_name.values())
    return merged


def verify_servers(servers: list[McpServer]) -> list[tuple[McpServer, ServerStatus, str | None]]:
    """Run shallow health checks on all servers.

    Args:
        servers: Servers to verify.

    Returns:
        List of (server, status, error_message) tuples.
    """
    import asyncio

    checker = HealthChecker(timeout=10, deep=False)
    return [
        (s, result.status, result.error_message)
        for s, result in zip(servers, asyncio.run(checker.check_all(servers)), strict=True)
    ]


def write_project_servers(path: Path, servers: list[McpServer]) -> None:
    """Write merged servers back to a .mcp-manager.yml file.

    Preserves non-server top-level keys (including ``extends``) but
    replaces the ``servers`` block entirely. Creates a backup before
    writing.

    Args:
        path: Path to .mcp-manager.yml.
        servers: Servers to write.

    Raises:
        WritebackError: On read or write failure.
    """
    if not path.is_file():
        raise WritebackError(f"Project config not found: {path}")

    data = parse_project_config(path, resolve_extends=False)
    data["servers"] = {s.name: _server_to_config(s) for s in servers}

    # Create backup
    backup_path = path.with_suffix(path.suffix + _BACKUP_SUFFIX)
    try:
        shutil.copy2(path, backup_path)
    except OSError as exc:
        raise WritebackError(f"Failed to create backup at {backup_path}: {exc}") from exc

    _atomic_write(path, data)


def _server_to_config(server: McpServer) -> dict[str, Any]:
    """Convert an McpServer back to a .mcp-manager.yml server dict."""
    if server.transport == TransportType.STDIO and server.stdio_config:
        result: dict[str, Any] = {
            "command": server.stdio_config.command,
            "args": server.stdio_config.args,
        }
        if server.stdio_config.env:
            result["env"] = server.stdio_config.env
        if server.tags:
            result["tags"] = server.tags
        return result

    if server.network_config:
        result = {
            "type": server.network_config.type,
            "url": server.network_config.url,
        }
        if server.network_config.headers:
            result["headers"] = server.network_config.headers
        if server.tags:
            result["tags"] = server.tags
        return result

    raise WritebackError(f"Server {server.name!r} has no valid transport config")


def _atomic_write(path: Path, data: dict[str, Any]) -> None:
    """Write YAML atomically via a temp file."""
    try:
        fd, tmp_path = tempfile.mkstemp(
            dir=path.parent,
            prefix=f".{path.name}-tmp-",
            suffix=".yml",
        )
        with open(fd, "w", encoding="utf-8") as fh:
            yaml.dump(data, fh, default_flow_style=False, sort_keys=False)
            fh.write("\n")
        Path(tmp_path).rename(path)
    except OSError as exc:
        raise WritebackError(f"Failed to write {path}: {exc}") from exc
