"""Marketplace: curated MCP server directory."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from mcp_manager.models import StdioConfig
from mcp_manager.project_config import DEFAULT_FILENAME

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class QualityScore:
    """Computed quality metrics for a marketplace server."""

    def __init__(
        self,
        health_pass_rate: float = 0.0,
        tool_count: int = 0,
        last_updated: str | None = None,
        license_id: str = "",
        verified: bool = False,
    ) -> None:
        self.health_pass_rate = health_pass_rate
        self.tool_count = tool_count
        self.last_updated = last_updated
        self.license_id = license_id
        self.verified = verified

    def to_dict(self) -> dict[str, Any]:
        return {
            "health_pass_rate": self.health_pass_rate,
            "tool_count": self.tool_count,
            "last_updated": self.last_updated,
            "license": self.license_id,
            "verified": self.verified,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> QualityScore:
        return cls(
            health_pass_rate=float(data.get("health_pass_rate", 0.0)),
            tool_count=int(data.get("tool_count", 0)),
            last_updated=data.get("last_updated"),
            license_id=str(data.get("license", "")),
            verified=bool(data.get("verified", False)),
        )


class MarketplaceServer:
    """A single entry in the MCP server marketplace."""

    def __init__(
        self,
        name: str,
        display_name: str,
        description: str,
        repository: str,
        categories: list[str],
        install_spec: dict[str, Any],
        quality: QualityScore,
    ) -> None:
        self.name = name
        self.display_name = display_name
        self.description = description
        self.repository = repository
        self.categories = categories
        self.install_spec = install_spec
        self.quality = quality

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "repository": self.repository,
            "categories": self.categories,
            "install_spec": self.install_spec,
            "quality": self.quality.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MarketplaceServer:
        return cls(
            name=str(data["name"]),
            display_name=str(data.get("display_name", data["name"])),
            description=str(data.get("description", "")),
            repository=str(data.get("repository", "")),
            categories=list(data.get("categories", [])),
            install_spec=dict(data.get("install_spec", {})),
            quality=QualityScore.from_dict(data.get("quality", {})),
        )

    def _env_var_placeholders(self) -> list[str]:
        """Return list of ${VAR} env var names in install_spec."""
        env = self.install_spec.get("env", {})
        placeholders: list[str] = []
        for value in env.values():
            match = re.match(r"\$\{(\w+)\}", str(value))
            if match:
                placeholders.append(match.group(1))
        return placeholders

    def build_stdio_config(self, env_overrides: dict[str, str] | None = None) -> StdioConfig:
        """Build a StdioConfig from install_spec, applying env overrides."""
        env_overrides = env_overrides or {}
        raw_env = self.install_spec.get("env", {})
        resolved_env: dict[str, str] = {}
        for key, value in raw_env.items():
            match = re.match(r"\$\{(\w+)\}", str(value))
            if match:
                var_name = match.group(1)
                resolved_env[key] = env_overrides.get(var_name, value)
            else:
                resolved_env[key] = str(value)

        return StdioConfig(
            command=str(self.install_spec["command"]),
            args=[str(a) for a in self.install_spec.get("args", [])],
            env=resolved_env,
        )


class MarketplaceIndex:
    """In-memory representation of the marketplace index."""

    def __init__(
        self,
        categories: list[dict[str, str]],
        servers: list[MarketplaceServer],
    ) -> None:
        self.categories = categories
        self.servers = {s.name: s for s in servers}

    def search(
        self,
        query: str | None = None,
        category: str | None = None,
        verified_only: bool = True,
    ) -> list[MarketplaceServer]:
        """Return servers matching filters, sorted by name."""
        results: list[MarketplaceServer] = []
        q = (query or "").lower()
        for server in self.servers.values():
            if verified_only and not server.quality.verified:
                continue
            if category and category not in server.categories:
                continue
            if q and q not in server.name.lower() and q not in server.description.lower():
                continue
            results.append(server)
        return sorted(results, key=lambda s: s.name)

    def get(self, name: str) -> MarketplaceServer | None:
        return self.servers.get(name)


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------


def load_index(path: Path | None = None) -> MarketplaceIndex:
    """Load marketplace/index.yaml from repo or package."""
    if path is None:
        # Resolve relative to this module's package root.
        module_dir = Path(__file__).resolve().parent.parent.parent
        path = module_dir / "marketplace" / "index.yaml"

    if not path.is_file():
        raise MarketplaceError(f"Marketplace index not found: {path}")

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise MarketplaceError(f"Failed to parse marketplace index: {exc}") from exc

    if not isinstance(raw, dict):
        raise MarketplaceError("Marketplace index must be a YAML mapping")

    categories = [dict(c) for c in raw.get("categories", [])]
    servers = [MarketplaceServer.from_dict(s) for s in raw.get("servers", [])]
    return MarketplaceIndex(categories=categories, servers=servers)


# ---------------------------------------------------------------------------
# Install
# ---------------------------------------------------------------------------


class MarketplaceError(Exception):
    """Raised on marketplace loading or install failures."""


def _env_var_prompts(server: MarketplaceServer) -> dict[str, str]:
    """Collect env var values from user for ${VAR} placeholders."""
    import typer

    placeholders = server._env_var_placeholders()
    if not placeholders:
        return {}

    console = typer.secho
    console(f"Server '{server.display_name}' requires environment variables:")
    overrides: dict[str, str] = {}
    for var in placeholders:
        value = typer.prompt(f"  {var}", default="", show_default=False)
        overrides[var] = value
    return overrides


def _read_project_config(path: Path) -> dict[str, Any]:
    """Load existing .mcp-manager.yml or return empty structure."""
    if not path.is_file():
        return {"project": "my-project", "servers": {}}

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise MarketplaceError(f"Failed to read project config: {exc}") from exc

    if not isinstance(raw, dict):
        raise MarketplaceError("Project config must be a YAML mapping")

    raw.setdefault("project", "my-project")
    raw.setdefault("servers", {})
    return raw


def _write_project_config(path: Path, data: dict[str, Any]) -> None:
    """Write project config back to disk atomically."""
    try:
        text = yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)
        path.write_text(text, encoding="utf-8")
    except OSError as exc:
        raise MarketplaceError(f"Failed to write project config: {exc}") from exc


def install_to_project(
    server: MarketplaceServer,
    project_path: Path,
    *,
    dry_run: bool = False,
    interactive: bool = True,
) -> Path:
    """Add a marketplace server to .mcp-manager.yml.

    Returns the path written.
    """
    config_path = project_path / DEFAULT_FILENAME
    data = _read_project_config(config_path)

    if server.name in data.get("servers", {}):
        raise MarketplaceError(f"Server {server.name!r} already exists in {config_path}")

    env_overrides: dict[str, str] = {}
    if interactive:
        env_overrides = _env_var_prompts(server)

    stdio = server.build_stdio_config(env_overrides)
    data["servers"][server.name] = {
        "command": stdio.command,
        "args": stdio.args,
        "env": stdio.env,
    }

    if dry_run:
        return config_path

    _write_project_config(config_path, data)
    return config_path


# ---------------------------------------------------------------------------
# Refresh quality scores
# ---------------------------------------------------------------------------


def refresh_marketplace(
    index_path: Path,
    *,
    timeout: int = 30,
) -> bool:
    """Run deep health checks on all marketplace servers and update scores.

    Returns True if any scores were updated.
    """
    import asyncio
    from datetime import UTC, datetime

    from mcp_manager.health import HealthChecker
    from mcp_manager.models import McpServer, TransportType

    index = load_index(index_path)
    updated = False

    for server in index.servers.values():
        stdio = server.build_stdio_config()
        mcp_server = McpServer(
            name=server.name,
            transport=TransportType.STDIO,
            stdio_config=stdio,
        )

        checker = HealthChecker(timeout=timeout)
        try:
            result = asyncio.run(checker._check_stdio(mcp_server))
            if result.status.name == "HEALTHY":
                server.quality.health_pass_rate = 1.0
            elif result.status.name == "DEGRADED":
                server.quality.health_pass_rate = 0.5
            else:
                server.quality.health_pass_rate = 0.0
            server.quality.tool_count = result.server_info.get("tool_count", 0)
        except Exception:
            server.quality.health_pass_rate = 0.0
            server.quality.tool_count = 0

        server.quality.last_updated = datetime.now(UTC).isoformat()
        updated = True

    if updated:
        _write_index(index_path, index)

    return updated


def _write_index(path: Path, index: MarketplaceIndex) -> None:
    """Persist a MarketplaceIndex back to disk."""
    data = {
        "categories": index.categories,
        "servers": [s.to_dict() for s in index.servers.values()],
    }
    try:
        text = yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)
        path.write_text(text, encoding="utf-8")
    except OSError as exc:
        raise MarketplaceError(f"Failed to write marketplace index: {exc}") from exc
