"""Discover MCP server configurations across IDEs and tools."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from mcp_manager.config import IDE_CONFIG_PATHS, PROJECT_CONFIG_NAME, PROJECT_CONFIG_TOOL
from mcp_manager.exceptions import DiscoveryError
from mcp_manager.models import McpServer, NetworkConfig, StdioConfig, TransportType

logger = logging.getLogger(__name__)


class ConfigDiscovery:
    """Scan IDE config files for MCP server definitions.

    All operations are **read-only** — no IDE config is ever modified.
    """

    def discover_all(self, *, project_dir: Path | None = None) -> list[McpServer]:
        """Scan all known IDE config paths and return discovered servers."""
        servers: list[McpServer] = []

        # Global IDE configs.
        for tool_name, path_str, wrapper_key in IDE_CONFIG_PATHS:
            found = self._scan_config(tool_name, Path(path_str).expanduser(), wrapper_key)
            servers.extend(found)

        # Project-level .mcp.json (cwd and parents).
        if project_dir is not None:
            found = self._scan_project_configs(project_dir)
            servers.extend(found)

        return servers

    def discover_tool(self, tool_name: str) -> list[McpServer]:
        """Scan only a specific tool's config path."""
        for name, path_str, wrapper_key in IDE_CONFIG_PATHS:
            if name == tool_name:
                return self._scan_config(name, Path(path_str).expanduser(), wrapper_key)
        return []

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _scan_config(
        self,
        tool_name: str,
        path: Path,
        wrapper_key: str | None,
    ) -> list[McpServer]:
        """Parse a single JSON config file into McpServer objects."""
        if not path.is_file():
            return []

        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to parse %s: %s", path, exc)
            return []

        if not isinstance(raw, dict):
            return []

        servers_dict: dict[str, Any] = raw
        if wrapper_key is not None:
            servers_dict = raw.get(wrapper_key, {})
            if not isinstance(servers_dict, dict):
                return []

        return self._parse_servers(servers_dict, tool_name, path)

    def _scan_project_configs(self, start: Path) -> list[McpServer]:
        """Walk *start* and its parents looking for .mcp.json files."""
        servers: list[McpServer] = []
        current = start.resolve()

        for _ in range(20):  # safety limit
            config_path = current / PROJECT_CONFIG_NAME
            if config_path.is_file():
                found = self._scan_config(PROJECT_CONFIG_TOOL, config_path, None)
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
        results: list[McpServer] = []

        for name, config in servers_dict.items():
            if not isinstance(config, dict):
                logger.warning("Skipping non-dict entry %r in %s", name, source_path)
                continue
            try:
                server = self._build_server(name, config, tool_name, source_path)
                results.append(server)
            except DiscoveryError:
                logger.warning("Failed to parse server %r in %s", name, source_path)

        return results

    def _build_server(
        self,
        name: str,
        config: dict[str, Any],
        tool_name: str,
        source_path: Path,
    ) -> McpServer:
        """Build an McpServer from a raw config dict."""
        transport = self._classify_transport(config)

        stdio_config: StdioConfig | None = None
        network_config: NetworkConfig | None = None

        if transport == TransportType.STDIO:
            command = config.get("command", "")
            if not command:
                raise DiscoveryError(f"stdio server {name!r} has no command")
            stdio_config = StdioConfig(
                command=str(command),
                args=[str(a) for a in config.get("args", [])],
                env={str(k): str(v) for k, v in config.get("env", {}).items()},
            )
        else:
            url = config.get("url", "")
            if not url:
                raise DiscoveryError(f"{transport} server {name!r} has no url")
            network_config = NetworkConfig(
                type=transport.value,  # type: ignore[arg-type]
                url=str(url),
                headers={str(k): str(v) for k, v in config.get("headers", {}).items()},
            )

        return McpServer(
            name=name,
            transport=transport,
            stdio_config=stdio_config,
            network_config=network_config,
            source_tool=tool_name,
            source_path=source_path,
        )

    @staticmethod
    def _classify_transport(config: dict[str, Any]) -> TransportType:
        """Determine transport type from a raw config dict."""
        if "command" in config:
            return TransportType.STDIO

        explicit_type = config.get("type", "").lower()
        if explicit_type == "sse":
            return TransportType.SSE
        if explicit_type == "http":
            return TransportType.HTTP

        # Fallback: if there's a URL but no type, assume SSE.
        if "url" in config:
            return TransportType.SSE

        return TransportType.STDIO
