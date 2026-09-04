"""Version pinning lockfile: resolve and freeze MCP server versions."""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import yaml

from mcp_manager.atomic import atomic_write_text
from mcp_manager.exceptions import McpManagerError
from mcp_manager.models import McpServer, TransportType

logger = logging.getLogger(__name__)

# npm registry API endpoint.
NPM_REGISTRY_URL = "https://registry.npmjs.org"

# Regex for npm package references in args: @scope/name@version or name@version.
_NPM_PACKAGE_RE = re.compile(r"^(@[^/]+/[^@]+|[^@]+)(?:@(.+))?$")


class LockfileError(McpManagerError):
    """Raised when lockfile operations fail."""


class LockfileEntry:
    """A single resolved entry in the lockfile."""

    def __init__(
        self,
        *,
        resolved_version: str | None = None,
        resolved_at: str | None = None,
        error: str | None = None,
    ) -> None:
        self.resolved_version = resolved_version
        self.resolved_at = resolved_at or datetime.now(UTC).isoformat()
        self.error = error

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"resolvedAt": self.resolved_at}
        if self.resolved_version:
            data["resolvedVersion"] = self.resolved_version
        if self.error:
            data["error"] = self.error
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LockfileEntry:
        return cls(
            resolved_version=data.get("resolvedVersion"),
            resolved_at=data.get("resolvedAt"),
            error=data.get("error"),
        )


class Lockfile:
    """In-memory representation of .mcp-manager.lock."""

    def __init__(
        self,
        *,
        version: str = "1",
        resolved_at: str | None = None,
        servers: dict[str, LockfileEntry] | None = None,
    ) -> None:
        self.version = version
        self.resolved_at = resolved_at or datetime.now(UTC).isoformat()
        self.servers = servers or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "lockfileVersion": self.version,
            "resolvedAt": self.resolved_at,
            "servers": {name: entry.to_dict() for name, entry in self.servers.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Lockfile:
        servers = {
            name: LockfileEntry.from_dict(entry) for name, entry in data.get("servers", {}).items()
        }
        return cls(
            version=data.get("lockfileVersion", "1"),
            resolved_at=data.get("resolvedAt"),
            servers=servers,
        )


def _write_yaml(path: Path, data: dict[str, Any]) -> None:
    """Write YAML with deterministic ordering."""
    text = yaml.dump(
        data,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
    )
    atomic_write_text(path, text)


def write_lockfile(path: Path, lockfile: Lockfile) -> None:
    """Persist a Lockfile to disk."""
    try:
        _write_yaml(path, lockfile.to_dict())
    except OSError as exc:
        raise LockfileError(f"Failed to write lockfile: {exc}") from exc


def read_lockfile(path: Path) -> Lockfile:
    """Load a Lockfile from disk."""
    if not path.is_file():
        raise LockfileError(f"Lockfile not found: {path}")

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise LockfileError(f"Failed to parse lockfile: {exc}") from exc

    if not isinstance(raw, dict):
        raise LockfileError("Lockfile must be a YAML mapping")

    return Lockfile.from_dict(raw)


# ---------------------------------------------------------------------------
# Version resolution
# ---------------------------------------------------------------------------


def _extract_npm_package(args: list[str]) -> tuple[str, str | None] | None:
    """Find an npm package reference in args.

    Returns (package_name, explicit_version) or None if no npm package found.
    """
    for arg in args:
        # Skip flags.
        if arg.startswith("-"):
            continue
        # Look for @scope/name or plain name with optional @version.
        match = _NPM_PACKAGE_RE.match(arg)
        if match:
            pkg_name = match.group(1)
            version = match.group(2)
            # Sanity: must contain a word character, not a path.
            if "/" in pkg_name or pkg_name.startswith("@"):
                return pkg_name, version
            if "." not in pkg_name and not pkg_name.startswith("http"):
                return pkg_name, version
    return None


def _fetch_npm_latest(package: str) -> str:
    """Query npm registry for the latest version of a package.

    Args:
        package: npm package name (e.g. "@modelcontextprotocol/server-filesystem").

    Returns:
        Latest version string.

    Raises:
        LockfileError: On network or parse failure.
    """
    url = f"{NPM_REGISTRY_URL}/{package.replace('/', '%2F')}"
    try:
        response = httpx.get(url, timeout=10, follow_redirects=False)
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        raise LockfileError(f"Failed to query npm registry for {package}: {exc}") from exc

    dist_tags: dict[str, str] = data.get("dist-tags", {})
    latest = dist_tags.get("latest")
    if not latest:
        raise LockfileError(f"No 'latest' dist-tag for {package}")
    return str(latest)


def resolve_server(server: McpServer) -> LockfileEntry:
    """Resolve the version for a single server.

    Currently supports npm packages invoked via npx/node.
    Non-npm servers return an entry with error set.
    """
    if server.transport != TransportType.STDIO or not server.stdio_config:
        return LockfileEntry(error="Non-stdio transport: version not resolvable")

    cfg = server.stdio_config
    cmd = Path(cfg.command).name.lower()
    if cmd not in {"npx", "node", "npm"}:
        return LockfileEntry(error="Non-npm command: version not resolvable")

    npm_ref = _extract_npm_package(cfg.args)
    if not npm_ref:
        return LockfileEntry(error="No npm package found in args")

    pkg_name, explicit_version = npm_ref
    if explicit_version and explicit_version != "latest":
        return LockfileEntry(resolved_version=explicit_version)

    try:
        latest = _fetch_npm_latest(pkg_name)
        return LockfileEntry(resolved_version=latest)
    except LockfileError as exc:
        return LockfileEntry(error=str(exc))


def generate_lockfile(servers: list[McpServer]) -> Lockfile:
    """Resolve versions for all servers and return a Lockfile."""
    entries: dict[str, LockfileEntry] = {}
    for server in servers:
        entries[server.name] = resolve_server(server)
    return Lockfile(servers=entries)


def check_lockfile(config_servers: list[McpServer], lockfile: Lockfile) -> list[str]:
    """Validate that a lockfile is current for the given servers.

    Returns a list of human-readable error strings (empty if valid).
    """
    errors: list[str] = []
    config_names = {s.name for s in config_servers}
    lock_names = set(lockfile.servers.keys())

    missing = config_names - lock_names
    if missing:
        errors.append(f"Servers missing from lockfile: {', '.join(sorted(missing))}")

    extra = lock_names - config_names
    if extra:
        errors.append(f"Stale servers in lockfile: {', '.join(sorted(extra))}")

    for server in config_servers:
        entry = lockfile.servers.get(server.name)
        if not entry:
            continue

        current = resolve_server(server)

        # Expected errors that persist (non-npm commands, etc.) are not failures.
        if entry.error and current.error == entry.error:
            continue

        if entry.error:
            errors.append(f"Server {server.name!r}: lockfile has error: {entry.error}")
            continue

        if current.error:
            errors.append(f"Server {server.name!r}: resolution failed: {current.error}")
            continue

        if current.resolved_version != entry.resolved_version:
            errors.append(
                f"Server {server.name!r}: version drift "
                f"(config resolves to {current.resolved_version}, "
                f"lockfile has {entry.resolved_version})"
            )

    return errors
