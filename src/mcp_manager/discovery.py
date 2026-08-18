"""Discover MCP server configurations across IDEs and tools."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from mcp_manager.adapters import ConfigScope, TargetAdapter, build_target_adapters
from mcp_manager.adapters.common import classify_json_transport, server_from_json_mapping
from mcp_manager.adapters.json_target import JsonTargetAdapter
from mcp_manager.config import IDE_CONFIG_PATHS, PROJECT_CONFIG_NAME, PROJECT_CONFIG_TOOL
from mcp_manager.exceptions import DiscoveryError
from mcp_manager.models import McpServer, TransportType

logger = logging.getLogger(__name__)


class ConfigDiscovery:
    """Scan IDE config files for MCP server definitions.

    All operations are **read-only** — no IDE config is ever modified.
    """

    def discover_all(self, *, project_dir: Path | None = None) -> list[McpServer]:
        """Scan all known IDE config paths and return discovered servers."""
        servers: list[McpServer] = []

        for adapter in self._adapters().values():
            servers.extend(self._scan_adapter(adapter, adapter.user_path))

        if project_dir is not None:
            servers.extend(self._scan_project_configs(project_dir))
            for adapter in self._adapters().values():
                if adapter.project_path is None:
                    continue
                if adapter.project_path == Path(PROJECT_CONFIG_NAME):
                    # Claude's project file is already handled by the parent-walking
                    # scanner, which also supports mcp-manager's legacy top-level form.
                    continue
                project_path = adapter.resolve_path(scope="project", project_dir=project_dir)
                servers.extend(self._scan_adapter(adapter, project_path))

        return servers

    def discover_tool(
        self,
        tool_name: str,
        *,
        scope: ConfigScope = "user",
        project_dir: Path | None = None,
    ) -> list[McpServer]:
        """Scan only a specific tool's config path."""
        adapter = self._adapters().get(tool_name)
        if adapter is None:
            return []
        try:
            path = adapter.resolve_path(scope=scope, project_dir=project_dir)
        except Exception as exc:
            logger.warning("Cannot resolve %s config: %s", tool_name, exc)
            return []
        return self._scan_adapter(adapter, path)

    @staticmethod
    def _adapters() -> dict[str, TargetAdapter]:
        """Build adapters lazily so tests and callers can override configured paths."""
        return build_target_adapters(IDE_CONFIG_PATHS)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _scan_config(
        self,
        tool_name: str,
        path: Path,
        wrapper_key: str | None,
    ) -> list[McpServer]:
        """Parse one configured target file into ``McpServer`` objects."""
        adapter = build_target_adapters([(tool_name, path, wrapper_key)])[tool_name]
        return self._scan_adapter(adapter, path)

    def _scan_adapter(self, adapter: TargetAdapter, path: Path) -> list[McpServer]:
        if not path.is_file():
            return []

        try:
            return adapter.parse(path.read_text(encoding="utf-8"), source_path=path)
        except (DiscoveryError, OSError) as exc:
            logger.warning("Failed to parse %s: %s", path, exc)
            return []

    def _scan_project_configs(self, start: Path) -> list[McpServer]:
        """Walk *start* and its parents looking for .mcp.json files."""
        servers: list[McpServer] = []
        current = start.resolve()

        for _ in range(20):  # safety limit
            config_path = current / PROJECT_CONFIG_NAME
            if config_path.is_file():
                try:
                    text = config_path.read_text(encoding="utf-8")
                    raw = json.loads(text)
                except (OSError, ValueError):
                    raw = None
                wrapper_key = (
                    "mcpServers"
                    if isinstance(raw, dict) and isinstance(raw.get("mcpServers"), dict)
                    else None
                )
                tool_name = "claude-code" if wrapper_key else PROJECT_CONFIG_TOOL
                found = self._scan_config(tool_name, config_path, wrapper_key)
                servers.extend(found)
            parent = current.parent
            if parent == current:
                break
            current = parent

        return servers

    def _parse_servers(
        self,
        servers_dict: dict[str, Any],
        tool_name: str,
        source_path: Path,
    ) -> list[McpServer]:
        """Convert a raw server dict into McpServer objects."""
        adapter = JsonTargetAdapter(
            name=tool_name,
            user_path=source_path,
            wrapper_key=None,
        )
        return adapter.parse(json.dumps(servers_dict), source_path=source_path)

    def _build_server(
        self,
        name: str,
        config: dict[str, Any],
        tool_name: str,
        source_path: Path,
    ) -> McpServer:
        """Build an McpServer from a raw config dict."""
        return server_from_json_mapping(
            name,
            config,
            source_tool=tool_name,
            source_path=source_path,
        )

    @staticmethod
    def _classify_transport(config: dict[str, Any]) -> TransportType:
        """Determine transport type from a raw config dict."""
        return classify_json_transport(config)
